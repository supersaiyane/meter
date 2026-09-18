"""The billing export, read through Athena.

**Nothing in this file has ever made a call.** ISS-122. It is written against
the AWS documentation and the shapes botocore declares, it is unit tested
against recorded responses, and it is held to the same contract as the fake.
None of that is the same thing as having run. The column mapping below is the
part most likely to be wrong, because it is the part only a real export can
settle.

Two design decisions carry this file.

**A period is returned whole or not at all.** `read_period` buffers every page
before it returns anything. A generator that yields half a month and then
raises is indistinguishable, to the collector, from a month where half the
charges were retracted, and the collector deletes on that difference. Buffering
costs memory and buys the only safety property that matters here. The ceiling is
ISS-181.

**The query prunes on the billing period partition.** A full scan of a CUR
table is the tool that reports on cost becoming a line on the bill, and it is
the single most embarrassing way for this product to fail.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from finops_core.config import Settings
from finops_core.domain.cost import CostRecord, source_fingerprint
from finops_core.errors import NoData, SchemaDrift, Throttled, Unreachable
from finops_providers.aws.client import botocore_config, translate

COLLECTOR = "cost_focus"
SCOPE = "billing"

#: The partition key Data Exports writes, as `BILLING_PERIOD=2026-08`.
PARTITION_KEY = "BILLING_PERIOD"

#: Seconds before the first retry. Doubles per attempt, as in `accounts.py`.
THROTTLE_BACKOFF_BASE_SECONDS = 2.0

#: How long a single period's query may take before it is abandoned. A month of
#: CUR is large and Athena is not fast, so this is generous. It exists so a
#: query that will never finish fails the run rather than holding the worker for
#: the rest of the day.
QUERY_TIMEOUT_SECONDS = 900.0
POLL_INTERVAL_SECONDS = 2.0

ClientFactory = Callable[[str], Any]
Sleeper = Callable[[float], None]

#: FOCUS 1.1 column names as the export writes them, mapped to `CostRecord`.
#:
#: **This mapping is the unverified part of this adapter.** Every other line
#: here is checkable against botocore. These names are checkable only against a
#: real export, and a wrong one shows up as a null in a column that is NOT NULL
#: rather than as an error anybody can read.
COLUMNS: dict[str, str] = {
    "billingaccountid": "billing_account_id",
    "subaccountid": "sub_account_id",
    "billingperiodstart": "billing_period_start",
    "billingperiodend": "billing_period_end",
    "chargeperiodstart": "charge_period_start",
    "chargeperiodend": "charge_period_end",
    "providername": "provider_name",
    "publishername": "publisher_name",
    "invoiceissuername": "invoice_issuer_name",
    "servicename": "service_name",
    "servicecategory": "service_category",
    "resourceid": "resource_id",
    "resourcename": "resource_name",
    "regionid": "region_id",
    "availabilityzone": "availability_zone",
    "chargecategory": "charge_category",
    "chargedescription": "charge_description",
    "skuid": "sku_id",
    "pricingquantity": "pricing_quantity",
    "consumedquantity": "consumed_quantity",
    "consumedunit": "consumed_unit",
    "billedcost": "billed_cost",
    "effectivecost": "effective_cost",
    "listcost": "list_cost",
    "contractedcost": "contracted_cost",
    "commitmentdiscountid": "commitment_discount_id",
    "commitmentdiscounttype": "commitment_discount_type",
    "commitmentdiscountstatus": "commitment_discount_status",
}

#: Columns the table cannot accept a null in. A missing one is `SchemaDrift`
#: and never a zero, per constraint 5.
REQUIRED = (
    "billing_account_id",
    "billing_period_start",
    "billing_period_end",
    "charge_period_start",
    "charge_period_end",
    "provider_name",
    "service_name",
    "charge_category",
    "billed_cost",
    "effective_cost",
)

MONEY = frozenset({"billed_cost", "effective_cost", "list_cost", "contracted_cost"})
QUANTITY = frozenset({"pricing_quantity", "consumed_quantity"})
DAYS = frozenset({"billing_period_start", "billing_period_end"})
MOMENTS = frozenset({"charge_period_start", "charge_period_end"})


class AthenaCostExport:
    """`CostExport` over a Data Exports table. Never yet run against AWS."""

    def __init__(
        self,
        settings: Settings,
        tenant_id: Any,
        ingest_run_id: Any,
        client_factory: ClientFactory | None = None,
        sleeper: Sleeper = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._tenant_id = tenant_id
        self._ingest_run_id = ingest_run_id
        self._config = botocore_config(settings)
        self._factory = client_factory or self._default_client
        self._sleeper = sleeper
        self._monotonic = monotonic

    def _default_client(self, service: str) -> Any:
        return boto3.client(service, config=self._config)

    # -- the port ----------------------------------------------------------

    def latest_available_period(self) -> date | None:
        """The newest partition the export actually holds.

        Read by listing partition prefixes rather than by querying, because a
        query to find out whether there is anything to query is a charge for
        asking a question the object listing answers for free.
        """
        prefix = self._settings.cur_export_prefix.rstrip("/") + "/"
        periods = sorted(self._partition_periods(prefix))
        # None means the export is there and has published nothing, which the
        # port separates from an export that is missing. Collapsing the two
        # reports a configuration fault as an empty bill.
        return periods[-1] if periods else None

    def read_period(self, period_start: date, period_end: date) -> Iterable[CostRecord]:
        """Every charge row in the period, or an exception. Never a short list.

        See the module docstring. The whole period is materialized before
        anything is returned, so a read that failed part way cannot reach the
        collector looking like a month where charges were retracted.
        """
        rows = tuple(self._rows_for(period_start, period_end))
        if not rows:
            raise NoData(
                scope_key=SCOPE,
                collector=COLLECTOR,
                detail=f"the export holds no rows between {period_start} and {period_end}",
            )
        return rows

    # -- listing -----------------------------------------------------------

    def _partition_periods(self, prefix: str) -> Iterator[date]:
        client = self._factory("s3")
        paginator = client.get_paginator("list_objects_v2")
        pages = self._retrying(
            lambda: list(
                paginator.paginate(
                    Bucket=self._settings.cur_export_bucket, Prefix=prefix, Delimiter="/"
                )
            )
        )
        for page in pages:
            for entry in page.get("CommonPrefixes", ()):
                found = _period_from_prefix(entry.get("Prefix", ""))
                if found is not None:
                    yield found

    # -- querying ----------------------------------------------------------

    def _rows_for(self, period_start: date, period_end: date) -> Iterator[CostRecord]:
        client = self._factory("athena")
        execution = self._retrying(
            lambda: client.start_query_execution(
                QueryString=self._sql(period_start, period_end),
                QueryExecutionContext={"Database": self._settings.cur_athena_database},
                WorkGroup=self._settings.cur_athena_workgroup,
            )
        )["QueryExecutionId"]
        self._await(client, execution)

        paginator = client.get_paginator("get_query_results")
        header_seen = False
        for page in self._retrying(lambda: list(paginator.paginate(QueryExecutionId=execution))):
            columns = [
                info["Name"].lower()
                for info in page["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
            ]
            for row in page["ResultSet"]["Rows"]:
                values = [cell.get("VarCharValue") for cell in row["Data"]]
                # Athena repeats the header as the first row of the first page.
                # Dropping it by position would drop a real row on page two.
                if not header_seen and values == columns:
                    header_seen = True
                    continue
                yield self._record(dict(zip(columns, values, strict=False)))

    def _sql(self, period_start: date, period_end: date) -> str:
        """One partition pruned query.

        The predicate is on the partition column, not on a date extracted from
        a timestamp, because a function applied to a partition key stops Athena
        pruning and the query scans the whole table.
        """
        columns = ", ".join(sorted(COLUMNS))
        return (
            f"SELECT {columns} "
            f'FROM "{self._settings.cur_athena_database}"."{self._settings.cur_athena_table}" '
            f"WHERE {PARTITION_KEY.lower()} >= '{period_start:%Y-%m}' "
            f"AND {PARTITION_KEY.lower()} < '{period_end:%Y-%m}'"
        )

    def _await(self, client: Any, execution: str) -> None:
        deadline = self._monotonic() + QUERY_TIMEOUT_SECONDS
        while True:
            status = self._retrying(lambda: client.get_query_execution(QueryExecutionId=execution))[
                "QueryExecution"
            ]["Status"]
            state = status["State"]
            if state == "SUCCEEDED":
                return
            if state in ("FAILED", "CANCELLED"):
                reason = status.get("StateChangeReason", "no reason given")
                # Athena reports a throttle as a failed execution rather than as
                # a throttling error on the call, so the state reason is the
                # only place it appears.
                cause = Throttled if "throttl" in reason.lower() else SchemaDrift
                raise cause(scope_key=SCOPE, collector=COLLECTOR, detail=reason)
            if self._monotonic() >= deadline:
                raise Unreachable(
                    scope_key=SCOPE,
                    collector=COLLECTOR,
                    detail=f"query {execution} was still {state} after {QUERY_TIMEOUT_SECONDS}s",
                )
            self._sleeper(POLL_INTERVAL_SECONDS)

    def _retrying(self, call: Callable[[], Any]) -> Any:
        """Backoff on a throttle, and give up rather than hammer.

        A period that is still throttled after the retries raises. It is never
        returned short, because short and complete are the two states the
        collector's delete turns on.
        """
        attempt = 0
        while True:
            try:
                return call()
            except (ClientError, BotoCoreError) as failure:
                typed = translate(failure, scope_key=SCOPE, collector=COLLECTOR)
                if not isinstance(typed, Throttled) or attempt >= self._settings.aws_max_retries:
                    raise typed from failure
                self._sleeper(THROTTLE_BACKOFF_BASE_SECONDS * (2**attempt))
                attempt += 1

    # -- mapping -----------------------------------------------------------

    def _record(self, row: dict[str, str | None]) -> CostRecord:
        fields: dict[str, Any] = {}
        for column, field in COLUMNS.items():
            fields[field] = _coerce(field, row.get(column))

        missing = [name for name in REQUIRED if fields.get(name) is None]
        if missing:
            # Not a zero and not a skip. A row we cannot read is a row we do not
            # understand, and guessing at it puts a wrong number on a screen.
            raise SchemaDrift(
                scope_key=SCOPE,
                collector=COLLECTOR,
                detail=f"required columns absent or unparseable: {', '.join(missing)}",
            )

        return CostRecord(
            tenant_id=self._tenant_id,
            ingest_run_id=self._ingest_run_id,
            source_fingerprint=source_fingerprint(
                billing_account_id=fields["billing_account_id"],
                sub_account_id=fields["sub_account_id"],
                charge_period_start=fields["charge_period_start"],
                charge_period_end=fields["charge_period_end"],
                service_name=fields["service_name"],
                resource_id=fields["resource_id"],
                sku_id=fields["sku_id"],
                charge_category=fields["charge_category"],
                commitment_discount_id=fields["commitment_discount_id"],
            ),
            as_of=fields["charge_period_end"],
            collected_at=datetime.now(UTC),
            tags=_tags(row),
            **fields,
        )


def _period_from_prefix(prefix: str) -> date | None:
    """`.../BILLING_PERIOD=2026-08/` to a date, or None for anything else."""
    marker = f"{PARTITION_KEY}="
    if marker not in prefix:
        return None
    value = prefix.rsplit(marker, 1)[1].strip("/")
    try:
        year, month = value.split("-")
        return date(int(year), int(month), 1)
    except ValueError:
        # A prefix that is not a billing period is not an error. Data Exports
        # writes metadata alongside the data.
        return None


def _coerce(field: str, raw: str | None) -> Any:
    if raw is None or raw == "":
        return None
    try:
        if field in MONEY or field in QUANTITY:
            return Decimal(raw)
        if field in DAYS:
            return date.fromisoformat(raw[:10])
        if field in MOMENTS:
            return datetime.fromisoformat(raw).replace(tzinfo=UTC)
    except (InvalidOperation, ValueError):
        # None here becomes SchemaDrift in `_record` when the column is
        # required, and stays null when it is not. Either way it is never a
        # silently substituted zero.
        return None
    return raw


def _tags(row: dict[str, str | None]) -> dict[str, str]:
    """Resource tags, which FOCUS carries as `tags/<key>` columns.

    Absent rather than empty is the common case and is not a defect. Most line
    items in any estate carry no tags at all, which is the whole reason the
    unallocated bucket exists.
    """
    out: dict[str, str] = {}
    for column, value in row.items():
        if column.startswith("tags/") and value:
            out[column.removeprefix("tags/")] = value
    return out
