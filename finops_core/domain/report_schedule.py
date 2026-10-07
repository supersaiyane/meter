"""When a scheduled report runs next. FEAT-069, TASK-P8-011, P8 spec section 5.7.

Every cadence runs at one hour of the day in UTC, so a schedule's next run is a function of its
cadence and the moment after which a run is wanted, and of nothing else: no clock is read here,
and the same two arguments give the same answer on every machine.

- DAILY runs every day at the run hour.
- WEEKLY runs every Monday at the run hour.
- MONTHLY runs on the first day of every month at the run hour, so a monthly report of an open
  month reads it as it stood at the start of that day.
- MONTH_CLOSE runs on `MONTH_CLOSE_DAY` of every month, after the provider has finished amending
  the month before, so a report of a closed month is a report of its final bill.

The run hour falls after the overnight collection, so a daily report of yesterday reads a day
the collectors have already read.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final


class Cadence(StrEnum):
    """How often a schedule renders. The values are what the database and the API carry."""

    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    MONTH_CLOSE = "MONTH_CLOSE"


#: The hour of the day, in UTC, every cadence runs at.
RUN_HOUR_UTC: Final = 6
#: The day of the month a MONTH_CLOSE schedule runs on. AWS finalises a month's bill in the first
#: days of the next one, and the sixth leaves room for a late adjustment to land first.
MONTH_CLOSE_DAY: Final = 6
MONTHS_PER_YEAR: Final = 12


def next_run_after(cadence: Cadence, after: datetime) -> datetime:
    """The first run of `cadence` strictly after `after`, in UTC.

    Strictly after, so a run that finishes exactly on its hour schedules the next one rather
    than itself again.
    """
    if after.tzinfo is None:
        raise ValueError("a schedule's time is compared in UTC and needs a zone to be read in")
    at = after.astimezone(UTC)
    if cadence is Cadence.DAILY:
        today = _at_run_hour(at)
        return today if today > at else today + timedelta(days=1)
    if cadence is Cadence.WEEKLY:
        monday = _at_run_hour(at) - timedelta(days=at.weekday())
        return monday if monday > at else monday + timedelta(weeks=1)
    day = 1 if cadence is Cadence.MONTHLY else MONTH_CLOSE_DAY
    this_month = _at_run_hour(at).replace(day=day)
    if this_month > at:
        return this_month
    year, month = divmod(at.year * MONTHS_PER_YEAR + at.month, MONTHS_PER_YEAR)
    return this_month.replace(year=year, month=month + 1)


def _at_run_hour(at: datetime) -> datetime:
    return at.replace(hour=RUN_HOUR_UTC, minute=0, second=0, microsecond=0)
