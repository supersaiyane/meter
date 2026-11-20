"""Reading cloud accounts, never outside the scope that was handed in."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from sqlalchemy import Row, Table, func, select

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_api.guards import require_scope
from finops_core.domain.tenant import Scope


class AccountRepository(ScopedRepository):
    table: ClassVar[Table] = models.cloud_account
    resource: ClassVar[str] = "cloud_account"

    def list_in_scope(self, scope: Scope) -> Sequence[Row[tuple[object, ...]]]:
        """Every account the scope permits, and nothing else."""
        return self.fetch(scope)

    def count_in_organization(self, scope: Scope) -> int:
        """How many accounts the organization holds, whatever this scope can see.

        Deliberately not filtered by the account set. This is the denominator for
        `scope_coverage`, and computing it from the visible set is ISS-016 itself:
        it always reports full coverage, which is why that bug survives review.

        It is still confined to the tenant, and it returns a number rather than
        rows, so it cannot be turned into a way of reading out of scope data.
        """
        confirmed = require_scope(scope)
        total = self._connection.execute(
            select(func.count())
            .select_from(self.table)
            .where(self.table.c["tenant_id"] == confirmed.tenant_id)
        ).scalar_one()
        self._audit(confirmed, action="count", outcome="ALLOWED")
        return int(total)

    def get_in_scope(self, scope: Scope, account_id: str) -> Row[tuple[object, ...]] | None:
        """One account, or None when the scope does not reach it."""
        statement = self.scoped_select(scope).where(self.table.c["account_id"] == account_id)
        rows = self.fetch(scope, statement)
        return rows[0] if rows else None

    def set_role_health(
        self, scope: Scope, account_id: str, health: str, error: str | None, checked_at: object
    ) -> bool:
        """Record a recheck. Refuses an account the scope does not reach."""
        if self.get_in_scope(scope, account_id) is None:
            return False
        self._connection.execute(
            self.table.update()
            .where(
                self.table.c["tenant_id"] == scope.tenant_id,
                self.table.c["account_id"] == account_id,
            )
            .values(role_health=health, role_health_error=error, role_health_checked_at=checked_at)
        )
        return True

    def list_unhealthy(self, scope: Scope) -> Sequence[Row[tuple[object, ...]]]:
        """Accounts whose collector role is not healthy.

        An account we cannot read is still listed, because omitting it hides the
        gap rather than reporting it.
        """
        statement = self.scoped_select(scope).where(self.table.c["role_health"] != "HEALTHY")
        return self.fetch(scope, statement)
