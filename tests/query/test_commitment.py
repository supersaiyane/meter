"""What an uncovered baseline is worth, and the four times there is nothing to say.

FEAT-055, TASK-P1-022. Pure.

The case that carries this file is the usage floor, because it is the number that decides
whether buying a commitment was a mistake and it is the number a coverage chart cannot show. A
commitment obligates its whole term whether or not the usage continues, so a finding that
published only the saving would be recommending a multi year obligation while withholding the
one figure that says what going wrong looks like.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from finops_query.commitment import Commitment, assess, rationale

START = date(2026, 8, 1)
END = date(2026, 8, 31)

DISCOUNT = Decimal("30")
TERM = 12
FLOOR = Decimal("25")


def baseline(
    eligible: str = "10000",
    covered: str = "4000",
    *,
    window_start: date = START,
    window_end: date = END,
) -> Commitment | None:
    """`assess` under the rules in `.env.example`, so every case reads as one line.

    Named arguments rather than a dict splatted into the call: a dict of mixed value types is
    `dict[str, object]`, and splatting it defeats the type checker on exactly the arguments
    worth checking, a Decimal rate and two integer counts.
    """
    return assess(
        eligible=Decimal(eligible),
        covered=Decimal(covered),
        window_start=window_start,
        window_end=window_end,
        discount_percent=DISCOUNT,
        term_months=TERM,
        minimum_monthly_saving=FLOOR,
    )


def test_the_saving_is_the_discount_on_what_was_not_covered() -> None:
    """Six thousand uncovered over thirty days, at thirty percent, scaled to an average month.

    A rate rather than a sum, because the coverage window is whatever the collector read and is
    never exactly one month. Treating a twenty eight day window as a month would understate
    February by eight percent and nothing would notice.
    """
    found = baseline()
    assert found is not None
    assert found.uncovered == Decimal("6000")
    # 6000 / 30 days * 30.44 days * 0.30
    assert found.monthly_saving == Decimal("1826.4000")


def test_the_usage_floor_is_published_and_is_the_decision() -> None:
    """The case this module exists for. At a thirty percent discount the commitment beats on
    demand while usage stays above seventy percent of today's, and below that the unused
    commitment costs more than the discount saved.

    This is the number a coverage percentage cannot express, and it is what makes the finding a
    decision rather than an observation.
    """
    found = baseline()
    assert found is not None
    assert found.usage_floor_percent == Decimal("70.0")
    assert found.term_months == 12


def test_the_coverage_already_achieved_is_reported_beside_the_gap() -> None:
    found = baseline()
    assert found is not None
    assert found.covered_percent == Decimal("40.0")


def test_a_larger_discount_lowers_the_floor_and_raises_the_saving() -> None:
    """The two move in opposite directions, which is the shape of the trade. A test asserting
    only the saving would pass for an implementation that had the floor backwards."""
    generous = assess(
        eligible=Decimal("10000"),
        covered=Decimal("0"),
        window_start=START,
        window_end=END,
        discount_percent=Decimal("50"),
        term_months=36,
        minimum_monthly_saving=Decimal("25"),
    )
    assert generous is not None
    assert generous.usage_floor_percent == Decimal("50.0")
    thin = assess(
        eligible=Decimal("10000"),
        covered=Decimal("0"),
        window_start=START,
        window_end=END,
        discount_percent=Decimal("10"),
        term_months=36,
        minimum_monthly_saving=Decimal("25"),
    )
    assert thin is not None
    assert thin.usage_floor_percent == Decimal("90.0")
    assert thin.monthly_saving < generous.monthly_saving


# --- the four refusals ------------------------------------------------------


def test_a_fully_covered_baseline_is_not_a_finding() -> None:
    """The good outcome. A recommendation here would ask somebody to act on success."""
    assert baseline(eligible="10000", covered="10000") is None


def test_over_covered_spend_is_not_a_negative_finding() -> None:
    """Covered above eligible happens when a commitment spans a dimension the window splits.
    A negative uncovered figure would produce a negative saving, which would rank as the best
    finding on the list under a sort by money."""
    assert baseline(eligible="10000", covered="12000") is None


def test_nothing_eligible_is_not_a_finding() -> None:
    """No baseline to cover, which is different from a covered one and equally not an action."""
    assert baseline(eligible="0", covered="0") is None


def test_a_saving_below_the_floor_is_not_a_finding() -> None:
    """Advising somebody to sign a multi year obligation to save a few dollars a month is
    advice that costs more to act on than it returns.

    Fifty uncovered over thirty days is 15.22 USD a month at thirty percent, below the floor of
    twenty five. A hundred is 30.44 and clears it, which is worth noting because the first draft
    of this case used a hundred and passed for the wrong reason.
    """
    assert baseline(eligible="50", covered="0") is None
    assert baseline(eligible="100", covered="0") is not None


@pytest.mark.parametrize(
    ("start", "end"),
    [(START, START), (END, START)],
)
def test_a_window_that_is_not_a_window_is_refused(start: date, end: date) -> None:
    """A rate cannot be computed from zero days, and a reversed window would produce a negative
    one. Refused rather than divided by, because the traceback from the division would name
    arithmetic when the fault is the window."""
    assert baseline("10000", "0", window_start=start, window_end=end) is None


# --- the working, published -------------------------------------------------


def test_the_rationale_says_the_discount_was_configured_rather_than_quoted() -> None:
    """ADR-0007. The saving rests on a rate nobody has been quoted, and a reader deciding to
    commit real money is entitled to know which half of the number is an assumption."""
    found = baseline()
    assert found is not None
    said = rationale(found, dimension="COMPUTE", dimension_value="all accounts")
    assert "modelled from a configured discount rather than from a quote" in said


def test_the_rationale_names_the_term_the_floor_and_the_window() -> None:
    """Three facts a reader needs and none of which is the saving. The term is how long a wrong
    decision lasts, the floor is what wrong looks like, and the window is what the claim rests
    on."""
    found = baseline()
    assert found is not None
    said = rationale(found, dimension="COMPUTE", dimension_value="all accounts")
    assert "obligates 12 months" in said
    assert "above 70.0 percent of today's" in said
    assert "2026-08-01" in said and "2026-08-31" in said
