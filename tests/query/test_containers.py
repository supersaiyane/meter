"""The two container sizing rules, and the sentence that admits it could not check.

Most of the weight is on one case. A workload whose OOM history nobody could observe
gets the smaller memory margin, which is the decision spec section 5.4 made, and the
recommendation has to say so in words. A test that only checked the number would pass
on a rationale that read exactly like a workload observed and found clean, and that is
the failure this file exists to catch: the plan asks for a test that reads the
rationale, and `test_an_unobserved_kill_is_admitted_in_words` is it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from finops_core.domain.containers import (
    LaunchType,
    OomStatus,
    ReservationVsUse,
    Workload,
)
from finops_core.domain.observation import MINIMUM_HISTORY
from finops_core.domain.waste import WasteClass
from finops_query import waste
from finops_query.containers import (
    ALREADY_FITS,
    CPU_SHARE_OF_COST,
    FARGATE_SIZES,
    KILLED,
    NO_COST,
    NO_REQUEST,
    NO_USE,
    NOT_KILLED,
    UNOBSERVED,
    fargate_monthly_usd,
    fargate_sizes,
    is_orderable,
    needed_memory_mib,
    size,
    size_fargate_task,
    size_workload,
    snap_up,
)

NOW = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)
COST = Decimal("400.00")


def reservation(**overrides: Any) -> ReservationVsUse:
    fields: dict[str, Any] = {
        "workload": Workload(
            cluster_name="platform-eks",
            namespace="ledger",
            name="ledger-api",
            kind="Deployment",
            launch_type=LaunchType.EC2,
        ),
        "cpu_requested_millicores": Decimal(1000),
        "memory_requested_mib": Decimal(2048),
        "cpu_used_p99_millicores": Decimal("190.4"),
        "memory_used_peak_mib": Decimal(400),
        "oom_status": OomStatus.NOT_KILLED,
        "observation_days": 30,
        "as_of": NOW,
        "collected_at": NOW,
    }
    fields.update(overrides)
    return ReservationVsUse(**fields)


# --- the two rules --------------------------------------------------------------


def test_cpu_is_sized_at_its_99th_percentile_rounded_up() -> None:
    """Up, so a recommendation can never ask for less than the rule says is needed."""
    sized = size_workload(reservation=reservation(), monthly_cost=COST)
    assert sized.estimate.is_worth_acting_on
    assert sized.cpu_request_millicores == Decimal(191)


@pytest.mark.parametrize(
    ("status", "margin"),
    [
        (OomStatus.NOT_KILLED, Decimal("1.15")),
        (OomStatus.UNOBSERVED, Decimal("1.15")),
        (OomStatus.KILLED, Decimal("1.25")),
    ],
)
def test_memory_is_sized_at_its_peak_plus_the_margin_its_history_earns(
    status: OomStatus, margin: Decimal
) -> None:
    assert needed_memory_mib(Decimal(400), status) == Decimal(400) * margin


def test_the_margins_are_p3s_rather_than_a_second_copy() -> None:
    """Two copies of fifteen percent is how two screens size one workload differently."""
    assert needed_memory_mib(Decimal(100), OomStatus.NOT_KILLED) == (
        Decimal(100) * waste.MEMORY_HEADROOM
    )
    assert needed_memory_mib(Decimal(100), OomStatus.KILLED) == (
        Decimal(100) * waste.MEMORY_HEADROOM_AFTER_OOM
    )


# --- the sentence ---------------------------------------------------------------


def test_an_unobserved_kill_is_admitted_in_words() -> None:
    """The test the plan asks for. It reads the rationale, not the number.

    Unobserved and not killed produce the same margin, so a test of the number cannot
    tell them apart. Only the sentence can, and only the sentence stops a reader taking
    an unchecked workload for one that was checked and came back clean.
    """
    unobserved = size_workload(
        reservation=reservation(oom_status=OomStatus.UNOBSERVED), monthly_cost=COST
    )
    clean = size_workload(
        reservation=reservation(oom_status=OomStatus.NOT_KILLED), monthly_cost=COST
    )
    # Same margin, so the same requests and the same saving.
    assert unobserved.memory_request_mib == clean.memory_request_mib
    assert unobserved.estimate.monthly_saving == clean.estimate.monthly_saving
    # Different sentences, and that difference is the whole requirement.
    assert UNOBSERVED in unobserved.estimate.reason
    assert "could not be observed" in unobserved.estimate.reason
    assert "could not check" in unobserved.estimate.reason
    assert NOT_KILLED not in unobserved.estimate.reason
    assert NOT_KILLED in clean.estimate.reason
    assert UNOBSERVED not in clean.estimate.reason


def test_a_killed_workload_says_why_its_margin_is_larger() -> None:
    sized = size_workload(reservation=reservation(oom_status=OomStatus.KILLED), monthly_cost=COST)
    assert KILLED in sized.estimate.reason
    assert sized.memory_request_mib == Decimal(500)


def test_the_saving_says_it_is_modelled_and_names_its_assumption() -> None:
    sized = size_workload(reservation=reservation(), monthly_cost=COST)
    assert "modelled" in sized.estimate.reason
    assert "weighting CPU and memory equally" in sized.estimate.reason


# --- the arithmetic -------------------------------------------------------------


def test_the_saving_is_the_released_share_of_the_measured_cost() -> None:
    sized = size_workload(reservation=reservation(), monthly_cost=COST)
    cpu_spare = (Decimal(1000) - Decimal(191)) / Decimal(1000)
    memory_spare = (Decimal(2048) - Decimal(460)) / Decimal(2048)
    released = CPU_SHARE_OF_COST * cpu_spare + (1 - CPU_SHARE_OF_COST) * memory_spare
    assert sized.estimate.monthly_saving == (COST * released).quantize(Decimal("0.01"))


def test_a_request_already_below_its_need_is_kept_not_raised() -> None:
    """Raising a request is a reliability decision, not a waste finding."""
    sized = size_workload(
        reservation=reservation(
            cpu_requested_millicores=Decimal(150),
            memory_requested_mib=Decimal(4096),
        ),
        monthly_cost=COST,
    )
    assert sized.estimate.is_worth_acting_on
    assert sized.cpu_request_millicores == Decimal(150)


def test_it_writes_into_p3s_container_class() -> None:
    sized = size_workload(reservation=reservation(), monthly_cost=COST)
    assert sized.estimate.waste_class is WasteClass.CONTAINER_RIGHTSIZE


# --- the refusals, in order -----------------------------------------------------


def test_below_the_floor_there_is_no_recommendation_rather_than_a_cautious_one() -> None:
    sized = size_workload(
        reservation=reservation(observation_days=MINIMUM_HISTORY - 1), monthly_cost=COST
    )
    assert not sized.estimate.is_worth_acting_on
    assert "floor" in sized.estimate.reason
    assert sized.cpu_request_millicores is None


def test_a_cluster_that_cannot_publish_requests_is_refused_and_says_why() -> None:
    sized = size_workload(
        reservation=reservation(cpu_requested_millicores=None, memory_requested_mib=None),
        monthly_cost=COST,
    )
    assert sized.estimate.reason == NO_REQUEST


def test_no_observed_use_is_refused_rather_than_read_as_zero() -> None:
    sized = size_workload(reservation=reservation(cpu_used_p99_millicores=None), monthly_cost=COST)
    assert sized.estimate.reason == NO_USE


def test_no_attributed_cost_is_refused_and_names_iss_003() -> None:
    """Without a cost there is no saving, and without a saving no severity, ADR-0016."""
    for cost in (None, Decimal(0)):
        sized = size_workload(reservation=reservation(), monthly_cost=cost)
        assert sized.estimate.reason == NO_COST
        assert "ISS-003" in sized.estimate.reason


def test_a_workload_already_sized_right_is_refused() -> None:
    sized = size_workload(
        reservation=reservation(
            cpu_requested_millicores=Decimal(191),
            memory_requested_mib=Decimal(460),
        ),
        monthly_cost=COST,
    )
    assert sized.estimate.reason == ALREADY_FITS


def test_a_saving_under_the_floor_is_refused() -> None:
    sized = size_workload(reservation=reservation(), monthly_cost=Decimal("6.00"))
    assert not sized.estimate.is_worth_acting_on
    assert str(waste.FLOOR_USD) in sized.estimate.reason


def test_a_refusal_recommends_no_requests_at_all() -> None:
    """Not the current ones. A refusal is not advice to leave things as they are."""
    sized = size_workload(reservation=reservation(), monthly_cost=None)
    assert sized.cpu_request_millicores is None
    assert sized.memory_request_mib is None


# --- Fargate, TASK-P6-008 -------------------------------------------------------


def fargate(**overrides: Any) -> ReservationVsUse:
    fields: dict[str, Any] = {
        "workload": Workload(
            cluster_name="product-ecs",
            namespace="default",
            name="statements-renderer",
            kind="Service",
            launch_type=LaunchType.FARGATE,
        ),
        "cpu_requested_millicores": Decimal(4000),
        "memory_requested_mib": Decimal(16384),
        "cpu_used_p99_millicores": Decimal(600),
        "memory_used_peak_mib": Decimal(1700),
        "oom_status": OomStatus.UNOBSERVED,
        "observation_days": 30,
        "as_of": NOW,
        "collected_at": NOW,
    }
    fields.update(overrides)
    return ReservationVsUse(**fields)


def test_the_matrix_is_a_table_with_the_documented_rows() -> None:
    """Spot checked against the published table rather than restated as a rule."""
    rows = dict(FARGATE_SIZES)
    assert rows[250] == (512, 1024, 2048)
    assert rows[500] == (1024, 2048, 3072, 4096)
    assert rows[4000][0] == 8192 and rows[4000][-1] == 30720
    assert rows[16000][0] == 32768 and rows[16000][-1] == 122880
    for memories in rows.values():
        assert list(memories) == sorted(set(memories))


def test_snapping_is_always_up_and_never_to_the_nearer_size_below() -> None:
    """The criterion's own test: a size that would snap down if it snapped to nearest.

    1100 millicores is nearer 1000 than 2000. 1000 is the size that throttles it.
    """
    cpu, memory = snap_up(Decimal(1100), Decimal(2048))
    assert cpu == Decimal(2000), "snapped to the nearer, smaller size"
    assert cpu >= Decimal(1100) and memory >= Decimal(2048)


def test_every_need_snaps_to_a_size_that_holds_it() -> None:
    for cpu_need in range(1, 16001, 397):
        for memory_need in range(1, 122881, 6151):
            try:
                cpu, memory = snap_up(Decimal(cpu_need), Decimal(memory_need))
            except ValueError:
                continue
            assert cpu >= cpu_need and memory >= memory_need
            assert is_orderable(cpu, memory)


def test_a_need_larger_than_anything_sold_is_refused_not_shrunk() -> None:
    with pytest.raises(ValueError, match="no Fargate size"):
        snap_up(Decimal(16001), Decimal(1024))


def test_every_recommendation_is_an_orderable_combination() -> None:
    sized = size_fargate_task(reservation=fargate())
    assert sized.estimate.is_worth_acting_on
    assert sized.cpu_request_millicores is not None
    assert sized.memory_request_mib is not None
    assert is_orderable(sized.cpu_request_millicores, sized.memory_request_mib)


def test_the_saving_is_from_the_snapped_size_not_the_ideal_one() -> None:
    """The ideal size would show a larger saving that nobody can order."""
    sized = size_fargate_task(reservation=fargate())
    assert sized.cpu_request_millicores is not None
    assert sized.memory_request_mib is not None
    current = fargate_monthly_usd(Decimal(4000), Decimal(16384))
    snapped = fargate_monthly_usd(sized.cpu_request_millicores, sized.memory_request_mib)
    ideal = fargate_monthly_usd(
        Decimal(600), needed_memory_mib(Decimal(1700), OomStatus.UNOBSERVED)
    )
    assert sized.estimate.monthly_saving == (current - snapped).quantize(Decimal("0.01"))
    assert sized.estimate.monthly_saving < (current - ideal).quantize(Decimal("0.01"))
    assert "rather than from the ideal one" in sized.estimate.reason


def test_a_task_already_at_the_smallest_size_that_holds_it_is_refused() -> None:
    sized = size_fargate_task(
        reservation=fargate(
            cpu_requested_millicores=Decimal(2000),
            memory_requested_mib=Decimal(4096),
            cpu_used_p99_millicores=Decimal(1900),
            memory_used_peak_mib=Decimal(3400),
        )
    )
    assert sized.estimate.reason == ALREADY_FITS


def test_the_fargate_rationale_says_it_is_modelled_and_per_task() -> None:
    reason = size_fargate_task(reservation=fargate()).estimate.reason
    assert "Modelled from Fargate's published rate" in reason
    assert "per task" in reason
    assert UNOBSERVED in reason


def test_the_dispatcher_picks_the_rule_from_the_launch_type() -> None:
    """A Fargate task needs no measured cost, and an EC2 workload refuses without one."""
    assert size(reservation=fargate(), monthly_cost=None).estimate.is_worth_acting_on
    assert size(reservation=reservation(), monthly_cost=None).estimate.reason == NO_COST


def test_every_orderable_size_is_priced_by_the_published_rates() -> None:
    assert len(fargate_sizes()) == sum(len(memories) for _, memories in FARGATE_SIZES)
    assert fargate_monthly_usd(Decimal(1000), Decimal(1024)) > 0
