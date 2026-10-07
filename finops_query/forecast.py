"""What this month and the next three will cost. FEAT-066, TASK-P8-008.

No database, no clock, no provider. It takes the cost of each day and returns a range, or the
sentence saying why there is none, which is what makes it testable against a series whose answer
is known.

ADR-0015 permits a deterministic forecaster on four conditions, and the owner chose how this one
meets them on 2026-10-05.

**The method is a weekday profile.** Each day ahead is the average of the same weekday over the
eight weeks before the forecast is made. Spend has a weekly shape, and a run rate that ignores it
forecasts a Monday from a Sunday. The rule reproduces exactly from the same rows and explains
itself in one sentence, which is the sentence the screen prints beside the figure.

**The band is the method's own misses.** Every complete month in the history is forecast again as
if it were today, from the same day of its month and with only the data that existed then, and
the band is where the middle 80 percent of those misses fell. It assumes nothing about the noise,
and it widens by itself when the method does worse.

**A refusal, not a cautious guess.** With fewer than three months to test on, or a median miss
above 15 percent of what a month cost, no figure leaves this module, only the sentence saying
why. A forecast nobody could check is a modelled number wearing a forecast's clothes.

**Never a point.** The central estimate is arithmetic inside this module. What leaves it is a low
and a high, because a forecast drawn as one number is read as a promise it never was.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from typing import Final

#: Weeks of history behind each weekday's average.
PROFILE_WEEKS: Final = 8
#: Complete months the method must be tested on before its figure is shown.
MIN_HELD_OUT: Final = 3
#: The most months tested. A year covers a full season without letting a different estate,
#: years ago, decide how wide today's band is.
MAX_HELD_OUT: Final = 12
#: The median miss, as a share of what a month cost, above which no figure is shown.
MAX_MEDIAN_MISS: Final = Decimal("0.15")
LOW_QUANTILE: Final = Decimal("0.10")
HIGH_QUANTILE: Final = Decimal("0.90")
#: The share of past misses the band holds, LOW_QUANTILE to HIGH_QUANTILE.
INTERVAL_PERCENT: Final = 80
#: Calendar months forecast after the current one.
AHEAD_MONTHS: Final = 3
METHOD: Final = "weekday profile"
METHOD_DETAIL: Final = (
    "Each day ahead is the average of the same weekday over the eight weeks before the "
    "forecast was made."
)

NO_PROFILE: Final = (
    "The eight weeks before the forecast are not all collected, so there is no weekday profile "
    "to forecast from."
)
BILLED_IN_FULL: Final = (
    "The month is billed in full, so its total is measured and nothing is left to forecast."
)

#: The cost of each day the history holds. A collected day that billed nothing is a zero; a day
#: outside the collected range is absent, which is how the profile knows it cannot be drawn.
Daily = Mapping[date, Decimal]


@dataclass(frozen=True)
class Range:
    """A forecast: a low and a high at `INTERVAL_PERCENT` percent. Never a point."""

    low: Decimal
    high: Decimal


@dataclass(frozen=True)
class HeldOut:
    """One held out month, forecast again as if it were today."""

    month: date
    estimate: Decimal
    actual: Decimal

    @property
    def usable(self) -> bool:
        """A month that cost nothing, or was forecast as nothing, has no share to miss by."""
        return self.actual > 0 and self.estimate > 0

    @property
    def miss(self) -> Decimal:
        """How far off, as a share of what the month actually cost."""
        return abs(self.actual - self.estimate) / self.actual

    @property
    def ratio(self) -> Decimal:
        """The signed miss against the estimate, which is what the band is read from."""
        return (self.actual - self.estimate) / self.estimate


@dataclass(frozen=True)
class Day:
    """One day of the month as the chart draws it: billed so far, or the band, never both."""

    day: date
    actual: Decimal | None
    low: Decimal | None
    high: Decimal | None


@dataclass(frozen=True)
class Outcome:
    """One month's forecast, or the reason there is none, with the tests behind it."""

    month: date
    figure: Range | None
    withheld: str | None
    median_miss: Decimal | None
    tests: tuple[HeldOut, ...]
    days: tuple[Day, ...] = ()


def profile(daily: Daily, cut: date) -> dict[int, Decimal] | None:
    """Each weekday's average over the `PROFILE_WEEKS` weeks before `cut`.

    None where any of those days was not collected, because an average over the days that
    happen to exist is an average of a different, shorter history that says it is eight weeks.
    """
    days = [cut - timedelta(days=offset) for offset in range(1, PROFILE_WEEKS * 7 + 1)]
    if any(day not in daily for day in days):
        return None
    totals = {weekday: Decimal(0) for weekday in range(7)}
    for day in days:
        totals[day.weekday()] += daily[day]
    return {weekday: total / PROFILE_WEEKS for weekday, total in totals.items()}


def quantile(values: Sequence[Decimal], q: Decimal) -> Decimal:
    """The `q` quantile, read between the two nearest ranks as a spreadsheet's PERCENTILE is."""
    ordered = sorted(values)
    position = q * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def month_end(daily: Daily, month_start: date, cut: date) -> Outcome:
    """This month's total as a range, forecast from `cut`, the first day not yet billed."""
    tests = _tests(daily, month_start, _same_day(cut - month_start))
    if cut > _last_day(month_start):
        return Outcome(month_start, None, BILLED_IN_FULL, None, tests)
    estimate = _estimate(daily, month_start, cut)
    figure, withheld, middle = _judged(estimate, tests)
    days = _chart(daily, month_start, cut, estimate, figure)
    return Outcome(month_start, figure, withheld, middle, tests, days)


def ahead(daily: Daily, month_start: date, cut: date) -> tuple[Outcome, ...]:
    """The next `AHEAD_MONTHS` calendar months, each tested from as far ahead as it is today."""
    outcomes = []
    for count in range(1, AHEAD_MONTHS + 1):
        month = _month_after(month_start, count)
        tests = _tests(daily, month_start, _lead(month - cut))
        figure, withheld, middle = _judged(_estimate(daily, month, cut), tests)
        outcomes.append(Outcome(month, figure, withheld, middle, tests))
    return tuple(outcomes)


def _same_day(offset: timedelta) -> Callable[[date], date]:
    """A held out month cut on the same day of its month as today, kept inside a short month."""
    return lambda month: min(month + offset, _last_day(month))


def _lead(lead: timedelta) -> Callable[[date], date]:
    """A held out month cut as far before it as the forecast month is from today."""
    return lambda month: month - lead


def _tests(daily: Daily, month_start: date, cut_for: Callable[[date], date]) -> tuple[HeldOut, ...]:
    """The complete months before this one, newest first, each forecast from its own cut.

    It stops at the first month it cannot test, because every older month has even less
    history behind it.
    """
    tests: list[HeldOut] = []
    month = _month_after(month_start, -1)
    while len(tests) < MAX_HELD_OUT:
        estimate = _estimate(daily, month, cut_for(month))
        actual = _actual(daily, month)
        if estimate is None or actual is None:
            break
        tests.append(HeldOut(month, estimate, actual))
        month = _month_after(month, -1)
    return tuple(tests)


def _judged(
    estimate: Decimal | None, tests: Sequence[HeldOut]
) -> tuple[Range | None, str | None, Decimal | None]:
    usable = [test for test in tests if test.usable]
    middle = median([test.miss for test in usable]) if usable else None
    if estimate is None:
        return None, NO_PROFILE, middle
    if len(usable) < MIN_HELD_OUT:
        return (
            None,
            f"The forecast is tested on {MIN_HELD_OUT} complete months before it is shown, and "
            f"Meter holds {len(usable)} it can be tested on.",
            middle,
        )
    if middle is not None and middle > MAX_MEDIAN_MISS:
        return (
            None,
            f"Tested on {len(usable)} months, it missed by {_percent(middle)} at the median, "
            f"above the {int(MAX_MEDIAN_MISS * 100)} percent it has to stay within.",
            middle,
        )
    low, high = band(usable)
    return Range(low=estimate * (1 + low), high=estimate * (1 + high)), None, middle


def band(tests: Sequence[HeldOut]) -> tuple[Decimal, Decimal]:
    """The band's two edges, as signed shares of an estimate, read from the usable tests.

    Public because the backtest table applies the same edges to each held out month, and a
    second copy of this arithmetic would be the one that drifts.
    """
    ratios = [test.ratio for test in tests if test.usable]
    return quantile(ratios, LOW_QUANTILE), quantile(ratios, HIGH_QUANTILE)


def _chart(
    daily: Daily, month_start: date, cut: date, estimate: Decimal | None, figure: Range | None
) -> tuple[Day, ...]:
    """Billed so far, cumulative, then a band that opens from the last billed day.

    The band's width is spread over the days ahead in proportion to what each is forecast to
    cost, so it starts at nothing on the cut and ends exactly on the month's range.
    """
    end = _last_day(month_start)
    billed = Decimal(0)
    days: list[Day] = []
    for day in _days(month_start, min(cut - timedelta(days=1), end)):
        billed += daily.get(day, Decimal(0))
        days.append(Day(day, billed, None, None))
    forecast_days = _days(max(cut, month_start), end)
    weekdays = profile(daily, cut)
    if figure is None or estimate is None or weekdays is None:
        return (*days, *(Day(day, None, None, None) for day in forecast_days))
    rest = sum((weekdays[day.weekday()] for day in forecast_days), Decimal(0))
    running = Decimal(0)
    for day in forecast_days:
        running += weekdays[day.weekday()]
        share = running / rest if rest > 0 else Decimal(1)
        middle = billed + running
        days.append(
            Day(
                day,
                None,
                middle + (figure.low - estimate) * share,
                middle + (figure.high - estimate) * share,
            )
        )
    return tuple(days)


def _estimate(daily: Daily, month: date, cut: date) -> Decimal | None:
    """The month as the profile at `cut` sees it: billed before the cut, forecast from it."""
    weekdays = profile(daily, cut)
    if weekdays is None:
        return None
    end = _last_day(month)
    billed_days = _days(month, min(cut - timedelta(days=1), end))
    if any(day not in daily for day in billed_days):
        return None
    billed = sum((daily[day] for day in billed_days), Decimal(0))
    forecast = sum((weekdays[day.weekday()] for day in _days(max(cut, month), end)), Decimal(0))
    return billed + forecast


def _actual(daily: Daily, month: date) -> Decimal | None:
    days = _days(month, _last_day(month))
    if any(day not in daily for day in days):
        return None
    return sum((daily[day] for day in days), Decimal(0))


def _days(start: date, end: date) -> list[date]:
    """Every day from `start` to `end`, both included, and none where `end` comes first."""
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _month_after(month: date, count: int = 1) -> date:
    index = month.year * 12 + month.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


def _last_day(month: date) -> date:
    return _month_after(month) - timedelta(days=1)


def _percent(share: Decimal) -> str:
    """Half up, the way the screen rounds the same share, so the two never disagree."""
    return f"{(share * 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)} percent"
