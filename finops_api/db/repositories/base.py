"""The only way a scoped table is read, and the audit that goes with it.

Every read writes an `audit_event` recording the scope that was evaluated. That
is not bookkeeping: it is the thing that makes the global viewer credential
defensible, because "who looked at everything, and when" has an answer. The
write is in the same transaction as the read, so a read cannot succeed while
its audit silently fails.

`Scope` is a required argument on every method here and has no default. See
`finops_api.guards` for why.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID, uuid4

from sqlalchemy import Row, Select, Table
from sqlalchemy.engine import Connection

from finops_api import guards
from finops_api.db import models
from finops_api.guards import assert_scoped, require_scope
from finops_core.domain.tenant import Scope


@dataclass(frozen=True)
class AccessContext:
    """Who is reading, and under which request. Both land in the audit row."""

    request_id: str
    principal_id: UUID | None = None


class ScopedRepository:
    """Base for every repository that touches tenant data."""

    table: ClassVar[Table]
    #: What the audit row calls this. Read by humans during an incident.
    resource: ClassVar[str]

    def __init__(self, connection: Connection, context: AccessContext) -> None:
        self._connection = connection
        self._context = context

    def scoped_select(self, scope: Scope) -> Select[*tuple[object, ...]]:
        """A select already confined to the scope. There is no unconfined variant."""
        return guards.scoped_select(self.table, scope)

    def fetch(
        self,
        scope: Scope,
        statement: Select[*tuple[object, ...]] | None = None,
    ) -> Sequence[Row[*tuple[object, ...]]]:
        """Run a scoped read and record it.

        Passing a statement is allowed so a repository can add its own ordering
        or extra predicates, but it still goes through `assert_scoped` first.
        """
        confirmed = require_scope(scope)
        query = self.scoped_select(confirmed) if statement is None else statement
        assert_scoped(query, self.table)
        rows = self._connection.execute(query).all()
        self._audit(confirmed, action="read", outcome="ALLOWED")
        return rows

    def _audit(self, scope: Scope, action: str, outcome: str) -> None:
        self._connection.execute(
            models.audit_event.insert().values(
                event_id=uuid4(),
                tenant_id=scope.tenant_id,
                principal_id=self._context.principal_id,
                action=action,
                resource=self.resource,
                scope_evaluated=json.loads(scope_as_json(scope)),
                is_global_read=scope.is_global,
                outcome=outcome,
                request_id=self._context.request_id,
            )
        )


def scope_as_json(scope: Scope) -> str:
    """The scope as it was evaluated, so an audit row is readable a year later."""
    return json.dumps(
        {
            "tenant_id": str(scope.tenant_id),
            "is_global": scope.is_global,
            "accounts": sorted(str(key) for key in scope.accounts),
        },
        sort_keys=True,
    )
