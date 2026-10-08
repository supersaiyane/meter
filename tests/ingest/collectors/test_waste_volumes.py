"""A gp2 volume is priced as the gp3 that does its work, against the estate. TASK-P9-009.

The planted `amazonebs/fake-platform-b/0002` is 1,000 GiB of gp2, attached and busy, publishing
its operations and not its bytes. At the fake catalog's prices it costs 100.00 a month on gp2 and
85.00 on gp3 given gp2's 250 MiB/s, because its throughput was not measured: a saving of 15.00,
modelled, with the working in its rationale.
"""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_fakes import catalog, fixtures
from finops_fakes.catalog import VERSION
from finops_fakes.estate_metrics import EstateMetrics, volume_candidates
from finops_ingest.collectors.waste_compute import WasteComputeCollector
from finops_ingest.collectors.waste_volumes import VolumeCandidate
from finops_ingest.registry import CollectorContext
from tests.ingest.collectors.test_waste_targets import Unit, catalogued

pytestmark = pytest.mark.integration

NOW = fixtures.AS_OF
PLANTED = "amazonebs/fake-platform-b/0002"


def volumes(**extra: Any) -> list[VolumeCandidate]:
    found = [VolumeCandidate(**asdict(v)) for v in volume_candidates(at=NOW)]
    return [*found, *([VolumeCandidate(**extra)] if extra else [])]


def collect(engine: Engine, tenant: UUID, settings: Settings, chosen: list[VolumeCandidate]) -> int:
    collector = WasteComputeCollector(
        EstateMetrics(at=NOW), lambda _context: [], clock=lambda: NOW, volumes=lambda _c: chosen
    )
    with engine.begin() as connection:
        outcome = collector(
            CollectorContext(
                unit=Unit(tenant_id=tenant),
                connection=connection,
                run_id=uuid4(),
                settings=settings,
            )
        )
    return outcome.items_written


def rows(engine: Engine, tenant: UUID, table: str) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        found = connection.execute(
            text(f"SELECT * FROM {table} WHERE tenant_id = :t AND waste_class = 'EBS_GP2_TO_GP3'"),
            {"t": tenant},
        )
        return [dict(row) for row in found.mappings()]


def test_the_planted_gp2_volume_is_priced_as_gp3_with_its_working(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    catalogued(engine, tenant_id)
    assert collect(engine, tenant_id, settings, volumes()) == 1
    (found,) = rows(engine, tenant_id, "recommendation")
    assert found["resource_id"] == PLANTED
    assert found["source"] == "METER"
    assert found["estimated_monthly_saving"] == Decimal("15.00")
    assert found["rationale"].startswith(
        "Move gp2 to gp3 at 3,000 IOPS and 250 MiB/s: 1,000 GiB at 0.08, "
        "125 MiB/s above the included 125 at 0.04, 85.00 a month against 100.00 on gp2"
    )
    assert "Throughput was not measured, so gp3 is given gp2's 250 MiB/s" in found["rationale"]
    assert f"Priced from price list version {VERSION}" in found["rationale"]
    # Nothing to name a type or a price id for: the working is the rationale.
    assert found["target_instance_type"] is None
    assert found["price_version"] is None


def test_only_attached_gp2_volumes_are_judged(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    catalogued(engine, tenant_id)
    chosen = volumes()
    assert {v.volume_type for v in chosen} == {"gp2", "gp3"}
    collect(engine, tenant_id, settings, chosen)
    judged = rows(engine, tenant_id, "recommendation") + rows(engine, tenant_id, "sizing_refusal")
    assert {row["resource_id"] for row in judged} == {PLANTED}


def test_without_a_catalog_the_volume_is_refused_with_the_reason(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    assert collect(engine, tenant_id, settings, volumes()) == 0
    (refused,) = rows(engine, tenant_id, "sizing_refusal")
    assert refused["resource_id"] == PLANTED
    assert "the catalog holds no EC2 prices" in refused["reason"]


def test_a_version_without_gp3_iops_or_throughput_says_which_are_missing(
    engine: Engine, tenant_id: UUID, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A version loaded before TASK-P9-009 holds storage prices only.
    monkeypatch.setattr(catalog, "VOLUMES", catalog.VOLUMES[:2])
    catalogued(engine, tenant_id)
    assert collect(engine, tenant_id, settings, volumes()) == 0
    (refused,) = rows(engine, tenant_id, "sizing_refusal")
    assert refused["reason"] == (
        f"the catalog holds no gp3 iops, gp3 throughput price in version {VERSION}"
    )


def test_a_volume_publishing_nothing_is_unobserved_not_judged(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    catalogued(engine, tenant_id)
    silent = volumes(
        resource_id="amazonebs/fake-platform-b/9999",
        account_id=volume_candidates(at=NOW)[0].account_id,
        region_id=volume_candidates(at=NOW)[0].region_id,
        observation_days=30,
        monthly_cost=Decimal(50),
        size_gib=500,
        volume_type="gp2",
    )
    assert collect(engine, tenant_id, settings, silent) == 1
    assert {row["resource_id"] for row in rows(engine, tenant_id, "recommendation")} == {PLANTED}
    with engine.connect() as connection:
        said = connection.execute(
            text(
                "SELECT detail FROM sync_error WHERE tenant_id = :t AND collector = 'waste_compute'"
            ),
            {"t": tenant_id},
        ).scalar_one()
    assert said.startswith("1 resources published no metrics")
