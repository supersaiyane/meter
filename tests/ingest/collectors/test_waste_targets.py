"""A rightsizing names a priced target, against the estate and the catalog. TASK-P9-007.

The planted m5.2xlarge at about 7 percent CPU runs no agent, so the rule may only offer m5.xlarge,
one size down in its family, and the saving is the two list prices' difference for the hours it
runs, scaled to its bill: about half its cost, no longer 90.9 percent of it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_fakes import fixtures, planted
from finops_fakes.catalog import VERSION, FakeInstanceCatalog, FakePriceCatalog, on_demand_hourly
from finops_fakes.estate_metrics import EstateMetrics, ec2_candidates
from finops_fakes.estate_shape import REGIONS
from finops_ingest.collectors.instance_catalog import InstanceCatalogCollector
from finops_ingest.collectors.price_catalog import PriceCatalogCollector
from finops_ingest.collectors.waste_compute import Candidate, WasteComputeCollector
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext
from finops_query.targets import HOURS_PER_MONTH, saving

pytestmark = pytest.mark.integration

NOW = fixtures.AS_OF
OVERSIZED = next(p.subjects[0] for p in planted.PLANTED if p.code == "OVERSIZED_MEMORY_UNOBSERVED")


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


def catalogued(engine: Engine, tenant: UUID) -> None:
    """The fake catalog's prices and instance types, as the 8 hourly collectors store them."""
    instances = InstanceCatalogCollector(
        FakeInstanceCatalog(), hub_region=REGIONS[0], clock=lambda: NOW
    )
    prices = PriceCatalogCollector(FakePriceCatalog(), clock=lambda: NOW)
    for collector, name in ((prices, "price_catalog"), (instances, "instance_catalog")):
        unit = WorkUnit(
            tenant_id=tenant,
            collector=name,
            window_start=NOW,
            window_end=NOW,
            account=None,
            region=None,
        )
        with engine.begin() as connection:
            collector(CollectorContext(unit=unit, connection=connection, run_id=uuid4()))


def candidates(**overrides: Any) -> list[Candidate]:
    return [
        replace(
            Candidate(
                resource_id=c.resource_id,
                account_id=c.account_id,
                region_id=c.region_id,
                observation_days=c.observation_days,
                monthly_cost=c.monthly_cost,
                credit_balance=c.credit_balance,
                instance_type=c.instance_type,
            ),
            **(overrides if c.resource_id == OVERSIZED else {}),
        )
        for c in ec2_candidates(at=NOW)
    ]


def collect(engine: Engine, tenant: UUID, settings: Settings, chosen: list[Candidate]) -> None:
    context = CollectorContext
    with engine.begin() as connection:
        WasteComputeCollector(EstateMetrics(at=NOW), lambda _context: chosen, clock=lambda: NOW)(
            context(
                unit=Unit(tenant_id=tenant),
                connection=connection,
                run_id=uuid4(),
                settings=settings,
            )
        )


def oversized(engine: Engine, tenant: UUID) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    "SELECT * FROM recommendation WHERE tenant_id = :t AND source = 'METER' "
                    "AND resource_id = :r"
                ),
                {"t": tenant, "r": OVERSIZED},
            )
            .mappings()
            .first()
        )
    return None if row is None else dict(row)


def refusal(engine: Engine, tenant: UUID) -> str | None:
    with engine.connect() as connection:
        found = connection.execute(
            text("SELECT reason FROM sizing_refusal WHERE tenant_id = :t AND resource_id = :r"),
            {"t": tenant, "r": OVERSIZED},
        ).scalar()
    return None if found is None else str(found)


def test_the_planted_m5_2xlarge_names_m5_xlarge_and_saves_the_price_difference(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    catalogued(engine, tenant_id)
    collect(engine, tenant_id, settings, candidates())
    found = oversized(engine, tenant_id)
    assert found is not None
    assert found["target_instance_type"] == "m5.xlarge"
    assert found["target_sku_price_id"]
    assert found["current_sku_price_id"]
    assert found["price_version"] == VERSION
    cost = next(c.monthly_cost for c in ec2_candidates(at=NOW) if c.resource_id == OVERSIZED)
    expected = saving(
        current_hourly=on_demand_hourly("m5.2xlarge"),
        target_hourly=on_demand_hourly("m5.xlarge"),
        hours=HOURS_PER_MONTH,
        paid_monthly=cost,
    )
    assert abs(found["estimated_monthly_saving"] - expected.as_paid) < Decimal(1)
    # Half its cost, give or take the catalog's rounding, and no longer 90.9 percent of it.
    assert found["estimated_monthly_saving"] < cost * Decimal("0.55")
    assert "Move m5.2xlarge to m5.xlarge" in found["rationale"]
    assert "No agent publishes memory" in found["rationale"]
    assert f"price list version {VERSION}" in found["rationale"]


def test_without_a_catalog_the_old_estimate_stands_and_says_why(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    collect(engine, tenant_id, settings, candidates())
    found = oversized(engine, tenant_id)
    assert found is not None
    assert found["target_instance_type"] is None
    assert "the catalog holds no EC2 prices" in found["rationale"]


def test_without_a_type_no_target_is_named_and_it_says_why(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    catalogued(engine, tenant_id)
    collect(engine, tenant_id, settings, candidates(instance_type=None))
    found = oversized(engine, tenant_id)
    assert found is not None
    assert found["target_instance_type"] is None
    assert "type is not known" in found["rationale"]


def test_a_type_the_catalog_does_not_describe_names_no_target(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    catalogued(engine, tenant_id)
    collect(engine, tenant_id, settings, candidates(instance_type="m5.24xlarge"))
    found = oversized(engine, tenant_id)
    assert found is not None
    assert "does not describe m5.24xlarge" in found["rationale"]


def test_with_no_cheaper_type_offered_it_is_refused_with_the_reason(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    catalogued(engine, tenant_id)
    # The fake catalog's smallest m5 is m5.large, so there is nothing one size down from it.
    collect(engine, tenant_id, settings, candidates(instance_type="m5.large"))
    assert oversized(engine, tenant_id) is None
    reason = refusal(engine, tenant_id)
    assert reason is not None
    assert "No target" in reason


def test_a_target_that_stops_fitting_is_cleared_on_the_next_run(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    catalogued(engine, tenant_id)
    collect(engine, tenant_id, settings, candidates())
    collect(engine, tenant_id, settings, candidates(instance_type=None))
    found = oversized(engine, tenant_id)
    assert found is not None
    assert found["target_instance_type"] is None
    assert found["price_version"] is None


# --- growing, TASK-P9-008 ----------------------------------------------------------------

PRESSED = next(p.subjects[0] for p in planted.PLANTED if p.code == "EC2_OVER_UTILIZED")


def recommendation_of(engine: Engine, tenant: UUID, resource: str) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    "SELECT * FROM recommendation WHERE tenant_id = :t AND source = 'METER' "
                    "AND resource_id = :r"
                ),
                {"t": tenant, "r": resource},
            )
            .mappings()
            .first()
        )
    return None if row is None else dict(row)


def test_the_planted_c6i_2xlarge_above_ninety_percent_is_an_upsize(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    catalogued(engine, tenant_id)
    collect(engine, tenant_id, settings, candidates())
    found = recommendation_of(engine, tenant_id, PRESSED)
    assert found is not None
    assert found["waste_class"] == "UPSIZE_INSTANCE"
    assert found["estimated_monthly_saving"] == 0
    assert found["added_monthly_cost"] > 0
    assert found["target_instance_type"] == "c6i.4xlarge"
    assert found["price_version"] == VERSION
    assert "Under pressure, CPU p95" in found["rationale"]
    assert "Grow c6i.2xlarge to c6i.4xlarge" in found["rationale"]


def test_an_upsize_never_lowers_the_total_of_savings(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    catalogued(engine, tenant_id)
    collect(engine, tenant_id, settings, candidates())
    with engine.connect() as connection:
        every, without = connection.execute(
            text(
                "SELECT sum(estimated_monthly_saving), "
                "sum(estimated_monthly_saving) FILTER (WHERE waste_class <> 'UPSIZE_INSTANCE') "
                "FROM recommendation WHERE tenant_id = :t"
            ),
            {"t": tenant_id},
        ).one()
    assert every == without


def test_without_a_catalog_pressure_is_a_refusal_saying_why(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    collect(engine, tenant_id, settings, candidates())
    assert recommendation_of(engine, tenant_id, PRESSED) is None
    with engine.connect() as connection:
        reason = connection.execute(
            text(
                "SELECT reason FROM sizing_refusal WHERE tenant_id = :t AND resource_id = :r "
                "AND waste_class = 'UPSIZE_INSTANCE'"
            ),
            {"t": tenant_id, "r": PRESSED},
        ).scalar_one()
    assert "Under pressure" in reason
    assert "no description or price of c6i.2xlarge" in reason


def options(engine: Engine, tenant: UUID) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        found = connection.execute(
            text(
                "SELECT o.* FROM recommendation_option o JOIN recommendation r "
                "ON r.recommendation_id = o.recommendation_id "
                "WHERE r.tenant_id = :t AND r.resource_id = :r ORDER BY o.rank"
            ),
            {"t": tenant, "r": OVERSIZED},
        )
        return [dict(row) for row in found.mappings()]


def test_the_types_the_rule_found_to_fit_are_its_alternatives_the_target_first(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    # TASK-P9-010. With no agent the rule may only step once in the family, so one type fits.
    catalogued(engine, tenant_id)
    collect(engine, tenant_id, settings, candidates())
    (only,) = options(engine, tenant_id)
    assert (only["rank"], only["instance_type"]) == (1, "m5.xlarge")
    # The rule gives no risk score, and a nought would read as Compute Optimizer's "no risk".
    assert only["performance_risk"] is None
    assert only["price_version"] == VERSION
    found = oversized(engine, tenant_id)
    assert found is not None
    assert only["sku_price_id"] == found["target_sku_price_id"]
    assert only["hourly_price"] == on_demand_hourly("m5.xlarge")
    assert only["platform_differences"] == []


def test_alternatives_go_when_the_target_does(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    catalogued(engine, tenant_id)
    collect(engine, tenant_id, settings, candidates())
    collect(engine, tenant_id, settings, candidates(instance_type=None))
    assert options(engine, tenant_id) == []
