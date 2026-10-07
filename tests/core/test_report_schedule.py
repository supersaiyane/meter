"""When a scheduled report runs next. FEAT-069, TASK-P8-011.

Each cadence is held on both sides of its run hour and across the boundaries that break date
arithmetic: the end of a week, the end of a month and the end of a year. A run exactly on its
hour schedules the next one rather than itself, which is the case that would loop.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from finops_core.domain.report_schedule import (
    MONTH_CLOSE_DAY,
    RUN_HOUR_UTC,
    Cadence,
    next_run_after,
)


def at(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


@pytest.mark.parametrize(
    ("cadence", "after", "expected"),
    [
        (Cadence.DAILY, at(2026, 10, 7, 5, 59), at(2026, 10, 7, RUN_HOUR_UTC)),
        (Cadence.DAILY, at(2026, 10, 7, RUN_HOUR_UTC), at(2026, 10, 8, RUN_HOUR_UTC)),
        (Cadence.DAILY, at(2026, 12, 31, 23, 0), at(2027, 1, 1, RUN_HOUR_UTC)),
        # 2026-10-07 is a Wednesday, so the next Monday is the twelfth.
        (Cadence.WEEKLY, at(2026, 10, 7, 9, 30), at(2026, 10, 12, RUN_HOUR_UTC)),
        (Cadence.WEEKLY, at(2026, 10, 12, 5, 0), at(2026, 10, 12, RUN_HOUR_UTC)),
        (Cadence.WEEKLY, at(2026, 10, 12, RUN_HOUR_UTC), at(2026, 10, 19, RUN_HOUR_UTC)),
        (Cadence.MONTHLY, at(2026, 10, 7), at(2026, 11, 1, RUN_HOUR_UTC)),
        (Cadence.MONTHLY, at(2026, 11, 1, 5, 0), at(2026, 11, 1, RUN_HOUR_UTC)),
        (Cadence.MONTHLY, at(2026, 12, 1, RUN_HOUR_UTC), at(2027, 1, 1, RUN_HOUR_UTC)),
        (Cadence.MONTH_CLOSE, at(2026, 10, 7), at(2026, 11, MONTH_CLOSE_DAY, RUN_HOUR_UTC)),
        (Cadence.MONTH_CLOSE, at(2026, 10, 2), at(2026, 10, MONTH_CLOSE_DAY, RUN_HOUR_UTC)),
        (
            Cadence.MONTH_CLOSE,
            at(2026, 12, MONTH_CLOSE_DAY, RUN_HOUR_UTC),
            at(2027, 1, MONTH_CLOSE_DAY, RUN_HOUR_UTC),
        ),
    ],
    ids=[
        "daily-before",
        "daily-on-the-hour",
        "daily-new-year",
        "weekly-midweek",
        "weekly-monday-before",
        "weekly-on-the-hour",
        "monthly-mid-month",
        "monthly-first-before",
        "monthly-new-year",
        "close-after-the-day",
        "close-before-the-day",
        "close-new-year",
    ],
)
def test_the_next_run_is_the_first_after(
    cadence: Cadence, after: datetime, expected: datetime
) -> None:
    assert next_run_after(cadence, after) == expected


@pytest.mark.parametrize("cadence", list(Cadence))
def test_the_next_run_is_always_later_and_on_the_hour(cadence: Cadence) -> None:
    start = at(2026, 1, 1)
    for hours in range(0, 24 * 400, 7):
        moment = start + timedelta(hours=hours)
        upcoming = next_run_after(cadence, moment)
        assert upcoming > moment
        assert (upcoming.hour, upcoming.minute, upcoming.second) == (RUN_HOUR_UTC, 0, 0)
        assert upcoming.tzinfo is UTC


def test_a_time_in_another_zone_is_read_in_utc() -> None:
    india = timezone(timedelta(hours=5, minutes=30))
    # 11:00 in India is 05:30 UTC, still before the run hour.
    assert next_run_after(Cadence.DAILY, datetime(2026, 10, 7, 11, 0, tzinfo=india)) == at(
        2026, 10, 7, RUN_HOUR_UTC
    )


def test_a_time_with_no_zone_is_refused() -> None:
    with pytest.raises(ValueError, match="zone"):
        next_run_after(Cadence.DAILY, datetime(2026, 10, 7, 9, 0))
