"""Cost Explorer's reads over the FOCUS line items. FEAT-065, TASK-P8-007.

Every statement here is derived from `scoped_select`, the only constructor the scope guard
accepts, and the guard checks for the mark that constructor leaves rather than reading the
SQL. Wrapping one query in another would drop the mark, so nothing here does: the ranking is
a window count over the grouped rows, and the tag keys are joined in the FROM clause as a
function rather than read from a subquery.

Grouping and ordering name their columns by position. An expression carrying a bound value, a
tag key or a list of series names, renders a fresh placeholder each time it is written, and
PostgreSQL will not match a grouped column to its select list through two placeholders.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, ClassVar, Final, cast

from sqlalchemy import Date, Select, Table, and_, case, func, literal_column, null, or_, true
from sqlalchemy import cast as sql_cast
from sqlalchemy.engine import Row
from sqlalchemy.sql.elements import ColumnClause, ColumnElement

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_api.db.repositories.cost import GROUPABLE
from finops_core.domain.explore import Granularity, Window
from finops_core.domain.platform import UNALLOCATED
from finops_core.domain.tenant import Scope

#: What a reader may group and filter by besides a tag key: the three the cost screen always
#: grouped by and five more FOCUS columns, chosen by the owner on 2026-10-05. Each is on every
#: line item and none is as long as the list of resources, which is what keeps a two way
#: grouping inside the row limit. Looked up, never interpolated.
EXPLORABLE: Final[Mapping[str, str]] = {
    **GROUPABLE,
    "service_category": "service_category",
    "availability_zone": "availability_zone",
    "charge_category": "charge_category",
    "commitment_discount_type": "commitment_discount_type",
    "commitment_discount_status": "commitment_discount_status",
}

#: The word a grouping uses for a tag key rather than a column.
TAG: Final = "tag"

#: The measures, by their FOCUS names, Effective Cost first because it is the default.
METRICS: Final[tuple[str, ...]] = ("effective_cost", "billed_cost", "list_cost", "contracted_cost")

#: Not null on any line item, so always offered. The other two are offered only for a view in
#: which every line item carries them, because a sum over the rows that happen to hold a list
#: price is a smaller number that looks complete.
ALWAYS_HELD: Final = frozenset({"effective_cost", "billed_cost"})

#: The allow list of tag keys is the period's own most used keys, which the owner chose on
#: 2026-10-05 over a list somebody would have to keep.
TAG_KEY_LIMIT: Final = 50

#: The most table rows one answer carries. The answer says how many it left out and what they
#: add up to, so a limit never reads as a smaller estate.
ROW_LIMIT: Final = 500

#: How many groups the chart names before the rest become one series, so six series colours.
NAMED_SERIES: Final = 5

_FIRST: Final[ColumnClause[Any]] = literal_column("1")
_SECOND: Final[ColumnClause[Any]] = literal_column("2")
_THIRD: Final[ColumnClause[Any]] = literal_column("3")
_FOURTH: Final[ColumnClause[Any]] = literal_column("4")


@dataclass(frozen=True)
class Grouping:
    """A column from `EXPLORABLE`, or `TAG` with one tag key."""

    dimension: str
    tag_key: str | None = None


@dataclass(frozen=True)
class Filter:
    """The values one grouping is held to."""

    grouping: Grouping
    values: tuple[str, ...]


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time(), tzinfo=UTC)


class ExploreRepository(ScopedRepository):
    """Cost Explorer's reads, under the same guard as every other cost read."""

    table: ClassVar[Table] = models.cost_focus_daily
    resource: ClassVar[str] = "cost_focus_daily"

    def earliest_period(self, scope: Scope) -> date | None:
        """The first billing month this scope holds line items for, or None for none."""
        statement = self.scoped_select(scope).with_only_columns(
            func.min(self.table.c.billing_period_start)
        )
        rows = self._read(scope, statement)
        found = rows[0][0] if rows else None
        return found if isinstance(found, date) else None

    def window_facts(self, scope: Scope, window: Window) -> Row[*tuple[Any, ...]]:
        """Accounts spending, the oldest charge and the newest fetch in a window.

        Unfiltered, because these describe the estate the view draws on, and a reader's filter
        narrowing the rows is not the estate shrinking.
        """
        c = self.table.c
        statement = (
            self.scoped_select(scope)
            .with_only_columns(
                func.count(func.distinct(c.sub_account_id)),
                func.min(c.as_of),
                func.max(c.collected_at),
            )
            .where(self._within(window))
        )
        return self._read(scope, statement)[0]

    def tag_keys(self, scope: Scope, window: Window) -> list[str]:
        """The tag keys on the window's line items, most used first, at most `TAG_KEY_LIMIT`."""
        keys = (
            func.jsonb_object_keys(self.table.c.tags)
            .table_valued("key")
            .render_derived(name="tag_keys")
        )
        statement = (
            self.scoped_select(scope)
            .with_only_columns(keys.c.key, func.count())
            .join_from(self.table, keys, true())
            .where(self._within(window))
            .group_by(_FIRST)
            .order_by(_SECOND.desc(), _FIRST)
            .limit(TAG_KEY_LIMIT)
        )
        return [str(row[0]) for row in self._read(scope, statement)]

    def totals(
        self,
        scope: Scope,
        current: Window,
        previous: Window,
        metric: str,
        filters: Sequence[Filter],
    ) -> Row[*tuple[Any, ...]]:
        """One row: both windows' sums and line counts, and how many lack each optional measure."""
        c = self.table.c
        measure = self._measure(metric)
        now, before = self._within(current), self._within(previous)
        statement = (
            self.scoped_select(scope)
            .with_only_columns(
                func.sum(measure).filter(now),
                func.sum(measure).filter(before),
                func.count().filter(now),
                func.count().filter(before),
                func.count().filter(c.list_cost.is_(None)),
                func.count().filter(c.contracted_cost.is_(None)),
            )
            .where(or_(now, before))
        )
        return self._read(scope, self._filtered(statement, filters))[0]

    def rows(
        self,
        scope: Scope,
        current: Window,
        previous: Window,
        metric: str,
        groupings: tuple[Grouping, Grouping | None],
        filters: Sequence[Filter],
        limit: int,
    ) -> Sequence[Row[*tuple[Any, ...]]]:
        """The table, largest this period first, at most `limit` rows.

        Each row carries the count of every group in its fifth column, so a caller can say how
        many it left out without a second pass over the window.
        """
        statement = self._grouped(scope, current, previous, metric, groupings, filters)
        return self._read(scope, statement.add_columns(func.count().over()).limit(limit))

    def unallocated_rows(
        self,
        scope: Scope,
        current: Window,
        previous: Window,
        metric: str,
        groupings: tuple[Grouping, Grouping | None],
        filters: Sequence[Filter],
    ) -> Sequence[Row[*tuple[Any, ...]]]:
        """Every row naming the unallocated bucket, whatever its rank.

        Read separately so the row limit can never be what hides it. Unallocated cost is the
        first number finance asks about, and the bottom of a long table is where it would go.
        """
        first, second = groupings
        named = [self._expression(first) == UNALLOCATED]
        if second is not None:
            named.append(self._expression(second) == UNALLOCATED)
        statement = self._grouped(scope, current, previous, metric, groupings, filters)
        return self._read(scope, statement.where(or_(*named)))

    def named_series(
        self,
        scope: Scope,
        window: Window,
        metric: str,
        grouping: Grouping,
        filters: Sequence[Filter],
    ) -> list[str]:
        """The groups the chart names: the largest five, with unallocated always among them."""
        group = self._expression(grouping)
        statement = (
            self.scoped_select(scope)
            .with_only_columns(group, func.sum(self._measure(metric)))
            .where(self._within(window))
            .group_by(_FIRST)
            .order_by(_SECOND.desc(), _FIRST)
            .limit(NAMED_SERIES)
        )
        top = [str(row[0]) for row in self._read(scope, self._filtered(statement, filters))]
        if UNALLOCATED in top or len(top) < NAMED_SERIES:
            return top
        present = (
            self.scoped_select(scope)
            .with_only_columns(func.count())
            .where(self._within(window))
            .where(self._expression(grouping) == UNALLOCATED)
        )
        if int(self._read(scope, self._filtered(present, filters))[0][0]) > 0:
            return [*top[:-1], UNALLOCATED]
        return top

    def series(
        self,
        scope: Scope,
        window: Window,
        metric: str,
        grouping: Grouping,
        filters: Sequence[Filter],
        granularity: Granularity,
        named: Sequence[str],
    ) -> Sequence[Row[*tuple[Any, ...]]]:
        """What each named group cost per day or month, with null for everything else."""
        c = self.table.c
        unit = "day" if granularity == "daily" else "month"
        bucket = sql_cast(func.date_trunc(unit, func.timezone("UTC", c.charge_period_start)), Date)
        group = self._expression(grouping)
        label: ColumnElement[Any] = (
            case((group.in_(list(named)), group), else_=null()) if named else null()
        )
        statement = (
            self.scoped_select(scope)
            .with_only_columns(bucket, label, func.sum(self._measure(metric)))
            .where(self._within(window))
            .group_by(_FIRST, _SECOND)
            .order_by(_FIRST, _SECOND)
        )
        return self._read(scope, self._filtered(statement, filters))

    def _grouped(
        self,
        scope: Scope,
        current: Window,
        previous: Window,
        metric: str,
        groupings: tuple[Grouping, Grouping | None],
        filters: Sequence[Filter],
    ) -> Select[*tuple[Any, ...]]:
        first, second = groupings
        measure = self._measure(metric)
        now, before = self._within(current), self._within(previous)
        positions = [_FIRST] if second is None else [_FIRST, _SECOND]
        statement = (
            self.scoped_select(scope)
            .with_only_columns(
                self._expression(first),
                null() if second is None else self._expression(second),
                func.coalesce(func.sum(measure).filter(now), 0),
                func.coalesce(func.sum(measure).filter(before), 0),
            )
            .where(or_(now, before))
            .group_by(*positions)
            .order_by(_THIRD.desc(), _FOURTH.desc(), *positions)
        )
        return self._filtered(statement, filters)

    def _expression(self, grouping: Grouping) -> ColumnElement[Any]:
        """A grouping's value per line item, with a missing value named rather than dropped."""
        if grouping.dimension == TAG:
            if grouping.tag_key is None:
                raise ValueError("A tag grouping needs a tag key.")
            return func.coalesce(self.table.c.tags[grouping.tag_key].astext, UNALLOCATED)
        column = EXPLORABLE.get(grouping.dimension)
        if column is None:
            raise ValueError("That is not a column Cost Explorer groups by.")
        return func.coalesce(self.table.c[column], UNALLOCATED)

    def _measure(self, metric: str) -> ColumnElement[Any]:
        if metric not in METRICS:
            raise ValueError("That is not a measure Cost Explorer sums.")
        return self.table.c[metric]

    def _within(self, window: Window) -> ColumnElement[bool]:
        """The line items charged in a window.

        The billing month bounds come first because the table is partitioned on that column,
        so the planner reads only the months the window touches.
        """
        c = self.table.c
        return and_(
            c.billing_period_start >= window.start.replace(day=1),
            c.billing_period_start <= window.end.replace(day=1),
            c.charge_period_start >= _midnight(window.start),
            c.charge_period_start < _midnight(window.end + timedelta(days=1)),
        )

    def _filtered(
        self, statement: Select[*tuple[Any, ...]], filters: Sequence[Filter]
    ) -> Select[*tuple[Any, ...]]:
        for chosen in filters:
            statement = statement.where(self._expression(chosen.grouping).in_(list(chosen.values)))
        return statement

    def _read(
        self, scope: Scope, statement: Select[*tuple[Any, ...]]
    ) -> Sequence[Row[*tuple[Any, ...]]]:
        """Through the audited path, which checks the mark `scoped_select` left."""
        return self.fetch(scope, cast("Select[*tuple[object, ...]]", statement))
