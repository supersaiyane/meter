"""The sizing arithmetic, against lists.

No database and no fixture, which is what lets each decision be tested by the
situation it stands for rather than by a seeded estate.

The tests that matter most are the ones asserting a **refusal**. A detector that
finds waste everywhere is worthless, and every false positive here has a name: the
burstable instance running on credits, the batch worker idle for most of a
fortnight, the workload whose OOM history nobody could read.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from finops_core.domain.observation import MINIMUM_HISTORY
from finops_core.domain.waste import WasteClass
from finops_query.waste import (
    CPU_HEADROOM,
    MEMORY_HEADROOM,
    MEMORY_HEADROOM_AFTER_OOM,
    idle,
    memory_headroom,
    rightsize_cpu,
    rightsize_memory,
    whole_cost,
)

#: Hourly, which is what the collectors read and what makes a percentile mean
#: anything. Fourteen days is 336 points; a month is 720. The first version of this
#: file used 30 points and the spike test failed, because p99 of 31 samples is the
#: second largest one and the rule had quietly become "use the max".
HOURS_IN_A_MONTH = 720
STEADY_LOW = [Decimal("8")] * HOURS_IN_A_MONTH
COST = Decimal("400.00")


class TestPercentileNotMaximum:
    def test_one_spike_does_not_size_the_instance(self) -> None:
        """The decision this function exists for.

        A machine at 8 percent that touched 100 once is not a machine that needs to
        be that size. The maximum is what it needed on its worst second.

        Over 720 hourly points one spike moves p99 by nothing. Over 30 it moves it
        to the spike, which is how the first version of this test failed and how
        the granularity requirement got written down.
        """
        with_spike = [*STEADY_LOW, Decimal("100")]
        found = rightsize_cpu(
            utilization_percent=with_spike, observation_days=30, monthly_cost=COST
        )
        assert found.is_worth_acting_on
        assert found.monthly_saving > Decimal("200")

    def test_a_genuinely_busy_instance_is_left_alone(self) -> None:
        busy = [Decimal("85")] * HOURS_IN_A_MONTH
        found = rightsize_cpu(utilization_percent=busy, observation_days=30, monthly_cost=COST)
        assert not found.is_worth_acting_on
        assert "no room to shrink" in found.reason

    def test_headroom_is_left_above_the_percentile(self) -> None:
        # Sizing to exactly the observed p99 gets reversed within a month, the
        # first week the workload gets busier.
        found = rightsize_cpu(
            utilization_percent=STEADY_LOW, observation_days=30, monthly_cost=COST
        )
        implied = COST - found.monthly_saving
        assert implied > COST * Decimal("8") / Decimal("100")
        assert str(int((CPU_HEADROOM - 1) * 100)) in found.reason


class TestTheBurstableFalsePositive:
    def test_a_healthy_credit_balance_is_not_waste(self) -> None:
        """The most common false positive in this whole category.

        A t class instance at 20 percent with credits in the bank is correctly
        sized. Recommending it down is what teaches a platform team to distrust
        the screen.
        """
        found = rightsize_cpu(
            utilization_percent=[Decimal("20")] * HOURS_IN_A_MONTH,
            observation_days=30,
            monthly_cost=COST,
            credit_balance=Decimal("144"),
        )
        assert not found.is_worth_acting_on
        assert "burstable" in found.reason

    def test_an_exhausted_credit_balance_is_still_judged(self) -> None:
        # Credits near zero means the instance is running on its baseline, and its
        # utilization says what it usually says.
        found = rightsize_cpu(
            utilization_percent=STEADY_LOW,
            observation_days=30,
            monthly_cost=COST,
            credit_balance=Decimal("0"),
        )
        assert found.is_worth_acting_on

    def test_an_instance_with_no_credits_at_all_is_judged(self) -> None:
        found = rightsize_cpu(
            utilization_percent=STEADY_LOW,
            observation_days=30,
            monthly_cost=COST,
            credit_balance=None,
        )
        assert found.is_worth_acting_on


class TestIdle:
    def test_a_batch_worker_is_not_idle(self) -> None:
        """Idle for 95 percent of a fortnight and busy for the rest is a batch
        worker. The mean would call it idle; p95 does not."""
        batch = [Decimal("0")] * (HOURS_IN_A_MONTH - 40) + [Decimal("90")] * 40
        found = idle(utilization_percent=batch, observation_days=30, monthly_cost=COST)
        assert not found.is_worth_acting_on

    def test_genuinely_nothing_is_idle(self) -> None:
        found = idle(
            utilization_percent=[Decimal("0.1")] * HOURS_IN_A_MONTH,
            observation_days=30,
            monthly_cost=COST,
        )
        assert found.is_worth_acting_on
        assert found.monthly_saving == COST

    def test_no_observation_is_not_idle(self) -> None:
        # The most expensive possible instance of rendering a failure as zero. A
        # collector that read nothing and concluded idle recommends terminating a
        # running system.
        found = idle(utilization_percent=[], observation_days=30, monthly_cost=COST)
        assert not found.is_worth_acting_on
        assert "not the same as none used" in found.reason


class TestMemoryIsNotCpu:
    @pytest.mark.parametrize(
        ("oom", "expected"),
        [
            (True, MEMORY_HEADROOM_AFTER_OOM),
            (False, MEMORY_HEADROOM),
            (None, MEMORY_HEADROOM),
        ],
    )
    def test_the_margin_depends_on_whether_it_was_killed(
        self, oom: bool | None, expected: Decimal
    ) -> None:
        assert memory_headroom(was_oom_killed=oom) == expected

    def test_an_unknown_oom_status_says_so_rather_than_assuming(self) -> None:
        """The margin is the smaller one either way. The difference is that the
        reader is told it is because nobody could look, not because nobody was
        killed.

        This sentence is what makes the no agent decision reversible with
        evidence: the affected recommendations are the ones that say so.
        """
        found = rightsize_memory(
            peak_bytes=Decimal("1000"),
            requested_bytes=Decimal("4000"),
            observation_days=30,
            monthly_cost=COST,
            was_oom_killed=None,
        )
        assert found.is_worth_acting_on
        assert "could not be observed" in found.reason

    def test_a_killed_workload_gets_the_larger_margin(self) -> None:
        killed = rightsize_memory(
            peak_bytes=Decimal("1000"),
            requested_bytes=Decimal("4000"),
            observation_days=30,
            monthly_cost=COST,
            was_oom_killed=True,
        )
        safe = rightsize_memory(
            peak_bytes=Decimal("1000"),
            requested_bytes=Decimal("4000"),
            observation_days=30,
            monthly_cost=COST,
            was_oom_killed=False,
        )
        assert killed.monthly_saving < safe.monthly_saving

    def test_a_request_of_zero_is_unread_not_zero(self) -> None:
        found = rightsize_memory(
            peak_bytes=Decimal("1000"),
            requested_bytes=Decimal("0"),
            observation_days=30,
            monthly_cost=COST,
            was_oom_killed=False,
        )
        assert not found.is_worth_acting_on
        assert "not a request of zero" in found.reason


class TestTheFloors:
    @pytest.mark.parametrize(
        "call",
        [
            lambda: rightsize_cpu(
                utilization_percent=STEADY_LOW,
                observation_days=MINIMUM_HISTORY - 1,
                monthly_cost=COST,
            ),
            lambda: idle(
                utilization_percent=[Decimal("0")] * HOURS_IN_A_MONTH,
                observation_days=MINIMUM_HISTORY - 1,
                monthly_cost=COST,
            ),
            lambda: whole_cost(
                waste_class=WasteClass.EBS_UNATTACHED,
                monthly_cost=COST,
                observation_days=MINIMUM_HISTORY - 1,
                detail="unattached",
            ),
        ],
    )
    def test_under_the_day_floor_nothing_is_recommended(self, call: object) -> None:
        found = call()  # type: ignore[operator]
        assert not found.is_worth_acting_on
        assert "floor" in found.reason

    def test_a_saving_under_the_dollar_floor_is_not_a_row(self) -> None:
        # A screen filled with rounding is a screen nobody reads.
        found = rightsize_cpu(
            utilization_percent=STEADY_LOW, observation_days=30, monthly_cost=Decimal("3.00")
        )
        assert not found.is_worth_acting_on


class TestEveryEstimateShowsItsWorking:
    def test_a_finding_carries_a_sentence(self) -> None:
        found = whole_cost(
            waste_class=WasteClass.ELASTIC_IP_UNASSOCIATED,
            monthly_cost=Decimal("40.00"),
            observation_days=30,
            detail="unassociated",
        )
        assert found.is_worth_acting_on
        assert "30 days" in found.reason

    def test_a_refusal_carries_one_too(self) -> None:
        # A caller often needs to know a resource was examined and cleared, which
        # is a different fact from one never examined.
        found = idle(
            utilization_percent=[Decimal("50")] * HOURS_IN_A_MONTH,
            observation_days=30,
            monthly_cost=COST,
        )
        assert not found.is_worth_acting_on
        assert found.reason


class TestItHasNoDependencies:
    def test_the_module_imports_no_database_clock_or_provider(self) -> None:
        # The property that lets every test above be a list rather than a fixture.
        source = __import__("pathlib").Path("finops_query/waste.py").read_text(encoding="utf-8")
        for forbidden in ("sqlalchemy", "boto3", "datetime.now", "import requests"):
            assert forbidden not in source
