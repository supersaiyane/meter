"""The spend forecast's reads. FEAT-066, TASK-P8-008.

Two reads, both derived from `scoped_select`: the bounds of what this scope has collected, and
the effective cost of each day inside them. The forecast itself is `finops_query.forecast`, which
holds no database, so everything here is a read and nothing is a judgement.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, ClassVar, cast

from sqlalchemy import Date, Select, Table, func, literal_column
from sqlalchemy import cast as sql_cast
from sqlalchemy.engine import Row

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_core.domain.tenant import Scope


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time(), tzinfo=UTC)


class ForecastRepository(ScopedRepository):
    """Read only, and only the line items this scope may see."""

    table: ClassVar[Table] = models.cost_focus_daily
    resource: ClassVar[str] = "cost_focus_daily"

    def collected(self, scope: Scope) -> tuple[date | None, date | None]:
        """The first billing month this scope holds, and the last day it was billed for.

        Days between the two that billed nothing are zeros. Days outside them are not history
        at all, and the forecast has to be able to tell the two apart.
        """
        c = self.table.c
        statement = self.scoped_select(scope).with_only_columns(
            func.min(c.billing_period_start), func.max(c.charge_period_start)
        )
        first, last = self._read(scope, statement)[0]
        if not isinstance(first, date) or not isinstance(last, datetime):
            return None, None
        return first, last.astimezone(UTC).date()

    def daily(self, scope: Scope, start: date, end: date) -> dict[date, Decimal]:
        """Effective cost for each UTC day from `start` to `end`, zero where nothing billed."""
        c = self.table.c
        day = sql_cast(func.date_trunc("day", func.timezone("UTC", c.charge_period_start)), Date)
        statement = (
            self.scoped_select(scope)
            .with_only_columns(day, func.sum(c.effective_cost))
            # The partition key first, so the planner reads only the months in the window.
            .where(c.billing_period_start >= start.replace(day=1))
            .where(c.billing_period_start <= end.replace(day=1))
            .where(c.charge_period_start >= _midnight(start))
            .where(c.charge_period_start < _midnight(end + timedelta(days=1)))
            .group_by(literal_column("1"))
        )
        billed = {row[0]: Decimal(row[1]) for row in self._read(scope, statement)}
        days = (start + timedelta(days=offset) for offset in range((end - start).days + 1))
        return {day: billed.get(day, Decimal(0)) for day in days}

    def _read(
        self, scope: Scope, statement: Select[tuple[Any, ...]]
    ) -> Sequence[Row[tuple[Any, ...]]]:
        """Through the audited path, which checks the mark `scoped_select` left."""
        return self.fetch(scope, cast("Select[tuple[object, ...]]", statement))
