"""Whether a resource is larger than it needs to be, and by how much.

No database, no clock, no provider. It takes numbers and returns an estimate,
which is what lets the decisions below be tested against lists rather than against
a fixture. `anomaly.py` is here for the same reason and the same payoff.

Four decisions carry this file, and each is here because the obvious alternative
is wrong in a way that costs somebody an outage or a morning.

**p95 and p99, never max.** A single spike sizes an instance for a minute that
happened once. The percentile is what the resource actually needs; the maximum is
what it needed on its worst second.

That only holds with enough points. Every series here is **hourly**, which is 336
over the fourteen day floor, and at that resolution one spike moves the 99th
percentile by almost nothing. Passed daily points instead, p99 over a fortnight is
the second largest value and the rule silently becomes "use the max", which is the
rule it exists to replace. The collectors read at a one hour period for the billing
reason in FEAT-026; this is the second reason.

**CPU and memory are sized differently.** A CPU request set too low throttles a
workload. A memory request set too low kills it. So CPU uses a percentile and
memory uses the observed peak plus a margin, and anyone tempted to unify them
should read `memory_headroom` first.

**Burstable credits are an input, not a footnote.** A t class instance at 20
percent with a healthy credit balance is correctly sized. Recommending it down is
the single most common false positive in this whole category.

**Under the floor there is no estimate.** Not a cautious one. `MINIMUM_HISTORY`,
shared with the anomaly detector.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from statistics import quantiles

from finops_core.domain.observation import MINIMUM_HISTORY
from finops_core.domain.waste import WasteClass

#: At or above this memory peak, an instance is memory bound and is not shrunk on
#: its CPU. An EC2 family halves memory with vCPU, so the next size down would take
#: a resource peaking here past a hundred percent. Eighty rather than ninety because
#: the peak is a maximum over hourly points and the real peak sits above it.
MEMORY_BOUND_PERCENT = Decimal("80")

#: Below this, a burstable instance is running on credits rather than on its
#: baseline, and its low average says nothing about whether it is oversized.
HEALTHY_CREDIT_FLOOR = Decimal("20")

#: What a rightsizing leaves spare. Sizing to exactly the observed p99 leaves a
#: workload with no room for the week it gets busier, and the recommendation is
#: reversed within a month.
CPU_HEADROOM = Decimal("1.30")

#: Memory, per FEAT-036's rule. The larger margin is for workloads that have
#: already been killed once.
MEMORY_HEADROOM = Decimal("1.15")
MEMORY_HEADROOM_AFTER_OOM = Decimal("1.25")

#: A saving smaller than this is not worth a row. The same floor the anomaly
#: detector uses for the same reason: a screen filled with rounding is a screen
#: nobody reads.
FLOOR_USD = Decimal("5.00")


@dataclass(frozen=True)
class Estimate:
    """What a resource could be, and the sentence explaining why.

    `is_worth_acting_on` false with a reason set is deliberate, and it is the same
    shape `Verdict` uses: a caller often needs to know a resource was examined and
    cleared, which is a different fact from one that was never examined.
    """

    is_worth_acting_on: bool
    waste_class: WasteClass
    monthly_saving: Decimal
    reason: str


def percentile(values: Sequence[Decimal], p: int) -> Decimal:
    """The pth percentile, or the only value when there is one.

    `statistics.quantiles` needs at least two points and returns cut points rather
    than values, so the small case is handled here rather than at four call sites.
    """
    if not values:
        raise ValueError("a percentile of nothing is not zero, it is unanswerable")
    if len(values) == 1:
        return values[0]
    cuts = quantiles([float(v) for v in values], n=100, method="inclusive")
    return Decimal(str(cuts[min(p, 99) - 1]))


def too_short(observation_days: int) -> bool:
    return observation_days < MINIMUM_HISTORY


def _refused(waste_class: WasteClass, reason: str) -> Estimate:
    return Estimate(
        is_worth_acting_on=False,
        waste_class=waste_class,
        monthly_saving=Decimal("0"),
        reason=reason,
    )


def rightsize_cpu(
    *,
    utilization_percent: Sequence[Decimal],
    observation_days: int,
    monthly_cost: Decimal,
    credit_balance: Decimal | None = None,
    memory_peak_percent: Decimal | None = None,
) -> Estimate:
    """Whether an instance is larger than its own demand.

    `credit_balance` is None for an instance that has no credits, which is most of
    them. A burstable instance with a healthy balance is refused outright: its low
    average utilization is the design working, not waste.

    `memory_peak_percent` is None where no agent publishes memory, which is the
    common case and is unobserved rather than fine. Where it is present and high the
    instance is refused, because an EC2 family scales vCPU and memory together: the
    next size down halves both, so a downsize that looks free on CPU would put
    memory over a hundred percent. The rationale says which of the two happened, so
    a reader can tell a checked instance from an unchecked one.
    """
    kind = WasteClass.RIGHTSIZE_INSTANCE
    if too_short(observation_days):
        return _refused(kind, f"{observation_days} days is under the {MINIMUM_HISTORY} day floor")
    if credit_balance is not None and credit_balance >= HEALTHY_CREDIT_FLOOR:
        # The single most common false positive in this category.
        return _refused(
            kind,
            f"burstable with a credit balance of {credit_balance}, so low average "
            "utilization is the design rather than waste",
        )
    if memory_peak_percent is not None and memory_peak_percent >= MEMORY_BOUND_PERCENT:
        # The second most common, and the one a CPU only detector cannot see. The
        # work is memory work and the CPU is quiet because it is waiting.
        return _refused(
            kind,
            f"memory peaks at {memory_peak_percent:.1f} percent, at or above the "
            f"{MEMORY_BOUND_PERCENT} percent ceiling, so this is memory bound and a "
            "smaller size would halve the memory along with the vCPU",
        )

    p99 = percentile(utilization_percent, 99)
    needed = p99 * CPU_HEADROOM
    if needed >= Decimal("100"):
        return _refused(kind, f"p99 of {p99:.1f} percent leaves no room to shrink")

    # What fraction of the machine is never used, after leaving headroom.
    spare = (Decimal("100") - needed) / Decimal("100")
    saving = (monthly_cost * spare).quantize(Decimal("0.01"))
    if saving < FLOOR_USD:
        return _refused(kind, f"{saving} is under the {FLOOR_USD} floor")

    return Estimate(
        is_worth_acting_on=True,
        waste_class=kind,
        monthly_saving=saving,
        reason=(
            f"p99 of {p99:.1f} percent over {observation_days} days. With "
            f"{(CPU_HEADROOM - 1) * 100:.0f} percent headroom that needs "
            f"{needed:.1f} percent of the current size. "
            + (
                f"Memory peaks at {memory_peak_percent:.1f} percent, which leaves room"
                if memory_peak_percent is not None
                # Said, not assumed. A reader deciding whether to act needs to know
                # that the memory half of the question went unchecked.
                else "No agent publishes memory here, so whether it is memory bound "
                "could not be checked"
            )
        ),
    )


def idle(
    *,
    utilization_percent: Sequence[Decimal],
    observation_days: int,
    monthly_cost: Decimal,
    idle_below_percent: Decimal = Decimal("2"),
) -> Estimate:
    """Whether an instance is doing nothing at all.

    Uses p95 rather than the mean, because a machine that is idle for 95 percent of
    a fortnight and busy for the rest is a batch worker, not waste.
    """
    kind = WasteClass.IDLE_INSTANCE
    if too_short(observation_days):
        return _refused(kind, f"{observation_days} days is under the {MINIMUM_HISTORY} day floor")
    if not utilization_percent:
        # An absent series means unobserved. A collector concluding "idle" from no
        # data points would recommend terminating a running system.
        return _refused(kind, "no utilization was observed, which is not the same as none used")

    p95 = percentile(utilization_percent, 95)
    if p95 >= idle_below_percent:
        return _refused(kind, f"p95 of {p95:.1f} percent is above the {idle_below_percent} floor")
    saving = monthly_cost.quantize(Decimal("0.01"))
    if saving < FLOOR_USD:
        return _refused(kind, f"{saving} is under the {FLOOR_USD} floor")
    return Estimate(
        is_worth_acting_on=True,
        waste_class=kind,
        monthly_saving=saving,
        reason=(
            f"p95 of {p95:.1f} percent over {observation_days} days, which is under "
            f"{idle_below_percent} percent. The whole cost is the saving"
        ),
    )


def memory_headroom(*, was_oom_killed: bool | None) -> Decimal:
    """The margin to leave above observed peak memory.

    Three states, not two, and the third is why this is a function. `None` means
    nobody could observe whether the workload was killed, which is the state
    Container Insights leaves it in. Treating unknown as false applies the smaller
    margin to exactly the workloads that have already run out of memory once.
    """
    return MEMORY_HEADROOM_AFTER_OOM if was_oom_killed is True else MEMORY_HEADROOM


def rightsize_memory(
    *,
    peak_bytes: Decimal,
    requested_bytes: Decimal,
    observation_days: int,
    monthly_cost: Decimal,
    was_oom_killed: bool | None,
) -> Estimate:
    """Whether a workload reserves more memory than it has ever used.

    Peak, not a percentile. A percentile of memory is a number that kills a
    workload on the day it exceeds it, and the difference between CPU and memory
    here is the whole reason this is a separate function.
    """
    kind = WasteClass.CONTAINER_RIGHTSIZE
    if too_short(observation_days):
        return _refused(kind, f"{observation_days} days is under the {MINIMUM_HISTORY} day floor")
    if requested_bytes <= 0:
        return _refused(kind, "no request was observed, which is not a request of zero")

    margin = memory_headroom(was_oom_killed=was_oom_killed)
    needed = peak_bytes * margin
    if needed >= requested_bytes:
        return _refused(kind, f"peak of {peak_bytes} plus margin already needs the request")

    spare = (requested_bytes - needed) / requested_bytes
    saving = (monthly_cost * spare).quantize(Decimal("0.01"))
    if saving < FLOOR_USD:
        return _refused(kind, f"{saving} is under the {FLOOR_USD} floor")

    checked = (
        "never OOM killed"
        if was_oom_killed is False
        else "OOM killed, so the larger margin applies"
        if was_oom_killed
        # Said, not assumed. The margin is the smaller one and the reader is told
        # that is because nobody could look, not because nobody was killed.
        else "OOM status could not be observed, so the smaller margin was used"
    )
    return Estimate(
        is_worth_acting_on=True,
        waste_class=kind,
        monthly_saving=saving,
        reason=(
            f"peak of {peak_bytes} against a request of {requested_bytes} over "
            f"{observation_days} days, with a {(margin - 1) * 100:.0f} percent margin. {checked}"
        ),
    )


def whole_cost(
    *, waste_class: WasteClass, monthly_cost: Decimal, observation_days: int, detail: str
) -> Estimate:
    """For the classes where the resource should simply not exist.

    An unattached volume, an unassociated Elastic IP, an idle NAT Gateway. There is
    no sizing question: the saving is the whole cost, and the only judgement is
    whether it has been unused long enough to be sure.
    """
    if too_short(observation_days):
        return _refused(
            waste_class, f"{observation_days} days is under the {MINIMUM_HISTORY} day floor"
        )
    saving = monthly_cost.quantize(Decimal("0.01"))
    if saving < FLOOR_USD:
        return _refused(waste_class, f"{saving} is under the {FLOOR_USD} floor")
    return Estimate(
        is_worth_acting_on=True,
        waste_class=waste_class,
        monthly_saving=saving,
        reason=f"{detail} for {observation_days} days. The whole cost is the saving",
    )
