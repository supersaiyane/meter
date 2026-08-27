"""Monthly partitions for the two range partitioned cost tables.

`cost_focus_daily` and `cost_provider_extra` are declared `PARTITION BY RANGE`
and a range partitioned table with no partitions accepts no rows at all. The
insert fails with "no partition of relation found for row", which is not a
warning and not a slow path, it is a hard failure on the first cost record. So
this is not an optimisation, it is what makes those two tables writable.

It also has to run ahead of time. A partition created on demand is a partition
created during the first insert of the month, which is the one moment the
ingest is busiest and least able to take a schema lock. `MONTHS_AHEAD` is what
buys the margin: if this job stops, ingest keeps working for that many months
and the freshness screen shows the job stopped, rather than the whole cost
pipeline failing at midnight on the first.

Dropping a partition is also why the tables are partitioned. Removing three
year old cost data as a partition drop is one catalog operation. Removing it
row by row is a table scan, a mass delete and a vacuum, on the largest table in
the system, inside the transaction of a scheduled job.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text

from finops_ingest.registry import CollectorContext, CollectorOutcome

Clock = Callable[[], datetime]

#: The two tables declared PARTITION BY RANGE in migration 0001. A test holds
#: this equal to what the database actually reports, so adding a third
#: partitioned table without adding it here fails rather than silently leaving a
#: table nobody can write to.
PARTITIONED_TABLES: tuple[str, ...] = ("cost_focus_daily", "cost_provider_extra")

#: How far ahead partitions are created. Three months means this job can fail
#: silently for a quarter before it becomes an ingest failure, which is long
#: enough for a stopped job to be noticed on the freshness screen.
MONTHS_AHEAD = 3

#: cost_focus_daily_p202608. Matched rather than assumed, so a hand made
#: partition with a different name is left alone instead of being removed.
_SUFFIX = re.compile(r"_p(?P<year>\d{4})(?P<month>\d{2})$")


def _system_clock() -> datetime:
    return datetime.now(UTC)


def month_floor(day: date) -> date:
    return day.replace(day=1)


def next_month(month: date) -> date:
    if month.month == 12:
        return date(month.year + 1, 1, 1)
    return date(month.year, month.month + 1, 1)


def months_from(start: date, count: int) -> tuple[date, ...]:
    """`count` consecutive month starts, beginning at the month containing `start`."""
    months = [month_floor(start)]
    for _ in range(count - 1):
        months.append(next_month(months[-1]))
    return tuple(months)


def partition_name(parent: str, month: date) -> str:
    return f"{parent}_p{month:%Y%m}"


def month_of(name: str) -> date | None:
    """The month a partition name encodes, or None if it is not one of ours."""
    found = _SUFFIX.search(name)
    if found is None:
        return None
    return date(int(found["year"]), int(found["month"]), 1)


def existing_partitions(connection: Any, parent: str) -> tuple[str, ...]:
    """What the database actually has, asked rather than remembered."""
    rows = connection.execute(
        text(
            "SELECT child.relname FROM pg_inherits "
            "JOIN pg_class AS child ON child.oid = pg_inherits.inhrelid "
            "JOIN pg_class AS parent ON parent.oid = pg_inherits.inhparent "
            "WHERE parent.relname = :parent ORDER BY child.relname"
        ),
        {"parent": parent},
    ).scalars()
    return tuple(rows)


def ensure_partition(connection: Any, parent: str, month: date) -> bool:
    """Create one month's partition. Returns whether it had to be created.

    `IF NOT EXISTS` rather than a check and a create, because two workers running
    this at once is normal and losing the race should be free.
    """
    name = partition_name(parent, month)
    before = existing_partitions(connection, parent)
    connection.execute(
        text(
            f'CREATE TABLE IF NOT EXISTS "{name}" PARTITION OF "{parent}" '
            f"FOR VALUES FROM ('{month:%Y-%m-%d}') TO ('{next_month(month):%Y-%m-%d}')"
        )
    )
    return name not in before


def detach_partitions_before(connection: Any, parent: str, cutoff: date) -> tuple[str, ...]:
    """Remove partitions whose whole month is before `cutoff`. Returns their names.

    Strictly before, on a month boundary. A partition holding any day at or
    after the cutoff is left intact, because removing it would take data still
    inside the retention window with it. Those days wait for the next run, which
    is the whole reason the cadence is monthly rather than daily.
    """
    boundary = month_floor(cutoff)
    removed = []
    for name in existing_partitions(connection, parent):
        month = month_of(name)
        if month is None or next_month(month) > boundary:
            continue
        connection.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
        removed.append(name)
    return tuple(removed)


def partition_maintenance(
    context: CollectorContext,
    clock: Clock = _system_clock,
    tables: Sequence[str] = PARTITIONED_TABLES,
) -> CollectorOutcome:
    """Create the current month and the next few, for every partitioned table."""
    created = 0
    for parent in tables:
        for month in months_from(clock().date(), MONTHS_AHEAD + 1):
            if ensure_partition(context.connection, parent, month):
                created += 1
    return CollectorOutcome(items_written=created)
