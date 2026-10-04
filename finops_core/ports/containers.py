"""Reading what a cluster is, and what its workloads reserved against what they used.

Defined and implemented in P6. Two methods, because a cluster and a reservation are
read from different places and fail independently: cluster shape comes from the
node and pod metrics, and the reservation comparison needs requests, which only a
cluster with enhanced observability publishes at all.

**Nothing here can resize anything.** Constraint 6. There is no method that writes
into a cluster, the AWS adapter never names one, and a container recommendation is
delivered as a row in P3's table for somebody to act on.

**Absence is a value, not an error.** A cluster without enhanced observability
returns reservations whose requests are None, and those are returned rather than
omitted: a workload nobody can size is the finding the screen exists for, and
dropping it reports a tidier cluster than the one that exists. Likewise OOM status
arrives as `UNOBSERVED` and never as `NOT_KILLED`, because Container Insights does
not reliably report kills and the memory rule has to know the difference.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from finops_core.domain.account import AccountKey
from finops_core.domain.containers import ClusterSlice, ReservationVsUse


@runtime_checkable
class ContainerSource(Protocol):
    """Reads the clusters in an account and region, and what runs on them."""

    def list_clusters(self, account: AccountKey, region: str) -> Iterable[ClusterSlice]:
        """Every cluster, including the ones whose figures cannot be read.

        A cluster the provider names produces one entry whatever can be measured
        about it. `cost` is None where split cost allocation is not enabled, ISS-003,
        and the fleet ratios are None where the node metrics could not be read. None
        and never zero: a cluster costing nothing, or packed at nought percent, are
        both claims nobody measured.

        Raises:
            AccessDenied: The session may not describe clusters in this account.
            NotOptedIn: Container Insights has never been enabled here.
            Throttled: The provider rejected the call rate.
            Unreachable: The metrics endpoint did not answer.
            Misconfigured: This deployment names a cluster the provider cannot find.
            SchemaDrift: A cluster arrived without a name this adapter can use.
        """
        ...

    def reservations(self, account: AccountKey, region: str) -> Iterable[ReservationVsUse]:
        """What each workload asked for against what it used, where either is known.

        One entry per workload, including workloads whose requests are unavailable
        because the cluster has no enhanced observability. Those carry None requests
        rather than zero, and a request of zero beside a positive use is refused by
        the entity, because that pair means the request was unread.

        Raises:
            AccessDenied: The session may not read container metrics here.
            NotOptedIn: Container Insights has never been enabled here.
            Throttled: The provider rejected the call rate.
            Unreachable: The metrics endpoint did not answer.
            Misconfigured: This deployment names a cluster the provider cannot find.
            SchemaDrift: A metric arrived in a shape the adapter cannot read.
        """
        ...
