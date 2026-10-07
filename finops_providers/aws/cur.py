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

import re
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from finops_core.config import Settings
from finops_core.domain.cost import CostRecord, source_fingerprint
from finops_core.errors import CollectionError, NoData, SchemaDrift, Throttled, Unreachable
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

#: Split cost allocation columns, FEAT-035, mapped to `CostRecord` like the rest.
#:
#: **Separate from `COLUMNS` because they are optional at the source.** Split cost
#: allocation is switched on per export, ISS-003, and until it is these columns do
#: not exist in the table at all. Putting them in `COLUMNS` would make every read of
#: an ordinary export fail in Athena on a column that does not exist, which is the
#: opposite of tolerating their absence. `_present_split_columns` asks the catalog
#: what is actually there instead of assuming either way.
#:
#: These are AWS's published CUR 2.0 names rather than FOCUS ones, because FOCUS 1.1
#: has no column for a pod and a vendor extension is what carries one. Like
#: `COLUMNS`, the mapping is checkable only against a real export, ISS-002.
SPLIT_COLUMNS: dict[str, str] = {
    "resource_tags_aws_eks_cluster_name": "eks_cluster_name",
    "resource_tags_aws_eks_namespace": "eks_namespace",
    "resource_tags_aws_eks_workload_name": "eks_workload_name",
    "resource_tags_aws_eks_workload_type": "eks_workload_type",
    "resource_tags_aws_eks_pod_name": "eks_pod_name",
    "split_line_item_split_cost": "split_cost",
    "split_line_item_split_usage": "split_usage",
    "split_line_item_split_usage_ratio": "split_usage_ratio",
    "split_line_item_unused_cost": "unused_cost",
}

#: FOCUS 1.2 columns AWS's FOCUS 1.2 export carries and an older export does not, P10 spec
#: section 5.2, FEAT-004. Optional at the source for the same reason the split columns are:
#: asked of the catalog, so an older export is read with the SQL it always was and these
#: land as None rather than failing the read.
FOCUS_1_2_COLUMNS: dict[str, str] = {
    "billingaccountname": "billing_account_name",
    "billingcurrency": "billing_currency",
    "chargeclass": "charge_class",
    "pricingunit": "pricing_unit",
    "invoiceid": "invoice_id",
}

#: The form FOCUS 1.4 mandates for a currency: an ISO 4217 code, three capital letters.
CURRENCY = re.compile(r"[A-Z]{3}")

#: What the catalog is asked, to learn which of the above exist. It reads metadata,
#: so it scans no data and costs nothing against the bytes Athena bills for.
CATALOG_SQL = (
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_schema = '{database}' AND table_name = '{table}'"
)

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

MONEY = frozenset(
    {"billed_cost", "effective_cost", "list_cost", "contracted_cost", "split_cost", "unused_cost"}
)
QUANTITY = frozenset({"pricing_quantity", "consumed_quantity", "split_usage", "split_usage_ratio"})
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

    #: Filled on first use by `_present_split_columns`. None means not yet asked,
    #: which is different from an empty mapping meaning asked and absent.
    _split_columns: dict[str, str] | None = None
    #: The FOCUS 1.2 columns present, filled by the same probe as the split columns.
    _focus_columns: dict[str, str] | None = None

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

    def _present_split_columns(self) -> dict[str, str]:
        """The split cost allocation columns this export actually has.

        Asked of the catalog rather than assumed, and cached for the life of the
        adapter because the answer changes only when somebody reconfigures the
        export. An empty result is the normal state of an export where split cost
        allocation has never been switched on, ISS-003, and it is not a failure: the
        collector turns it into a named gap so a cluster reads as unmeasured rather
        than as costing nothing.

        A catalog that cannot be read at all is also not a failure here. It yields
        no split columns, which degrades to exactly the behaviour of an export
        without them, and the alternative would be failing a whole cost read over an
        optional extra.
        """
        if self._split_columns is not None:
            return self._split_columns

        found: set[str] = set()
        try:
            # Deliberately not through `self._retrying`. This is an optional extra,
            # and spending a read's retry budget on it would make a throttled
            # catalog look like a throttled bill.
            client = self._factory("athena")
            execution = client.start_query_execution(
                QueryString=CATALOG_SQL.format(
                    database=self._settings.cur_athena_database,
                    table=self._settings.cur_athena_table,
                ),
                QueryExecutionContext={"Database": self._settings.cur_athena_database},
                WorkGroup=self._settings.cur_athena_workgroup,
            )["QueryExecutionId"]
            self._await(client, execution)
            paginator = client.get_paginator("get_query_results")
            for page in paginator.paginate(QueryExecutionId=execution):
                for row in page["ResultSet"]["Rows"]:
                    for cell in row["Data"]:
                        name = (cell.get("VarCharValue") or "").lower()
                        if name in SPLIT_COLUMNS or name in FOCUS_1_2_COLUMNS:
                            found.add(name)
        except (CollectionError, BotoCoreError, ClientError, KeyError):
            # An unreadable catalog leaves the export looking like one without split
            # data, which is a state the product already handles. Aborting a whole
            # cost read over an optional breakdown would be the worse trade.
            #
            # Not cached, on purpose. Caching a transient failure would disable the
            # container grain for the life of the adapter, so the next read asks
            # again and a blip costs one period rather than a run.
            return {}

        self._split_columns = {
            name: SPLIT_COLUMNS[name] for name in sorted(found) if name in SPLIT_COLUMNS
        }
        self._focus_columns = {
            name: FOCUS_1_2_COLUMNS[name] for name in sorted(found) if name in FOCUS_1_2_COLUMNS
        }
        return self._split_columns

    def _present_focus_columns(self) -> dict[str, str]:
        """The FOCUS 1.2 columns this export has, from the probe the split columns run."""
        self._present_split_columns()
        return self._focus_columns or {}

    @property
    def split_cost_available(self) -> bool:
        """Whether this export carries the container grain at all.

        Read by the collector to decide whether to record the gap. A property rather
        than a flag set during a read, so asking does not depend on having read.
        """
        return bool(self._present_split_columns())

    def _sql(self, period_start: date, period_end: date) -> str:
        """One partition pruned query.

        The predicate is on the partition column, not on a date extracted from
        a timestamp, because a function applied to a partition key stops Athena
        pruning and the query scans the whole table.

        The projection is the required columns plus whichever split cost allocation
        columns this export actually has, so an export without them is read with the
        same SQL it was always read with.
        """
        columns = ", ".join(
            sorted([*COLUMNS, *self._present_split_columns(), *self._present_focus_columns()])
        )
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
        for column, field in (
            *COLUMNS.items(),
            *SPLIT_COLUMNS.items(),
            *FOCUS_1_2_COLUMNS.items(),
        ):
            # Every split column is read through `row.get`, so one absent from the
            # projection lands as None rather than raising. That is the whole of
            # "reads them where present and does not fail where absent".
            fields[field] = _coerce(field, row.get(column))

        currency = fields["billing_currency"]
        if currency is not None and not CURRENCY.fullmatch(currency):
            # Refused here as a typed failure, rather than by the table's constraint, which
            # would abort the whole period's write with an error nobody can read.
            raise SchemaDrift(
                scope_key=SCOPE,
                collector=COLLECTOR,
                detail=f"billing currency {currency!r} is not an ISO 4217 code",
            )

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
