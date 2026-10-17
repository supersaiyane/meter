"""Plans, their estimates, their pull requests and their comparisons. P16, FEAT-095 to 097.

TASK-P16-008. Every table here is `PayerWide` in the guard, ADR-0025 and spec section 5.8: a plan
names no account until it is applied, so a narrowed scope reads nothing from any of them. Each
read goes through the guard and is audited, as every scoped read is. Rows are joined in the route
rather than in one statement, because the guard confines a select to one table.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import Row, Table

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_core.domain.tenant import Scope

#: Through `Any`, as the other repositories read their rows.
EstimateRow = Row[*tuple[Any, ...]]


class PlanRepository(ScopedRepository):
    """The plans received, refused ones with them. FEAT-095."""

    table: ClassVar[Table] = models.terraform_plan
    resource: ClassVar[str] = "terraform_plan"

    def newest(self, scope: Scope, limit: int) -> Sequence[EstimateRow]:
        """The newest `limit` plans, newest first."""
        statement = (
            self.scoped_select(scope)
            .order_by(self.table.c.received_at.desc(), self.table.c.plan_id)
            .limit(limit)
        )
        rows: Sequence[EstimateRow] = self.fetch(scope, statement)
        return rows

    def one(self, scope: Scope, plan_id: UUID) -> EstimateRow | None:
        statement = self.scoped_select(scope).where(self.table.c.plan_id == plan_id)
        rows = self.fetch(scope, statement)
        return rows[0] if rows else None


class _ByPlan(ScopedRepository):
    """Rows that hang off a plan, read for the plans asked for."""

    def of(self, scope: Scope, plan_ids: Collection[UUID]) -> Sequence[EstimateRow]:
        if not plan_ids:
            return ()
        statement = self.scoped_select(scope).where(self.table.c.plan_id.in_(list(plan_ids)))
        rows: Sequence[EstimateRow] = self.fetch(scope, statement)
        return rows


class PlanEstimateRepository(_ByPlan):
    """A plan's monthly figures, line counts and comment. FEAT-095 and 096."""

    table: ClassVar[Table] = models.plan_estimate
    resource: ClassVar[str] = "plan_estimate"


class EstimateLineRepository(_ByPlan):
    """Each change priced, or the reason it is not. FEAT-095."""

    table: ClassVar[Table] = models.plan_estimate_line
    resource: ClassVar[str] = "plan_estimate_line"


class PlannedChangeRepository(_ByPlan):
    """What each change left unknown until apply, or withheld as sensitive. FEAT-095."""

    table: ClassVar[Table] = models.planned_change
    resource: ClassVar[str] = "planned_change"


class EstimateComparisonRepository(_ByPlan):
    """Each created resource set against its bill. FEAT-097."""

    table: ClassVar[Table] = models.estimate_comparison
    resource: ClassVar[str] = "estimate_comparison"

    def every(self, scope: Scope) -> Sequence[EstimateRow]:
        rows: Sequence[EstimateRow] = self.fetch(scope)
        return rows


class PlanPullRequestRepository(ScopedRepository):
    """Each pull request a plan came from, as the code host last reported it. FEAT-096."""

    table: ClassVar[Table] = models.plan_pull_request
    resource: ClassVar[str] = "plan_pull_request"

    def of(self, scope: Scope, repositories: Collection[str]) -> Sequence[EstimateRow]:
        """The pull requests of the repositories asked for; the route matches them by number."""
        if not repositories:
            return ()
        statement = self.scoped_select(scope).where(
            self.table.c.repository.in_(sorted(repositories))
        )
        rows: Sequence[EstimateRow] = self.fetch(scope, statement)
        return rows
