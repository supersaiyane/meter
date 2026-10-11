"""P9's exit criteria, held against the whole demo estate. TASK-P9-011, P9 spec section 13.

Each task's tests prove its rule on the case it plants. These read the estate the demo seeds,
with every collector run in order, so a criterion that holds for the planted case and not for
the rows around it fails here rather than in front of an audience.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from tests.ingest.collectors.test_waste_targets import OVERSIZED, PRESSED
from tests.ingest.collectors.test_waste_volumes import PLANTED as GP2
from tests.scripts.test_seed_demo import DEMO_TENANT, _now, seed_demo

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """The seed bills months into partitions, so this module gives them back. ISS-268."""


@pytest.fixture
def seeded(engine: Engine, settings: Settings) -> Iterator[Engine]:
    seed_demo.seed(engine, settings, _now())
    try:
        yield engine
    finally:
        seed_demo.remove(engine)


def rows(engine: Engine, sql: str) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(sql), {"t": DEMO_TENANT}).mappings()]


def test_every_rightsizing_names_an_offered_target_with_both_prices_and_the_version(
    seeded: Engine,
) -> None:
    """Criterion 2, across every source and every rightsizing the estate produces."""
    found = rows(
        seeded,
        "SELECT r.source, r.resource_id, r.waste_class, r.target_instance_type, "
        "r.current_sku_price_id, r.target_sku_price_id, r.price_version, EXISTS ("
        "  SELECT 1 FROM instance_type_spec s WHERE s.tenant_id = r.tenant_id "
        "  AND s.service_code = 'AmazonEC2' AND s.region = r.region_id "
        "  AND s.instance_type = r.target_instance_type AND s.offered"
        ") AS offered "
        "FROM recommendation r WHERE r.tenant_id = :t "
        "AND r.waste_class IN ('RIGHTSIZE_INSTANCE', 'UPSIZE_INSTANCE')",
    )
    assert {row["source"] for row in found} >= {"METER", "COMPUTE_OPTIMIZER"}
    unnamed = [
        row
        for row in found
        if not (
            row["target_instance_type"]
            and row["current_sku_price_id"]
            and row["target_sku_price_id"]
            and row["price_version"]
            and row["offered"]
        )
    ]
    assert unnamed == []


def test_every_price_carries_its_version_and_both_times_and_none_is_nought(
    seeded: Engine,
) -> None:
    """Criterion 4. The database refuses each of these, migration 0033; this counts them."""
    (counted,) = rows(
        seeded,
        "SELECT count(*) AS prices, "
        "count(*) FILTER (WHERE recurring_unit_price = 0 AND upfront_fee = 0) AS nought, "
        "count(*) FILTER (WHERE collected_at < as_of) AS before_true, "
        "count(DISTINCT version) AS versions "
        "FROM price WHERE tenant_id = :t",
    )
    assert counted["prices"] > 0
    assert (counted["nought"], counted["before_true"]) == (0, 0)
    assert counted["versions"] >= 1


def test_the_three_planted_cases_come_out_as_section_9_says(seeded: Engine) -> None:
    """Criterion 3, in the seeded estate rather than in each collector's own test."""
    found = {
        row["resource_id"]: row
        for row in rows(
            seeded,
            "SELECT resource_id, waste_class, target_instance_type, estimated_monthly_saving, "
            "added_monthly_cost, rationale FROM recommendation "
            "WHERE tenant_id = :t AND source = 'METER'",
        )
    }
    oversized, pressed, volume = found[OVERSIZED], found[PRESSED], found[GP2]
    assert (oversized["waste_class"], oversized["target_instance_type"]) == (
        "RIGHTSIZE_INSTANCE",
        "m5.xlarge",
    )
    assert oversized["estimated_monthly_saving"] > 0
    assert (pressed["waste_class"], pressed["target_instance_type"]) == (
        "UPSIZE_INSTANCE",
        "c6i.4xlarge",
    )
    assert pressed["estimated_monthly_saving"] == 0
    assert pressed["added_monthly_cost"] > 0
    assert volume["waste_class"] == "EBS_GP2_TO_GP3"
    assert volume["rationale"].startswith("Move gp2 to gp3")
