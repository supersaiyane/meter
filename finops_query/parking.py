"""A recurring window in which nothing happens, found by folding a fortnight into a week.

FEAT-054, TASK-P3-021. Adopted from the 2026-09-26 IBM Turbonomic review, whose workload
parking is the biggest untouched saving in most estates.

**This is the opposite finding to `IDLE_INSTANCE`, not a variation on it.** Idle says nothing
ever uses this, so delete it. Parking says something uses this every weekday and nothing uses
it at night, so keep it and stop paying for the nights. A resource that is busy at noon passes
every other rule in the product, which is exactly why the saving is still there.

**Three rules, and each one exists because the alternative recommends something false.**

1. **Absence is not idleness, and the test is per hour.** An hour counts only when it was
   seen in at least `minimum_weeks` different weeks and was quiet in every one of them. A
   resource that is already stopped every night publishes nothing in those hours, so they are
   never seen, never counted, and never recommended for parking: which is the failure this
   rule exists to prevent, and it is prevented at the hour rather than at the estate.

   The first draft demanded that every hour be present in every week the data touched, which
   looks stricter and refuses everything. A window of now minus a fortnight starts and ends
   mid week, so it straddles three Monday aligned weeks and the two ragged ends have no hour
   in common: no hour was present in all three, nothing was ever quiet, and the collector
   produced not one finding against an estate built to contain them.

2. **Two weeks minimum per hour, and below that no finding at all.** One week holds exactly
   one of each weekday, so a bank holiday, a deployment freeze or a monthly batch job all
   read as the normal shape of the week. Not a low confidence finding: a confidence band on a
   claim about somebody's production schedule is not a warning anybody acts on.

3. **A week that is idle throughout is not parkable.** It is `IDLE_INSTANCE`, and saying both
   would put two findings on one resource recommending opposite actions, one to schedule it
   and one to delete it. The reader cannot do both and has no way to choose.

**Everything here is UTC, and the caller has to say so.** Meter holds no tenant timezone, so
a window is reported in UTC and labelled UTC. A window of 22:00 to 06:00 means something
different to a team in Sydney than to a team in Dublin, and printing a bare clock time would
let each of them read it as their own. ISS-206.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from finops_core.domain.metrics import MetricPoint

#: Hours in a week. The fold's modulus, and the one number here that is not a policy.
HOURS_IN_WEEK = 168

#: Monday first, because `datetime.weekday()` puts it there. Named rather than indexed, since
#: an hour of week index in a rationale is a number no reader can act on.
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@dataclass(frozen=True)
class Window:
    """A contiguous run of quiet hours in the week, in UTC.

    `start_hour` is an hour of week, 0 being Monday 00:00 UTC. A window may wrap past Sunday
    into Monday, because a Friday night to Monday morning window is the common case and one
    that stopped at the end of the array would be reported as two.
    """

    start_hour: int
    hours: int

    def __post_init__(self) -> None:
        if not 0 <= self.start_hour < HOURS_IN_WEEK:
            raise ValueError(f"{self.start_hour} is not an hour of the week")
        if not 0 < self.hours <= HOURS_IN_WEEK:
            raise ValueError(f"a window of {self.hours} hours is not a window")

    def say(self) -> str:
        """The window in words, with the day names and the UTC label.

        The label is not decoration. A bare 22:00 is read as local time by whoever is
        reading it, and the whole point of naming a parking window is that somebody acts on
        it.
        """
        end = (self.start_hour + self.hours) % HOURS_IN_WEEK
        return (
            f"{DAYS[self.start_hour // 24]} {self.start_hour % 24:02d}:00 UTC "
            f"to {DAYS[end // 24]} {end % 24:02d}:00 UTC"
        )


@dataclass(frozen=True)
class ParkingShape:
    """What a fortnight of hourly readings says about the shape of a week."""

    observed_weeks: int
    windows: tuple[Window, ...]

    @property
    def hours_per_week(self) -> int:
        return sum(window.hours for window in self.windows)

    def say(self) -> str:
        """Every window, in the order they occur in the week."""
        return ", ".join(window.say() for window in self.windows)


def _hour_of_week(point: MetricPoint) -> int:
    return point.at.weekday() * 24 + point.at.hour


def _week_of(point: MetricPoint) -> int:
    """Which week a point belongs to: the day number of that week's Monday.

    Monday aligned, which is the whole requirement and is not what dividing the day number by
    seven gives. The proleptic calendar starts on a Monday but its seven day buckets break on
    a Sunday, so a Monday to Sunday week falls across two of them: a fortnight then reports
    three weeks, no hour is present in all three, and every finding is refused. That was the
    first draft, and it refused everything.

    `isocalendar` is the other obvious choice and puts the last days of December in week one
    of the following year, which would fold a fortnight spanning New Year into one week and
    silently halve the denominator, refusing on exactly two days a year.
    """
    return point.at.toordinal() - point.at.weekday()


def _runs(quiet: frozenset[int], minimum: int) -> tuple[Window, ...]:
    """Maximal contiguous runs of quiet hours around the week, longest first.

    Circular, so a run crossing Sunday midnight is one window. Runs shorter than `minimum`
    are dropped: a one hour window costs a stop and a start to save one hour, and the risk of
    that is not worth the saving.
    """
    if not quiet:
        return ()
    # A start is a quiet hour whose predecessor is not quiet. On a ring where every hour is
    # quiet there is no such hour, and the run is the whole ring: returned as one window here
    # rather than as nothing, so that this function is correct about rings and the question of
    # whether a whole quiet week is a parking finding stays in `shape_of`, where it is a
    # policy. Returning nothing here instead made that policy unfalsifiable: the caller's
    # guard was never the thing that fired, and removing it changed no test.
    if len(quiet) == HOURS_IN_WEEK:
        whole = Window(start_hour=0, hours=HOURS_IN_WEEK)
        return (whole,) if minimum <= HOURS_IN_WEEK else ()
    starts = sorted(hour for hour in quiet if (hour - 1) % HOURS_IN_WEEK not in quiet)
    found = []
    for start in starts:
        length = 1
        while (start + length) % HOURS_IN_WEEK in quiet:
            length += 1
        if length >= minimum:
            found.append(Window(start_hour=start, hours=length))
    return tuple(found)


def shape_of(
    points: Iterable[MetricPoint],
    *,
    idle_at_or_below: Decimal,
    minimum_weeks: int,
    minimum_window_hours: int,
) -> ParkingShape | None:
    """The parkable windows in a week, or None where there is no honest answer.

    None rather than an empty shape in three cases, and they are different failures that a
    caller must not be able to confuse with "this resource has no quiet window":

    - fewer than `minimum_weeks` distinct weeks were observed, so no pattern has been seen
    - every hour of the week is quiet, which is `IDLE_INSTANCE` and not a schedule
    - no run survives `minimum_window_hours`

    The third returns None rather than an empty tuple on purpose. A shape with no windows is
    a finding with nothing in it, and something would eventually render it as a park
    recommendation for zero hours.
    """
    readings: dict[int, list[Decimal]] = {}
    weeks_seen: dict[int, set[int]] = {}
    for point in points:
        hour = _hour_of_week(point)
        readings.setdefault(hour, []).append(point.value)
        weeks_seen.setdefault(hour, set()).add(_week_of(point))

    quiet = frozenset(
        hour
        for hour, values in readings.items()
        # The evidence rule, per hour rather than per estate. This hour has to have been seen
        # in at least `minimum_weeks` different weeks, and to have been quiet in every one of
        # them. An hour seen once is not a pattern and an hour never seen is not quiet.
        if len(weeks_seen[hour]) >= minimum_weeks
        and all(value <= idle_at_or_below for value in values)
    )
    if not quiet:
        return None
    if len(quiet) == HOURS_IN_WEEK:
        return None

    windows = _runs(quiet, minimum_window_hours)
    if not windows:
        return None
    # The weakest evidence behind any hour in the answer, so the rationale understates rather
    # than overstates. Every flagged hour was seen at least this many times and was quiet
    # every time.
    weeks = min(len(weeks_seen[hour]) for hour in quiet)
    return ParkingShape(observed_weeks=weeks, windows=windows)
