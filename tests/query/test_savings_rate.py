"""The effective savings rate's arithmetic. TASK-P14-004, FEAT-087."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from finops_query.savings_rate import NO_LIST_COST, savings_rate

PERIOD = date(2026, 9, 1)


def test_the_rate_is_one_minus_effective_over_list_on_the_same_lines() -> None:
    month = savings_rate(
        PERIOD,
        effective_cost=Decimal("800"),
        list_cost=Decimal("1000"),
        lines=10,
        lines_without_list_cost=2,
        effective_cost_without_list_cost=Decimal("50"),
    )
    assert (month.rate, month.reason) == (Decimal("0.2000"), None)
    assert (month.lines_without_list_cost, month.effective_cost_without_list_cost) == (
        2,
        Decimal("50"),
    )


def test_a_month_with_no_list_cost_has_no_rate_and_says_why_never_nought() -> None:
    month = savings_rate(
        PERIOD,
        effective_cost=Decimal(0),
        list_cost=Decimal(0),
        lines=4,
        lines_without_list_cost=4,
        effective_cost_without_list_cost=Decimal("120"),
    )
    assert (month.rate, month.reason) == (None, NO_LIST_COST)


def test_usage_dearer_than_list_is_a_rate_below_zero_not_a_rate_hidden() -> None:
    month = savings_rate(
        PERIOD,
        effective_cost=Decimal("110"),
        list_cost=Decimal("100"),
        lines=1,
        lines_without_list_cost=0,
        effective_cost_without_list_cost=Decimal(0),
    )
    assert month.rate == Decimal("-0.1000")
