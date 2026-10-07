"""Cost Explorer's periods, against fixed dates. FEAT-065.

Fixed, because a boundary tested against the day the suite runs is tested on one day in
thirty: the month to date of the first of a month, and the comparison that a short month
clamps, are exactly the days a clock based test never meets.
"""

from __future__ import annotations

from datetime import date

import pytest

from finops_core.domain.explore import (
    LONGEST_CUSTOM_DAYS,
    PeriodError,
    Window,
    previous,
    window_for,
)

TODAY = date(2026, 10, 5)


class TestThePresets:
    def test_month_to_date_runs_from_the_first_to_today(self) -> None:
        assert window_for("mtd", TODAY) == Window(date(2026, 10, 1), TODAY)

    def test_three_months_is_this_month_to_date_and_the_two_before(self) -> None:
        assert window_for("3m", TODAY) == Window(date(2026, 8, 1), TODAY)

    def test_six_months_reaches_back_across_a_year_end_when_it_has_to(self) -> None:
        assert window_for("6m", date(2026, 2, 10)) == Window(date(2025, 9, 1), date(2026, 2, 10))

    def test_twelve_months_is_a_year_ending_today(self) -> None:
        assert window_for("12m", TODAY) == Window(date(2025, 11, 1), TODAY)

    def test_year_to_date_starts_on_the_first_of_january(self) -> None:
        assert window_for("ytd", TODAY) == Window(date(2026, 1, 1), TODAY)


class TestTheComparison:
    """Like for like, as the owner chose on 2026-10-05."""

    def test_month_to_date_is_set_against_the_same_days_last_month(self) -> None:
        current = window_for("mtd", TODAY)
        assert previous(current, "mtd") == Window(date(2026, 9, 1), date(2026, 9, 5))

    def test_a_long_month_to_date_is_held_to_the_end_of_a_short_month(self) -> None:
        current = window_for("mtd", date(2026, 3, 31))
        assert previous(current, "mtd") == Window(date(2026, 2, 1), date(2026, 2, 28))

    def test_three_months_is_set_against_the_three_months_before(self) -> None:
        current = window_for("3m", TODAY)
        assert previous(current, "3m") == Window(date(2026, 5, 1), date(2026, 7, 5))

    def test_twelve_months_is_set_against_the_year_before(self) -> None:
        current = window_for("12m", TODAY)
        assert previous(current, "12m") == Window(date(2024, 11, 1), date(2025, 10, 5))

    def test_year_to_date_is_set_against_the_same_days_a_year_earlier(self) -> None:
        current = window_for("ytd", TODAY)
        assert previous(current, "ytd") == Window(date(2025, 1, 1), date(2025, 10, 5))

    def test_a_custom_period_is_set_against_as_many_days_just_before_it(self) -> None:
        current = window_for("custom", TODAY, date(2026, 9, 10), date(2026, 9, 19))
        assert current.days == 10
        assert previous(current, "custom") == Window(date(2026, 8, 31), date(2026, 9, 9))

    def test_the_comparison_never_overlaps_the_period(self) -> None:
        for preset in ("mtd", "3m", "6m", "12m", "ytd"):
            current = window_for(preset, TODAY)
            assert previous(current, preset).end < current.start, preset


class TestACustomPeriod:
    def test_one_day_is_a_period(self) -> None:
        assert window_for("custom", TODAY, TODAY, TODAY).days == 1

    @pytest.mark.parametrize(
        ("start", "end", "said"),
        [
            (None, TODAY, "needs both a start and an end"),
            (TODAY, None, "needs both a start and an end"),
            (date(2026, 9, 2), date(2026, 9, 1), "end on or after the day it starts"),
            (date(2026, 10, 1), date(2026, 10, 6), "cannot end after today"),
            (date(2025, 1, 1), date(2026, 1, 5), f"at most {LONGEST_CUSTOM_DAYS} days"),
        ],
    )
    def test_a_period_that_cannot_be_drawn_says_why(
        self, start: date | None, end: date | None, said: str
    ) -> None:
        with pytest.raises(PeriodError, match=said):
            window_for("custom", TODAY, start, end)

    def test_the_longest_custom_period_is_allowed(self) -> None:
        start = date(2025, 10, 5)
        assert window_for("custom", TODAY, start, TODAY).days == LONGEST_CUSTOM_DAYS
