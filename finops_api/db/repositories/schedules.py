"""Report schedules. FEAT-069, TASK-P8-011, P8 spec sections 5.7 and 6.

A schedule is its owner's alone, `ByPrincipal` in the guard: the people it renders for read the
runs it made for them and never the schedule or its list of recipients. The writes confine
themselves to the owner through the same predicate, so a route that forgot to check ownership
would still change nothing, and each write is audited in its own transaction.

The view a schedule names is read beside it through the guard's own predicate for that table,
so a view its owner can no longer open lists as one they cannot, rather than by its name.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, Row, and_, delete, insert, update

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_api.guards import ScopeViolationError, require_scope, scope_predicate
from finops_core.domain.tenant import Scope

ScheduleRow = Row[*tuple[Any, ...]]


class ScheduleRepository(ScopedRepository):
    """The schedules the reader owns, and the changes only they can make."""

    table = models.report_schedule
    resource = "report_schedule"

    def schedules(self, scope: Scope) -> Sequence[ScheduleRow]:
        """The reader's schedules with the view each names, the latest changed first."""
        view = models.saved_view
        statement = (
            self.scoped_select(scope)
            .outerjoin(
                view,
                and_(view.c.view_id == self.table.c.view_id, scope_predicate(view, scope)),
            )
            .add_columns(view.c.name.label("view_name"), view.c.screen_path.label("screen_path"))
            .order_by(self.table.c.updated_at.desc(), self.table.c.schedule_id)
        )
        rows: Sequence[ScheduleRow] = self.fetch(scope, statement)
        return rows

    def schedule(self, scope: Scope, schedule_id: UUID) -> ScheduleRow | None:
        """One of the reader's schedules, or None."""
        rows: Sequence[ScheduleRow] = self.fetch(
            scope, self.scoped_select(scope).where(self.table.c.schedule_id == schedule_id)
        )
        return rows[0] if rows else None

    def create(
        self,
        scope: Scope,
        *,
        view_id: UUID,
        export_path: str,
        file_format: str,
        cadence: str,
        recipients: Sequence[str],
        next_run_at: datetime,
        at: datetime,
    ) -> ScheduleRow:
        """A new schedule, owned by the person the scope names, enabled."""
        confirmed = require_scope(scope)
        statement = (
            insert(self.table)
            .values(
                schedule_id=uuid4(),
                tenant_id=confirmed.tenant_id,
                owner_id=_owner(confirmed),
                view_id=view_id,
                export_path=export_path,
                format=file_format,
                cadence=cadence,
                recipients=list(recipients),
                enabled=True,
                next_run_at=next_run_at,
                created_at=at,
                updated_at=at,
            )
            .returning(*self.table.c)
        )
        row: ScheduleRow = self._connection.execute(statement).one()
        self._audit(confirmed, action="create", outcome="ALLOWED")
        return row

    def change(
        self, scope: Scope, schedule_id: UUID, *, at: datetime, values: dict[str, object]
    ) -> ScheduleRow | None:
        """Change a schedule the reader owns. None, audited as DENIED, when they own none."""
        confirmed = require_scope(scope)
        statement = (
            update(self.table)
            .where(*self._owned(confirmed, schedule_id))
            .values(**values, updated_at=at)
            .returning(*self.table.c)
        )
        row: ScheduleRow | None = self._connection.execute(statement).one_or_none()
        self._audit(confirmed, action="change", outcome="DENIED" if row is None else "ALLOWED")
        return row

    def delete(self, scope: Scope, schedule_id: UUID) -> ScheduleRow | None:
        """Delete a schedule the reader owns and return it. None, audited DENIED, otherwise."""
        confirmed = require_scope(scope)
        statement = (
            delete(self.table).where(*self._owned(confirmed, schedule_id)).returning(*self.table.c)
        )
        row: ScheduleRow | None = self._connection.execute(statement).one_or_none()
        self._audit(confirmed, action="delete", outcome="DENIED" if row is None else "ALLOWED")
        return row

    def _owned(self, scope: Scope, schedule_id: UUID) -> tuple[ColumnElement[bool], ...]:
        return (scope_predicate(self.table, scope), self.table.c.schedule_id == schedule_id)


def _owner(scope: Scope) -> str:
    """The person a schedule belongs to. A scope naming nobody owns nothing, as the guard says."""
    if scope.principal_id is None:
        raise ScopeViolationError(
            "A report schedule belongs to a person and this scope names nobody, so nothing is "
            "written. See ADR-0029."
        )
    return scope.principal_id
