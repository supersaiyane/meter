"""What the organization holds, what its plans aim for and buy. P14, FEAT-086, 088 and 089.

TASK-P14-005. Both tables belong to the payer, ADR-0025, and are `PayerWide` in the guard, so a
narrowed scope reads nothing from either. The policy is the payer's to change: its write is made
by a person, audited ALLOWED or DENIED in the write's own transaction, and a refusal reaches the
end of its request without raising so the rollback cannot take the audit row with it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, ClassVar, Final
from uuid import UUID, uuid4

from sqlalchemy import Row, Table, func, select, update
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


#: The transitions a person makes, spec section 5.2, OPEN-36: each status, and those it leaves from.
#: Lapsing and verifying are the collector's. The database holds the same list, constraint 11.
PERSON_TRANSITIONS: Final[dict[str, tuple[str, ...]]] = {
    "APPROVED": ("DRAFT",),
    "BOUGHT": ("APPROVED",),
    "WITHDRAWN": ("DRAFT", "APPROVED"),
}
#: Each transition as a reader says it.
DONE: Final = {"APPROVED": "approved", "BOUGHT": "recorded as bought", "WITHDRAWN": "withdrawn"}


class TransitionRefusedError(Exception):
    """A transition the plan's status does not allow, in words for the person who asked."""


class PurchasePlanRepository(ScopedRepository):
    """Meter's purchase plans, one a month. FEAT-089 and FEAT-090, TASK-P14-007 and 008."""

    table: ClassVar[Table] = models.purchase_plan
    resource: ClassVar[str] = "purchase_plan"

    def current(self, scope: Scope) -> CommitmentRow | None:
        """The newest month's plan, whatever its status, or None before one was drafted."""
        statement = self.scoped_select(scope).order_by(self.table.c.plan_month.desc()).limit(1)
        rows: Sequence[CommitmentRow] = self.fetch(scope, statement)
        return rows[0] if rows else None

    def one(self, scope: Scope, plan_id: UUID) -> CommitmentRow | None:
        statement = self.scoped_select(scope).where(self.table.c.plan_id == plan_id)
        rows: Sequence[CommitmentRow] = self.fetch(scope, statement)
        return rows[0] if rows else None

    def transition(
        self, scope: Scope, plan_id: UUID, *, to_status: str, note: str, at: datetime
    ) -> CommitmentRow | None:
        """Move a plan on, as a person, with a note, audited ALLOWED. None for a plan not found.

        Only a person whose scope is the organization may, because a commitment is the payer's,
        ADR-0025. A transition the plan's status does not allow raises `TransitionRefusedError`,
        and a plan with nothing to buy this month cannot be approved. The status is changed only
        if it is still what was read, so two people acting at once cannot both move it.
        """
        confirmed = require_scope(scope)
        if not confirmed.is_global or confirmed.principal_id is None:
            raise ScopeViolationError(
                "A purchase plan is the payer's, so only a person whose scope is the whole "
                "organization may approve, record or withdraw it. See ADR-0025."
            )
        plan = self.one(confirmed, plan_id)
        if plan is None:
            return None
        if plan.status not in PERSON_TRANSITIONS[to_status]:
            raise TransitionRefusedError(
                f"This plan is {plan.status.lower()}, so it cannot be {DONE[to_status]}."
            )
        if to_status == "APPROVED" and not self._buys_this_month(plan):
            raise TransitionRefusedError(
                "This plan buys nothing this month, so there is nothing to approve."
            )
        statement = (
            update(self.table)
            .where(
                self.table.c.plan_id == plan_id,
                self.table.c.tenant_id == confirmed.tenant_id,
                self.table.c.status == plan.status,
            )
            .values(status=to_status)
            .returning(*self.table.c)
        )
        row: CommitmentRow | None = self._connection.execute(statement).one_or_none()
        if row is None:
            raise TransitionRefusedError(
                "The plan changed while this was being decided; read it again."
            )
        self._connection.execute(
            models.purchase_plan_event.insert().values(
                event_id=uuid4(),
                plan_id=plan_id,
                tenant_id=confirmed.tenant_id,
                from_status=plan.status,
                to_status=to_status,
                principal=confirmed.principal_id,
                at=at,
                note=note,
            )
        )
        self._audit(confirmed, action=f"plan.{to_status.lower()}", outcome="ALLOWED")
        return row

    def refuse(self, scope: Scope, to_status: str) -> None:
        """Record a refused transition, so a narrowed attempt is in the audit trail."""
        self._audit(require_scope(scope), action=f"plan.{to_status.lower()}", outcome="DENIED")

    def _buys_this_month(self, plan: CommitmentRow) -> bool:
        lines = models.purchase_plan_line.c
        count = self._connection.execute(
            select(func.count())
            .select_from(models.purchase_plan_line)
            .where(lines.plan_id == plan.plan_id, lines.tranche_month == plan.plan_month)
        ).scalar_one()
        return bool(count)


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


class PurchasePlanEventRepository(ScopedRepository):
    """Each step of one plan's lifecycle, the oldest first, with who took it. FEAT-090."""

    table: ClassVar[Table] = models.purchase_plan_event
    resource: ClassVar[str] = "purchase_plan_event"

    def of(self, scope: Scope, plan_id: UUID) -> Sequence[CommitmentRow]:
        statement = (
            self.scoped_select(scope)
            .where(self.table.c.plan_id == plan_id)
            .order_by(self.table.c.at, self.table.c.event_id)
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
