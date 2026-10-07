"""Saved views, the report library's rows. FEAT-068, TASK-P8-010, P8 spec sections 5.6 and 6.

A view is read by its owner, and by everybody in the tenant once its owner shares it, through the
`OwnedOrShared` rule in the guard, ADR-0032. Only the owner changes one. The write statements
below confine themselves to the owner's own rows as well as to the scope, so a route that forgot
to check ownership would still change nothing: the second of the two places scope is enforced,
constraint 3, applied to writes.

Every write is audited, ALLOWED or DENIED, in the transaction of the write. A refused write
therefore has to reach the end of its request without raising, or the rollback takes the
audit row with it, and the routes answer a refusal rather than raise one for that reason.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, Row, Select, delete, func, insert, update

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_api.guards import ScopeViolationError, require_scope, scope_predicate
from finops_core.domain.tenant import Scope

#: A saved view's row. Read through `Any`, as the other repositories read theirs: SQLAlchemy 2.1
#: types a row's cells, and the general select types them as `object`.
ViewRow = Row[*tuple[Any, ...]]


class SavedViewRepository(ScopedRepository):
    """The saved views a person may open, and the changes only their owner may make."""

    table = models.saved_view
    resource = "saved_view"

    def views(self, scope: Scope, limit: int) -> Sequence[ViewRow]:
        """The reader's own views and the tenant's shared ones, the latest changed first."""
        statement = (
            self.scoped_select(scope)
            .order_by(self.table.c.updated_at.desc(), self.table.c.view_id)
            .limit(limit)
        )
        rows: Sequence[ViewRow] = self.fetch(scope, statement)
        return rows

    def count(self, scope: Scope) -> int:
        """How many the reader may open, so a list cut at its limit says it was cut."""
        # The projection narrows the select's type and `fetch` is declared for the general one,
        # so it is cast here, as the assistant's repository does for its counts.
        projected = self.scoped_select(scope).with_only_columns(func.count())
        rows: Sequence[ViewRow] = self.fetch(scope, cast("Select[*tuple[object, ...]]", projected))
        return int(rows[0][0])

    def view(self, scope: Scope, view_id: UUID) -> ViewRow | None:
        """One view, or None when the reader may open none of that id."""
        statement = self.scoped_select(scope).where(self.table.c.view_id == view_id)
        rows: Sequence[ViewRow] = self.fetch(scope, statement)
        return rows[0] if rows else None

    def create(
        self,
        scope: Scope,
        *,
        name: str,
        screen_path: str,
        query: Mapping[str, str | list[str]],
        visibility: str,
        at: datetime,
    ) -> ViewRow:
        """A new view, owned by the person the scope names."""
        confirmed = require_scope(scope)
        statement = (
            insert(self.table)
            .values(
                view_id=uuid4(),
                tenant_id=confirmed.tenant_id,
                owner_id=_owner(confirmed),
                name=name,
                screen_path=screen_path,
                query=dict(query),
                visibility=visibility,
                created_at=at,
                updated_at=at,
            )
            .returning(*self.table.c)
        )
        row: ViewRow = self._connection.execute(statement).one()
        self._audit(confirmed, action="create", outcome="ALLOWED")
        return row

    def change(
        self,
        scope: Scope,
        view_id: UUID,
        *,
        at: datetime,
        name: str | None = None,
        visibility: str | None = None,
    ) -> ViewRow | None:
        """Rename or share a view the reader owns. None, audited as DENIED, when they own none."""
        confirmed = require_scope(scope)
        values: dict[str, object] = {"updated_at": at}
        if name is not None:
            values["name"] = name
        if visibility is not None:
            values["visibility"] = visibility
        statement = (
            update(self.table)
            .where(*self._owned(confirmed, view_id))
            .values(**values)
            .returning(*self.table.c)
        )
        row: ViewRow | None = self._connection.execute(statement).one_or_none()
        self._audit(confirmed, action="change", outcome="DENIED" if row is None else "ALLOWED")
        return row

    def delete(self, scope: Scope, view_id: UUID) -> ViewRow | None:
        """Delete a view the reader owns and return it. None, audited DENIED, if they own none."""
        confirmed = require_scope(scope)
        statement = (
            delete(self.table).where(*self._owned(confirmed, view_id)).returning(*self.table.c)
        )
        row: ViewRow | None = self._connection.execute(statement).one_or_none()
        self._audit(confirmed, action="delete", outcome="DENIED" if row is None else "ALLOWED")
        return row

    def _owned(self, scope: Scope, view_id: UUID) -> tuple[ColumnElement[bool], ...]:
        """The view of that id, if the scope may open it and its person owns it."""
        return (
            scope_predicate(self.table, scope),
            self.table.c.view_id == view_id,
            self.table.c.owner_id == _owner(scope),
        )


def _owner(scope: Scope) -> str:
    """The person a write is made by. A scope naming nobody writes nothing, the fail closed case."""
    if scope.principal_id is None:
        raise ScopeViolationError(
            "A saved view is written by a person and this scope names nobody, so nothing is "
            "written. See ADR-0032."
        )
    return scope.principal_id
