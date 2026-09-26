"""The fold, and the three things it refuses to answer.

FEAT-054, TASK-P3-021. Pure, because all of `finops_query` is.

The cases worth having are the refusals. Finding a quiet window in an obviously quiet week is
arithmetic, and one test covers it. What this module exists to get right is the three shapes
that look like a parkable resource and are not: a fortnight that is really one week, a
resource that is quiet always, and a gap in the readings that a naive fold reads as quiet.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.metrics import MetricPoint
from finops_query.parking import HOURS_IN_WEEK, ParkingShape, Window, _runs, shape_of

# A Monday, so hour of week 0 is the first reading and the day names in a failure read
# straight across.
MONDAY = datetime(2026, 9, 7, 0, 0, tzinfo=UTC)
ACCOUNT = AccountKey(provider=Provider.AWS, account_id="111122223333")

IDLE = Decimal("5")


def fold(points: list[MetricPoint]) -> ParkingShape | None:
    """`shape_of` under the rules in `.env.example`, so every case reads as one line.

    Named rather than a dict splatted into the call, because a dict of mixed value types is
    `dict[str, object]` and splatting it defeats the type checker on exactly the arguments
    worth checking: a Decimal threshold and two integer counts.
    """
    return shape_of(
        points,
        idle_at_or_below=IDLE,
        minimum_weeks=2,
        minimum_window_hours=3,
    )


def point(at: datetime, value: str) -> MetricPoint:
    return MetricPoint(
        account_key=ACCOUNT,
        namespace="AWS/EC2",
        metric_name="CPUUtilization",
        statistic="Maximum",
        unit="Percent",
        value=Decimal(value),
        at=at,
        as_of=at,
        collected_at=at,
    )


def fortnight(
    quiet_hours: frozenset[int], *, weeks: int = 2, skip: frozenset[int] = frozenset()
) -> list[MetricPoint]:
    """An hourly reading for every hour of `weeks` weeks, quiet in `quiet_hours`.

    `skip` is an hour of week that is omitted from the **second** week only, which is how the
    absence rule is exercised: present in one week, missing in another.
    """
    points = []
    for week in range(weeks):
        for hour in range(HOURS_IN_WEEK):
            if week == 1 and hour in skip:
                continue
            at = MONDAY + timedelta(weeks=week, hours=hour)
            points.append(point(at, "2" if hour in quiet_hours else "60"))
    return points


NIGHTS = frozenset(hour for hour in range(HOURS_IN_WEEK) if hour % 24 in (22, 23, 0, 1, 2, 3))


# --- the arithmetic, once ----------------------------------------------------


def test_a_nightly_quiet_window_is_found_on_every_day() -> None:
    """Six hours a night, seven nights. The window wraps midnight, so a fold that stopped at
    the end of the day would report fourteen windows of two and three hours instead of seven
    of six, and two of those would fall under the minimum and vanish."""
    shape = fold(fortnight(NIGHTS))
    assert shape is not None
    assert shape.observed_weeks == 2
    assert len(shape.windows) == 7
    assert {window.hours for window in shape.windows} == {6}
    assert shape.hours_per_week == 42


def test_a_weekend_window_crosses_sunday_midnight_as_one_window() -> None:
    """Saturday and Sunday quiet is 48 hours ending at Monday 00:00, which is hour 0. A fold
    that treated the array as flat rather than circular would be correct here by accident and
    wrong for a window starting on Sunday evening, so the wrap is asserted directly."""
    weekend = frozenset(range(5 * 24, HOURS_IN_WEEK))
    shape = fold(fortnight(weekend))
    assert shape is not None
    assert shape.windows == (Window(start_hour=120, hours=48),)
    assert shape.windows[0].say() == "Saturday 00:00 UTC to Monday 00:00 UTC"


def test_a_window_running_into_monday_morning_is_not_split_in_two() -> None:
    """Friday 22:00 to Monday 03:00. The run starts on Friday, passes the end of the array and
    ends inside Monday, which is the case a flat scan reports as two windows."""
    late = frozenset(range(4 * 24 + 22, HOURS_IN_WEEK)) | frozenset(range(0, 3))
    shape = fold(fortnight(late))
    assert shape is not None
    assert len(shape.windows) == 1
    assert shape.windows[0].say() == "Friday 22:00 UTC to Monday 03:00 UTC"


# --- the three refusals -----------------------------------------------------


def test_one_week_is_not_a_pattern_and_produces_nothing() -> None:
    """The first refusal. One week holds exactly one of each weekday, so a bank holiday, a
    deployment freeze or a monthly batch job all read as the normal shape of the week.

    None rather than a low confidence finding: a confidence band on a claim about somebody's
    production schedule is not a warning anybody acts on.
    """
    assert fold(fortnight(NIGHTS, weeks=1)) is None


def test_a_resource_quiet_all_week_is_not_parkable() -> None:
    """The second refusal, and the one that stops the product contradicting itself. A resource
    quiet in all 168 hours is IDLE_INSTANCE, which says delete it. Reporting it here as well
    would put two findings on one resource, one saying schedule it and one saying delete it,
    and the reader cannot do both."""
    everything = frozenset(range(HOURS_IN_WEEK))
    assert fold(fortnight(everything)) is None


def test_an_hour_missing_from_one_week_is_unknown_rather_than_quiet() -> None:
    """The third refusal, and the subtlest. A resource that is already stopped publishes
    nothing, so an absent hour counted as quiet would recommend parking a window the resource
    is already parked in.

    One hour of the nightly window is dropped from the second week only. That hour is unknown,
    so the six hour run breaks into runs of shorter length on each affected night.
    """
    with_gap = fold(fortnight(NIGHTS, skip=frozenset({23})))
    assert with_gap is not None
    # Hour 23 is Monday 23:00. Without it the Monday night run splits, and the remaining
    # pieces around the gap are shorter than the six hours the other nights still have.
    assert 23 not in {window.start_hour for window in with_gap.windows}
    assert with_gap.hours_per_week < 42


def test_a_quiet_window_shorter_than_the_minimum_produces_nothing() -> None:
    """A single quiet hour every night costs a stop and a start to save an hour. None rather
    than an empty shape, because a finding with no windows in it would eventually be rendered
    as a recommendation to park for no hours."""
    one_hour = frozenset(hour for hour in range(HOURS_IN_WEEK) if hour % 24 == 3)
    assert fold(fortnight(one_hour)) is None


def test_a_busy_week_produces_nothing_rather_than_an_empty_shape() -> None:
    assert fold(fortnight(frozenset())) is None


# --- the fortnight that spans a year boundary --------------------------------


def test_a_fortnight_across_new_year_is_still_two_weeks() -> None:
    """`isocalendar` puts the last days of December in week one of the following year, which
    would fold a fortnight spanning New Year into one week and silently halve the denominator.
    That is a refusal the caller would read as "not enough data" on exactly two days a year."""
    new_year = datetime(2026, 12, 28, 0, 0, tzinfo=UTC)  # a Monday
    points = [
        point(new_year + timedelta(weeks=week, hours=hour), "2" if hour in NIGHTS else "60")
        for week in range(2)
        for hour in range(HOURS_IN_WEEK)
    ]
    shape = fold(points)
    assert shape is not None
    assert shape.observed_weeks == 2


# --- the words ---------------------------------------------------------------


def test_every_window_is_labelled_utc() -> None:
    """Meter holds no tenant timezone, ISS-206. A bare 22:00 is read as local time by whoever
    is reading it, and the whole point of naming a window is that somebody acts on it."""
    shape = fold(fortnight(NIGHTS))
    assert shape is not None
    assert shape.say().count("UTC") == len(shape.windows) * 2


@pytest.mark.parametrize(
    ("start", "hours"),
    [(-1, 4), (HOURS_IN_WEEK, 4), (0, 0), (0, HOURS_IN_WEEK + 1)],
)
def test_a_window_outside_the_week_is_refused(start: int, hours: int) -> None:
    with pytest.raises(ValueError):
        Window(start_hour=start, hours=hours)


def test_an_all_quiet_ring_is_one_window_at_the_run_level() -> None:
    """`_runs` is correct about rings, and `shape_of` decides what to do about it.

    Tested directly because the split is what makes the policy above it falsifiable. The first
    draft had `_runs` return nothing for an all quiet ring, so `shape_of`'s rule that a whole
    quiet week is IDLE_INSTANCE rather than parking could be deleted without a single test
    noticing: the refusal came from the empty run check further down, and the rule that looked
    load bearing was dead code.
    """
    everything = frozenset(range(HOURS_IN_WEEK))
    assert _runs(everything, 3) == (Window(start_hour=0, hours=HOURS_IN_WEEK),)
    # And the minimum still applies to it, rather than the whole ring being a special case
    # that skips every other rule.
    assert _runs(everything, HOURS_IN_WEEK + 1) == ()
