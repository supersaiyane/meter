"""Meter's purchase plan, drafted from the bill, P9's rates and the inventory. TASK-P14-007.

FEAT-089. The collector drafts this month's plan and redrafts it while it is a draft, lapses an
earlier month's draft nobody approved, and leaves alone a plan somebody acted on. The database
refuses a transition out of order whatever path tries it, constraint 11, and a usage type P9 prices
for two operating systems, with no SKU on the bill to choose between them, is never priced.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from finops_core.domain.commitments import EC2, RESERVATION, SAVINGS_PLAN
from finops_fakes import fixtures
from finops_fakes.catalog import FakePriceCatalog, FakeSavingsPlansRates, on_demand_hourly
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.collectors.price_catalog import PriceCatalogCollector
from finops_ingest.collectors.purchase_plan import (
    PRINCIPAL,
    PurchasePlanCollector,
    _holding,
    _Price,
    _rate,
    family_of,
)
from finops_ingest.collectors.savings_plan_rates import SavingsPlanRatesCollector
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.purchase_plan import FAMILY_BOUND

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 13, 6, tzinfo=UTC)
REGION = fixtures.REGION
TYPE = "m6i.large"
USAGE_TYPE = f"BoxUsage:{TYPE}"


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


def unit(tenant: UUID, collector: str = "purchase_plan") -> WorkUnit:
    return WorkUnit(
        tenant_id=tenant,
        collector=collector,
        window_start=NOW - timedelta(days=1),
        window_end=NOW,
    )


def run(engine: Engine, tenant: UUID, collector: Any, name: str = "purchase_plan") -> Any:
    with engine.begin() as connection:
        return collector(
            CollectorContext(unit=unit(tenant, name), connection=connection, run_id=uuid4())
        )


def priced(engine: Engine, tenant: UUID) -> None:
    """P9's fake prices and Savings Plans rates, loaded the way the collectors load them."""
    run(engine, tenant, PriceCatalogCollector(FakePriceCatalog(regions=[REGION])), "price_catalog")
    rates = SavingsPlanRatesCollector(FakeSavingsPlansRates(regions=[REGION]))
    run(engine, tenant, rates, "savings_plan_rates")


def billed(engine: Engine, tenant: UUID, days: int = 30, hourly_units: int = 4) -> None:
    """`hourly_units` m6i.large instances on demand all day, for `days` days to yesterday."""
    cost = on_demand_hourly(TYPE) * 24 * hourly_units
    with engine.begin() as connection:
        for offset in range(1, days + 1):
            day = NOW.date() - timedelta(days=offset)
            period = day.replace(day=1)
            ensure_partition(connection, "cost_focus_daily", period)
            start = datetime(day.year, day.month, day.day, tzinfo=UTC)
            connection.execute(
                text(
                    "INSERT INTO cost_focus_daily (tenant_id, ingest_run_id, source_fingerprint, "
                    "as_of, collected_at, billing_account_id, sub_account_id, "
                    "billing_period_start, billing_period_end, charge_period_start, "
                    "charge_period_end, provider_name, service_name, region_id, "
                    "charge_category, billed_cost, effective_cost, list_cost, x_usage_type, "
                    "tags) VALUES (:t, :run, :fp, :end, :end, 'payer', 'account', :period, "
                    ":period_end, :start, :end, 'Fake', 'AmazonEC2', :region, 'Usage', :cost, "
                    ":cost, :cost, :usage, '{}'::jsonb)"
                ),
                {
                    "t": tenant,
                    "run": uuid4(),
                    "fp": f"ec2:{day}",
                    "period": period,
                    "period_end": (period + timedelta(days=32)).replace(day=1),
                    "start": start,
                    "end": start + timedelta(days=1),
                    "region": REGION,
                    "cost": cost,
                    "usage": USAGE_TYPE,
                },
            )


def plans(engine: Engine, tenant: UUID) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                text(
                    "SELECT plan_id, plan_month, status, days_held, steady_hourly, "
                    "target_hourly, no_purchase_reason FROM purchase_plan WHERE tenant_id = :t "
                    "ORDER BY plan_month"
                ),
                {"t": tenant},
            ).mappings()
        ]


def lines(engine: Engine, tenant: UUID) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                text(
                    "SELECT program, instance_family, region_id, tranche_month, "
                    "hourly_commitment FROM purchase_plan_line WHERE tenant_id = :t "
                    "ORDER BY line_no"
                ),
                {"t": tenant},
            ).mappings()
        ]


def events(engine: Engine, tenant: UUID) -> list[tuple[str | None, str, str]]:
    with engine.connect() as connection:
        return [
            (row.from_status, row.to_status, row.principal)
            for row in connection.execute(
                text(
                    "SELECT from_status, to_status, principal FROM purchase_plan_event "
                    "WHERE tenant_id = :t ORDER BY at, to_status"
                ),
                {"t": tenant},
            )
        ]


def collector(at: datetime = NOW) -> PurchasePlanCollector:
    return PurchasePlanCollector(clock=lambda: at)


def test_a_month_of_steady_usage_drafts_a_family_bound_plan(
    engine: Engine, tenant_id: UUID
) -> None:
    priced(engine, tenant_id)
    billed(engine, tenant_id)
    outcome: CollectorOutcome = run(engine, tenant_id, collector())
    (plan,) = plans(engine, tenant_id)
    assert (plan["plan_month"], plan["status"], plan["days_held"]) == (
        date(2026, 10, 1),
        "DRAFT",
        30,
    )
    assert plan["steady_hourly"] == on_demand_hourly(TYPE) * 4
    found = lines(engine, tenant_id)
    assert {(one["program"], one["instance_family"], one["region_id"]) for one in found} == {
        (FAMILY_BOUND, "m6i", REGION)
    }
    # The cautious ladder: a twelfth a month, twelve months named.
    assert len({one["tranche_month"] for one in found}) == 12
    assert outcome.items_written == 1 + len(found)
    assert events(engine, tenant_id) == [(None, "DRAFT", PRINCIPAL)]


def test_a_redraft_keeps_the_plan_and_replaces_its_lines(engine: Engine, tenant_id: UUID) -> None:
    priced(engine, tenant_id)
    billed(engine, tenant_id)
    run(engine, tenant_id, collector())
    (first,) = plans(engine, tenant_id)
    count = len(lines(engine, tenant_id))
    outcome = run(engine, tenant_id, collector(NOW + timedelta(hours=1)))
    (again,) = plans(engine, tenant_id)
    assert again["plan_id"] == first["plan_id"]
    assert outcome.items_removed == count
    assert len(lines(engine, tenant_id)) == count
    assert events(engine, tenant_id) == [(None, "DRAFT", PRINCIPAL)]


def test_an_earlier_months_draft_nobody_approved_lapses(engine: Engine, tenant_id: UUID) -> None:
    priced(engine, tenant_id)
    billed(engine, tenant_id)
    run(engine, tenant_id, collector())
    run(engine, tenant_id, collector(datetime(2026, 11, 2, 6, tzinfo=UTC)))
    october, november = plans(engine, tenant_id)
    assert (october["status"], november["status"]) == ("LAPSED", "DRAFT")
    assert ("DRAFT", "LAPSED", PRINCIPAL) in events(engine, tenant_id)


def test_a_plan_somebody_acted_on_is_left_as_it_is(engine: Engine, tenant_id: UUID) -> None:
    priced(engine, tenant_id)
    billed(engine, tenant_id)
    run(engine, tenant_id, collector())
    before = lines(engine, tenant_id)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE purchase_plan SET status = 'APPROVED' WHERE tenant_id = :t"),
            {"t": tenant_id},
        )
    outcome = run(engine, tenant_id, collector(NOW + timedelta(hours=1)))
    assert outcome.items_written == 0
    assert lines(engine, tenant_id) == before


def test_a_bill_holding_too_few_days_drafts_the_reason_and_nothing_to_buy(
    engine: Engine, tenant_id: UUID
) -> None:
    priced(engine, tenant_id)
    billed(engine, tenant_id, days=10)
    run(engine, tenant_id, collector())
    (plan,) = plans(engine, tenant_id)
    assert plan["no_purchase_reason"].startswith("The bill holds 10 of the last 30 days")
    assert (plan["steady_hourly"], plan["target_hourly"]) == (None, None)
    assert lines(engine, tenant_id) == []


@pytest.mark.parametrize(
    ("change", "says"),
    [
        ("UPDATE purchase_plan SET status = 'BOUGHT' WHERE tenant_id = :t", "from DRAFT to BOUGHT"),
        ("UPDATE purchase_plan SET status = 'VERIFIED' WHERE tenant_id = :t", "to VERIFIED"),
    ],
)
def test_the_database_refuses_a_plan_skipping_a_step(
    engine: Engine, tenant_id: UUID, change: str, says: str
) -> None:
    run(engine, tenant_id, collector())
    with pytest.raises(DBAPIError, match=says), engine.begin() as connection:
        connection.execute(text(change), {"t": tenant_id})


def test_the_database_refuses_a_plan_born_approved_and_an_event_out_of_order(
    engine: Engine, tenant_id: UUID
) -> None:
    run(engine, tenant_id, collector())
    (plan,) = plans(engine, tenant_id)
    with pytest.raises(DBAPIError, match="begins as a draft"), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO purchase_plan (plan_id, tenant_id, ingest_run_id, plan_month, status, "
                "target_coverage, term_years, payment_option, ladder_limit, window_start, "
                "window_end, days_held, currency, as_of, collected_at) VALUES (:id, :t, :id, "
                "'2026-12-01', 'APPROVED', 0.8, 1, 'No Upfront', 0.0833, '2026-11-01', "
                "'2026-12-01', 30, 'USD', now(), now())"
            ),
            {"id": uuid4(), "t": tenant_id},
        )
    with pytest.raises(DBAPIError, match="a_transition_allowed"), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO purchase_plan_event (event_id, plan_id, tenant_id, from_status, "
                "to_status, principal, at) VALUES (:id, :plan, :t, 'DRAFT', 'VERIFIED', 'x', now())"
            ),
            {"id": uuid4(), "plan": plan["plan_id"], "t": tenant_id},
        )


def price(sku: str, system: str, rate: str = "0.10") -> _Price:
    return _Price(REGION, sku, USAGE_TYPE, Decimal(rate), system, NOW)


def test_a_usage_type_priced_for_two_systems_is_priced_only_by_its_sku() -> None:
    two = [price("sku-linux", "Linux"), price("sku-windows", "Windows", "0.19")]
    assert _rate(REGION, USAGE_TYPE, None, two, ()).on_demand is None
    rate = _rate(REGION, USAGE_TYPE, "sku-windows", two, ())
    assert rate.on_demand == Decimal("0.19")


def test_a_rate_is_the_savings_plans_rate_for_the_same_operating_system() -> None:
    committed = [
        SimpleNamespace(
            region=REGION,
            sku_meter=USAGE_TYPE,
            product=product,
            offering_class=program,
            recurring_unit_price=Decimal(value),
            as_of=NOW,
        )
        for program, product, value in (
            ("Compute", "Linux/UNIX", "0.07"),
            ("EC2Instance", "Linux/UNIX", "0.06"),
            ("Compute", "Windows", "0.15"),
        )
    ]
    rate = _rate(REGION, USAGE_TYPE, None, [price("sku-linux", "Linux")], committed)
    assert (rate.flexible, rate.family_bound) == (Decimal("0.07"), Decimal("0.06"))


def test_an_operating_system_no_savings_plan_names_has_no_committed_rate() -> None:
    rate = _rate(REGION, USAGE_TYPE, None, [price("sku-byol", "Windows BYOL")], ())
    assert rate.on_demand == Decimal("0.10")
    assert (rate.flexible, rate.family_bound) == (None, None)


def test_a_family_is_read_from_a_usage_type_or_an_instance_type() -> None:
    assert family_of("EU-BoxUsage:m6i.large") == "m6i"
    assert family_of("m6i.large") == "m6i"


def holding(**overrides: Any) -> Any:
    values: dict[str, Any] = {
        "kind": SAVINGS_PLAN,
        "commitment_id": "c-1",
        "program": "Compute",
        "region_id": None,
        "applies_to": None,
        "quantity": None,
        "hourly_commitment": Decimal("1.5"),
        "recurring_hourly": Decimal("1.5"),
        "upfront_amount": Decimal(0),
        "term_months": 12,
        "ends_at": datetime(2027, 6, 1, tzinfo=UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_what_is_held_lands_on_its_family_or_on_the_estate() -> None:
    flexible = _holding(holding())
    assert (flexible.hourly, flexible.family, flexible.region) == (Decimal("1.5"), None, None)
    bound = _holding(holding(program="EC2Instance", applies_to="m5", region_id=REGION))
    assert (bound.family, bound.region) == ("m5", REGION)
    reserved = _holding(
        holding(
            kind=RESERVATION,
            program=EC2,
            applies_to="m6i.large",
            region_id=REGION,
            quantity=2,
            hourly_commitment=None,
            recurring_hourly=Decimal("0.05"),
        )
    )
    assert (reserved.hourly, reserved.family, reserved.region) == (Decimal("0.10"), "m6i", REGION)
