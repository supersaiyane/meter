"""Meter's own bill, and the two ways a self metering report flatters itself.

Dropping untagged cost makes the report under count quietly. That is worse than
having no report at all, because a number on a page is believed and an absent
one is not.

Leaving the metering charge in unallocated means the one cost this tool
definitely creates is the one cost it never owns. Cost Explorer charges per
request and the charge arrives untagged, because an account level API charge has
no resource to hang a tag on.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_core.constants import PLATFORM_TAG_KEY
from finops_core.domain.platform import UNALLOCATED, PlatformCost
from finops_core.errors import AccessDenied, SchemaDrift, Throttled
from finops_ingest.collectors.platform_cost import (
    SERVICE_TO_MODULE,
    PlatformCostCollector,
    attribute,
)
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext
from finops_providers.aws.platform_cost import AwsPlatformCostSource, ModuleCharge

DAY = date(2026, 8, 26)
NEXT_DAY = date(2026, 8, 27)
AT = datetime(2026, 8, 27, 6, 0, tzinfo=UTC)
CE_SERVICE = "AWS Cost Explorer"


def group(module: str, service: str, amount: str) -> dict[str, Any]:
    return {
        "Keys": [f"{PLATFORM_TAG_KEY}${module}", service],
        "Metrics": {"AmortizedCost": {"Amount": amount, "Unit": "USD"}},
    }


def response(*groups: dict[str, Any]) -> dict[str, Any]:
    return {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": DAY.isoformat(), "End": NEXT_DAY.isoformat()},
                "Groups": list(groups),
            }
        ]
    }


class StubCostExplorer:
    def __init__(self, payload: dict[str, Any], failure: Exception | None = None) -> None:
        self.payload = payload
        self.failure = failure
        self.calls: list[dict[str, Any]] = []

    def get_cost_and_usage(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.failure is not None:
            raise self.failure
        return self.payload


def source(settings: Settings, client: StubCostExplorer) -> AwsPlatformCostSource:
    return AwsPlatformCostSource(settings, client_factory=lambda: client)


# --- attribution, with nothing else involved --------------------------------


def test_a_tagged_charge_keeps_its_module() -> None:
    assert attribute("ingest", "AmazonECS") == "ingest"


def test_untagged_cost_is_named_rather_than_dropped() -> None:
    assert attribute("", "AmazonECS") == UNALLOCATED


def test_the_metering_charge_is_attributed_to_the_module_that_caused_it() -> None:
    """Otherwise the one cost this tool definitely creates is the one it disowns."""
    assert attribute("", CE_SERVICE) == "ingest"
    assert SERVICE_TO_MODULE[CE_SERVICE] == "ingest"


def test_a_platform_cost_with_no_module_is_refused() -> None:
    with pytest.raises(ValueError, match="unallocated"):
        PlatformCost(
            day=DAY,
            module="",
            service="AmazonECS",
            amortized_cost=Decimal("1"),
            as_of=AT,
            collected_at=AT,
        )


# --- the request itself ------------------------------------------------------


def test_one_grouped_request_answers_the_whole_question(settings: Settings) -> None:
    """Per module calls multiply a metered API by the number of modules."""
    client = StubCostExplorer(response(group("ingest", "AmazonECS", "1.5")))
    source(settings, client).daily_by_module(DAY, NEXT_DAY)
    assert len(client.calls) == 1


def test_the_request_is_daily_and_grouped_by_module_and_service(
    settings: Settings,
) -> None:
    client = StubCostExplorer(response(group("ingest", "AmazonECS", "1.5")))
    source(settings, client).daily_by_module(DAY, NEXT_DAY)
    sent = client.calls[0]
    assert sent["Granularity"] == "DAILY"
    assert sent["Metrics"] == ["AmortizedCost"]
    assert sent["GroupBy"] == [
        {"Type": "TAG", "Key": PLATFORM_TAG_KEY},
        {"Type": "DIMENSION", "Key": "SERVICE"},
    ]


def test_the_amounts_arrive_as_decimals(settings: Settings) -> None:
    """A float total over a month of line items is wrong in the last places."""
    client = StubCostExplorer(response(group("ingest", "AmazonECS", "1.55")))
    charges = source(settings, client).daily_by_module(DAY, NEXT_DAY)
    assert charges[0].amortized_cost == Decimal("1.55")
    assert isinstance(charges[0].amortized_cost, Decimal)


def test_an_untagged_group_comes_back_with_an_empty_module(settings: Settings) -> None:
    """The adapter reports what the provider said. Naming it is a domain decision."""
    client = StubCostExplorer(response(group("", "AmazonS3", "0.2")))
    charges = source(settings, client).daily_by_module(DAY, NEXT_DAY)
    assert charges[0].module == ""


def test_being_answered_about_another_tag_is_loud(settings: Settings) -> None:
    """Every module attribution below would be wrong, so it must not be absorbed."""
    payload = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": DAY.isoformat(), "End": NEXT_DAY.isoformat()},
                "Groups": [
                    {
                        "Keys": ["some:other:tag$ingest", "AmazonECS"],
                        "Metrics": {"AmortizedCost": {"Amount": "1"}},
                    }
                ],
            }
        ]
    }
    with pytest.raises(SchemaDrift):
        source(settings, StubCostExplorer(payload)).daily_by_module(DAY, NEXT_DAY)


def test_a_group_of_the_wrong_shape_is_loud(settings: Settings) -> None:
    payload = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": DAY.isoformat(), "End": NEXT_DAY.isoformat()},
                "Groups": [{"Keys": ["only-one-key"], "Metrics": {}}],
            }
        ]
    }
    with pytest.raises(SchemaDrift):
        source(settings, StubCostExplorer(payload)).daily_by_module(DAY, NEXT_DAY)


@pytest.mark.parametrize(
    ("code", "expected"),
    [("AccessDenied", AccessDenied), ("ThrottlingException", Throttled)],
)
def test_provider_failures_arrive_typed(
    settings: Settings, code: str, expected: type[Exception]
) -> None:
    failure = ClientError({"Error": {"Code": code, "Message": "no"}}, "GetCostAndUsage")
    client = StubCostExplorer({}, failure=failure)
    with pytest.raises(expected):
        source(settings, client).daily_by_module(DAY, NEXT_DAY)


# --- writing it down ---------------------------------------------------------


def charge(module: str, service: str, amount: str) -> ModuleCharge:
    return ModuleCharge(day=DAY, module=module, service=service, amortized_cost=Decimal(amount))


class StubSource:
    def __init__(self, *charges: ModuleCharge) -> None:
        self._charges = charges

    def daily_by_module(self, _start: date, _end: date) -> tuple[ModuleCharge, ...]:
        return self._charges


def unit_for(tenant: UUID) -> WorkUnit:
    return WorkUnit(
        tenant_id=tenant,
        collector="platform_cost",
        window_start=datetime(2026, 8, 26, tzinfo=UTC),
        window_end=datetime(2026, 8, 27, tzinfo=UTC),
    )


def collect(engine: Engine, tenant: UUID, stub: StubSource) -> int:
    with engine.begin() as connection:
        outcome = PlatformCostCollector(stub, clock=lambda: AT)(
            CollectorContext(unit=unit_for(tenant), connection=connection)
        )
    return outcome.items_written


def stored(engine: Engine, tenant: UUID) -> dict[tuple[str, str], Decimal]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT * FROM platform_cost WHERE tenant_id = :t"), {"t": tenant}
        ).mappings()
        return {(row["module"], row["service"]): row["amortized_cost"] for row in rows}


@pytest.mark.integration
def test_costs_are_written_by_module_and_service(engine: Engine, tenant_id: UUID) -> None:
    written = collect(
        engine,
        tenant_id,
        StubSource(charge("ingest", "AmazonECS", "1.50"), charge("api", "AmazonRDS", "2.25")),
    )
    assert written == 2
    assert stored(engine, tenant_id) == {
        ("ingest", "AmazonECS"): Decimal("1.5000000000"),
        ("api", "AmazonRDS"): Decimal("2.2500000000"),
    }


@pytest.mark.integration
def test_untagged_cost_lands_in_unallocated_rather_than_being_dropped(
    engine: Engine, tenant_id: UUID
) -> None:
    """A report that quietly under counts is worse than no report."""
    collect(engine, tenant_id, StubSource(charge("", "AmazonS3", "0.20")))
    assert (UNALLOCATED, "AmazonS3") in stored(engine, tenant_id)


@pytest.mark.integration
def test_the_cost_explorer_charge_is_attributed_to_ingest(engine: Engine, tenant_id: UUID) -> None:
    collect(engine, tenant_id, StubSource(charge("", CE_SERVICE, "0.01")))
    written = stored(engine, tenant_id)
    assert ("ingest", CE_SERVICE) in written
    assert (UNALLOCATED, CE_SERVICE) not in written


@pytest.mark.integration
def test_re_attribution_sums_rather_than_overwrites(engine: Engine, tenant_id: UUID) -> None:
    """Two rows can merge into one, and neither may be silently discarded."""
    collect(
        engine,
        tenant_id,
        StubSource(charge("ingest", CE_SERVICE, "0.01"), charge("", CE_SERVICE, "0.02")),
    )
    assert stored(engine, tenant_id)[("ingest", CE_SERVICE)] == Decimal("0.0300000000")


@pytest.mark.integration
def test_a_rerun_updates_rather_than_duplicating(engine: Engine, tenant_id: UUID) -> None:
    collect(engine, tenant_id, StubSource(charge("ingest", "AmazonECS", "1.00")))
    collect(engine, tenant_id, StubSource(charge("ingest", "AmazonECS", "1.75")))
    assert stored(engine, tenant_id) == {("ingest", "AmazonECS"): Decimal("1.7500000000")}


@pytest.mark.integration
def test_one_tenant_never_sees_another_platform_bill(engine: Engine, tenant_id: UUID) -> None:
    from uuid import uuid4

    other = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenant (tenant_id, name) VALUES (:id, :name)"),
            {"id": other, "name": f"tenant-{other}"},
        )
    collect(engine, tenant_id, StubSource(charge("ingest", "AmazonECS", "1.00")))
    assert stored(engine, other) == {}


# --- the cadence is a cost decision -----------------------------------------


def test_the_platform_cost_cadence_is_daily_and_says_why() -> None:
    """Each run is a paid request, so hourly would pay twenty four times over."""
    from finops_ingest.registry import DAILY, DEFAULT_SCHEDULE

    entry = next(e for e in DEFAULT_SCHEDULE if e.collector == "platform_cost")
    assert entry.cadence_seconds == DAILY
    assert "per request" in entry.reason
    assert Decimal(entry.est_cost_per_run) > 0
