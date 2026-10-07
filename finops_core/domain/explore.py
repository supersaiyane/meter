"""Cost Explorer's periods, and the period each is compared with. FEAT-065.

Pure date arithmetic, kept out of the query so every boundary a reader sees is tested against
fixed dates rather than against whatever day the suite happens to run on.

A window is inclusive at both ends, because a reader says 1 to 5 October and means the fifth.
The comparison is like for like, which the owner chose on 2026-10-05: month to date 1 to 5
October is set against 1 to 5 September, three months against the three months before, a year
to date against the same days a year earlier, and a custom range against the same number of
days immediately before it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final, Literal

Preset = Literal["mtd", "3m", "6m", "12m", "ytd", "custom"]
Granularity = Literal["daily", "monthly"]
Metric = Literal["effective_cost", "billed_cost", "list_cost", "contracted_cost"]

#: Each measure's FOCUS display name, which is what a screen and a refusal call it.
METRIC_NAMES: Final[dict[str, str]] = {
    "effective_cost": "Effective Cost",
    "billed_cost": "Billed Cost",
    "list_cost": "List Cost",
    "contracted_cost": "Contracted Cost",
}

#: How many calendar months each preset spans, which is also how far its comparison moves.
_SPAN: Final[dict[str, int]] = {"mtd": 1, "3m": 3, "6m": 6, "12m": 12, "ytd": 12}

#: The longest custom period, a leap year, so a custom range holds any preset and no more.
LONGEST_CUSTOM_DAYS: Final = 366


class PeriodError(ValueError):
    """A period that cannot be drawn, carrying the sentence that says why."""


@dataclass(frozen=True)
class Window:
    """A run of days, inclusive at both ends."""

    start: date
    end: date

    @property
    def days(self) -> int:
        """How many days the window holds, both ends counted."""
        return (self.end - self.start).days + 1


def window_for(
    preset: Preset, today: date, start: date | None = None, end: date | None = None
) -> Window:
    """The window a preset names on `today`, or the custom one given.

    Every preset ends today. Three months is this month to date and the two whole months
    before it, so a reader comparing presets is never comparing windows that end on
    different days.
    """
    if preset == "custom":
        return _custom(today, start, end)
    month_start = today.replace(day=1)
    if preset == "mtd":
        return Window(month_start, today)
    if preset == "ytd":
        return Window(date(today.year, 1, 1), today)
    return Window(_months_back(month_start, _SPAN[preset] - 1), today)


def previous(window: Window, preset: Preset) -> Window:
    """The window `window` is compared with: like for like, immediately before it."""
    if preset == "custom":
        end = window.start - timedelta(days=1)
        return Window(end - timedelta(days=window.days - 1), end)
    months = _SPAN[preset]
    return Window(_months_back(window.start, months), _months_back(window.end, months))


def _custom(today: date, start: date | None, end: date | None) -> Window:
    if start is None or end is None:
        raise PeriodError("A custom period needs both a start and an end date.")
    if end < start:
        raise PeriodError("A custom period has to end on or after the day it starts.")
    if end > today:
        raise PeriodError(
            "A custom period cannot end after today, because nothing after today is billed."
        )
    window = Window(start, end)
    if window.days > LONGEST_CUSTOM_DAYS:
        raise PeriodError(
            f"A custom period can hold at most {LONGEST_CUSTOM_DAYS} days, the longest preset."
        )
    return window


def _months_back(day: date, months: int) -> date:
    """`day` moved back `months` calendar months, held to the last day of a shorter month."""
    index = day.year * 12 + day.month - 1 - months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, _last_day(year, month + 1)))


def _last_day(year: int, month: int) -> int:
    following = date(year + month // 12, month % 12 + 1, 1)
    return (following - timedelta(days=1)).day
