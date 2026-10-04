"""The `ContainerSource` sentences, held to the fake and the AWS adapter alike.

Five requirements, and every one is about absence, because absence is where the
two implementations are most likely to drift apart and the drift is silent in
both:

1. Every cluster the provider names comes back, measurable or not.
2. A cluster without enhanced observability returns usage and **no request**. Never
   a request of zero, which would make a workload look infinitely wasteful and sort
   it to the top of the screen that exists to find real waste.
3. A request of zero beside a positive use is impossible, because that pair means
   the request was unread.
4. OOM status is never `NOT_KILLED` from a real read. Container Insights does not
   reliably publish kills, so the only honest answers are killed and unobserved.
5. A cluster the deployment names and the provider cannot find is `Misconfigured`,
   not `SchemaDrift`: the first says the operator is wrong and the second says we
   are.

These belong in a contract rather than in one adapter's tests because the failure
they prevent, a zero standing in for an unknown, reads identically whichever
implementation produced it.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest

from finops_core.domain.containers import ClusterSlice, OomStatus, ReservationVsUse
from finops_core.ports.containers import ContainerSource
from tests.contract.conftest import CONTAINER_SOURCE, ProviderUnderTest

Requires = Callable[[str], None]


def test_the_source_satisfies_the_port(subject: ProviderUnderTest, requires_port: Requires) -> None:
    requires_port(CONTAINER_SOURCE)
    assert isinstance(subject.provider, ContainerSource)


def test_every_cluster_comes_back_whatever_can_be_measured_about_it(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    requires_port(CONTAINER_SOURCE)
    clusters = tuple(subject.provider.list_clusters(subject.known_account, subject.region))

    assert clusters, "no cluster at all, so nothing below proves anything"
    for cluster in clusters:
        assert isinstance(cluster, ClusterSlice)
        assert cluster.cluster_name
        # A cost here would be this source inventing money. Cost is the bill's
        # answer, and a metrics source that guessed one would put a modelled
        # figure on a screen that says measured.
        assert cluster.cost is None


def test_a_cluster_without_enhanced_observability_says_why(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    requires_port(CONTAINER_SOURCE)
    for cluster in subject.provider.list_clusters(subject.known_account, subject.region):
        if cluster.enhanced_observability:
            continue
        stated = (cluster.unmeasurable_reason or "").strip()
        assert len(stated) > 20, (
            f"{cluster.cluster_name} cannot report requests and does not say why. A "
            f"blank reason teaches a reader that the explanations here are empty."
        )


def test_a_request_that_could_not_be_read_is_absent_and_never_zero(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """The requirement the whole sub project turns on."""
    requires_port(CONTAINER_SOURCE)
    unreadable = {
        cluster.cluster_name
        for cluster in subject.provider.list_clusters(subject.known_account, subject.region)
        if not cluster.enhanced_observability
    }
    reservations = tuple(subject.provider.reservations(subject.known_account, subject.region))
    assert reservations, "no reservations, so nothing below proves anything"

    if not unreadable:
        # Whether one account holds a cluster of each kind is a property of an
        # estate rather than of this port. The fake's unreadable cluster lives in
        # another account, and `tests/providers/fake/test_utilization_estates.py`
        # asserts the same requirement against it directly. Skipped loudly rather
        # than passed vacuously, which would read as the case being covered.
        pytest.skip("no cluster in this slice is unable to report requests")

    seen = 0
    for reservation in reservations:
        assert isinstance(reservation, ReservationVsUse)
        if reservation.workload.cluster_name not in unreadable:
            continue
        seen += 1
        assert reservation.cpu_requested_millicores is None
        assert reservation.memory_requested_mib is None
        assert reservation.has_requests is False
        # And the consequence a screen depends on: no efficiency figure at all,
        # rather than an efficiency of zero.
        assert reservation.cpu_efficiency is None
        assert reservation.memory_efficiency is None
    assert seen, "no workload on an unreadable cluster, so this asserted nothing"


def test_a_zero_request_never_sits_beside_a_positive_use(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    requires_port(CONTAINER_SOURCE)
    for reservation in subject.provider.reservations(subject.known_account, subject.region):
        if reservation.cpu_requested_millicores == Decimal(0):
            assert not (reservation.cpu_used_p99_millicores or Decimal(0)) > 0
        if reservation.memory_requested_mib == Decimal(0):
            assert not (reservation.memory_used_peak_mib or Decimal(0)) > 0


def test_an_unobserved_oom_is_never_reported_as_not_killed(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """Container Insights does not reliably publish kills.

    So a reading of not killed can only come from somewhere that actually looked.
    A provider returning it for a cluster whose kills it cannot see would send the
    smaller memory margin to exactly the workloads that needed the larger one.
    """
    requires_port(CONTAINER_SOURCE)
    unreadable = {
        cluster.cluster_name
        for cluster in subject.provider.list_clusters(subject.known_account, subject.region)
        if not cluster.enhanced_observability
    }
    for reservation in subject.provider.reservations(subject.known_account, subject.region):
        if reservation.workload.cluster_name in unreadable:
            assert reservation.oom_status is OomStatus.UNOBSERVED
            assert reservation.oom_status.was_checked is False


def test_every_reservation_carries_both_timestamps(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """Constraint 10. `as_of` is never later than `collected_at`."""
    requires_port(CONTAINER_SOURCE)
    for reservation in subject.provider.reservations(subject.known_account, subject.region):
        assert reservation.as_of <= reservation.collected_at
    for cluster in subject.provider.list_clusters(subject.known_account, subject.region):
        assert cluster.as_of <= cluster.collected_at
