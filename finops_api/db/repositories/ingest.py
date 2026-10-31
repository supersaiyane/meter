"""Reading runs and the failures inside them.

Constraint 5 in CLAUDE.md: partial failure is first class. A caller asking for
runs gets the failures alongside them from `SyncErrorRepository`, because a run
list that omits its errors is how PARTIAL quietly reads as success.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from sqlalchemy import Row, Table

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_core.domain.tenant import Scope


class IngestRunRepository(ScopedRepository):
    table: ClassVar[Table] = models.ingest_run
    resource: ClassVar[str] = "ingest_run"

    def recent(self, scope: Scope, limit: int) -> Sequence[Row[tuple[object, ...]]]:
        statement = (
            self.scoped_select(scope).order_by(self.table.c["started_at"].desc()).limit(limit)
        )
        return self.fetch(scope, statement)


class SyncErrorRepository(ScopedRepository):
    table: ClassVar[Table] = models.sync_error
    resource: ClassVar[str] = "sync_error"

    def open_errors(self, scope: Scope) -> Sequence[Row[tuple[object, ...]]]:
        statement = self.scoped_select(scope).order_by(self.table.c["last_seen_at"].desc())
        return self.fetch(scope, statement)
