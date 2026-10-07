"""The price catalog stored by version, against a migrated database. TASK-P9-004, FEAT-071.

The fake catalog prices EC2 in the estate's three Regions under one version. A republished
source below moves every Region to a later one, which is how AWS publishing new prices looks.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.catalog import Price, PriceListVersion
from finops_core.errors import AccessDenied, CollectionError, SchemaDrift, Throttled
from finops_fakes.catalog import EC2, VERSION, FakePriceCatalog
from finops_fakes.estate_shape import REGIONS
from finops_fakes.prices import INSTANCE_USD
from finops_ingest.collectors import price_catalog
from finops_ingest.collectors.price_catalog import PriceCatalogCollector
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext, CollectorOutcome

AT = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
#: Every price the fake sells in one Region: each type on demand and in six reservations.
PER_REGION = len(INSTANCE_USD) * 7
LATER = "20260821000000"

pytestmark = pytest.mark.integration


def run(engine: Engine, tenant: UUID, source: Any, **options: Any) -> CollectorOutcome:
    unit = WorkUnit(
        tenant_id=tenant,
        collector="price_catalog",
        window_start=AT,
        window_end=AT,
        account=None,
        region=None,
    )
    with engine.begin() as connection:
        return PriceCatalogCollector(source, clock=lambda: AT, **options)(
            CollectorContext(unit=unit, connection=connection, run_id=uuid4())
        )


def scalar(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def held(engine: Engine, tenant: UUID) -> dict[tuple[str, str], int]:
    """Each stored version and the rows it says it holds."""
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT region, version, row_count FROM price_list_version WHERE tenant_id = :t"),
            {"t": tenant},
        )
        return {(row.region, row.version): row.row_count for row in rows}


def errors(engine: Engine, tenant: UUID) -> dict[str, str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT scope_key, error_type FROM sync_error "
                "WHERE tenant_id = :t AND collector = 'price_catalog'"
            ),
            {"t": tenant},
        )
        return {row.scope_key: row.error_type for row in rows}


class Republished:
    """The fake catalog, every Region republished a day later under a new version."""

    def __init__(self) -> None:
        self._inner = FakePriceCatalog()
        self.loaded: list[str] = []

    def versions(self, service_code: str) -> Iterable[PriceListVersion]:
        return tuple(
            replace(v, version=LATER, as_of=v.as_of + timedelta(days=1))
            for v in self._inner.versions(service_code)
        )

    def prices(self, version: PriceListVersion) -> Iterator[Price]:
        self.loaded.append(version.region)
        original = replace(version, version=VERSION, as_of=version.as_of - timedelta(days=1))
        for price in self._inner.prices(original):
            yield replace(price, version=LATER, as_of=version.as_of)


class Counting:
    """The fake catalog, counting the versions it was asked to load."""

    def __init__(self) -> None:
        self._inner = FakePriceCatalog()
        self.loaded = 0

    def versions(self, service_code: str) -> Iterable[PriceListVersion]:
        return self._inner.versions(service_code)

    def prices(self, version: PriceListVersion) -> Iterable[Price]:
        self.loaded += 1
        return self._inner.prices(version)


class FailingIn:
    """The fake catalog, failing one Region partway through its prices."""

    def __init__(self, region: str, failure: type[CollectionError], after: int) -> None:
        self._inner = FakePriceCatalog()
        self._region = region
        self._failure = failure
        self._after = after

    def versions(self, service_code: str) -> Iterable[PriceListVersion]:
        return self._inner.versions(service_code)

    def prices(self, version: PriceListVersion) -> Iterator[Price]:
        for count, price in enumerate(self._inner.prices(version)):
            if version.region == self._region and count == self._after:
                raise self._failure(
                    scope_key=f"{version.service_code}:{version.region}",
                    collector="price_catalog",
                    detail="planned",
                )
            yield price


class RefusingService:
    """The fake catalog, with one more service whose versions cannot be listed."""

    def __init__(self) -> None:
        self._inner = FakePriceCatalog()

    def versions(self, service_code: str) -> Iterable[PriceListVersion]:
        if service_code == "AmazonRDS":
            raise AccessDenied(scope_key=service_code, collector="price_catalog")
        return self._inner.versions(service_code)

    def prices(self, version: PriceListVersion) -> Iterable[Price]:
        return self._inner.prices(version)


# --- loading -----------------------------------------------------------------------------


def test_a_first_run_loads_every_region_and_counts_what_it_stored(
    engine: Engine, tenant_id: UUID
) -> None:
    outcome = run(engine, tenant_id, FakePriceCatalog())
    assert outcome.items_written == PER_REGION * len(REGIONS)
    assert held(engine, tenant_id) == {(region, VERSION): PER_REGION for region in REGIONS}


def test_a_price_is_stored_as_the_source_read_it(engine: Engine, tenant_id: UUID) -> None:
    run(engine, tenant_id, FakePriceCatalog())
    expected = next(
        p
        for p in FakePriceCatalog().prices(next(iter(FakePriceCatalog().versions(EC2))))
        if p.upfront_fee and p.lease_years == 3 and p.recurring_unit_price == 0
    )
    with engine.connect() as connection:
        row = (
            connection.execute(
                text("SELECT * FROM price WHERE tenant_id = :t AND sku_price_id = :id"),
                {"t": tenant_id, "id": expected.sku_price_id},
            )
            .mappings()
            .one()
        )
    assert row["recurring_unit_price"] == 0
    assert row["upfront_fee"] == expected.upfront_fee
    assert (row["lease_years"], row["purchase_option"]) == (3, "All Upfront")
    assert row["pricing_category"] == "Committed"
    assert row["sku_price_details"] == dict(expected.details)
    assert row["as_of"] == expected.as_of


def test_an_unchanged_version_does_no_work(engine: Engine, tenant_id: UUID) -> None:
    run(engine, tenant_id, FakePriceCatalog())
    source = Counting()
    outcome = run(engine, tenant_id, source)
    assert source.loaded == 0
    assert (outcome.items_written, outcome.items_removed) == (0, 0)


def test_prices_are_written_in_batches(
    engine: Engine, tenant_id: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(price_catalog, "BATCH", 10)
    outcome = run(engine, tenant_id, FakePriceCatalog())
    assert outcome.items_written == PER_REGION * len(REGIONS)


# --- a new version ---------------------------------------------------------------------


def test_a_new_version_replaces_the_old_one_whole(engine: Engine, tenant_id: UUID) -> None:
    run(engine, tenant_id, FakePriceCatalog())
    source = Republished()
    outcome = run(engine, tenant_id, source)
    assert sorted(source.loaded) == sorted(REGIONS)
    assert held(engine, tenant_id) == {(region, LATER): PER_REGION for region in REGIONS}
    # Every old price and every old version.
    assert outcome.items_removed == (PER_REGION + 1) * len(REGIONS)
    assert scalar(engine, "SELECT count(*) FROM price WHERE tenant_id = :t", t=tenant_id) == (
        PER_REGION * len(REGIONS)
    )


def test_a_price_a_recommendation_quotes_outlives_its_version(
    engine: Engine, tenant_id: UUID
) -> None:
    run(engine, tenant_id, FakePriceCatalog())
    region = REGIONS[0]
    with engine.begin() as connection:
        quoted = list(
            connection.execute(
                text(
                    "SELECT sku_price_id FROM price WHERE tenant_id = :t AND region = :r "
                    "AND pricing_category = 'Standard' "
                    "AND sku_price_details ->> 'instanceType' IN ('m5.2xlarge', 'm5.xlarge') "
                    "ORDER BY sku_price_details ->> 'instanceType' DESC"
                ),
                {"t": tenant_id, "r": region},
            ).scalars()
        )
        connection.execute(
            text(
                "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, "
                "source, source_reference, waste_class, resource_id, region_id, "
                "estimated_monthly_saving, confidence, severity, observation_days, lifecycle, "
                "rationale, as_of, collected_at, current_sku_price_id, target_instance_type, "
                "target_sku_price_id, price_version) "
                "VALUES (:id, :t, '111122223333', 'METER', 'ref:quoted', 'IDLE_INSTANCE', "
                "'i-0quoted', :r, 42, 'HIGH', 'HIGH', 30, 'OPEN', 'because', :at, :at, "
                ":current, 'm5.xlarge', :target, :v)"
            ),
            {
                "id": uuid4(),
                "t": tenant_id,
                "r": region,
                "at": AT,
                "current": quoted[0],
                "target": quoted[1],
                "v": VERSION,
            },
        )
    outcome = run(engine, tenant_id, Republished())
    stored = held(engine, tenant_id)
    # The quoted version stays, holding the two prices it is quoted from and nothing else.
    assert {(r, v) for r, v in stored if v == VERSION} == {(region, VERSION)}
    left = scalar(
        engine,
        "SELECT count(*) FROM price WHERE tenant_id = :t AND version = :v",
        t=tenant_id,
        v=VERSION,
    )
    assert left == 2
    assert outcome.items_removed == (PER_REGION - 2) + (PER_REGION + 1) * (len(REGIONS) - 1)


# --- partial failure ----------------------------------------------------------------------


@pytest.mark.parametrize("failure", [Throttled, SchemaDrift])
def test_a_region_that_fails_partway_stores_nothing_and_says_why(
    engine: Engine, tenant_id: UUID, failure: type[CollectionError]
) -> None:
    broken = REGIONS[1]
    outcome = run(engine, tenant_id, FailingIn(broken, failure, after=50))
    assert outcome.items_written == PER_REGION * (len(REGIONS) - 1)
    assert {region for region, _ in held(engine, tenant_id)} == set(REGIONS) - {broken}
    in_broken = scalar(
        engine,
        "SELECT count(*) FROM price WHERE tenant_id = :t AND region = :r",
        t=tenant_id,
        r=broken,
    )
    assert in_broken == 0
    assert errors(engine, tenant_id) == {f"{EC2}:{broken}": failure.__name__}


def test_a_failed_region_keeps_the_version_it_held(engine: Engine, tenant_id: UUID) -> None:
    run(engine, tenant_id, FakePriceCatalog())

    class RepublishedButBroken(Republished):
        def prices(self, version: PriceListVersion) -> Iterator[Price]:
            if version.region == REGIONS[2]:
                raise Throttled(scope_key=version.region, collector="price_catalog")
            yield from super().prices(version)

    run(engine, tenant_id, RepublishedButBroken())
    stored = held(engine, tenant_id)
    assert (REGIONS[2], VERSION) in stored
    assert (REGIONS[2], LATER) not in stored
    assert (REGIONS[0], LATER) in stored


def test_a_service_that_cannot_be_listed_is_recorded_and_the_rest_load(
    engine: Engine, tenant_id: UUID
) -> None:
    outcome = run(engine, tenant_id, RefusingService(), services=(EC2, "AmazonRDS"))
    assert outcome.items_written == PER_REGION * len(REGIONS)
    assert errors(engine, tenant_id) == {"AmazonRDS": "AccessDenied"}


def test_a_run_that_reads_nothing_at_all_fails(engine: Engine, tenant_id: UUID) -> None:
    with pytest.raises(AccessDenied):
        run(engine, tenant_id, FakePriceCatalog(failure=AccessDenied))
    assert held(engine, tenant_id) == {}


def test_a_service_with_no_versions_is_neither_read_nor_failed(
    engine: Engine, tenant_id: UUID
) -> None:
    # The fake sells only EC2, as a service AWS has no list for would look.
    outcome = run(engine, tenant_id, FakePriceCatalog(), services=("AmazonRDS",))
    assert outcome.items_written == 0
    assert errors(engine, tenant_id) == {}
