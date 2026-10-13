"""The effective savings rate, measured from the bill. FEAT-087, TASK-P14-004.

P14 spec section 5.7. One minus Effective Cost over List Cost: what the organization paid against
what the same usage would have cost at the on demand rate, the KPI library's definition the
overview tile already uses. Measured, because both sums are the bill's own.

**Over the lines that carry a List Cost, and saying how much does not.** A sum of Effective Cost
over every line against List Cost over some of them would overstate the discount by every line
without one. So both sums are over the same lines, and the month says how many lines it left out
and what they cost, so a reader can see how much of the bill the rate speaks for.

**No List Cost is no rate, never a rate of zero.** A month whose lines carry none has nothing to
measure against; drawn as nought, it would claim the discounts saved nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

#: Four places of a fraction: a rate to a hundredth of a percent.
RATE_PLACES: Final = Decimal("0.0001")

NO_LIST_COST: Final = (
    "No usage line this month carries a List Cost, so there is no on demand equivalent to "
    "measure the rate against"
)


@dataclass(frozen=True, kw_only=True)
class SavingsRateMonth:
    """One billing month's rate, with the sums it came from and what it left out."""

    period: date
    #: Over the lines that carry a List Cost.
    effective_cost: Decimal
    list_cost: Decimal
    #: Null where no line carries a List Cost; may be below zero where usage cost more than list.
    rate: Decimal | None
    lines: int
    lines_without_list_cost: int
    effective_cost_without_list_cost: Decimal
    reason: str | None


def savings_rate(
    period: date,
    *,
    effective_cost: Decimal,
    list_cost: Decimal,
    lines: int,
    lines_without_list_cost: int,
    effective_cost_without_list_cost: Decimal,
) -> SavingsRateMonth:
    """The month's rate, or none with the reason, never nought for want of a List Cost."""
    measurable = lines > lines_without_list_cost and list_cost > 0
    rate = (Decimal(1) - effective_cost / list_cost).quantize(RATE_PLACES) if measurable else None
    return SavingsRateMonth(
        period=period,
        effective_cost=effective_cost,
        list_cost=list_cost,
        rate=rate,
        lines=lines,
        lines_without_list_cost=lines_without_list_cost,
        effective_cost_without_list_cost=effective_cost_without_list_cost,
        reason=None if measurable else NO_LIST_COST,
    )
