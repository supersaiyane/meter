"""How one gp2 volume is judged, without a database. TASK-P9-009.

The connection is a stand-in serving one price list version and the fake catalog's four EBS
prices, gp2 at 0.10 and gp3 at 0.08 per GiB a month, IOPS at 0.005 and throughput at 0.04.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.metrics import MetricPoint
from finops_fakes.catalog import VERSION, VOLUMES
from finops_ingest.collectors.catalog_reads import LATEST_VERSION
from finops_ingest.collectors.waste_volumes import VolumeCandidate, hourly_p99, judged
from finops_query.volumes import VolumeDemand

ACCOUNT = "111111111111"


class _Result:
    def __init__(self, rows: list[Any], scalar: object = None) -> None:
        self._rows = rows
        self._scalar = scalar

    def scalar(self) -> object:
        return self._scalar

    def __iter__(self) -> Iterator[Any]:
        return iter(self._rows)


class Catalog:
    """A connection holding one version and the fake catalog's EBS prices."""

    def execute(self, statement: object, _params: dict[str, Any]) -> _Result:
        if statement is LATEST_VERSION:
            return _Result([], scalar=VERSION)
        return _Result(
            [
                SimpleNamespace(volume=volume, pricing_unit=unit, recurring_unit_price=price)
                for volume, _family, _meter, unit, price in VOLUMES
            ]
        )


def gp2(size_gib: int, paid: str) -> VolumeCandidate:
    return VolumeCandidate(
        resource_id="vol-0123",
        account_id=ACCOUNT,
        region_id="us-fake-1",
        observation_days=30,
        monthly_cost=Decimal(paid),
        size_gib=size_gib,
        volume_type="gp2",
    )


QUIET = VolumeDemand(Decimal(19), None)


def test_a_bill_under_list_scales_the_saving_down_and_says_so() -> None:
    found = judged(Catalog(), "tenant", gp2(1000, "50"), QUIET)
    assert found.is_worth_acting_on
    # 15.00 at list, half of it as paid.
    assert found.monthly_saving == Decimal("7.50")
    assert found.reason.endswith("Scaled to the bill, which shows 50 against 100.00 at list")


def test_a_bill_over_list_never_scales_it_up() -> None:
    found = judged(Catalog(), "tenant", gp2(1000, "130"), QUIET)
    assert found.monthly_saving == Decimal("15.00")
    assert "Scaled" not in found.reason


def test_a_saving_under_the_floor_is_refused_with_the_figure() -> None:
    # 100 GiB: 10.00 on gp2 against 8.12 on gp3, which needs 3 MiB/s above the included 125.
    found = judged(Catalog(), "tenant", gp2(100, "10"), QUIET)
    assert not found.is_worth_acting_on
    assert found.reason.endswith("It saves 1.88 a month, under the floor of 5.00")


def test_what_gp3_cannot_give_is_refused_with_the_reason() -> None:
    found = judged(Catalog(), "tenant", gp2(10, "1"), VolumeDemand(Decimal(6000), None))
    assert not found.is_worth_acting_on
    assert found.reason.startswith("No gp3 move: gp3 gives at most 500 IOPS per GiB")


def test_half_a_sum_is_not_a_measurement() -> None:
    at = datetime(2026, 10, 1, tzinfo=UTC)
    point = MetricPoint(
        account_key=AccountKey(provider=Provider.AWS, account_id=ACCOUNT),
        namespace="AWS/EBS",
        metric_name="VolumeReadOps",
        statistic="Sum",
        unit="Count",
        value=Decimal(3600),
        at=at,
        as_of=at,
        collected_at=at,
    )
    assert hourly_p99([(point,), None]) is None
    assert hourly_p99([(), ()]) is None
    assert hourly_p99([(point,), (point,)]) == Decimal(7200)
