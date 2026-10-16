"""An estimate set against the bill. TASK-P16-007, FEAT-097, spec section 5.6.

The window skips the day the resource was seen and its first full day, then runs thirty days; it is
judged once the bill reaches its end. List cost scaled to 730 hours within 10 percent of the
estimate is right, at the boundary too; a window with no row, rows with no list cost, or a nought
estimate is not compared, with the reason. Accuracy counts only what was judged.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from finops_query.estimate_accuracy import (
    ALL,
    Accuracy,
    Billed,
    Verdict,
    Window,
    accuracy,
    billed_through,
    judge,
    unseen_too_long,
    window_after,
)

SEEN = datetime(2026, 10, 10, 15, 0, tzinfo=UTC)


def billed(list_cost: str, effective_cost: str | None = None, rows: int = 30) -> Billed:
    return Billed(
        rows=rows,
        listed_rows=rows,
        list_cost=Decimal(list_cost),
        effective_cost=Decimal(effective_cost or list_cost),
    )


def test_the_window_skips_the_day_seen_and_its_first_full_day_then_runs_thirty() -> None:
    assert window_after(SEEN) == Window(date(2026, 10, 12), date(2026, 11, 11))


@pytest.mark.parametrize(
    ("last_billed", "through"),
    [
        (None, False),
        (date(2026, 11, 9), False),
        (date(2026, 11, 10), True),
        (date(2026, 12, 1), True),
    ],
)
def test_a_window_is_judged_once_the_bill_reaches_its_last_day(
    last_billed: date | None, through: bool
) -> None:
    assert billed_through(window_after(SEEN), last_billed) is through


def test_a_resource_unseen_sixty_days_after_its_merge_is_given_up_on() -> None:
    assert unseen_too_long(SEEN, SEEN + timedelta(days=60)) is False
    assert unseen_too_long(SEEN, SEEN + timedelta(days=61)) is True


@pytest.mark.parametrize(
    ("estimate", "list_cost", "verdict"),
    [
        ("82.51", "81.36", Verdict.WITHIN),
        ("73", "79.2", Verdict.WITHIN),
        ("82.51", "100", Verdict.ABOVE),
        ("82.51", "60", Verdict.BELOW),
    ],
)
def test_the_list_cost_scaled_to_the_estimates_month_decides_the_verdict(
    estimate: str, list_cost: str, verdict: Verdict
) -> None:
    found = judge(Decimal(estimate), billed(list_cost))
    assert found.verdict is verdict
    assert found.list_monthly == Decimal(list_cost) * 730 / 720
    assert found.reason is None


def test_exactly_ten_percent_above_is_within_and_effective_cost_is_kept_beside() -> None:
    found = judge(Decimal("73"), billed("79.2", effective_cost="57.6"))
    assert (found.verdict, found.list_monthly, found.variance_percent) == (
        Verdict.WITHIN,
        Decimal("80.3"),
        Decimal("10.0"),
    )
    assert found.effective_monthly == Decimal("58.4")


@pytest.mark.parametrize(
    ("estimate", "seen", "says"),
    [
        ("10", Billed(0, 0, Decimal(0), Decimal(0)), "no row for it in its thirty days, NoData"),
        ("10", Billed(10, 9, Decimal(5), Decimal(5)), "a list cost for 9 of its 10 rows"),
        ("0", billed("5"), "its estimate was nought"),
    ],
)
def test_what_cannot_be_compared_says_why_and_carries_no_figure(
    estimate: str, seen: Billed, says: str
) -> None:
    found = judge(Decimal(estimate), seen)
    assert found.verdict is Verdict.NOT_COMPARED
    assert found.reason is not None and says in found.reason
    assert (found.list_monthly, found.variance_percent) == (None, None)


def test_accuracy_is_by_type_and_in_all_from_the_judged_alone() -> None:
    found = accuracy(
        [
            ("aws_instance", Verdict.WITHIN, Decimal("2")),
            ("aws_instance", Verdict.ABOVE, Decimal("20")),
            ("aws_ebs_volume", Verdict.BELOW, Decimal("-30")),
            ("aws_instance", Verdict.PENDING, None),
            ("aws_db_instance", Verdict.NOT_COMPARED, None),
        ]
    )
    assert found == (
        Accuracy("aws_ebs_volume", 1, 0, Decimal("30")),
        Accuracy("aws_instance", 2, 1, Decimal("11")),
        Accuracy(ALL, 3, 1, Decimal("20")),
    )
    assert accuracy([]) == (Accuracy(ALL, 0, 0, None),)
