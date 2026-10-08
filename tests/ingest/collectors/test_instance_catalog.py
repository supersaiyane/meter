"""Instance types stored where they are sold, against a migrated database. TASK-P9-005, FEAT-072.

The fake describes every type the estate prices, and the fake price catalog sells all of them in
the estate's three Regions, so a run after the prices are loaded stores each type three times.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.catalog import InstanceTypeSpec
from finops_core.errors import AccessDenied, NotOptedIn
from finops_fakes.catalog import EC2, SPECS, FakeInstanceCatalog, FakePriceCatalog
from finops_fakes.estate_shape import REGIONS
from finops_ingest.collectors.instance_catalog import InstanceCatalogCollector
from finops_ingest.collectors.price_catalog import PriceCatalogCollector
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext, CollectorOutcome

AT = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
HUB, OTHER = REGIONS[0], REGIONS[1]
TYPES = len(SPECS)
RDS = "AmazonRDS"

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


def run(engine: Engine, tenant: UUID, ec2: Any, **options: Any) -> CollectorOutcome:
    options.setdefault("hub_region", HUB)
    with engine.begin() as connection:
        collector = InstanceCatalogCollector(ec2, clock=lambda: AT, **options)
        return collector(context(connection, tenant, "instance_catalog"))


def priced(engine: Engine, tenant: UUID) -> None:
    with engine.begin() as connection:
        PriceCatalogCollector(FakePriceCatalog(), clock=lambda: AT)(
            context(connection, tenant, "price_catalog")
        )


def stored(engine: Engine, tenant: UUID, **where: Any) -> dict[tuple[str, str], dict[str, Any]]:
    clauses = "".join(f" AND {column} = :{column}" for column in where)
    with engine.connect() as connection:
        rows = connection.execute(
            text(f"SELECT * FROM instance_type_spec WHERE tenant_id = :t{clauses}"),
            {"t": tenant, **where},
        ).mappings()
        return {(row["region"], row["instance_type"]): dict(row) for row in rows}


def errors(engine: Engine, tenant: UUID) -> dict[str, str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT scope_key, error_type, detail FROM sync_error "
                "WHERE tenant_id = :t AND collector = 'instance_catalog'"
            ),
            {"t": tenant},
        )
        return {row.scope_key: f"{row.error_type}: {row.detail}" for row in rows}


class Adding:
    """The fake, with extra or replaced descriptions, in every Region or in one."""

    def __init__(self, *extra: InstanceTypeSpec, only_in: str | None = None) -> None:
        self._inner = FakeInstanceCatalog()
        self._extra = {spec.instance_type: spec for spec in extra}
        self._only_in = only_in

    def instance_types(self, region: str) -> Iterable[InstanceTypeSpec]:
        found = {s.instance_type: s for s in self._inner.instance_types(region)}
        if self._only_in is None or region == self._only_in:
            found.update({n: replace(s, region=region) for n, s in self._extra.items()})
        return tuple(found.values())


class Without:
    """The fake, with some types no longer described."""

    def __init__(self, *gone: str) -> None:
        self._inner = FakeInstanceCatalog()
        self._gone = set(gone)

    def instance_types(self, region: str) -> Iterable[InstanceTypeSpec]:
        found = self._inner.instance_types(region)
        return tuple(s for s in found if s.instance_type not in self._gone)


def fake_spec(name: str, region: str = HUB) -> InstanceTypeSpec:
    found = FakeInstanceCatalog().instance_types(region)
    return next(s for s in found if s.instance_type == name)


class Managed:
    """One managed service's classes, dated by the read as the adapter dates a product without
    a publication time, and counting the Regions it was asked for."""

    def __init__(self, failing: str | None = None) -> None:
        self.asked: list[str] = []
        self._failing = failing

    def instance_types(self, region: str) -> Iterable[InstanceTypeSpec]:
        self.asked.append(region)
        if region == self._failing:
            raise AccessDenied(scope_key=f"{RDS}:{region}", collector="instance_catalog")
        node = replace(
            fake_spec("m5.large"),
            service_code=RDS,
            region=region,
            instance_type="db.m5.large",
            as_of=AT,
            collected_at=AT,
        )
        return (node,)


def listed(engine: Engine, tenant: UUID, region: str, as_of: datetime) -> None:
    """A price list version for RDS, as the price catalog would have stored it."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO price_list_version (version_pk, tenant_id, ingest_run_id, "
                "service_code, region, version, row_count, as_of, collected_at) "
                "VALUES (:pk, :t, :run, :s, :r, :v, 0, :at, :at)"
            ),
            {
                "pk": uuid4(),
                "t": tenant,
                "run": uuid4(),
                "s": RDS,
                "r": region,
                "v": as_of.strftime("%Y%m%d%H%M%S"),
                "at": as_of,
            },
        )


# --- EC2 ---------------------------------------------------------------------------------


def test_before_any_prices_the_types_are_stored_in_the_hubs_region(
    engine: Engine, tenant_id: UUID
) -> None:
    outcome = run(engine, tenant_id, FakeInstanceCatalog())
    assert outcome.items_written == TYPES
    assert {region for region, _ in stored(engine, tenant_id)} == {HUB}


def test_each_type_is_stored_in_every_region_the_price_list_sells_it(
    engine: Engine, tenant_id: UUID
) -> None:
    priced(engine, tenant_id)
    outcome = run(engine, tenant_id, FakeInstanceCatalog())
    assert outcome.items_written == TYPES * len(REGIONS)
    rows = stored(engine, tenant_id)
    assert {region for region, _ in rows} == set(REGIONS)
    assert all(row["offered"] for row in rows.values())


def test_a_burstable_type_is_stored_with_the_guides_baseline(
    engine: Engine, tenant_id: UUID
) -> None:
    run(engine, tenant_id, FakeInstanceCatalog())
    row = stored(engine, tenant_id)[(HUB, "t3.large")]
    assert row["burstable"] is True
    assert float(row["baseline_cpu"]) == pytest.approx(0.30)
    assert float(row["maximum_credits"]) == 864
    assert "burstable-credits-baseline-concepts" in row["baseline_source"]
    assert row["architectures"] == ["x86_64"]


def test_a_burstable_type_the_table_lacks_is_named_and_not_stored(
    engine: Engine, tenant_id: UUID
) -> None:
    new = replace(
        fake_spec("t3.micro"),
        instance_type="t9.micro",
        baseline_cpu=None,
        maximum_credits=None,
        baseline_source=None,
    )
    outcome = run(engine, tenant_id, Adding(new))
    assert outcome.items_written == TYPES
    assert (HUB, "t9.micro") not in stored(engine, tenant_id)
    assert "t9.micro" in errors(engine, tenant_id)[f"{EC2}:{HUB}:burstable"]


def test_a_type_sold_that_the_hub_does_not_describe_is_counted(
    engine: Engine, tenant_id: UUID
) -> None:
    priced(engine, tenant_id)
    run(engine, tenant_id, Without("m5.large"))
    assert all(name != "m5.large" for _, name in stored(engine, tenant_id))
    assert "m5.large" in errors(engine, tenant_id)[f"{EC2}:undescribed"]


def test_a_type_described_differently_in_the_second_region_is_kept_where_it_was_read(
    engine: Engine, tenant_id: UUID
) -> None:
    priced(engine, tenant_id)
    bigger = replace(fake_spec("m5.large", OTHER), vcpus=4)
    run(engine, tenant_id, Adding(bigger, only_in=OTHER), compare_region=OTHER)
    rows = stored(engine, tenant_id)
    assert (HUB, "m5.large") in rows
    assert (OTHER, "m5.large") not in rows
    assert (REGIONS[2], "m5.large") not in rows
    assert (OTHER, "m5.xlarge") in rows
    assert "m5.large" in errors(engine, tenant_id)[f"{EC2}:{OTHER}"]


def test_a_second_region_that_cannot_be_read_is_noted_and_the_rest_stored(
    engine: Engine, tenant_id: UUID
) -> None:
    class Refusing(FakeInstanceCatalog):
        def instance_types(self, region: str) -> Iterable[InstanceTypeSpec]:
            if region == OTHER:
                raise NotOptedIn(scope_key=f"{EC2}:{OTHER}", collector="instance_catalog")
            return super().instance_types(region)

    outcome = run(engine, tenant_id, Refusing(), compare_region=OTHER)
    assert outcome.items_written == TYPES
    assert errors(engine, tenant_id)[f"{EC2}:{OTHER}"].startswith("NotOptedIn")


def test_a_type_no_longer_described_is_marked_not_offered_and_kept(
    engine: Engine, tenant_id: UUID
) -> None:
    run(engine, tenant_id, FakeInstanceCatalog())
    run(engine, tenant_id, Without("m5.large"))
    rows = stored(engine, tenant_id)
    assert rows[(HUB, "m5.large")]["offered"] is False
    assert rows[(HUB, "m5.xlarge")]["offered"] is True


def test_a_hub_that_cannot_be_described_and_nothing_else_read_fails_the_run(
    engine: Engine, tenant_id: UUID
) -> None:
    with pytest.raises(AccessDenied):
        run(engine, tenant_id, FakeInstanceCatalog(failure=AccessDenied))


def test_a_description_compared_with_itself_is_refused() -> None:
    with pytest.raises(ValueError, match="compared with itself"):
        InstanceCatalogCollector(FakeInstanceCatalog(), hub_region=HUB, compare_region=HUB)


# --- the managed services ---------------------------------------------------------------


def test_a_managed_service_is_described_where_its_prices_are_and_only_when_they_change(
    engine: Engine, tenant_id: UUID
) -> None:
    listed(engine, tenant_id, HUB, AT - timedelta(days=2))
    service = Managed()
    run(engine, tenant_id, FakeInstanceCatalog(), managed={RDS: service})
    assert service.asked == [HUB]
    assert (HUB, "db.m5.large") in stored(engine, tenant_id, service_code=RDS)

    # Nothing new published: nothing read.
    run(engine, tenant_id, FakeInstanceCatalog(), managed={RDS: service})
    assert service.asked == [HUB]

    # A newer list: read again.
    listed(engine, tenant_id, HUB, AT + timedelta(hours=1))
    run(engine, tenant_id, FakeInstanceCatalog(), managed={RDS: service})
    assert service.asked == [HUB, HUB]


def test_a_managed_region_that_fails_is_recorded_and_the_run_stands(
    engine: Engine, tenant_id: UUID
) -> None:
    listed(engine, tenant_id, HUB, AT - timedelta(days=1))
    listed(engine, tenant_id, OTHER, AT - timedelta(days=1))
    managed = {RDS: Managed(failing=OTHER)}
    outcome = run(engine, tenant_id, FakeInstanceCatalog(), managed=managed)
    assert outcome.items_written == TYPES + 1
    assert errors(engine, tenant_id)[f"{RDS}:{OTHER}"].startswith("AccessDenied")


def test_managed_services_alone_keep_a_run_whose_ec2_failed(
    engine: Engine, tenant_id: UUID
) -> None:
    listed(engine, tenant_id, HUB, AT - timedelta(days=1))
    failing = FakeInstanceCatalog(failure=AccessDenied)
    outcome = run(engine, tenant_id, failing, managed={RDS: Managed()})
    assert outcome.items_written == 1
    # The fake names the Region alone as its scope.
    assert errors(engine, tenant_id)[HUB].startswith("AccessDenied")
