"""Whether a verified saving held, month by month after it verified. FEAT-078, TASK-P11-007.

P11 spec section 5.5. A month is judged once it has closed, against the cost before the change at
FEAT-029's own daily rate: the before window's cost over its days, times the days in the month.

- **HELD**: the account's bill holds rows for the month and the resource cost less than that. The
  saving is the difference, measured, and a resource with no charge in a billed month cost nothing,
  as FEAT-029 reads a missing charge.
- **REGRESSED**: billed, and the resource cost as much or more. The credit stops accruing here, and
  no later month is judged, because a saving that came back is not the same saving holding.
- **UNOBSERVED**: the account's bill holds no rows for the month at all, so nothing can be said,
  and the month carries neither a cost nor a saving. Never nought, constraint 5.

A credit's total is the sum of its held months, what the bill showed it kept saving, never a
figure projected forward.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class MonthState(StrEnum):
    """What one closed month says, the database's `ck_savings_credit_month__state` values."""

    HELD = "HELD"
    REGRESSED = "REGRESSED"
    UNOBSERVED = "UNOBSERVED"


@dataclass(frozen=True)
class Billed:
    """One month of the bill: the resource's cost, and how many rows the account's bill holds."""

    cost: Decimal
    rows: int


@dataclass(frozen=True)
class MonthHeld:
    """One closed month after verification. Cost and saving are absent exactly when unobserved."""

    month: date
    state: MonthState
    cost: Decimal | None
    saving: Decimal | None


def next_month(month: date) -> date:
    """The first day of the month after the one `month` falls in."""
    return date(month.year + month.month // 12, month.month % 12 + 1, 1)


def closed_months(verified_on: date, today: date) -> tuple[date, ...]:
    """The first day of each month wholly after verification that has closed by `today`."""
    month = verified_on if verified_on.day == 1 else next_month(verified_on)
    found: list[date] = []
    while next_month(month) <= today:
        found.append(month)
        month = next_month(month)
    return tuple(found)


def judge(month: date, daily_before: Decimal, billed: Billed | None) -> MonthHeld:
    """One closed month against the cost before the change, at the before window's daily rate."""
    if billed is None or billed.rows == 0:
        return MonthHeld(month=month, state=MonthState.UNOBSERVED, cost=None, saving=None)
    expected = daily_before * (next_month(month) - month).days
    saving = expected - billed.cost
    state = MonthState.HELD if saving > 0 else MonthState.REGRESSED
    return MonthHeld(month=month, state=state, cost=billed.cost, saving=saving)


def held(
    verified_on: date,
    today: date,
    daily_before: Decimal,
    billed: Mapping[date, Billed],
) -> tuple[MonthHeld, ...]:
    """Every closed month since verification, up to and including the first that regressed."""
    found: list[MonthHeld] = []
    for month in closed_months(verified_on, today):
        one = judge(month, daily_before, billed.get(month))
        found.append(one)
        if one.state is MonthState.REGRESSED:
            break
    return tuple(found)
