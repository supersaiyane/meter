"""The three container entities, and the four things they refuse to say.

Most of this file is about absence. A request that could not be read, a use that was
never published, and an OOM check that never happened are three different unknowns,
and each has an obvious wrong answer that would make a screen look complete: zero,
zero, and false. Every test below is one of those wrong answers being refused.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from finops_core.domain.containers import (
    ClusterSlice,
    LaunchType,
    OomStatus,
    ReservationVsUse,
    Workload,
)
from finops_core.domain.fact import Fact
from finops_core.domain.observation import MINIMUM_HISTORY

NOW = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)


def workload(**overrides: Any) -> Workload:
    fields: dict[str, Any] = {
        "cluster_name": "platform-eks",
        "namespace": "ledger",
        "name": "ledger-api",
        "kind": "Deployment",
        "launch_type": LaunchType.EC2,
    }
    fields.update(overrides)
    return Workload(**fields)


def reservation(**overrides: Any) -> ReservationVsUse:
    fields: dict[str, Any] = {
        "workload": workload(),
        "cpu_requested_millicores": Decimal(1000),
        "memory_requested_mib": Decimal(2048),
        "cpu_used_p99_millicores": Decimal(190),
        "memory_used_peak_mib": Decimal(400),
        "oom_status": OomStatus.NOT_KILLED,
        "observation_days": 30,
        "as_of": NOW,
        "collected_at": NOW,
    }
    fields.update(overrides)
    return ReservationVsUse(**fields)


def cluster(**overrides: Any) -> ClusterSlice:
    fields: dict[str, Any] = {
        "cluster_name": "platform-eks",
        "account_id": "fake-platform-a",
        "region_id": "eu-west-1",
        "platform": "EKS",
        "enhanced_observability": True,
        "as_of": NOW,
        "collected_at": NOW,
    }
    fields.update(overrides)
    return ClusterSlice(**fields)


# --- the three OOM states ------------------------------------------------------


def test_oom_status_has_exactly_three_members() -> None:
    """A fourth would be a state no collector can produce."""
    assert {member.value for member in OomStatus} == {"KILLED", "NOT_KILLED", "UNOBSERVED"}


@pytest.mark.parametrize(
    ("reading", "expected"),
    [(True, OomStatus.KILLED), (False, OomStatus.NOT_KILLED), (None, OomStatus.UNOBSERVED)],
)
def test_a_nullable_reading_maps_to_the_three_states(
    reading: bool | None, expected: OomStatus
) -> None:
    """The column and the fake both hold a nullable boolean. This is the one mapping."""
    assert OomStatus.from_observation(reading) is expected


def test_unobserved_is_not_a_synonym_for_not_killed() -> None:
    """The whole reason this is an enum rather than a nullable boolean.

    Container Insights does not reliably report OOM events, so unobserved is a
    common reading. Treating it as not killed applies the smaller memory margin to
    exactly the workloads that may have been killed for running out of memory, which
    is the substitution spec section 5.4 forbids.
    """
    assert len({OomStatus.UNOBSERVED, OomStatus.NOT_KILLED, OomStatus.KILLED}) == 3
    assert OomStatus.UNOBSERVED.was_checked is False
    assert OomStatus.NOT_KILLED.was_checked is True
    assert OomStatus.KILLED.was_checked is True


def test_no_oom_state_is_falsy_so_a_truthiness_test_cannot_quietly_pass() -> None:
    """A nullable boolean makes unobserved falsy, and that is the whole bug.

    This asserts the property the enum was chosen for: `if status:` cannot silently
    sort unobserved in with not killed, because every member is truthy and the
    comparison has to be written out in full.
    """
    assert all(bool(member) for member in OomStatus)


# --- absence, several times ----------------------------------------------------


def test_a_reservation_with_no_observed_use_has_no_efficiency_figure() -> None:
    """Not an efficiency of zero, which reads as a workload wasting everything."""
    without_use = reservation(cpu_used_p99_millicores=None, memory_used_peak_mib=None)
    assert without_use.cpu_efficiency is None
    assert without_use.memory_efficiency is None


def test_a_cluster_that_cannot_report_requests_has_no_efficiency_figure() -> None:
    """A cluster without enhanced observability publishes usage and no request."""
    unreadable = reservation(cpu_requested_millicores=None, memory_requested_mib=None)
    assert unreadable.has_requests is False
    assert unreadable.cpu_efficiency is None
    assert unreadable.memory_efficiency is None


def test_a_request_of_zero_yields_no_efficiency_rather_than_dividing_by_it() -> None:
    zeroed = reservation(
        cpu_requested_millicores=Decimal(0),
        memory_requested_mib=Decimal(0),
        cpu_used_p99_millicores=None,
        memory_used_peak_mib=None,
    )
    assert zeroed.cpu_efficiency is None
    assert zeroed.memory_efficiency is None


def test_efficiency_is_computed_where_both_sides_are_known() -> None:
    """The positive case, so the tests above cannot all be passing on a stub."""
    assert reservation().cpu_efficiency == Decimal(190) / Decimal(1000)
    assert reservation().memory_efficiency == Decimal(400) / Decimal(2048)


def test_a_cluster_without_split_cost_data_has_no_cost_rather_than_a_cost_of_zero() -> None:
    """ISS-003. A cluster costing nothing is a claim nobody measured."""
    unsplit = cluster(cost=None, unmeasurable_reason="split cost allocation is not enabled")
    assert unsplit.cost is None
    assert unsplit.is_cost_measured is False
    assert cluster(cost=Decimal("12.50")).is_cost_measured is True


def test_a_fleet_that_could_not_be_read_has_no_ratios() -> None:
    unread = cluster(node_count=None, spot_ratio=None, packing_efficiency=None)
    assert unread.node_count is None
    assert unread.spot_ratio is None
    assert unread.packing_efficiency is None


# --- the 14 day floor ----------------------------------------------------------


def test_below_the_floor_no_recommendation_can_be_constructed() -> None:
    assert reservation(observation_days=MINIMUM_HISTORY - 1).supports_recommendation is False
    assert reservation(observation_days=MINIMUM_HISTORY).supports_recommendation is True


def test_the_fake_estate_floor_agrees_with_the_real_constant() -> None:
    """The test `finops_fakes/estate_shape.py` has been promising since P3.

    Its comment says the real constant is `MINIMUM_HISTORY` and that a test asserts
    the two agree once that constant exists. It exists, and this is that test. Two
    definitions of 14 is how they come to disagree.
    """
    from finops_fakes.estate_shape import MINIMUM_HISTORY_DAYS

    assert MINIMUM_HISTORY_DAYS == MINIMUM_HISTORY


def test_enough_history_is_not_enough_on_its_own() -> None:
    """All three conditions are necessary, so none can be dropped unnoticed.

    Ninety days of history with nothing to compare is still nothing to compare.
    """
    for absent in (
        "cpu_requested_millicores",
        "memory_requested_mib",
        "cpu_used_p99_millicores",
        "memory_used_peak_mib",
    ):
        sized = reservation(observation_days=90, **{absent: None})
        assert sized.supports_recommendation is False, absent


# --- the invariants ------------------------------------------------------------


def test_a_zero_request_cannot_sit_beside_a_positive_use() -> None:
    """That pair means the request was unread, which is None rather than zero.

    The same invariant is a check constraint on `container_usage`, and the
    duplication is deliberate per constraint 11: the database stops the bad row and
    this stops the bad object, so the failure arrives at the line that caused it.
    """
    with pytest.raises(ValueError, match="unread"):
        reservation(cpu_requested_millicores=Decimal(0), cpu_used_p99_millicores=Decimal(500))
    with pytest.raises(ValueError, match="unread"):
        reservation(memory_requested_mib=Decimal(0), memory_used_peak_mib=Decimal(128))


def test_a_float_quantity_is_refused() -> None:
    """A request compared against a use decides money, so it is Decimal."""
    with pytest.raises(TypeError, match="float"):
        reservation(cpu_requested_millicores=1000.0)


def test_a_negative_quantity_is_refused() -> None:
    with pytest.raises(ValueError, match="not a quantity"):
        reservation(memory_used_peak_mib=Decimal(-1))


def test_negative_observation_days_are_refused() -> None:
    with pytest.raises(ValueError, match="observation_days"):
        reservation(observation_days=-1)


def test_a_ratio_outside_zero_to_one_is_refused() -> None:
    """Two figures measured over different periods produce exactly this."""
    with pytest.raises(ValueError, match="fraction of one"):
        cluster(spot_ratio=Decimal("1.4"))
    with pytest.raises(ValueError, match="fraction of one"):
        cluster(packing_efficiency=Decimal("-0.1"))


def test_a_negative_cluster_cost_is_refused() -> None:
    with pytest.raises(ValueError, match="credit landing on the wrong grain"):
        cluster(cost=Decimal(-5))


def test_a_float_cluster_cost_is_refused() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        cluster(cost=12.5)


def test_a_workload_missing_part_of_its_name_is_refused() -> None:
    """It could not be joined to its cost, so it would appear as an orphan row."""
    for field in ("cluster_name", "namespace", "name", "kind"):
        with pytest.raises(ValueError, match=field):
            workload(**{field: "  "})


# --- shape ---------------------------------------------------------------------


def test_the_two_measured_entities_are_facts_and_the_identity_is_not() -> None:
    """Constraint 10. A measurement carries both timestamps; an identity does not.

    `Workload` is left off deliberately, the way `IngestRun` is: giving an identity
    timestamps invites two copies of one workload differing only in when somebody
    happened to read it.
    """
    assert issubclass(ClusterSlice, Fact)
    assert issubclass(ReservationVsUse, Fact)
    assert not issubclass(Workload, Fact)


def test_every_container_entity_is_frozen() -> None:
    with pytest.raises(Exception, match=r"frozen|read-only|cannot assign"):
        reservation().observation_days = 1  # type: ignore[misc]


def test_the_workload_key_matches_the_shape_the_fake_emits() -> None:
    """A different shape here would silently fail to join against seeded rows."""
    assert workload().key == "container/platform-eks/ledger/ledger-api"


def test_both_launch_types_exist_because_they_are_resized_differently() -> None:
    assert {member.value for member in LaunchType} == {"EC2", "FARGATE"}
