"""Savings Plans rates stored by their own digest, against a migrated database. TASK-P9-012.

The fake sells 21 types in three Regions, each at 12 rates: two plan types, two lengths, three
payment options. The Regions read are the ones the price catalog holds EC2 for.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.catalog import SAVINGS_PLANS, PriceListVersion, PriceSheet, sheet_version
from finops_core.errors import AccessDenied, Throttled
from finops_fakes.catalog import FakePriceCatalog, FakeSavingsPlansRates
from finops_fakes.estate_shape import REGIONS
from finops_fakes.prices import INSTANCE_USD
from finops_ingest.collectors.price_catalog import PriceCatalogCollector
from finops_ingest.collectors.savings_plan_rates import SavingsPlanRatesCollector
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext, CollectorOutcome

AT = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
PER_REGION = len(INSTANCE_USD) * 12

pytestmark = pytest.mark.integration


def context(connection: Any, tenant: UUID, collector: str) -> CollectorContext:
    unit = WorkUnit(
        tenant_id=tenant,
        collector=collector,
        window_start=AT,
        window_end=AT,
        account=None,
        region=None,
    )
    return CollectorContext(unit=unit, connection=connection, run_id=uuid4())


def run(engine: Engine, tenant: UUID, source: Any) -> CollectorOutcome:
    with engine.begin() as connection:
        collector = SavingsPlanRatesCollector(source, clock=lambda: AT)
        return collector(context(connection, tenant, "savings_plan_rates"))


def priced(engine: Engine, tenant: UUID) -> None:
    with engine.begin() as connection:
        PriceCatalogCollector(FakePriceCatalog(), clock=lambda: AT)(
            context(connection, tenant, "price_catalog")
        )


def versions(engine: Engine, tenant: UUID) -> dict[str, list[str]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT region, version FROM price_list_version "
                "WHERE tenant_id = :t AND service_code = :s ORDER BY as_of"
            ),
            {"t": tenant, "s": SAVINGS_PLANS},
        )
        found: dict[str, list[str]] = {}
        for row in rows:
            found.setdefault(row.region, []).append(row.version)
        return found


def errors(engine: Engine, tenant: UUID) -> dict[str, str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT scope_key, error_type FROM sync_error "
                "WHERE tenant_id = :t AND collector = 'savings_plan_rates'"
            ),
            {"t": tenant},
        )
        return {row.scope_key: row.error_type for row in rows}


class Moved:
    """The fake, every rate a cent an hour dearer and read a day later."""

    def __init__(self) -> None:
        self._inner = FakeSavingsPlansRates()

    def rates(self, region: str) -> PriceSheet:
        sheet = self._inner.rates(region)
        cent = Decimal("0.01")
        dearer = [
            replace(p, recurring_unit_price=p.recurring_unit_price + cent) for p in sheet.prices
        ]
        version = sheet_version((p.sku_price_id, p.recurring_unit_price) for p in dearer)
        later = sheet.version.as_of + timedelta(days=1)
        new = PriceListVersion(
            service_code=SAVINGS_PLANS,
            region=region,
            version=version,
            as_of=later,
            collected_at=later,
        )
        moved = tuple(replace(p, version=version, as_of=later, collected_at=later) for p in dearer)
        return PriceSheet(version=new, prices=moved)


class FailingIn:
    """The fake, one Region throttled."""

    def __init__(self, region: str) -> None:
        self._inner = FakeSavingsPlansRates()
        self._region = region

    def rates(self, region: str) -> PriceSheet:
        if region == self._region:
            raise Throttled(scope_key=f"{SAVINGS_PLANS}:{region}", collector="savings_plan_rates")
        return self._inner.rates(region)


def test_with_no_prices_held_there_is_no_region_to_read(engine: Engine, tenant_id: UUID) -> None:
    outcome = run(engine, tenant_id, FakeSavingsPlansRates())
    assert (outcome.items_written, outcome.items_removed) == (0, 0)
    assert versions(engine, tenant_id) == {}


def test_every_region_the_prices_are_held_for_is_read_and_stored(
    engine: Engine, tenant_id: UUID
) -> None:
    priced(engine, tenant_id)
    outcome = run(engine, tenant_id, FakeSavingsPlansRates())
    assert outcome.items_written == PER_REGION * len(REGIONS)
    assert set(versions(engine, tenant_id)) == set(REGIONS)


def test_rates_that_have_not_moved_store_nothing(engine: Engine, tenant_id: UUID) -> None:
    priced(engine, tenant_id)
    run(engine, tenant_id, FakeSavingsPlansRates())
    outcome = run(engine, tenant_id, FakeSavingsPlansRates())
    assert (outcome.items_written, outcome.items_removed) == (0, 0)


def test_rates_that_moved_replace_the_sheet_held(engine: Engine, tenant_id: UUID) -> None:
    priced(engine, tenant_id)
    run(engine, tenant_id, FakeSavingsPlansRates())
    outcome = run(engine, tenant_id, Moved())
    assert outcome.items_written == PER_REGION * len(REGIONS)
    assert outcome.items_removed == (PER_REGION + 1) * len(REGIONS)
    assert all(len(held) == 1 for held in versions(engine, tenant_id).values())


def test_a_region_that_fails_keeps_its_sheet_and_says_why(engine: Engine, tenant_id: UUID) -> None:
    priced(engine, tenant_id)
    run(engine, tenant_id, FakeSavingsPlansRates())
    before = versions(engine, tenant_id)[REGIONS[1]]
    run(engine, tenant_id, FailingIn(REGIONS[1]))
    assert versions(engine, tenant_id)[REGIONS[1]] == before
    assert errors(engine, tenant_id) == {f"{SAVINGS_PLANS}:{REGIONS[1]}": "Throttled"}


def test_a_run_that_reads_nothing_at_all_fails(engine: Engine, tenant_id: UUID) -> None:
    priced(engine, tenant_id)
    with pytest.raises(AccessDenied):
        run(engine, tenant_id, FakeSavingsPlansRates(failure=AccessDenied))
