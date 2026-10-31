"""Reading cloud accounts, never outside the scope that was handed in."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from sqlalchemy import Row, Table

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_core.domain.tenant import Scope


class AccountRepository(ScopedRepository):
    table: ClassVar[Table] = models.cloud_account
    resource: ClassVar[str] = "cloud_account"

    def list_in_scope(self, scope: Scope) -> Sequence[Row[tuple[object, ...]]]:
        """Every account the scope permits, and nothing else."""
        return self.fetch(scope)

    def list_unhealthy(self, scope: Scope) -> Sequence[Row[tuple[object, ...]]]:
        """Accounts whose collector role is not healthy.

        An account we cannot read is still listed, because omitting it hides the
        gap rather than reporting it.
        """
        statement = self.scoped_select(scope).where(self.table.c["role_health"] != "HEALTHY")
        return self.fetch(scope, statement)
