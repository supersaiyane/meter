"""Reading runs and the failures inside them.

Constraint 5 in CLAUDE.md: partial failure is first class. A caller asking for
runs gets the failures alongside them from `SyncErrorRepository`, because a run
list that omits its errors is how PARTIAL quietly reads as success.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from sqlalchemy import Row, Table, func, select

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_api.guards import require_scope, scope_predicate
from finops_core.domain.tenant import Scope


class IngestRunRepository(ScopedRepository):
    table: ClassVar[Table] = models.ingest_run
    resource: ClassVar[str] = "ingest_run"

    def recent(self, scope: Scope, limit: int) -> Sequence[Row[tuple[object, ...]]]:
        statement = (
            self.scoped_select(scope).order_by(self.table.c["started_at"].desc()).limit(limit)
        )
        return self.fetch(scope, statement)

    def never_succeeded(self, scope: Scope) -> Sequence[Row[tuple[object, ...]]]:
        """Collector and scope pairs that have run and never once succeeded.

        The freshness page lists watermarks, and a watermark only appears after
        a success. So the pair a reader most wants to find there, the one that
        has never worked at all, was the one pair the page omitted. ISS-163.

        `DISTINCT ON` rather than a group by, because what is wanted is the
        latest run of each pair including its typed cause, not an aggregate over
        all of them. A cause averaged across attempts is not a cause.
        """
        watermark = models.ingest_watermark
        already = select(1).where(
            watermark.c.tenant_id == self.table.c.tenant_id,
            watermark.c.collector == self.table.c.collector,
            watermark.c.scope_key == self.table.c.scope_key,
        )
        statement = (
            self.scoped_select(scope)
            .where(~already.exists())
            .distinct(self.table.c.collector, self.table.c.scope_key)
            .order_by(
                self.table.c.collector,
                self.table.c.scope_key,
                self.table.c.started_at.desc(),
            )
        )
        return self.fetch(scope, statement)

    def coverage(self, scope: Scope, shown: int) -> tuple[int, int]:
        """Runs shown, over runs the tenant has.

        The denominator is every run, not the page, because the page is capped
        at `RECENT_RUNS` and a reader has to know they are looking at the most
        recent few rather than at all of them.
        """
        confirmed = require_scope(scope)
        total = self._connection.execute(
            select(func.count())
            .select_from(self.table)
            .where(scope_predicate(self.table, confirmed))
        ).scalar_one()
        return shown, max(int(total), shown)


class SyncErrorRepository(ScopedRepository):
    table: ClassVar[Table] = models.sync_error
    resource: ClassVar[str] = "sync_error"

    def open_errors(self, scope: Scope) -> Sequence[Row[tuple[object, ...]]]:
        statement = self.scoped_select(scope).order_by(self.table.c["last_seen_at"].desc())
        return self.fetch(scope, statement)
