"""Meter's purchase plan: the steady baseline, P9's rates, the policy and the ladder. FEAT-089.

TASK-P14-007, P14 spec section 5.6, OPEN-38 and OPEN-40. Pure arithmetic, so every figure in a plan
can be traced to its inputs and tested without a database. Every figure it returns is modelled.

**The baseline is a quiet day, not an average.** For each kind of usage the bill shows on the days
it holds, the steady baseline is the tenth percentile of the daily on demand equivalent spend,
divided by 24. A day the bill does not hold is left out rather than read as a day of nothing, and a
held day on which a kind did not run is a day of nothing for that kind.

**Split by stability, OPEN-40.** The steady part of each family in each Region is bought as a family
bound plan, which saves more. Steady usage that moves between families or Regions shows in the
estate's own tenth percentile and not in any one family's, and is bought as a flexible plan. A share
with no rate under either is named and not priced, never priced at zero.

**What is held counts once it outlasts the month.** A commitment ending within `HELD_HORIZON` of the
draft no longer covers what a purchase this month is for, so it does not reduce the target.

**The ladder is measured against the commitment the plan completes.** At most `ladder_limit` of the
organization's hourly commitment, held and planned, may end in any one month. Measured against what
is held today alone, a payer holding nothing could never buy. A plan buys this month's tranche and
names the months after it, up to `MAX_TRANCHES`; what they cannot place is reported, not dropped.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Final

from finops_core.domain.commitments import CommitmentPolicy

#: The two programs a plan buys: bound to a family in a Region, or flexible across both.
FAMILY_BOUND: Final = "EC2Instance"
FLEXIBLE: Final = "Compute"

PERCENTILE: Final = Decimal("0.10")
HOURS_PER_DAY: Final = Decimal(24)
HOURS_PER_MONTH: Final = Decimal(730)
HOURS_PER_YEAR: Final = Decimal(8760)
#: The fewest days the bill must hold of the window before a tenth percentile means anything.
MIN_DAYS_HELD: Final = 14
#: A commitment ending sooner than this after the draft does not count toward the target.
HELD_HORIZON: Final = timedelta(days=30)
#: Tranches named, this month's included. A year of monthly purchases.
MAX_TRANCHES: Final = 12
#: How much of a commitment's price is paid at purchase, by payment option.
UPFRONT_SHARE: Final[Mapping[str, Decimal]] = {
    "No Upfront": Decimal(0),
    "Partial Upfront": Decimal("0.5"),
    "All Upfront": Decimal(1),
}
#: AWS sells a Savings Plan's hourly commitment to a tenth of a cent.
COMMITMENT_STEP: Final = Decimal("0.001")
MONEY: Final = Decimal("0.01")
RATE: Final = Decimal("0.0001")

#: A pot's identity: its program, and the family and Region a family bound one is held to.
PotKey = tuple[str, str | None, str | None]


@dataclass(frozen=True)
class Usage:
    """One day's eligible usage of one kind in one Region, at its on demand equivalent. Measured."""

    day: date
    region: str
    family: str
    kind: str
    on_demand: Decimal


@dataclass(frozen=True)
class Rate:
    """P9's hourly rates for one kind in one Region, in the policy's term and payment option."""

    on_demand: Decimal | None
    flexible: Decimal | None
    family_bound: Decimal | None


@dataclass(frozen=True)
class Held:
    """A commitment held, at its hourly commitment; a family bound one names family and Region."""

    hourly: Decimal
    ends: date
    family: str | None = None
    region: str | None = None


@dataclass(frozen=True)
class Unpriced:
    """A steady share no rate prices, named with why."""

    family: str | None
    region: str | None
    steady_hourly: Decimal
    reason: str


@dataclass(frozen=True)
class Line:
    """One purchase in one tranche. Every figure modelled."""

    program: str
    family: str | None
    region: str | None
    tranche: date
    hourly_commitment: Decimal
    discount_percent: Decimal
    #: The on demand spend an hour this commitment pays for.
    covers_hourly: Decimal
    monthly_saving: Decimal
    #: FEAT-055's honest figure: below this share of today's usage the commitment costs more.
    usage_floor_percent: Decimal
    upfront_cost: Decimal


@dataclass(frozen=True)
class Plan:
    """A drafted plan, or the reason there is nothing to buy."""

    window_start: date
    window_end: date
    days_held: int
    steady_hourly: Decimal | None
    held_hourly: Decimal | None
    target_hourly: Decimal | None
    beyond_hourly: Decimal | None
    lines: tuple[Line, ...]
    unpriced: tuple[Unpriced, ...]
    reason: str | None


@dataclass(frozen=True)
class _Pot:
    """What one future line must cover: its steady baseline and the discount it buys at."""

    program: str
    family: str | None
    region: str | None
    steady: Decimal
    discount: Decimal

    @property
    def key(self) -> PotKey:
        return (self.program, self.family, self.region)


def tenth_percentile(values: Sequence[Decimal]) -> Decimal:
    """The tenth percentile, interpolated between the two nearest ranks. Zero of no values."""
    ordered = sorted(values)
    if not ordered:
        return Decimal(0)
    position = PERCENTILE * (len(ordered) - 1)
    low = int(position)
    if low + 1 >= len(ordered):
        return ordered[low]
    return ordered[low] + (ordered[low + 1] - ordered[low]) * (position - low)


def first_of_month(day: date) -> date:
    return day.replace(day=1)


def months_after(month: date, count: int) -> date:
    index = month.year * 12 + month.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


def draft(
    *,
    usage: Iterable[Usage],
    rates: Mapping[tuple[str, str], Rate],
    held: Iterable[Held],
    days_held: Iterable[date],
    policy: CommitmentPolicy,
    start: date,
    window_start: date,
    window_end: date,
) -> Plan:
    """Meter's plan for the month `start` falls in, from the window's bill and P9's rates."""
    rows = tuple(usage)
    commitments = tuple(held)
    days = sorted(set(days_held) | {row.day for row in rows})
    span = (window_end - window_start).days

    def nothing(
        reason: str,
        *,
        steady: Decimal | None = None,
        held_hourly: Decimal | None = None,
        unpriced: tuple[Unpriced, ...] = (),
    ) -> Plan:
        return Plan(
            window_start=window_start,
            window_end=window_end,
            days_held=len(days),
            steady_hourly=steady,
            held_hourly=held_hourly,
            target_hourly=None if steady is None else Decimal(0),
            beyond_hourly=None,
            lines=(),
            unpriced=unpriced,
            reason=reason,
        )

    if len(days) < MIN_DAYS_HELD:
        return nothing(
            f"The bill holds {len(days)} of the last {span} days, and a steady baseline needs at "
            f"least {MIN_DAYS_HELD}."
        )
    total = _steady(rows, days, lambda _row: "estate").get("estate", Decimal(0))
    if total <= 0:
        return nothing("No eligible usage ran on every day the bill holds.", steady=Decimal(0))

    pots, unpriced, flexible = _pots(rows, rates, days, total)
    counted = tuple(one for one in commitments if one.ends > start + HELD_HORIZON)
    held_total = sum((one.hourly for one in counted), Decimal(0))
    needs = _needs(pots, counted, policy.target_coverage, flexible)
    target = sum(needs.values(), Decimal(0))
    if target <= 0:
        reason = (
            f"What is held already covers {_percent(policy.target_coverage)} percent of the "
            "steady baseline, the policy's target."
            if pots
            else "No part of the steady baseline has a rate to price it."
        )
        return nothing(
            reason, steady=_hourly(total), held_hourly=_hourly(held_total), unpriced=unpriced
        )

    lines, beyond = _ladder(needs, pots, commitments, held_total + target, policy, start)
    return Plan(
        window_start=window_start,
        window_end=window_end,
        days_held=len(days),
        steady_hourly=_hourly(total),
        held_hourly=_hourly(held_total),
        target_hourly=_hourly(target),
        beyond_hourly=_hourly(beyond),
        lines=lines,
        unpriced=unpriced,
        reason=None,
    )


def _steady[Key: Hashable](
    rows: Iterable[Usage], days: Sequence[date], key_of: Callable[[Usage], Key]
) -> dict[Key, Decimal]:
    """Each key's tenth percentile of daily spend over the held days, as an hourly figure."""
    by_key: dict[Key, dict[date, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for row in rows:
        by_key[key_of(row)][row.day] += row.on_demand
    return {
        key: tenth_percentile([daily.get(day, Decimal(0)) for day in days]) / HOURS_PER_DAY
        for key, daily in by_key.items()
    }


def _pots(
    rows: Sequence[Usage],
    rates: Mapping[tuple[str, str], Rate],
    days: Sequence[date],
    total: Decimal,
) -> tuple[list[_Pot], tuple[Unpriced, ...], Decimal | None]:
    """The family bound pots, the flexible one, the steady shares nothing prices, and the
    flexible discount, spend weighted over every kind that has one, whether or not a pot does."""
    bound: list[Usage] = []
    loose: list[Usage] = []
    bound_spend: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    bound_saving: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    flexible_spend = Decimal(0)
    flexible_saving = Decimal(0)
    for row in rows:
        rate = rates.get((row.region, row.kind)) or Rate(None, None, None)
        family_discount = _discount(rate.on_demand, rate.family_bound)
        flexible_discount = _discount(rate.on_demand, rate.flexible)
        if flexible_discount is not None:
            flexible_spend += row.on_demand
            flexible_saving += row.on_demand * flexible_discount
        if family_discount is not None:
            bound.append(row)
            bound_spend[(row.family, row.region)] += row.on_demand
            bound_saving[(row.family, row.region)] += row.on_demand * family_discount
        elif flexible_discount is None:
            loose.append(row)

    def by_place(row: Usage) -> tuple[str, str]:
        return (row.family, row.region)

    pots = [
        _Pot(
            FAMILY_BOUND,
            family,
            region,
            value,
            bound_saving[(family, region)] / bound_spend[(family, region)],
        )
        for (family, region), value in sorted(_steady(bound, days, by_place).items())
        if value > 0
    ]
    loose_steady = _steady(loose, days, by_place)
    unpriced = tuple(
        Unpriced(
            family=family,
            region=region,
            steady_hourly=_hourly(value),
            reason="P9 holds no Savings Plans rate for this family in this Region",
        )
        for (family, region), value in sorted(loose_steady.items())
        if value > 0
    )
    flexible = flexible_saving / flexible_spend if flexible_spend > 0 else None
    pool = total - sum((pot.steady for pot in pots), Decimal(0))
    pool -= sum(loose_steady.values(), Decimal(0))
    if pool <= 0:
        return pots, unpriced, flexible
    if flexible is None:
        moving = Unpriced(
            family=None,
            region=None,
            steady_hourly=_hourly(pool),
            reason="Usage that moves between families has no flexible rate to price it",
        )
        return pots, (*unpriced, moving), flexible
    return [*pots, _Pot(FLEXIBLE, None, None, pool, flexible)], unpriced, flexible


def _needs(
    pots: Sequence[_Pot],
    held: Sequence[Held],
    coverage: Decimal,
    flexible_discount: Decimal | None,
) -> dict[PotKey, Decimal]:
    """The hourly commitment each pot still needs, after what is held, in commitment terms.

    A family bound commitment counts against its own family and Region. What it holds beyond that
    target, and a family bound commitment whose family is not steady anywhere, can cover only the
    usage that moves, which is the flexible pot's. A flexible commitment covers any eligible usage:
    the flexible pot first, then each family's. Held amounts are valued on demand at the discount
    of what they land on, which for anything not landing on a family is the flexible discount.
    """
    by_key = {pot.key: pot for pot in pots}
    wanted = {key: coverage * pot.steady for key, pot in by_key.items()}
    moving_only = Decimal(0)
    anywhere = Decimal(0)
    for one in held:
        pot = by_key.get((FAMILY_BOUND, one.family, one.region)) if one.family else None
        if pot is not None:
            wanted[pot.key] -= one.hourly / (1 - pot.discount)
        elif flexible_discount is not None:
            valued = one.hourly / (1 - flexible_discount)
            if one.family:
                moving_only += valued
            else:
                anywhere += valued
    for key, value in tuple(wanted.items()):
        if value < 0:
            moving_only -= value
            wanted[key] = Decimal(0)
    flexible = (FLEXIBLE, None, None)
    if flexible in wanted:
        used = min(moving_only, wanted[flexible])
        wanted[flexible] -= used
        used = min(anywhere, wanted[flexible])
        wanted[flexible] -= used
        anywhere -= used
    for key in sorted(wanted, key=lambda key: (key[1] or "", key[2] or "")):
        used = min(anywhere, wanted[key])
        wanted[key] -= used
        anywhere -= used
    needs = {key: wanted[key] * (1 - by_key[key].discount) for key in wanted}
    return {key: value for key, value in needs.items() if value >= COMMITMENT_STEP}


def _ladder(
    needs: Mapping[PotKey, Decimal],
    pots: Sequence[_Pot],
    held: Sequence[Held],
    completed: Decimal,
    policy: CommitmentPolicy,
    start: date,
) -> tuple[tuple[Line, ...], Decimal]:
    """Tranches month by month, each kept within the ladder given what already ends then."""
    discounts = {pot.key: pot.discount for pot in pots}
    remaining = dict(needs)
    ceiling = policy.ladder_limit * completed
    lines: list[Line] = []
    month = first_of_month(start)
    for index in range(MAX_TRANCHES):
        tranche = months_after(month, index)
        ends = months_after(tranche, 12 * policy.term_years)
        ending = sum((one.hourly for one in held if first_of_month(one.ends) == ends), Decimal(0))
        left = sum(remaining.values(), Decimal(0))
        room = _step(min(left, max(ceiling - ending, Decimal(0))))
        for key, share in _shares(remaining, room).items():
            remaining[key] -= share
            lines.append(_line(key, share, discounts[key], tranche, policy))
        if sum(remaining.values(), Decimal(0)) < COMMITMENT_STEP:
            return tuple(lines), Decimal(0)
    return tuple(lines), sum(remaining.values(), Decimal(0))


def _shares(remaining: Mapping[PotKey, Decimal], room: Decimal) -> dict[PotKey, Decimal]:
    """`room` split across the pots by what each still needs, to the tenth of a cent."""
    open_ = {key: value for key, value in remaining.items() if value >= COMMITMENT_STEP}
    if room < COMMITMENT_STEP or not open_:
        return {}
    left = sum(open_.values(), Decimal(0))
    keys = sorted(open_, key=lambda key: (key[0], key[1] or "", key[2] or ""))
    shares: dict[PotKey, Decimal] = {}
    for key in keys[:-1]:
        shares[key] = min(_step(room * open_[key] / left), open_[key])
    last = keys[-1]
    shares[last] = min(room - sum(shares.values(), Decimal(0)), open_[last])
    return {key: value for key, value in shares.items() if value >= COMMITMENT_STEP}


def _line(
    key: PotKey, hourly: Decimal, discount: Decimal, tranche: date, policy: CommitmentPolicy
) -> Line:
    program, family, region = key
    covers = hourly / (1 - discount)
    return Line(
        program=program,
        family=family,
        region=region,
        tranche=tranche,
        hourly_commitment=hourly,
        discount_percent=(discount * 100).quantize(RATE),
        covers_hourly=covers.quantize(RATE),
        monthly_saving=((covers - hourly) * HOURS_PER_MONTH).quantize(MONEY),
        usage_floor_percent=((1 - discount) * 100).quantize(Decimal("0.1")),
        upfront_cost=(
            hourly * HOURS_PER_YEAR * policy.term_years * UPFRONT_SHARE[policy.payment_option]
        ).quantize(MONEY),
    )


def _discount(on_demand: Decimal | None, committed: Decimal | None) -> Decimal | None:
    """The share a committed rate takes off on demand, or None where it takes nothing off."""
    if on_demand is None or committed is None or on_demand <= 0 or committed >= on_demand:
        return None
    return 1 - committed / on_demand


def _step(value: Decimal) -> Decimal:
    return value.quantize(COMMITMENT_STEP, rounding=ROUND_DOWN)


def _hourly(value: Decimal) -> Decimal:
    return value.quantize(RATE)


def _percent(value: Decimal) -> str:
    return f"{(value * 100).normalize():f}"


#: A program as a reader knows it.
PROGRAM_NAMES: Final[Mapping[str, str]] = {
    FAMILY_BOUND: "EC2 Instance Savings Plans",
    FLEXIBLE: "Compute Savings Plans",
}


@dataclass(frozen=True)
class Advice:
    """The provider's recommendation for one Savings Plans program, as the comparison needs it."""

    program: str
    lookback_days: int
    hourly_commitment: Decimal | None
    failed: bool


def difference(
    *,
    target_coverage: Decimal,
    ladder_limit: Decimal,
    days_held: int,
    window_days: int,
    lines: Sequence[Line],
    currency: str,
    advice: Sequence[Advice],
) -> tuple[str, ...]:
    """Why Meter's plan and the provider's differ, in words, OPEN-35. The screen does not choose.

    The lookback each used, the coverage each aims for, and the ladder only Meter's applies, each a
    sentence built from the figures, so a sentence never claims a difference the figures lack.
    """
    read = [one for one in advice if not one.failed]
    lookback = max((one.lookback_days for one in read), default=None)
    said = [
        (
            f"Meter's plan is drawn from the tenth percentile of the {days_held} days the bill "
            f"holds of the last {window_days}, so a quiet day sets it; the provider looked back "
            f"{lookback} days and does not say which day set its figure."
        )
        if lookback is not None
        else "The provider's recommendation could not be read, so Meter's plan is shown alone.",
        f"Meter's aims to cover {_percent(target_coverage)} percent of the steady baseline, "
        "counting what is already held; the provider's is sized to save the most by its own "
        "estimate.",
    ]
    if lines:
        first = min(line.tranche for line in lines)
        now = sum((line.hourly_commitment for line in lines if line.tranche == first), Decimal(0))
        total = sum((line.hourly_commitment for line in lines), Decimal(0))
        bound = sum(
            (line.hourly_commitment for line in lines if line.program == FAMILY_BOUND), Decimal(0)
        )
        said.append(
            f"Only Meter's applies the ladder, at most {_percent(ladder_limit)} percent of the "
            f"commitment ending in any month: it buys {now} {currency} an hour this month of "
            f"{total} in all, and names the rest as later tranches."
        )
        said.append(
            f"Meter's buys {bound} {currency} an hour bound to families steady in one Region and "
            f"{total - bound} flexible across them."
        )
    offered = sorted((one.program, one.hourly_commitment) for one in read if one.hourly_commitment)
    if offered:
        parts = " and ".join(
            f"{value} {currency} an hour of {PROGRAM_NAMES.get(program, program)}"
            for program, value in offered
        )
        said.append(f"The provider recommends {parts}, bought at once.")
    elif read:
        said.append("The provider recommends buying no Savings Plan.")
    return tuple(said)
