"""Containers: what a cluster reserves, what it actually uses, and what it costs.

Three entities. `Workload` is the grain every container figure is reported at,
`ClusterSlice` is one cluster's cost and fleet shape, and `ReservationVsUse` is the
comparison the whole sub project exists to make.

**OOM status is an enum of three members, not a nullable boolean.** The plan asks for
a three state value because killed, not killed and unobserved are three different
facts. `bool | None` does carry three values and fails open: `if was_oom_killed:`
treats unobserved as not killed, silently, which is the precise substitution spec
section 5.4 says must never happen quietly, because the workloads that have been
killed are exactly the ones needing the larger memory margin. An enum member has no
truthiness to trip over. The database column stays a nullable boolean as the spec
specifies, and the mapping happens at the collector, which is where cloud shaped data
becomes domain data everywhere else here. `ManagementState` in `iac.py` made this
argument first and this follows it.

**A request that could not be read is None, never zero.** A cluster without enhanced
observability reports usage and no request at all, spec section 5.4. Zero would claim
a workload asked for nothing, making it look infinitely wasteful and sorting it to the
top of the screen that exists to find real waste.

**Efficiency is absent rather than zero wherever either side is unknown.** The same
reason `QuotaUsage.headroom` returns None: a ratio with an unknown numerator or an
unknown denominator is not a small number, it is not a number.

**The 14 day floor is imported, not restated.** `MINIMUM_HISTORY` lives in
`observation.py` and is already shared with P3's recommendations and the anomaly
detector. A fourth definition of 14 is how three of them come to disagree.

Constraint 1 forbids the cloud SDK here, not the knowledge of what it returns, so
`LaunchType.FARGATE` naming an AWS concept is deliberate and follows `quota.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from finops_core.domain.fact import Fact
from finops_core.domain.observation import MINIMUM_HISTORY


class LaunchType(StrEnum):
    """Where a workload's compute comes from, which decides how it gets resized.

    An EC2 backed workload is resized by changing its request, to any value. A
    Fargate task is resized by ordering a different task size, and only certain
    combinations exist, which is why sizing snaps up to a matrix rather than
    reporting the ideal figure nobody can order.
    """

    EC2 = "EC2"
    FARGATE = "FARGATE"


class OomStatus(StrEnum):
    """Whether a workload has been killed for running out of memory.

    Three members because there are three facts. `UNOBSERVED` is the honest default
    and is never inferred away: Container Insights does not reliably report OOM
    events, so many readings land here, and the memory rule has to say so in words
    rather than apply the smaller margin as though it had checked and found nothing.
    """

    KILLED = "KILLED"
    NOT_KILLED = "NOT_KILLED"
    #: Nothing was read that would show a kill. Not a synonym for NOT_KILLED.
    UNOBSERVED = "UNOBSERVED"

    @classmethod
    def from_observation(cls, killed: bool | None) -> OomStatus:
        """Map a nullable reading, which is how the column and the fake both hold it.

        The one place a nullable boolean is allowed to become an OOM status, so there
        is a single line to inspect when asking whether null was handled, rather than
        one per caller.
        """
        if killed is None:
            return cls.UNOBSERVED
        return cls.KILLED if killed else cls.NOT_KILLED

    @property
    def was_checked(self) -> bool:
        """Whether anything was read at all, which a rationale has to state."""
        return self is not OomStatus.UNOBSERVED


@dataclass(frozen=True, kw_only=True)
class Workload:
    """One deployable thing in one namespace of one cluster.

    Deliberately not a `Fact`. It is an identity that container figures are reported
    against, the way an account identifies rather than measures, and giving it
    timestamps would invite two copies of one workload differing only in when they
    were read. The facts about it carry their own, which is why `IngestRun` leaves
    `Fact` off for the mirror image of this reason.
    """

    cluster_name: str
    namespace: str
    name: str
    #: Deployment, StatefulSet, DaemonSet, Job, or an ECS service.
    kind: str
    launch_type: LaunchType

    def __post_init__(self) -> None:
        for field_name in ("cluster_name", "namespace", "name", "kind"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(
                    f"{field_name} is empty. A workload missing part of its name cannot "
                    f"be joined to its cost or shown on a screen."
                )

    @property
    def key(self) -> str:
        """The stable identifier, matching the shape the fake estate already emits."""
        return f"container/{self.cluster_name}/{self.namespace}/{self.name}"


@dataclass(frozen=True, kw_only=True)
class ClusterSlice(Fact):
    """One cluster's cost and fleet shape, with either part allowed to be unknown.

    Two separate unknowns, and conflating them would hide which one to go and fix.
    `cost` is absent when split cost allocation data is not enabled on the export,
    ISS-003. `node_count`, `spot_ratio` and `packing_efficiency` are absent when the
    node metrics could not be read. A cluster is listed either way, because a cluster
    nobody can measure is itself the finding, and omitting it reports a smaller,
    tidier estate than the one that exists.
    """

    cluster_name: str
    account_id: str
    region_id: str
    #: EKS or ECS. The platform decides which signals exist at all.
    platform: str
    #: Whether requests can be read. False means usage and no request, spec 5.4.
    enhanced_observability: bool
    #: None where split cost allocation data is absent from the export, not zero.
    cost: Decimal | None = None
    #: None where the node fleet could not be read. ECS on Fargate has no nodes.
    node_count: int | None = None
    spot_ratio: Decimal | None = None
    packing_efficiency: Decimal | None = None
    #: Why a figure above is absent, in words, for the screen to show per cluster.
    unmeasurable_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.cluster_name.strip():
            raise ValueError("a cluster slice needs a cluster name")
        if isinstance(self.cost, float):
            raise TypeError(
                f"{self.cluster_name} has a float cost. Money is Decimal here, because "
                f"a cluster total is reconciled against an invoice."
            )
        if self.cost is not None and self.cost < 0:
            raise ValueError(
                f"{self.cluster_name} has cost {self.cost}. A negative cluster cost is a "
                f"credit landing on the wrong grain, not a cheap cluster."
            )
        for name in ("spot_ratio", "packing_efficiency"):
            value = getattr(self, name)
            if value is not None and not (Decimal(0) <= value <= Decimal(1)):
                raise ValueError(
                    f"{self.cluster_name} has {name}={value}. It is a fraction of one, and "
                    f"a value outside that range means the ratio was built from two figures "
                    f"measured over different periods."
                )
        if self.node_count is not None and self.node_count < 0:
            raise ValueError(f"{self.cluster_name} has node_count {self.node_count}")

    @property
    def is_cost_measured(self) -> bool:
        """Whether this cluster's cost breakdown exists, which a screen splits on."""
        return self.cost is not None


@dataclass(frozen=True, kw_only=True)
class ReservationVsUse(Fact):
    """What a workload asked for against what it actually used.

    The comparison FEAT-036 exists for, and it stays two figures rather than one
    efficiency percentage, spec section 9: a namespace at 20 percent could be over
    requesting by a factor of five or could be idle, and those are different
    conversations with different people.

    Memory is held at its peak and CPU at a high percentile, which is not an
    inconsistency. A CPU request set too low throttles a workload and a memory
    request set too low kills it, so a percentile is right for the first and
    reckless for the second. Spec section 5.3.

    This is the aggregated view a recommendation is built from, not a stored row.
    `container_usage` holds one row per workload per day, and `observation_days` here
    is the count of those days, which is why the floor is checked at this grain.
    """

    workload: Workload
    #: None where the cluster cannot report requests at all. Never zero.
    cpu_requested_millicores: Decimal | None
    memory_requested_mib: Decimal | None
    #: The 99th percentile of the daily max rate, and the observed peak. None where
    #: the metric itself could not be read.
    cpu_used_p99_millicores: Decimal | None
    memory_used_peak_mib: Decimal | None
    oom_status: OomStatus
    observation_days: int

    def __post_init__(self) -> None:
        """Refuse the combinations that would misreport how a figure was obtained."""
        if self.observation_days < 0:
            raise ValueError(f"observation_days is {self.observation_days}")
        for name in (
            "cpu_requested_millicores",
            "memory_requested_mib",
            "cpu_used_p99_millicores",
            "memory_used_peak_mib",
        ):
            value = getattr(self, name)
            if isinstance(value, float):
                raise TypeError(
                    f"{name} arrived as a float. Container quantities are Decimal, because "
                    f"a request compared against a use decides money."
                )
            if value is not None and value < 0:
                raise ValueError(f"{name} is {value}, which is not a quantity")
        # A request of zero beside a positive use means the request was unread rather
        # than zero, which is the pair the database also forbids in `container_usage`.
        for request_name, use_name in (
            ("cpu_requested_millicores", "cpu_used_p99_millicores"),
            ("memory_requested_mib", "memory_used_peak_mib"),
        ):
            request = getattr(self, request_name)
            use = getattr(self, use_name)
            if request == 0 and use is not None and use > 0:
                raise ValueError(
                    f"{self.workload.key} has {request_name}=0 beside {use_name}={use}. "
                    f"A workload using something it never asked for means the request was "
                    f"unread, which is None rather than zero."
                )

    @property
    def has_requests(self) -> bool:
        """Whether this cluster could report what was asked for at all."""
        return self.cpu_requested_millicores is not None and self.memory_requested_mib is not None

    @property
    def cpu_efficiency(self) -> Decimal | None:
        """Used over requested, or None where that is not a number.

        None rather than zero wherever either side is unknown or the request is zero.
        Zero would say the workload uses none of a real reservation, which is a
        finding, and reporting an unknown as a finding is how a screen built to
        surface waste comes to surface a measurement gap instead.
        """
        return _ratio(self.cpu_used_p99_millicores, self.cpu_requested_millicores)

    @property
    def memory_efficiency(self) -> Decimal | None:
        """Used over requested, or None where that is not a number."""
        return _ratio(self.memory_used_peak_mib, self.memory_requested_mib)

    @property
    def supports_recommendation(self) -> bool:
        """Whether there is enough history, and enough read, to size this workload.

        Three conditions and each is necessary. Below the shared 14 day floor there is
        no recommendation rather than a low confidence one, which is P3's rule and is
        imported rather than restated. Without a request there is nothing to compare
        against, and without a use there is nothing to compare.
        """
        return (
            self.observation_days >= MINIMUM_HISTORY
            and self.has_requests
            and self.cpu_used_p99_millicores is not None
            and self.memory_used_peak_mib is not None
        )


def _ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    """A fraction, or None where it would be a claim rather than a measurement."""
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator
