"""The Athena billing export adapter, which has never made a call.

Every test here runs against a recorded response shape. That proves the adapter
turns those shapes into domain objects, which is worth proving, and it proves
nothing at all about whether the real export looks like this. ISS-122.

What is worth the most here is the partition predicate and the refusal to
return a short period, because both are failures that would look like success:
a full table scan reads as a slow query and arrives as a line on the bill, and a
half read month reads as a month where charges were retracted and gets half
deleted.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError

from finops_core import errors
from finops_core.config import Settings
from finops_providers.aws.cur import AthenaCostExport

ROW = {
    "billingaccountid": "111122223333",
    "subaccountid": "444455556666",
    "billingperiodstart": "2026-08-01",
    "billingperiodend": "2026-09-01",
    "chargeperiodstart": "2026-08-01T00:00:00",
    "chargeperiodend": "2026-08-02T00:00:00",
    "providername": "AWS",
    "publishername": "AWS",
    "invoiceissuername": "AWS",
    "servicename": "AmazonEC2",
    "servicecategory": "Compute",
    "resourceid": "i-0001",
    "resourcename": "web-01",
    "regionid": "eu-west-2",
    "availabilityzone": "eu-west-2a",
    "chargecategory": "Usage",
    "chargedescription": "BoxUsage",
    "skuid": "SKU1",
    "pricingquantity": "24",
    "consumedquantity": "24",
    "consumedunit": "Hrs",
    "billedcost": "12.3400",
    "effectivecost": "11.0000",
    "listcost": "15.0000",
    "contractedcost": "",
    "commitmentdiscountid": "",
    "commitmentdiscounttype": "",
    "commitmentdiscountstatus": "",
}


AUGUST = date(2026, 8, 1)
SEPTEMBER = date(2026, 9, 1)


def page_for(rows: list[dict[str, str]], *, with_header: bool = True) -> dict[str, Any]:
    columns = sorted(ROW)
    data = []
    if with_header:
        data.append({"Data": [{"VarCharValue": name} for name in columns]})
    for row in rows:
        data.append({"Data": [{"VarCharValue": row.get(name, "")} for name in columns]})
    return {
        "ResultSet": {
            "ResultSetMetadata": {"ColumnInfo": [{"Name": name} for name in columns]},
            "Rows": data,
        }
    }


class StubPaginator:
    def __init__(self, pages: list[Any]) -> None:
        self._pages = pages

    def paginate(self, **_: Any) -> Any:
        for page in self._pages:
            if isinstance(page, Exception):
                raise page
            yield page


class StubAthena:
    def __init__(self, pages: list[Any], states: list[str] | None = None) -> None:
        self.pages = pages
        self.states = states or ["SUCCEEDED"]
        self.queries: list[str] = []

    def start_query_execution(self, **kwargs: Any) -> Any:
        self.queries.append(kwargs["QueryString"])
        return {"QueryExecutionId": "q-1"}

    def get_query_execution(self, **_: Any) -> Any:
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return {"QueryExecution": {"Status": {"State": state, "StateChangeReason": state}}}

    def get_paginator(self, _: str) -> StubPaginator:
        return StubPaginator(self.pages)


class StubS3:
    def __init__(self, prefixes: list[str]) -> None:
        self._prefixes = prefixes

    def get_paginator(self, _: str) -> StubPaginator:
        return StubPaginator([{"CommonPrefixes": [{"Prefix": p} for p in self._prefixes]}])


def export(
    settings: Settings, athena: Any = None, s3: Any = None, **kwargs: Any
) -> AthenaCostExport:
    clients = {"athena": athena, "s3": s3}
    return AthenaCostExport(
        settings,
        tenant_id=uuid4(),
        ingest_run_id=uuid4(),
        client_factory=lambda service: clients[service],
        sleeper=lambda _: None,
        **kwargs,
    )


def one_row(settings: Settings) -> Any:
    """The single row the recorded page holds."""
    athena = StubAthena([page_for([ROW])])
    return next(iter(export(settings, athena=athena).read_period(AUGUST, SEPTEMBER)))


class TestTheQueryPrunes:
    def test_the_predicate_is_on_the_partition_column(self, settings: Settings) -> None:
        """A full scan of a CUR table is the tool that reports on cost becoming
        a line on the bill."""
        athena = StubAthena([page_for([ROW])])
        list(export(settings, athena=athena).read_period(date(2026, 8, 1), date(2026, 9, 1)))
        sql = athena.queries[0]
        assert "billing_period >= '2026-08'" in sql
        assert "billing_period < '2026-09'" in sql

    def test_no_function_wraps_the_partition_key(self, settings: Settings) -> None:
        # A function applied to a partition key stops Athena pruning, and the
        # query silently scans the whole table at full price.
        athena = StubAthena([page_for([ROW])])
        list(export(settings, athena=athena).read_period(date(2026, 8, 1), date(2026, 9, 1)))
        sql = athena.queries[0].lower()
        for wrapper in ("date(", "date_parse(", "substr(", "cast("):
            assert f"{wrapper}billing_period" not in sql


class TestAPeriodIsWholeOrNothing:
    def test_a_failure_part_way_through_paging_raises(self, settings: Settings) -> None:
        """The property TASK-P1-005's delete turns on.

        A short list reaching the collector is indistinguishable from a month
        where those charges were retracted, and the collector would delete them.
        """
        boom = ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "GetQueryResults")
        athena = StubAthena([page_for([ROW]), boom])
        with pytest.raises(errors.AccessDenied):
            export(settings, athena=athena).read_period(date(2026, 8, 1), date(2026, 9, 1))

    def test_an_empty_period_raises_no_data_rather_than_returning_empty(
        self, settings: Settings
    ) -> None:
        athena = StubAthena([page_for([])])
        with pytest.raises(errors.NoData):
            export(settings, athena=athena).read_period(date(2026, 8, 1), date(2026, 9, 1))


class TestThrottling:
    def test_it_backs_off_and_then_gives_up_rather_than_hammering(self, settings: Settings) -> None:
        waits: list[float] = []
        throttle = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
            "StartQueryExecution",
        )

        class AlwaysThrottles(StubAthena):
            def start_query_execution(self, **_: Any) -> Any:
                raise throttle

        subject = AthenaCostExport(
            settings,
            tenant_id=uuid4(),
            ingest_run_id=uuid4(),
            client_factory=lambda _: AlwaysThrottles([]),
            sleeper=waits.append,
        )
        with pytest.raises(errors.Throttled):
            subject.read_period(date(2026, 8, 1), date(2026, 9, 1))

        assert len(waits) == settings.aws_max_retries, "gave up at the wrong point"
        assert waits == sorted(waits), "the backoff does not back off"
        assert len(set(waits)) == len(waits), "the backoff is flat, which is a tight retry"

    def test_athena_reporting_a_throttle_as_a_failed_query_is_still_a_throttle(
        self, settings: Settings
    ) -> None:
        # Athena fails the execution rather than the call, so the state reason
        # is the only place a throttle appears. Reading it as schema drift would
        # send somebody to look at the table.
        athena = StubAthena([], states=["FAILED"])
        athena.get_query_execution = lambda **_: {  # type: ignore[method-assign]
            "QueryExecution": {
                "Status": {"State": "FAILED", "StateChangeReason": "Query was THROTTLED"}
            }
        }
        with pytest.raises(errors.Throttled):
            export(settings, athena=athena).read_period(date(2026, 8, 1), date(2026, 9, 1))


class TestTheHeaderRow:
    def test_athenas_repeated_header_is_dropped(self, settings: Settings) -> None:
        athena = StubAthena([page_for([ROW])])
        rows = list(export(settings, athena=athena).read_period(date(2026, 8, 1), date(2026, 9, 1)))
        assert len(rows) == 1

    def test_a_real_row_that_looks_like_the_header_is_not_dropped(self, settings: Settings) -> None:
        """Dropping the header by position drops a real row on page two.

        Athena repeats the column names as the first row of the first page
        only. A second page starts with data.
        """
        athena = StubAthena([page_for([ROW]), page_for([ROW], with_header=False)])
        rows = list(export(settings, athena=athena).read_period(date(2026, 8, 1), date(2026, 9, 1)))
        assert len(rows) == 2


class TestMapping:
    def test_a_recorded_row_becomes_a_cost_record(self, settings: Settings) -> None:
        row = one_row(settings)
        assert row.service_name == "AmazonEC2"
        assert row.effective_cost == Decimal("11.0000")
        assert row.billed_cost == Decimal("12.3400")
        assert row.billing_period_start == date(2026, 8, 1)
        assert row.resource_id == "i-0001"
        # Empty strings are nulls, not empty strings, or every optional column
        # would read as present and blank.
        assert row.contracted_cost is None
        assert row.commitment_discount_id is None

    def test_the_fingerprint_is_the_shared_one(self, settings: Settings) -> None:
        # Not the adapter's own. Two implementations of an identity is how a
        # duplicate is created.
        from finops_core.domain.cost import source_fingerprint

        row = one_row(settings)
        assert row.source_fingerprint == source_fingerprint(
            billing_account_id=row.billing_account_id,
            sub_account_id=row.sub_account_id,
            charge_period_start=row.charge_period_start,
            charge_period_end=row.charge_period_end,
            service_name=row.service_name,
            resource_id=row.resource_id,
            sku_id=row.sku_id,
            charge_category=row.charge_category,
            commitment_discount_id=row.commitment_discount_id,
        )

    def test_a_missing_required_column_is_drift_and_never_a_zero(self, settings: Settings) -> None:
        """Constraint 5. A row we cannot read is a row we do not understand."""
        broken = {**ROW, "effectivecost": ""}
        athena = StubAthena([page_for([broken])])
        with pytest.raises(errors.SchemaDrift):
            export(settings, athena=athena).read_period(date(2026, 8, 1), date(2026, 9, 1))

    def test_tags_come_off_the_tag_columns(self, settings: Settings) -> None:
        row = one_row(settings)
        # The recorded row carries none, which is the common case in any estate
        # and is the reason the unallocated bucket exists.
        assert row.tags == {}


class TestFindingThePeriods:
    def test_partition_prefixes_become_periods(self, settings: Settings) -> None:
        s3 = StubS3(
            [
                "exports/focus/BILLING_PERIOD=2026-06/",
                "exports/focus/BILLING_PERIOD=2026-07/",
                "exports/focus/BILLING_PERIOD=2026-08/",
            ]
        )
        assert export(settings, s3=s3).latest_available_period() == date(2026, 8, 1)

    def test_a_prefix_that_is_not_a_period_is_ignored_rather_than_raising(
        self, settings: Settings
    ) -> None:
        # Data Exports writes metadata beside the data. It is not an error.
        s3 = StubS3(["exports/focus/metadata/", "exports/focus/BILLING_PERIOD=2026-08/"])
        assert export(settings, s3=s3).latest_available_period() == date(2026, 8, 1)

    def test_an_export_that_has_published_nothing_returns_none(self, settings: Settings) -> None:
        # The port's distinction: present and empty, versus missing. A caller
        # that collapsed them reports a configuration fault as an empty bill.
        assert export(settings, s3=StubS3([])).latest_available_period() is None
