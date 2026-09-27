"""The pace rule, and the four times it refuses to say green.

FEAT-060. Pure.

A budget status is the one figure in this product an executive will look at and nothing else,
so the cases that matter are the ones where it declines to be green. Three separate sources
put a red amber green budget status at the top of the executive view, and every one of them is
describing a light that somebody acts on without reading the number beside it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from finops_core.domain.budget import BudgetStatus, elapsed_fraction, status_of

MARGIN = Decimal("0.1")


def status(
    *,
    limit: str = "1000",
    actual: str | None = "500",
    elapsed: str = "0.5",
    joinable: bool = True,
) -> BudgetStatus:
    return status_of(
        limit=Decimal(limit),
        actual=None if actual is None else Decimal(actual),
        elapsed=Decimal(elapsed),
        at_risk_when_ahead_by=MARGIN,
        joinable=joinable,
    )


# --- the four refusals to be green ------------------------------------------


def test_no_collected_spend_is_unknown_rather_than_under() -> None:
    """An estate whose first ingest has not run has not spent nothing. Rendering that as under
    budget is the same defect as rendering a failed collection as a zero, which is the thing
    this product exists to stop."""
    assert status(actual=None) is BudgetStatus.UNKNOWN


def test_a_scope_we_cannot_join_is_unknown_rather_than_under() -> None:
    """A budget drawn around a tag or a filter expression we cannot reproduce has no honest
    actual. Matching it against the wrong spend would be worse than not showing it, because a
    green light on the wrong number is acted on."""
    assert status(joinable=False) is BudgetStatus.UNKNOWN


def test_a_period_that_has_not_started_is_unknown() -> None:
    """Nought spent of a budget on day zero is not under budget, it is not yet anything. The
    pace rule divides by elapsed and would otherwise report every new period as healthy."""
    assert status(elapsed="0") is BudgetStatus.UNKNOWN


def test_a_budget_of_zero_is_unknown_rather_than_over() -> None:
    """A limit of nought cannot be under and calling it over says somebody overspent when what
    happened is that nobody set a budget."""
    assert status(limit="0", actual="0") is BudgetStatus.UNKNOWN


# --- the three it does answer ------------------------------------------------


def test_spending_at_pace_is_under() -> None:
    """Half the budget, half the month. The ordinary case, and it has to be quiet: a status
    that shouts at the ordinary case is a status people turn off."""
    assert status(actual="500", elapsed="0.5") is BudgetStatus.UNDER


def test_ahead_of_pace_by_more_than_the_margin_is_at_risk() -> None:
    """Eighty percent spent, sixty percent through. The only status that asks somebody to do
    something, which is why the margin producing it is configuration rather than a constant."""
    assert status(actual="800", elapsed="0.6") is BudgetStatus.AT_RISK


def test_ahead_of_pace_by_less_than_the_margin_is_still_under() -> None:
    """Spending is lumpy and a budget that flips to amber on a Tuesday because an annual
    invoice landed is a budget nobody trusts by Friday. The margin is what absorbs that."""
    assert status(actual="650", elapsed="0.6") is BudgetStatus.UNDER


def test_spending_the_whole_limit_is_over_whatever_the_pace() -> None:
    """Over is over. A budget fully spent on day two is not at risk of being exceeded, it has
    been, and the pace rule must not soften that."""
    assert status(actual="1000", elapsed="0.05") is BudgetStatus.OVER
    assert status(actual="1200", elapsed="0.99") is BudgetStatus.OVER


def test_the_margin_moves_the_boundary() -> None:
    """Asserted by moving it, because a threshold tested at one value is a threshold whose
    direction is a guess."""
    strict = status_of(
        limit=Decimal("1000"),
        actual=Decimal("650"),
        elapsed=Decimal("0.6"),
        at_risk_when_ahead_by=Decimal("0.01"),
    )
    assert strict is BudgetStatus.AT_RISK


# --- how far through a period we are -----------------------------------------


def test_elapsed_is_clamped_at_both_ends() -> None:
    """A period that has not started is nought rather than negative, and one that has closed is
    one rather than more. A pace rule fed a negative denominator is confidently wrong."""
    start, end = date(2026, 9, 1), date(2026, 10, 1)
    assert elapsed_fraction(start=start, end=end, today=date(2026, 8, 20)) == Decimal("0")
    assert elapsed_fraction(start=start, end=end, today=date(2026, 11, 5)) == Decimal("1")


def test_elapsed_is_the_fraction_of_days_through() -> None:
    start, end = date(2026, 9, 1), date(2026, 10, 1)
    assert elapsed_fraction(start=start, end=end, today=date(2026, 9, 16)) == Decimal("0.5")


@pytest.mark.parametrize(
    ("start", "end"),
    [(date(2026, 9, 1), date(2026, 9, 1)), (date(2026, 10, 1), date(2026, 9, 1))],
)
def test_a_period_that_is_not_a_period_is_nought(start: date, end: date) -> None:
    """Which makes the status UNKNOWN rather than dividing by zero, so a malformed budget from
    a provider is a thing the screen reports rather than a stack trace."""
    assert elapsed_fraction(start=start, end=end, today=date(2026, 9, 15)) == Decimal("0")
