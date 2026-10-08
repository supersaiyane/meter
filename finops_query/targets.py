"""A smaller machine that still fits, named and priced. TASK-P9-007, P9 spec sections 5.5 and 5.6.

No database, no clock, no provider, as `waste.py` is: it takes the type an instance runs as, the
types offered in its Region with their catalog prices, and the demand measured on it, and returns
a target or the sentence saying why there is none.

**Candidates.** The same family one or two sizes down, the newer generations of the same series,
and their AMD and Graviton variants, at the same size or one or two sizes down, every one offered
in the Region and priced. A size step halves the vCPUs, as an EC2 family's ladder does. A
burstable type is only ever replaced by a burstable one, and the reverse, because credits change
what a percentage of CPU means.

**Fit.** CPU p99 times 1.30 against the target's vCPUs; the memory peak times 1.15, or 1.25 after
an out of memory kill, against its memory; network and EBS p99 against its baseline, never its
burst. A figure the target does not publish is not checked, and the rationale says so rather than
passing it silently.

**No memory figure, one step only.** Without an agent nothing says how much memory the work
needs, so the only candidate is the same family one size down, and the rationale says why.

**Snap to the cheapest fit.** Among the candidates that fit, the one with the lowest price.

**Growing, TASK-P9-008, spec section 5.7.** CPU or memory p95 above 90 percent, or network p99
at the type's baseline, is pressure. The candidates are the next size up in the family or a
newer generation of it, and, where memory is the pressure, a type of the same size with more
memory per vCPU; the cheapest that fits the demand with the same headroom is chosen, and what it
adds is a cost, never a negative saving.

**The saving is a price difference.** The current type's price less the target's, for the hours
the instance runs, at list, and scaled by what the bill shows for those hours, never scaled up:
a bill line above list for the same hours is carrying something else, and multiplying by it would
overstate the saving. Both are modelled.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from finops_query.waste import CPU_HEADROOM, MEMORY_HEADROOM, MEMORY_HEADROOM_AFTER_OOM

#: At or above this p95, CPU or memory is under pressure and the instance needs room. TASK-P9-008.
PRESSURE_PERCENT: Final = Decimal(90)

#: AWS's own month for a monthly figure from an hourly price: 8,760 hours over twelve.
HOURS_PER_MONTH: Final = Decimal(8760) / Decimal(12)
HOURS_PER_DAY: Final = Decimal(24)
#: An EC2 family's name: series, generation, then what follows it, `m6gd` or `c7gn`.
_FAMILY: Final = re.compile(r"([a-z]+)(\d+)([a-z-]*)")
#: The letter a family's suffix names its processor by.
_GRAVITON: Final = "g"
_AMD: Final = "a"
_CENT: Final = Decimal("0.01")


@dataclass(frozen=True)
class TypeOffer:
    """One type offered in a Region, as the catalog describes and prices it."""

    instance_type: str
    vcpus: int
    memory_mib: int
    architectures: tuple[str, ...]
    burstable: bool
    #: The comparable price, None where the catalog holds none for this type.
    hourly_price: Decimal | None
    sku_price_id: str | None = None
    network_baseline_gbps: Decimal | None = None
    ebs_baseline_mbps: int | None = None


@dataclass(frozen=True)
class Demand:
    """What the instance was measured to need, over its observation window."""

    cpu_p99_percent: Decimal
    #: None where no agent publishes memory, which is unobserved rather than fine.
    memory_peak_percent: Decimal | None = None
    oom_killed: bool | None = None
    network_p99_gbps: Decimal | None = None
    ebs_p99_mbps: Decimal | None = None
    #: The p95s pressure is judged on, TASK-P9-008. None where unmeasured.
    cpu_p95_percent: Decimal | None = None
    memory_p95_percent: Decimal | None = None


@dataclass(frozen=True)
class Target:
    """The cheapest type that fits, with what was not equivalent or not checked."""

    offer: TypeOffer
    needed_vcpus: Decimal
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Family:
    series: str
    generation: int
    processor: str
    features: str
    size: str


def family_of(instance_type: str) -> Family | None:
    """`m6gd.2xlarge` as its parts, or None for a name outside the EC2 grammar."""
    name, _, size = instance_type.partition(".")
    match = _FAMILY.fullmatch(name)
    if match is None or not size:
        return None
    series, generation, suffix = match.group(1), int(match.group(2)), match.group(3)
    processor = _GRAVITON if _GRAVITON in suffix else _AMD if suffix.startswith(_AMD) else ""
    features = suffix.replace(processor, "", 1) if processor else suffix.removeprefix("i")
    return Family(series, generation, processor, features, size)


def candidates(
    current: TypeOffer, offered: Iterable[TypeOffer], *, memory_known: bool
) -> list[TypeOffer]:
    """The types worth comparing, by the rule in this module's docstring."""
    mine = family_of(current.instance_type)
    if mine is None:
        return []
    found: list[TypeOffer] = []
    for offer in offered:
        theirs = family_of(offer.instance_type)
        if theirs is None or offer.instance_type == current.instance_type:
            continue
        if offer.burstable != current.burstable:
            continue
        same_family = (theirs.series, theirs.generation, theirs.processor, theirs.features) == (
            mine.series,
            mine.generation,
            mine.processor,
            mine.features,
        )
        if not memory_known:
            if same_family and offer.vcpus * 2 == current.vcpus:
                found.append(offer)
            continue
        related = (
            theirs.series == mine.series
            and theirs.generation >= mine.generation
            and theirs.features == mine.features
        )
        if related and offer.vcpus in {current.vcpus, current.vcpus // 2, current.vcpus // 4}:
            found.append(offer)
    return found


def misfit(current: TypeOffer, offer: TypeOffer, demand: Demand) -> str | None:
    """Why `offer` cannot take the work, or None if it can."""
    needed = demand.cpu_p99_percent / 100 * current.vcpus * CPU_HEADROOM
    if needed > offer.vcpus:
        return f"{offer.instance_type} has {offer.vcpus} vCPUs and {needed:.2f} are needed"
    if demand.memory_peak_percent is not None:
        headroom = MEMORY_HEADROOM_AFTER_OOM if demand.oom_killed else MEMORY_HEADROOM
        memory = demand.memory_peak_percent / 100 * current.memory_mib * headroom
        if memory > offer.memory_mib:
            return f"{offer.instance_type} has {offer.memory_mib} MiB and {memory:.0f} are needed"
    if (
        demand.network_p99_gbps is not None
        and offer.network_baseline_gbps is not None
        and demand.network_p99_gbps > offer.network_baseline_gbps
    ):
        return f"{offer.instance_type}'s network baseline is under the p99"
    if (
        demand.ebs_p99_mbps is not None
        and offer.ebs_baseline_mbps is not None
        and demand.ebs_p99_mbps > offer.ebs_baseline_mbps
    ):
        return f"{offer.instance_type}'s EBS baseline is under the p99"
    return None


def choose(current: TypeOffer, offered: Sequence[TypeOffer], demand: Demand) -> Target | str:
    """The cheapest candidate that fits and costs less, or why there is none."""
    if current.hourly_price is None:
        return f"the catalog holds no price for {current.instance_type}, so no saving can be quoted"
    memory_known = demand.memory_peak_percent is not None
    cheaper = [
        offer
        for offer in candidates(current, offered, memory_known=memory_known)
        if offer.hourly_price is not None and offer.hourly_price < current.hourly_price
    ]
    if not cheaper:
        step = "one size down in the family" if not memory_known else "a smaller or cheaper type"
        return f"the catalog offers {step} at no lower price in this Region"
    fitting = [offer for offer in cheaper if misfit(current, offer, demand) is None]
    if not fitting:
        return "no cheaper type fits: " + "; ".join(
            str(misfit(current, offer, demand)) for offer in sorted(cheaper, key=_price)
        )
    best = min(fitting, key=_price)
    return Target(
        offer=best,
        needed_vcpus=demand.cpu_p99_percent / 100 * current.vcpus * CPU_HEADROOM,
        notes=_notes(current, best, demand),
    )


def _price(offer: TypeOffer) -> tuple[Decimal, str]:
    return (offer.hourly_price or Decimal(0), offer.instance_type)


def _notes(current: TypeOffer, target: TypeOffer, demand: Demand) -> tuple[str, ...]:
    notes: list[str] = []
    mine, theirs = family_of(current.instance_type), family_of(target.instance_type)
    if (
        mine is not None
        and theirs is not None
        and (mine.generation, mine.processor) != (theirs.generation, theirs.processor)
    ):
        notes.append("vCPUs are not equivalent across a generation or an architecture")
    if "arm64" in target.architectures and "arm64" not in current.architectures:
        notes.append("Graviton needs arm64 builds of everything the instance runs")
    if demand.memory_peak_percent is None:
        notes.append(
            "no agent publishes memory, so only one size down within the family is offered"
        )
    if demand.network_p99_gbps is not None and target.network_baseline_gbps is None:
        notes.append(f"{target.instance_type} publishes no network baseline to check against")
    if demand.ebs_p99_mbps is not None and target.ebs_baseline_mbps is None:
        notes.append(f"{target.instance_type} publishes no EBS baseline to check against")
    return tuple(notes)


def pressure(current: TypeOffer, demand: Demand) -> str | None:
    """What the instance is short of, in words, or None if nothing is under pressure."""
    short: list[str] = []
    if demand.cpu_p95_percent is not None and demand.cpu_p95_percent > PRESSURE_PERCENT:
        short.append(f"CPU p95 of {demand.cpu_p95_percent:.1f} percent")
    if demand.memory_p95_percent is not None and demand.memory_p95_percent > PRESSURE_PERCENT:
        short.append(f"memory p95 of {demand.memory_p95_percent:.1f} percent")
    baseline = current.network_baseline_gbps
    if (
        demand.network_p99_gbps is not None
        and baseline is not None
        and demand.network_p99_gbps >= baseline
    ):
        short.append(f"network p99 at its {baseline} Gbps baseline")
    return " and ".join(short) or None


def larger(current: TypeOffer, offered: Iterable[TypeOffer], demand: Demand) -> list[TypeOffer]:
    """The types worth growing into, by the rule in this module's docstring."""
    mine = family_of(current.instance_type)
    if mine is None:
        return []
    memory_short = (
        demand.memory_p95_percent is not None and demand.memory_p95_percent > PRESSURE_PERCENT
    )
    per_vcpu = Decimal(current.memory_mib) / current.vcpus
    found: list[TypeOffer] = []
    for offer in offered:
        theirs = family_of(offer.instance_type)
        if theirs is None or offer.burstable != current.burstable:
            continue
        same_processor = theirs.processor == mine.processor
        next_size = (
            theirs.series == mine.series
            and theirs.generation >= mine.generation
            and theirs.features == mine.features
            and same_processor
            and offer.vcpus == current.vcpus * 2
        )
        more_memory = (
            memory_short
            and same_processor
            and offer.vcpus == current.vcpus
            and Decimal(offer.memory_mib) / offer.vcpus > per_vcpu
        )
        if next_size or more_memory:
            found.append(offer)
    return found


def grow(current: TypeOffer, offered: Sequence[TypeOffer], demand: Demand) -> Target | str:
    """The cheapest larger type that fits, or why there is none."""
    if current.hourly_price is None:
        return f"the catalog holds no price for {current.instance_type}, so no cost can be quoted"
    priced = [o for o in larger(current, offered, demand) if o.hourly_price is not None]
    if not priced:
        return "the catalog offers no larger type of this line in this Region"
    fitting = [offer for offer in priced if misfit(current, offer, demand) is None]
    if not fitting:
        return "no larger type fits: " + "; ".join(
            str(misfit(current, offer, demand)) for offer in sorted(priced, key=_price)
        )
    best = min(fitting, key=_price)
    return Target(
        offer=best,
        needed_vcpus=demand.cpu_p99_percent / 100 * current.vcpus * CPU_HEADROOM,
        notes=_notes(current, best, demand),
    )


def added_cost(
    *, current_hourly: Decimal, target_hourly: Decimal, hours: Decimal, paid_monthly: Decimal
) -> Saving:
    """What growing adds a month, at list and as the bill pays: the mirror of `saving`."""
    return _scaled(target_hourly - current_hourly, current_hourly, hours, paid_monthly)


@dataclass(frozen=True)
class Saving:
    """A price difference for the hours run, at list and as paid. Both modelled."""

    hours_per_month: Decimal
    at_list: Decimal
    as_paid: Decimal
    #: What the bill shows over list for the same hours, capped at one.
    paid_ratio: Decimal


def hours_per_month(points: int, observation_days: int) -> Decimal:
    """The hours a month the instance runs, from its hourly points over its window."""
    if observation_days <= 0:
        return Decimal(0)
    per_day = min(HOURS_PER_DAY, Decimal(points) / Decimal(observation_days))
    return per_day / HOURS_PER_DAY * HOURS_PER_MONTH


def saving(
    *, current_hourly: Decimal, target_hourly: Decimal, hours: Decimal, paid_monthly: Decimal
) -> Saving:
    """The difference of two list prices over `hours`, and the same scaled to the bill."""
    return _scaled(current_hourly - target_hourly, current_hourly, hours, paid_monthly)


def _scaled(
    difference: Decimal, current_hourly: Decimal, hours: Decimal, paid_monthly: Decimal
) -> Saving:
    """An hourly difference over `hours`, at list and scaled by what the bill shows over list
    for the current type in those hours, never scaled up."""
    at_list_cost = current_hourly * hours
    ratio = min(Decimal(1), paid_monthly / at_list_cost) if at_list_cost > 0 else Decimal(1)
    at_list = difference * hours
    return Saving(
        hours_per_month=hours,
        at_list=at_list.quantize(_CENT),
        as_paid=(at_list * ratio).quantize(_CENT),
        paid_ratio=ratio,
    )
