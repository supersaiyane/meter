"""Whether a verified saving held, month by month. TASK-P11-007, P11 spec section 5.5."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from finops_query.ledger import Billed, MonthState, closed_months, held, judge, next_month

#: Thirty dollars a day before the change: a thirty day month expected 900 without it.
DAILY = Decimal("30")
OCTOBER, NOVEMBER, DECEMBER = date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1)


@pytest.mark.parametrize(
    ("month", "after"),
    [
        (date(2026, 10, 20), NOVEMBER),
        (DECEMBER, date(2027, 1, 1)),
        (date(2027, 1, 31), date(2027, 2, 1)),
    ],
)
def test_the_next_month_starts_on_its_first_day(month: date, after: date) -> None:
    assert next_month(month) == after


@pytest.mark.parametrize(
    ("verified_on", "today", "months"),
    [
        # A saving verified mid month is first judged on the whole month after.
        (date(2026, 9, 20), date(2026, 11, 1), (OCTOBER,)),
        (date(2026, 9, 20), date(2026, 10, 31), ()),
        (OCTOBER, date(2026, 12, 2), (OCTOBER, NOVEMBER)),
    ],
)
def test_only_months_wholly_after_verification_and_closed_are_judged(
    verified_on: date, today: date, months: tuple[date, ...]
) -> None:
    assert closed_months(verified_on, today) == months


def test_a_billed_month_cheaper_than_before_held_its_saving() -> None:
    one = judge(NOVEMBER, DAILY, Billed(cost=Decimal("600"), rows=40))
    assert (one.state, one.cost, one.saving) == (MonthState.HELD, Decimal("600"), Decimal("300"))


def test_a_resource_with_no_charge_in_a_billed_month_cost_nothing() -> None:
    # Deleted, so the bill names it nowhere, while the account's bill is there: a measured zero.
    one = judge(OCTOBER, DAILY, Billed(cost=Decimal("0"), rows=12))
    assert (one.state, one.saving) == (MonthState.HELD, Decimal("930"))


@pytest.mark.parametrize("cost", [Decimal("900"), Decimal("950")])
def test_a_month_that_cost_as_much_as_before_regressed(cost: Decimal) -> None:
    one = judge(NOVEMBER, DAILY, Billed(cost=cost, rows=40))
    assert (one.state, one.cost) == (MonthState.REGRESSED, cost)
    assert one.saving is not None and one.saving <= 0


@pytest.mark.parametrize("billed", [None, Billed(cost=Decimal("0"), rows=0)])
def test_a_month_the_bill_holds_nothing_for_is_unobserved_never_nought(
    billed: Billed | None,
) -> None:
    one = judge(OCTOBER, DAILY, billed)
    assert (one.state, one.cost, one.saving) == (MonthState.UNOBSERVED, None, None)


def test_accrual_stops_at_a_regressed_month_and_not_an_unobserved_one() -> None:
    billed = {
        OCTOBER: Billed(cost=Decimal("500"), rows=10),
        DECEMBER: Billed(cost=Decimal("2000"), rows=10),
        date(2027, 1, 1): Billed(cost=Decimal("100"), rows=10),
    }
    found = held(date(2026, 9, 20), date(2027, 3, 1), DAILY, billed)
    assert [(one.month, one.state) for one in found] == [
        (OCTOBER, MonthState.HELD),
        (NOVEMBER, MonthState.UNOBSERVED),
        (DECEMBER, MonthState.REGRESSED),
    ]
