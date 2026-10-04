"""Whether a workload reserves more than it uses, and what it should reserve instead.

TASK-P6-007, FEAT-036. No database, no clock, no provider: it takes one workload's
reservation and its measured cost and returns an estimate, which is what lets the
rules be tested against numbers rather than fixtures. The write lives in the
collector, because this package imports no database and a contract holds that.

**Composed onto P3, not beside it.** The memory margins, the fourteen day floor, the
saving floor and the shape of an estimate already exist in `finops_query.waste`, and
P3 built the memory rule for containers ahead of this sub project. A second copy of
fifteen and twenty five percent is how two screens come to size the same workload
differently, so this module imports them.

**CPU and memory are sized differently on purpose.** Spec section 5.3. A CPU request
set too low lets a workload be scheduled where it then competes; a memory request set
too low gets it killed. So CPU is sized at the 99th percentile of the daily peak and
memory at the observed peak plus a margin, and the margin is larger for a workload
that has already been killed.

**An unobserved kill is said, in words.** Container Insights does not reliably report
OOM events, so most workloads arrive with an unobserved status. The smaller margin
then applies, as spec section 5.4 decided, and the rationale says the check could not
be made rather than reading as though it was made and came back clean. That sentence
is what makes the no agent decision reversible: when somebody decides the gap matters
more than an agent costs, the recommendations that were affected are the ones that
say so.

**The saving is modelled and says why.** A pod is charged for what it reserves, so
releasing part of a request releases part of its cost, but the instance's own split of
cost between CPU and memory is not read. The two are weighted equally and the
rationale names that assumption instead of presenting a precise looking figure.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from finops_core.domain.containers import LaunchType, OomStatus, ReservationVsUse
from finops_core.domain.observation import MINIMUM_HISTORY
from finops_core.domain.waste import WasteClass
from finops_query.waste import (
    FLOOR_USD,
    MEMORY_HEADROOM,
    MEMORY_HEADROOM_AFTER_OOM,
    Estimate,
    memory_headroom,
    too_short,
)

#: The share of a pod's cost that follows its CPU request rather than its memory
#: request. One half, as an assumption the bill cannot check: the instance's own split
#: between the two is not read. Every rationale that uses it says so.
CPU_SHARE_OF_COST = Decimal("0.5")

#: Requests are rounded up to whole millicores and whole MiB. Up, never down, so a
#: recommendation can never ask for less than the rule says a workload needs.
_WHOLE = Decimal("1")

KIND = WasteClass.CONTAINER_RIGHTSIZE

#: The refusals, as sentences. A refusal reading "not eligible" teaches a reader that
#: the explanations here are empty, so each says what was missing and what would fix it.
NO_REQUEST = (
    "this cluster does not publish pod requests, so there is nothing to compare use "
    "against. Enhanced observability on the cluster would publish them"
)
NO_USE = "no use was observed for this workload, which is not the same as a use of zero"
NO_COST = (
    "no cost is attributed to this workload, so a saving cannot be stated. Split cost "
    "allocation on the billing export would attribute one, ISS-003"
)
ALREADY_FITS = "its peak use plus the margin it needs already fills the whole request"

#: The three things the rationale can say about OOM status. The unobserved one is the
#: sentence a test reads, so it has to be unmistakable.
KILLED = (
    "It has been killed for running out of memory, so the larger "
    f"{(MEMORY_HEADROOM_AFTER_OOM - 1) * 100:.0f} percent margin applies."
)
NOT_KILLED = (
    "It has been observed and has not been killed for running out of memory, so the "
    f"{(MEMORY_HEADROOM - 1) * 100:.0f} percent margin applies."
)
UNOBSERVED = (
    "Whether it has been killed for running out of memory could not be observed, so the "
    f"{(MEMORY_HEADROOM - 1) * 100:.0f} percent margin was used. If it has been killed it "
    f"needs {(MEMORY_HEADROOM_AFTER_OOM - 1) * 100:.0f} percent, and this recommendation "
    "could not check."
)


@dataclass(frozen=True)
class ContainerSizing:
    """An estimate, and the requests it recommends where it recommends anything.

    The requests are absent on a refusal rather than set to the current ones, because a
    refusal is not a recommendation to keep things as they are. It is the statement
    that no recommendation could be made.
    """

    estimate: Estimate
    cpu_request_millicores: Decimal | None = None
    memory_request_mib: Decimal | None = None


def _refused(reason: str) -> ContainerSizing:
    return ContainerSizing(
        estimate=Estimate(
            is_worth_acting_on=False,
            waste_class=KIND,
            monthly_saving=Decimal("0"),
            reason=reason,
        )
    )


def _was_killed(status: OomStatus) -> bool | None:
    """The enum as P3's memory rule takes it. None for unobserved, never False."""
    if status is OomStatus.UNOBSERVED:
        return None
    return status is OomStatus.KILLED


def _oom_sentence(status: OomStatus) -> str:
    if status is OomStatus.KILLED:
        return KILLED
    if status is OomStatus.NOT_KILLED:
        return NOT_KILLED
    return UNOBSERVED


def _up(value: Decimal) -> Decimal:
    return value.to_integral_value(rounding=ROUND_CEILING).quantize(_WHOLE)


def _spare(requested: Decimal, needed: Decimal) -> Decimal:
    """The fraction of a request that could be released. Never negative.

    A workload using more than it asked for has nothing spare, and this module is about
    waste: an under requested workload is a reliability question for another screen.
    """
    if requested <= 0 or needed >= requested:
        return Decimal("0")
    return (requested - needed) / requested


def needed_memory_mib(peak_mib: Decimal, status: OomStatus) -> Decimal:
    """The memory a workload needs: its peak plus the margin its OOM history earns."""
    return peak_mib * memory_headroom(was_oom_killed=_was_killed(status))


def size_workload(
    *, reservation: ReservationVsUse, monthly_cost: Decimal | None
) -> ContainerSizing:
    """Whether a workload's requests can come down, and to what.

    Refuses in a fixed order, so the reason given is the first thing that stopped it:
    too little history, then nothing to compare against, then no cost to state a saving
    in. A Fargate task is sized by the matrix in TASK-P6-008 rather than here, because
    only certain task sizes can be ordered.
    """
    days = reservation.observation_days
    if too_short(days):
        return _refused(
            f"{days} days is under the {MINIMUM_HISTORY} day floor. There is no "
            "recommendation, not a low confidence one"
        )
    cpu_requested = reservation.cpu_requested_millicores
    memory_requested = reservation.memory_requested_mib
    if cpu_requested is None or memory_requested is None:
        return _refused(NO_REQUEST)
    cpu_used = reservation.cpu_used_p99_millicores
    memory_peak = reservation.memory_used_peak_mib
    if cpu_used is None or memory_peak is None:
        return _refused(NO_USE)
    if monthly_cost is None or monthly_cost <= 0:
        return _refused(NO_COST)

    cpu_needed = _up(cpu_used)
    memory_needed = _up(needed_memory_mib(memory_peak, reservation.oom_status))
    cpu_spare = _spare(cpu_requested, cpu_needed)
    memory_spare = _spare(memory_requested, memory_needed)
    if cpu_spare == 0 and memory_spare == 0:
        return _refused(ALREADY_FITS)

    released = CPU_SHARE_OF_COST * cpu_spare + (1 - CPU_SHARE_OF_COST) * memory_spare
    saving = (monthly_cost * released).quantize(Decimal("0.01"))
    if saving < FLOOR_USD:
        return _refused(f"{saving} is under the {FLOOR_USD} floor")

    margin = memory_headroom(was_oom_killed=_was_killed(reservation.oom_status))
    reason = (
        f"CPU: the 99th percentile of the daily peak is {cpu_needed} millicores against a "
        f"request of {cpu_requested}. Memory: the peak is {memory_peak} MiB against a "
        f"request of {memory_requested}, which needs {memory_needed} MiB with a "
        f"{(margin - 1) * 100:.0f} percent margin. {_oom_sentence(reservation.oom_status)} "
        f"Over {days} days. The saving is modelled: it releases "
        f"{released * 100:.0f} percent of a measured monthly cost of {monthly_cost}, "
        "weighting CPU and memory equally because the instance's own split between them "
        "is not read."
    )
    return ContainerSizing(
        estimate=Estimate(
            is_worth_acting_on=True,
            waste_class=KIND,
            monthly_saving=saving,
            reason=reason,
        ),
        # Lowered only where there is room. A request already below its need is kept,
        # because raising it is a reliability decision this screen does not make.
        cpu_request_millicores=min(cpu_requested, cpu_needed),
        memory_request_mib=min(memory_requested, memory_needed),
    )


# --- Fargate, TASK-P6-008 ------------------------------------------------------

#: The task sizes Fargate sells, Linux, as the ECS developer guide's task size table
#: publishes them: each CPU size with the memory sizes it may be paired with. CPU in
#: millicores, so one vCPU is 1000, and memory in MiB. A table rather than a rule,
#: because the increments differ by row and a formula would have to encode every
#: exception to stay true.
FARGATE_SIZES: tuple[tuple[int, tuple[int, ...]], ...] = (
    (250, (512, 1024, 2048)),
    (500, tuple(range(1024, 4096 + 1, 1024))),
    (1000, tuple(range(2048, 8192 + 1, 1024))),
    (2000, tuple(range(4096, 16384 + 1, 1024))),
    (4000, tuple(range(8192, 30720 + 1, 1024))),
    (8000, tuple(range(16384, 61440 + 1, 4096))),
    (16000, tuple(range(32768, 122880 + 1, 8192))),
)

#: Fargate's published Linux x86 on demand rates, per vCPU hour and per GB hour, in the
#: least expensive regions. Every other region charges more, so a saving computed here
#: is a floor rather than a ceiling, which is the safe direction for a waste screen.
FARGATE_VCPU_HOUR_USD = Decimal("0.04048")
FARGATE_GB_HOUR_USD = Decimal("0.004445")

#: The hours AWS bills a month as.
HOURS_PER_MONTH = Decimal("730")

_MIB_PER_GB = Decimal("1024")
_MILLICORES_PER_VCPU = Decimal("1000")


def fargate_sizes() -> tuple[tuple[Decimal, Decimal], ...]:
    """Every orderable combination, as (CPU millicores, memory MiB)."""
    return tuple(
        (Decimal(cpu), Decimal(memory)) for cpu, memories in FARGATE_SIZES for memory in memories
    )


def fargate_monthly_usd(cpu_millicores: Decimal, memory_mib: Decimal) -> Decimal:
    """What one task of this size costs a month at the published rate."""
    vcpu = cpu_millicores / _MILLICORES_PER_VCPU
    gb = memory_mib / _MIB_PER_GB
    return (vcpu * FARGATE_VCPU_HOUR_USD + gb * FARGATE_GB_HOUR_USD) * HOURS_PER_MONTH


def snap_up(cpu_millicores: Decimal, memory_mib: Decimal) -> tuple[Decimal, Decimal]:
    """The cheapest orderable size that holds at least this much of both.

    Always up, never to the nearest. A task needing 1100 millicores is nearer 1000 than
    2000, and 1000 is the size that throttles it. Snapping down would report a larger
    saving and deliver a task too small to run.

    Raises when nothing is large enough, rather than returning the largest size: a
    recommendation to order a task smaller than its need is the defect this exists to
    prevent, and the largest size would be exactly that.
    """
    fits = [size for size in fargate_sizes() if size[0] >= cpu_millicores and size[1] >= memory_mib]
    if not fits:
        raise ValueError(f"no Fargate size holds {cpu_millicores} millicores and {memory_mib} MiB")
    return min(fits, key=lambda size: (fargate_monthly_usd(*size), size))


def is_orderable(cpu_millicores: Decimal, memory_mib: Decimal) -> bool:
    return (cpu_millicores, memory_mib) in set(fargate_sizes())


def size_fargate_task(*, reservation: ReservationVsUse) -> ContainerSizing:
    """The smallest size somebody can actually order, and what it saves per task.

    The saving is computed from the snapped size and never from the ideal one. Reporting
    the ideal would look better and be a number nobody can realise: the first person to
    order the recommendation would find the saving smaller than promised and stop
    believing the rest of the screen.

    Modelled from the published rate rather than measured, because a Fargate task's cost
    is a pure function of its size, and per task, because how many tasks a service runs
    is not read. Both are said in the rationale.
    """
    days = reservation.observation_days
    if too_short(days):
        return _refused(
            f"{days} days is under the {MINIMUM_HISTORY} day floor. There is no "
            "recommendation, not a low confidence one"
        )
    cpu_requested = reservation.cpu_requested_millicores
    memory_requested = reservation.memory_requested_mib
    if cpu_requested is None or memory_requested is None:
        return _refused(NO_REQUEST)
    cpu_used = reservation.cpu_used_p99_millicores
    memory_peak = reservation.memory_used_peak_mib
    if cpu_used is None or memory_peak is None:
        return _refused(NO_USE)

    cpu_needed = _up(cpu_used)
    memory_needed = _up(needed_memory_mib(memory_peak, reservation.oom_status))
    try:
        cpu_snapped, memory_snapped = snap_up(cpu_needed, memory_needed)
    except ValueError as error:
        return _refused(str(error))

    if cpu_snapped >= cpu_requested and memory_snapped >= memory_requested:
        return _refused(ALREADY_FITS)

    current = fargate_monthly_usd(cpu_requested, memory_requested)
    snapped = fargate_monthly_usd(cpu_snapped, memory_snapped)
    saving = (current - snapped).quantize(Decimal("0.01"))
    if saving < FLOOR_USD:
        return _refused(f"{saving} per task is under the {FLOOR_USD} floor")

    reason = (
        f"The task is sized {cpu_requested} millicores and {memory_requested} MiB. It needs "
        f"{cpu_needed} millicores, the 99th percentile of its daily peak, and "
        f"{memory_needed} MiB, its peak plus margin. "
        f"{_oom_sentence(reservation.oom_status)} The smallest size Fargate sells that "
        f"holds both is {cpu_snapped} millicores and {memory_snapped} MiB, rounded up and "
        f"never down, and the saving is computed from that size rather than from the "
        f"ideal one. Over {days} days. Modelled from Fargate's published rate, per task: "
        "how many tasks the service runs is not read, so a service running several saves "
        "more than this."
    )
    return ContainerSizing(
        estimate=Estimate(
            is_worth_acting_on=True,
            waste_class=KIND,
            monthly_saving=saving,
            reason=reason,
        ),
        cpu_request_millicores=cpu_snapped,
        memory_request_mib=memory_snapped,
    )


def size(*, reservation: ReservationVsUse, monthly_cost: Decimal | None) -> ContainerSizing:
    """The right rule for the workload's launch type.

    An EC2 backed workload is resized by changing its request to any value, and its
    saving is a share of its measured cost. A Fargate task is resized by ordering a
    different size from a fixed list, and its saving is the difference between two
    sizes' published rates.
    """
    if reservation.workload.launch_type is LaunchType.FARGATE:
        return size_fargate_task(reservation=reservation)
    return size_workload(reservation=reservation, monthly_cost=monthly_cost)
