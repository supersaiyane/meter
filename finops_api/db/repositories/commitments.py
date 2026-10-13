"""What the organization holds, what its plans aim for and buy. P14, FEAT-086, 088 and 089.

TASK-P14-005. Both tables belong to the payer, ADR-0025, and are `PayerWide` in the guard, so a
narrowed scope reads nothing from either. The policy is the payer's to change: its write is made
by a person, audited ALLOWED or DENIED in the write's own transaction, and a refusal reaches the
end of its request without raising so the rollback cannot take the audit row with it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import Row, Table
from sqlalchemy.dialects.postgresql import insert

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_api.guards import ScopeViolationError, require_scope
from finops_core.domain.commitments import CommitmentPolicy
from finops_core.domain.tenant import Scope

#: Through `Any`, as the other repositories read their rows.
CommitmentRow = Row[*tuple[Any, ...]]


class CommitmentInventoryRepository(ScopedRepository):
    """Every commitment the organization holds. FEAT-086."""

    table: ClassVar[Table] = models.commitment_inventory
    resource: ClassVar[str] = "commitment_inventory"

    def held(self, scope: Scope) -> Sequence[CommitmentRow]:
        """Every commitment, the soonest ending first; retired ones included, as they are rows."""
        statement = self.scoped_select(scope).order_by(
            self.table.c.ends_at, self.table.c.commitment_id
        )
        rows: Sequence[CommitmentRow] = self.fetch(scope, statement)
        return rows


class CommitmentPolicyRepository(ScopedRepository):
    """What the tenant's purchase plans aim for. FEAT-088, OPEN-38."""

    table: ClassVar[Table] = models.commitment_policy
    resource: ClassVar[str] = "commitment_policy"

    def current(self, scope: Scope) -> CommitmentRow | None:
        """The tenant's policy, or None where none was installed."""
        rows: Sequence[CommitmentRow] = self.fetch(scope, self.scoped_select(scope))
        return rows[0] if rows else None

    def change(
        self, scope: Scope, policy: CommitmentPolicy, *, reason: str, at: datetime
    ) -> CommitmentRow:
        """Set the policy, audited ALLOWED. Only a global scope naming a person may."""
        confirmed = require_scope(scope)
        if not confirmed.is_global or confirmed.principal_id is None:
            raise ScopeViolationError(
                "The commitment policy is the payer's, so only a person whose scope is the whole "
                "organization may change it. See ADR-0025."
            )
        values = {
            "target_coverage": policy.target_coverage,
            "term_years": policy.term_years,
            "payment_option": policy.payment_option,
            "ladder_limit": policy.ladder_limit,
            "reason": reason,
            "updated_by": confirmed.principal_id,
            "updated_at": at,
        }
        statement = (
            insert(self.table)
            .values(tenant_id=confirmed.tenant_id, **values)
            .on_conflict_do_update(index_elements=[self.table.c.tenant_id], set_=values)
            .returning(*self.table.c)
        )
        row: CommitmentRow = self._connection.execute(statement).one()
        self._audit(confirmed, action="change", outcome="ALLOWED")
        return row

    def refuse(self, scope: Scope) -> None:
        """Record a refused change, so a narrowed attempt is in the audit trail."""
        self._audit(require_scope(scope), action="change", outcome="DENIED")


class PurchasePlanRepository(ScopedRepository):
    """Meter's purchase plans, one a month. FEAT-089, TASK-P14-007."""

    table: ClassVar[Table] = models.purchase_plan
    resource: ClassVar[str] = "purchase_plan"

    def current(self, scope: Scope) -> CommitmentRow | None:
        """The newest month's plan, whatever its status, or None before one was drafted."""
        statement = self.scoped_select(scope).order_by(self.table.c.plan_month.desc()).limit(1)
        rows: Sequence[CommitmentRow] = self.fetch(scope, statement)
        return rows[0] if rows else None


class PurchasePlanLineRepository(ScopedRepository):
    """The lines of one plan, in the order the plan placed them. FEAT-089."""

    table: ClassVar[Table] = models.purchase_plan_line
    resource: ClassVar[str] = "purchase_plan_line"

    def of(self, scope: Scope, plan_id: UUID) -> Sequence[CommitmentRow]:
        statement = (
            self.scoped_select(scope)
            .where(self.table.c.plan_id == plan_id)
            .order_by(self.table.c.line_no)
        )
        rows: Sequence[CommitmentRow] = self.fetch(scope, statement)
        return rows


class PurchaseRecommendationRepository(ScopedRepository):
    """The provider's own purchase recommendations, one per program. FEAT-089, TASK-P14-006."""

    table: ClassVar[Table] = models.purchase_recommendation
    resource: ClassVar[str] = "purchase_recommendation"

    def all(self, scope: Scope) -> Sequence[CommitmentRow]:
        statement = self.scoped_select(scope).order_by(
            self.table.c.kind.desc(), self.table.c.program
        )
        rows: Sequence[CommitmentRow] = self.fetch(scope, statement)
        return rows
