"""The calendar and the variation every fake utilization estate shares.

Four estates read from this module: the metric series P3 reads, the container
usage P6 reads, the quota history P5 reads, and the topology P4 reads. They
share it so that a quarter end in one is a quarter end in all of them. A batch
cluster that spikes on a different day from the vCPU quota it consumes is two
estates pretending to be one, and a test joining them would prove nothing.

**Nothing here is random and nothing reads a clock.** Variation comes from a
keyed hash of the series name and the hour, so the same series at the same hour
has the same value on every machine and every run, and two different series
never move in lockstep. That is the property a random generator with a fixed
seed also has, but a hash cannot be advanced out of order by somebody adding a
series above yours, which is how a seeded fixture changes every number in the
file when one line is inserted.

**The window is derived from `at`**, as `cur.periods_ending_at` is. The default
is `fixtures.AS_OF`, and a demo seeded next year passes next year's clock and
gets two years ending then.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import blake2b

from finops_providers.fake import fixtures

#: Two years of history. Long enough for a year over year comparison and for
#: every calendar effect below to occur at least twice.
WINDOW_DAYS = 730

#: The period every series is sampled at. P3 reads `GetMetricData` at one hour,
#: TASK-P3-007, and a fake sampled at any other period proves a different read.
STEP = timedelta(hours=1)

#: The floor below which P3 and P6 must refuse to recommend, TASK-P3-002 and
#: TASK-P6-001. Declared here only so the planted under floor resource can be
#: sized against it. The real constant is `MINIMUM_HISTORY` and a test asserts
#: the two agree once that constant exists.
MINIMUM_HISTORY_DAYS = 14

_TWO_TO_64 = float(2**64)


def window(at: datetime) -> tuple[datetime, datetime]:
    """The half open window `[start, end)` ending at the hour containing `at`."""
    end = at.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return end - timedelta(days=WINDOW_DAYS), end


def hours(start: datetime, end: datetime) -> Iterator[datetime]:
    """Every hour in `[start, end)`, oldest first."""
    cursor = start
    while cursor < end:
        yield cursor
        cursor += STEP


def days(start: datetime, end: datetime) -> Iterator[date]:
    """Every whole or part day touched by `[start, end)`, oldest first."""
    cursor = start.date()
    while datetime(cursor.year, cursor.month, cursor.day, tzinfo=UTC) < end:
        yield cursor
        cursor += timedelta(days=1)


def slot(ts: datetime) -> int:
    """The hour number since the epoch. The second half of every hash key."""
    return int(ts.timestamp()) // 3600


def unit(key: str) -> float:
    """A stable value in `[0, 1)` for `key`."""
    digest = blake2b(key.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") / _TWO_TO_64


def jitter(key: str, ts: datetime) -> float:
    """A stable value in `[-1, 1)` for one series at one hour."""
    return unit(f"{key}|{slot(ts)}") * 2.0 - 1.0


def diurnal(ts: datetime) -> float:
    """Demand shape in `[0, 1]`: peaks at 14:00 UTC on weekdays, low at night.

    A weekend reaches a quarter of a weekday. That is what makes a development
    box idle on Saturday look like waste to a detector reading averages, and why
    TASK-P3-006 plants one.
    """
    curve = 0.5 * (1.0 + math.cos(2.0 * math.pi * (ts.hour - 14) / 24.0))
    return curve * (0.25 if ts.weekday() >= 5 else 1.0)


def is_business_hours(ts: datetime) -> bool:
    """Weekday, 08:00 to 19:00 UTC."""
    # allow-hardcoded: the shape of the fake estate rather than a policy. A
    # configurable definition of the working day would make a demo estate whose
    # diurnal curve moved with a setting, which is a curve nobody can reason about.
    return ts.weekday() < 5 and 8 <= ts.hour < 19  # allow-hardcoded: fake estate shape


def last_day_of_month(d: date) -> date:
    first_next = date(d.year + (d.month // 12), (d.month % 12) + 1, 1)
    return first_next - timedelta(days=1)


def is_month_end(d: date) -> bool:
    """The last two days of a month, when reconciliation batches run."""
    return (last_day_of_month(d) - d).days < 2


def is_quarter_end(d: date) -> bool:
    """The last three days of March, June, September and December.

    A bank's regulatory reporting and risk batches land here, and they are the
    reason a p99 and a p95 disagree on the batch cluster.
    """
    return d.month in (3, 6, 9, 12) and (last_day_of_month(d) - d).days < 3


def is_peak_retail(d: date) -> bool:
    """Black Friday through Cyber Monday: card volumes for a retail bank."""
    if d.month != 11:
        return False
    first = date(d.year, 11, 1)
    first_thursday = first + timedelta(days=(3 - first.weekday()) % 7)
    black_friday = first_thursday + timedelta(days=22)
    return black_friday <= d <= black_friday + timedelta(days=3)


def is_kill_window(ts: datetime) -> bool:
    """The hours of a peak day a memory hungry workload gets killed in.

    Named here rather than written twice in `containers.py`, where the memory series
    and the restart count both need it and two copies of the same hours would let
    one describe an event the other does not. The literal is the shape of the fake
    estate rather than a policy: a configurable definition of when a pod dies would
    make a demo estate nobody can reason about.
    """
    return 10 <= ts.hour < 16  # allow-hardcoded: fake estate shape


def is_year_end(d: date) -> bool:
    """18 to 31 December: holiday payments and year end close."""
    # allow-hardcoded: the calendar, not a threshold. Year end close is a date.
    return d.month == 12 and d.day >= 18  # allow-hardcoded: the calendar


def seasonal(d: date) -> float:
    """The multiplier demand driven services carry on day `d`. One is ordinary."""
    factor = 1.0
    if is_year_end(d):
        factor *= 1.18
    if is_peak_retail(d):
        factor *= 1.30
    if is_quarter_end(d):
        factor *= 1.12
    elif is_month_end(d):
        factor *= 1.05
    return factor


def progress(ts: datetime, start: datetime, end: datetime) -> float:
    """How far `ts` sits through `[start, end)`, in `[0, 1]`."""
    span = (end - start).total_seconds()
    return min(1.0, max(0.0, (ts - start).total_seconds() / span)) if span else 1.0


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def dec(value: float, places: int = 4) -> Decimal:
    """A float rendered as a `Decimal` with fixed places, never a binary float."""
    return Decimal(f"{value:.{places}f}")


#: Three regions, per the fourth rule of the P4 plan: one of them refuses.
#: `fake-region-a` is the fixture region every account lives in, `fake-region-b`
#: holds the platform accounts' disaster recovery copies, and `fake-region-c`
#: is enabled in no account, so every read of it is refused as `NotOptedIn`.
#: Fictional for the reason `fixtures.py` gives.
REGION_A = fixtures.REGION
REGION_B = "fake-region-b"
REGION_C = "fake-region-c"
REGIONS = (REGION_A, REGION_B, REGION_C)
REFUSING_REGION = REGION_C

#: The account no role can be assumed into, from `fixtures.py`. It is on the
#: bill and nowhere else, and every reader here raises for it.
DENIED_ACCOUNT = fixtures.DENIED_ACCOUNT_KEY.account_id

#: Accounts a reader can reach.
READABLE_ACCOUNTS = tuple(a for a in fixtures.ACCOUNT_IDS if a != DENIED_ACCOUNT)


def zone(region: str, letter: str) -> str:
    """An availability zone name in a fictional region."""
    return f"{region}-{letter}"
