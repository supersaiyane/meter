"""gp2 priced as the gp3 that does the same work, held to the EBS guide. TASK-P9-009.

The prices are the spec's eu-west-2 example, gp2 at 0.116 and gp3 at 0.0928 per GiB a month and
throughput at 0.0464 per MiB/s a month; the IOPS price is invented, because the example needs none.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from finops_query.volumes import (
    Gp3,
    VolumeDemand,
    VolumePrices,
    gp2_iops,
    gp2_mibps,
    gp3_for,
    working,
)

EU_WEST_2 = VolumePrices(
    gp2_gib_month=Decimal("0.116"),
    gp3_gib_month=Decimal("0.0928"),
    gp3_iops_month=Decimal("0.006"),
    gp3_mibps_month=Decimal("0.0464"),
)


def test_the_spec_example_saves_17_40_a_month() -> None:
    found = gp3_for(1000, VolumeDemand(mibps_p99=Decimal(250)), EU_WEST_2)
    assert isinstance(found, Gp3)
    assert (found.iops, found.mibps) == (3000, 250)
    assert found.gp2_monthly == Decimal("116.00")
    assert found.gp3_monthly == Decimal("98.60")
    assert found.saving == Decimal("17.40")


@pytest.mark.parametrize(
    ("size", "iops"), [(1, 100), (33, 100), (34, 102), (1000, 3000), (5334, 16000), (9000, 16000)]
)
def test_gp2_iops_are_3_per_gib_between_100_and_16_000(size: int, iops: int) -> None:
    assert gp2_iops(size) == iops


@pytest.mark.parametrize(("size", "mibps"), [(1, 128), (170, 128), (171, 250), (1000, 250)])
def test_gp2_throughput_is_128_to_170_gib_and_250_above(size: int, mibps: int) -> None:
    assert gp2_mibps(size) == mibps


def test_a_gp2_baseline_above_what_gp3_includes_is_provisioned_and_paid_for() -> None:
    found = gp3_for(2000, VolumeDemand(Decimal(10), Decimal(10)), EU_WEST_2)
    assert isinstance(found, Gp3)
    # 6,000 IOPS, 3,000 of them above the included, at 0.006; 125 MiB/s above at 0.0464.
    assert (found.iops, found.mibps) == (6000, 250)
    assert found.gp3_monthly == Decimal("209.40")
    assert found.gp2_monthly == Decimal("232.00")
    assert found.notes == ()


def test_a_p99_above_what_gp2_gives_is_provisioned() -> None:
    found = gp3_for(1000, VolumeDemand(Decimal("3999.2"), Decimal(10)), EU_WEST_2)
    assert isinstance(found, Gp3)
    assert found.iops == 4000
    assert found.gp3_monthly == Decimal("104.60")


def test_throughput_above_750_needs_iops_of_its_own() -> None:
    dear_gp2 = VolumePrices(Decimal("0.30"), Decimal("0.0928"), Decimal("0.006"), Decimal("0.0464"))
    found = gp3_for(1000, VolumeDemand(Decimal(10), Decimal(1000)), dear_gp2)
    assert isinstance(found, Gp3)
    assert (found.iops, found.mibps) == (4000, 1000)


def test_a_figure_not_measured_is_taken_at_what_gp2_gives_and_said() -> None:
    found = gp3_for(1000, VolumeDemand(iops_p99=Decimal(19)), EU_WEST_2)
    assert isinstance(found, Gp3)
    assert (found.iops, found.mibps) == (3000, 250)
    assert found.notes == ("throughput was not measured, so gp3 is given gp2's 250 MiB/s",)
    both = gp3_for(1000, VolumeDemand(), EU_WEST_2)
    assert isinstance(both, Gp3)
    assert both.notes[0] == "IOPS were not measured, so gp3 is given gp2's 3,000"


@pytest.mark.parametrize(
    ("size", "demand", "says"),
    [
        (0, VolumeDemand(), "size is not known"),
        (1000, VolumeDemand(Decimal(10), Decimal(2500)), "at most 2,000 MiB/s and 2,500"),
        (1000, VolumeDemand(Decimal(90000), Decimal(10)), "at most 80,000 IOPS and 90,000"),
        (10, VolumeDemand(Decimal(6000), Decimal(10)), "500 IOPS per GiB, 5,000 at 10 GiB"),
    ],
)
def test_what_gp3_cannot_give_is_a_sentence_saying_why(
    size: int, demand: VolumeDemand, says: str
) -> None:
    found = gp3_for(size, demand, EU_WEST_2)
    assert isinstance(found, str)
    assert says in found


def test_a_gp3_that_costs_no_less_is_not_offered() -> None:
    dear = VolumePrices(Decimal("0.10"), Decimal("0.10"), Decimal("0.005"), Decimal("0.04"))
    found = gp3_for(1000, VolumeDemand(Decimal(10), Decimal(250)), dear)
    assert isinstance(found, str)
    assert found == (
        "gp3 at 3,000 IOPS and 250 MiB/s costs 105.00 a month, no less than gp2's 100.00"
    )


def test_the_working_states_every_term_of_the_sum() -> None:
    found = gp3_for(2000, VolumeDemand(Decimal(10), Decimal(300)), EU_WEST_2)
    assert isinstance(found, Gp3)
    assert working(found) == (
        "Move gp2 to gp3 at 6,000 IOPS and 300 MiB/s: 2,000 GiB at 0.0928, "
        "3,000 IOPS above the included 3,000 at 0.006, "
        "175 MiB/s above the included 125 at 0.0464, "
        "211.72 a month against 232.00 on gp2 at 0.116 per GiB"
    )


def test_the_working_writes_prices_as_written_not_as_a_column_pads_them() -> None:
    padded = VolumePrices(
        Decimal("10.0000000000"),
        Decimal("0.0800000000"),
        Decimal("0.0050000000"),
        Decimal("0.0400000000"),
    )
    found = gp3_for(1000, VolumeDemand(Decimal(10), Decimal(250)), padded)
    assert isinstance(found, Gp3)
    said = working(found)
    assert "1,000 GiB at 0.08, 125 MiB/s above the included 125 at 0.04" in said
    assert said.endswith("on gp2 at 10 per GiB")
