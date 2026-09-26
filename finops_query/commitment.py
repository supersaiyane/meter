"""What an uncovered baseline would be worth, and what committing to it risks.

FEAT-055, TASK-P1-022. Adopted from the 2026-09-26 IBM Turbonomic review, whose commitment
work turns a coverage gap into an action rather than a chart.

**Why a chart was not enough.** We already report commitment coverage. A percentage on a chart
is a fact and nobody owns it; a recommendation has an owner, a lifecycle and a realized saving
measured afterwards, which is machinery P3 built and nothing in P1 used. A chart is read once a
quarter and a finding is worked.

**The deviation from the plan, stated rather than quietly made.** TASK-P1-022 asks the
rationale to publish a break even month. For the instrument this is about, a no upfront
commitment billed monthly, the break even month is one, always, for every finding: the discount
applies from the first invoice. A number that is the same on every row is not evidence, and
publishing it would have satisfied the criterion while telling a reader nothing.

The honest number is the other one, and it is the number that decides whether a commitment was
a mistake: **the usage floor**. A commitment obligates the whole term whether or not the usage
continues. At a discount of d, the commitment beats on demand for as long as usage stays above
`1 - d` of today's, and below that the unused commitment costs more than the discount saved. A
thirty percent discount means usage may fall by thirty percent before the decision goes
negative, and that is a sentence somebody can hold a capacity plan against.

**Nothing here recommends an instrument.** Which Savings Plan or Reserved Instance to buy is a
procurement decision with constraints Meter does not hold, and a tool that picked one would be
wrong in a way nobody could see until the term ended. The finding says a baseline is uncovered
and what covering it would be worth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

#: Days in an average month. The coverage window is whatever the collector read, usually a
#: month but never exactly one, so a monthly figure is a rate rather than a sum.
DAYS_PER_MONTH = Decimal("30.44")


@dataclass(frozen=True)
class Commitment:
    """What committing to one uncovered baseline is worth, and what it risks.

    Every field is modelled. `eligible` and `covered` are measured, from the bill, and every
    number derived from them here depends on a discount rate that is a configured assumption
    about a price nobody has been quoted.
    """

    #: Spend a commitment could have discounted, over the window, measured.
    eligible: Decimal
    #: Of that, spend a commitment did discount, measured.
    covered: Decimal
    #: Modelled. The discount that would have applied to the rest.
    monthly_saving: Decimal
    #: How far usage may fall before the commitment costs more than it saves, as a percentage
    #: of today's. The number that decides whether this was a mistake.
    usage_floor_percent: Decimal
    term_months: int
    window_start: date
    window_end: date

    @property
    def uncovered(self) -> Decimal:
        return self.eligible - self.covered

    @property
    def covered_percent(self) -> Decimal:
        """How much of the eligible spend was already discounted.

        Zero eligible spend returns zero rather than raising, because a dimension with nothing
        eligible is a real state of a real estate and it is the caller's `assess` that refuses
        to build a finding from it.
        """
        if self.eligible == 0:
            return Decimal("0")
        return (self.covered / self.eligible * 100).quantize(Decimal("0.1"))


def assess(
    *,
    eligible: Decimal,
    covered: Decimal,
    window_start: date,
    window_end: date,
    discount_percent: Decimal,
    term_months: int,
    minimum_monthly_saving: Decimal,
) -> Commitment | None:
    """One uncovered baseline, or None where there is nothing honest to say.

    None in four cases, and each is a different thing that is not a finding:

    - the window is not a window, so a rate cannot be computed from it
    - nothing was eligible, so there is no baseline to cover
    - nothing is uncovered, which is the good outcome and not a recommendation
    - the modelled saving is below the floor, because advising somebody to sign a multi year
      obligation to save a few dollars a month is advice that costs more to act on than it
      returns

    The last is a threshold rather than a judgement about size, and it is configuration for the
    reason ADR-0012 gives about cadence: a number in code is one nobody can argue with.
    """
    days = (window_end - window_start).days
    if days <= 0:
        return None
    if eligible <= 0:
        return None
    uncovered = eligible - covered
    if uncovered <= 0:
        return None

    rate = discount_percent / Decimal("100")
    monthly_uncovered = uncovered / Decimal(days) * DAYS_PER_MONTH
    saving = (monthly_uncovered * rate).quantize(Decimal("0.0001"))
    if saving < minimum_monthly_saving:
        return None

    return Commitment(
        eligible=eligible,
        covered=covered,
        monthly_saving=saving,
        # At a discount of d, the commitment beats on demand while usage stays above 1 - d of
        # today's. Expressed as a percentage because that is how a capacity plan is written,
        # and it is the only number on this finding that says what going wrong looks like.
        usage_floor_percent=((Decimal("1") - rate) * 100).quantize(Decimal("0.1")),
        term_months=term_months,
        window_start=window_start,
        window_end=window_end,
    )


def rationale(commitment: Commitment, *, dimension: str, dimension_value: str) -> str:
    """The working, published. ADR-0007: a modelled number states how it was reached.

    The order is deliberate. What is uncovered, then what it would save, then what it would
    cost to be wrong. A reader who stops after the second sentence has the number; a reader who
    stops after the third has the decision.
    """
    return (
        f"{commitment.covered_percent} percent of eligible {dimension} spend for "
        f"{dimension_value} was covered by a commitment between {commitment.window_start} and "
        f"{commitment.window_end}, leaving {commitment.uncovered} USD uncovered over that "
        f"window. Covering it would save about {commitment.monthly_saving} USD a month, "
        f"modelled from a configured discount rather than from a quote. A commitment "
        f"obligates {commitment.term_months} months whether or not the usage continues, so "
        f"this is worth doing while usage stays above {commitment.usage_floor_percent} "
        f"percent of today's for the whole term, and costs more than it saves below that."
    )
