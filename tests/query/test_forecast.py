"""The spend forecast against fixed series. FEAT-066, TASK-P8-008.

Every series here is built so the right answer can be worked out by hand: a week that repeats,
a month that misses on purpose, five dollars billed on a known Friday. A forecast tested against
realistic noise proves it runs; one tested against a series whose answer is known proves it is
right.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

import pytest

from finops_query.forecast import (
    MAX_MEDIAN_MISS,
    MIN_HELD_OUT,
    PROFILE_WEEKS,
    HeldOut,
    ahead,
    month_end,
    profile,
    quantile,
)

WEEKDAY = Decimal("100")
WEEKEND = Decimal("40")


def series(
    start: date, end: date, cost: Callable[[date], int] | None = None
) -> dict[date, Decimal]:
    """A day by day series: weekdays at 100 and weekends at 40 unless told otherwise."""
    days: dict[date, Decimal] = {}
    day = start
    while day <= end:
        if cost is not None:
            days[day] = Decimal(cost(day))
        else:
            days[day] = WEEKEND if day.weekday() >= 5 else WEEKDAY
        day += timedelta(days=1)
    return days


def month_total(month: date) -> Decimal:
    """What the default series costs over a whole calendar month."""
    following = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    day, total = month, Decimal(0)
    while day < following:
        total += WEEKEND if day.weekday() >= 5 else WEEKDAY
        day += timedelta(days=1)
    return total


class TestTheProfile:
    def test_is_each_weekday_averaged_over_the_weeks_before_the_cut(self) -> None:
        daily = series(date(2026, 7, 1), date(2026, 10, 4))
        weekdays = profile(daily, date(2026, 10, 5))
        assert weekdays is not None
        assert [weekdays[day] for day in range(7)] == [WEEKDAY] * 5 + [WEEKEND] * 2

    def test_is_refused_where_the_weeks_before_the_cut_were_not_all_collected(self) -> None:
        cut = date(2026, 10, 5)
        daily = series(cut - timedelta(days=PROFILE_WEEKS * 7 - 1), cut - timedelta(days=1))
        assert profile(daily, cut) is None


class TestTheMonthEnd:
    def test_is_shown_as_a_range_once_three_months_test_it_well(self) -> None:
        daily = series(date(2026, 1, 1), date(2026, 10, 4))
        outcome = month_end(daily, date(2026, 10, 1), date(2026, 10, 5))
        assert outcome.withheld is None
        assert outcome.figure is not None
        # A week that repeats is forecast exactly, so every test missed by nothing and the
        # range closes on the true total.
        assert outcome.figure.low == outcome.figure.high == month_total(date(2026, 10, 1))
        assert outcome.median_miss == Decimal(0)
        assert len(outcome.tests) >= MIN_HELD_OUT

    def test_counts_what_is_billed_and_forecasts_only_the_days_after_it(self) -> None:
        daily = series(date(2026, 1, 1), date(2026, 10, 4))
        # Five dollars more on Friday 2 October. It counts once as billed, and an eighth of it
        # again on each of the four Fridays left, because a billed Friday is one of the eight
        # the profile averages.
        daily[date(2026, 10, 2)] += Decimal(5)
        outcome = month_end(daily, date(2026, 10, 1), date(2026, 10, 5))
        assert outcome.figure is not None
        assert outcome.figure.low == month_total(date(2026, 10, 1)) + Decimal("7.5")

    def test_is_withheld_with_fewer_than_three_months_to_test_on(self) -> None:
        daily = series(date(2026, 7, 1), date(2026, 10, 4))
        outcome = month_end(daily, date(2026, 10, 1), date(2026, 10, 5))
        assert outcome.figure is None
        assert outcome.withheld is not None
        assert f"tested on {MIN_HELD_OUT} complete months" in outcome.withheld

    def test_is_withheld_when_it_missed_by_more_than_the_floor_at_the_median(self) -> None:
        # Each month doubles the last, so a profile of the weeks before always falls short.
        def doubling(day: date) -> int:
            return int(2 ** (day.year * 12 + day.month - (2026 * 12 + 1)))

        daily = series(date(2026, 1, 1), date(2026, 10, 4), doubling)
        outcome = month_end(daily, date(2026, 10, 1), date(2026, 10, 5))
        assert outcome.figure is None
        assert outcome.median_miss is not None
        assert outcome.median_miss > MAX_MEDIAN_MISS
        assert outcome.withheld is not None
        assert "above the 15 percent" in outcome.withheld

    def test_is_withheld_when_the_month_is_already_billed_in_full(self) -> None:
        daily = series(date(2026, 1, 1), date(2026, 10, 31))
        outcome = month_end(daily, date(2026, 10, 1), date(2026, 11, 1))
        assert outcome.figure is None
        assert outcome.withheld is not None
        assert "billed in full" in outcome.withheld

    def test_draws_a_cumulative_band_that_ends_on_the_range(self) -> None:
        daily = series(date(2026, 1, 1), date(2026, 10, 4))
        # One September spike, so the tests disagree and the band has width.
        daily[date(2026, 9, 7)] += Decimal(300)
        outcome = month_end(daily, date(2026, 10, 1), date(2026, 10, 5))
        assert outcome.figure is not None
        assert outcome.figure.high > outcome.figure.low
        days = {point.day: point for point in outcome.days}
        assert days[date(2026, 10, 4)].actual is not None
        assert days[date(2026, 10, 4)].low is None
        assert days[date(2026, 10, 5)].actual is None
        last = days[date(2026, 10, 31)]
        assert (last.low, last.high) == (outcome.figure.low, outcome.figure.high)


class TestTheMonthsAhead:
    def test_are_each_forecast_and_tested_at_their_own_distance(self) -> None:
        daily = series(date(2025, 6, 1), date(2026, 10, 4))
        outcomes = ahead(daily, date(2026, 10, 1), date(2026, 10, 5))
        assert [outcome.month for outcome in outcomes] == [
            date(2026, 11, 1),
            date(2026, 12, 1),
            date(2027, 1, 1),
        ]
        for outcome in outcomes:
            assert outcome.figure is not None, outcome.withheld
            assert outcome.figure.low == month_total(outcome.month)

    def test_are_withheld_where_the_history_is_too_short_to_test_that_far(self) -> None:
        daily = series(date(2026, 3, 1), date(2026, 10, 4))
        outcomes = ahead(daily, date(2026, 10, 1), date(2026, 10, 5))
        assert outcomes[0].figure is not None
        assert outcomes[-1].figure is None
        assert outcomes[-1].withheld is not None


class TestTheBand:
    def test_is_read_between_ranks_the_way_a_spreadsheet_reads_a_percentile(self) -> None:
        values = [Decimal(n) for n in (0, 10, 20, 30, 40)]
        assert quantile(values, Decimal("0.10")) == Decimal(4)
        assert quantile(values, Decimal("0.90")) == Decimal(36)
        assert quantile([Decimal(7)], Decimal("0.10")) == Decimal(7)

    def test_a_miss_is_a_share_of_what_the_month_actually_cost(self) -> None:
        test = HeldOut(month=date(2026, 9, 1), estimate=Decimal(90), actual=Decimal(100))
        assert test.miss == Decimal("0.1")
        assert test.ratio == (Decimal(100) - Decimal(90)) / Decimal(90)

    @pytest.mark.parametrize("estimate", [Decimal(0), Decimal(100)])
    def test_a_month_that_cost_nothing_or_was_forecast_as_nothing_tests_nothing(
        self, estimate: Decimal
    ) -> None:
        nothing = HeldOut(month=date(2026, 9, 1), estimate=estimate, actual=Decimal(0))
        assert nothing.usable is False
