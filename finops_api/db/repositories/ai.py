"""Reading AI spend: the bill's AI lines, AI usage, GPU utilization and the connected providers.

TASK-P13-007, FEAT-081 to 085. Every read goes through the scope guard and the audit, constraint 3.
The bill's AI lines are scoped as the bill is, by account, so a provider's lines, whose sub account
is a project or a workspace no grant names, are visible at global scope only, P13 spec section 5.5.
AI usage and GPU utilization are scoped by the account they name, and a provider's usage, whose
account is its organization, is visible at global scope only for the same reason.

ADR-0028: nothing here names a vendor. An AI line is one a provider billed itself, one whose model
the bill names, or one FOCUS files under AI and Machine Learning.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, ClassVar, Final, cast

from sqlalchemy import Row, Select, Table, func, or_

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_core.domain.ai import ACCELERATED_FAMILIES
from finops_core.domain.tenant import Scope

#: The FOCUS service category a model's line is filed under.
AI_CATEGORY: Final = "AI and Machine Learning"
#: The cloud bill's own lines, as `ingest_source` names them.
CLOUD_BILL: Final = "aws_export"
#: A usage type naming an accelerated instance type, as a prefilter in the database; the domain's
#: `accelerated_instance_type` decides, so the database and the screen cannot disagree.
ACCELERATED_PATTERN: Final = r":(ml\.)?(" + "|".join(ACCELERATED_FAMILIES) + r")[0-9]"


def _fetch(
    repository: ScopedRepository, scope: Scope, statement: Any
) -> Sequence[Row[*tuple[Any, ...]]]:
    """Run a projected read through the audited path, as the cost repository does."""
    return repository.fetch(scope, cast("Select[*tuple[object, ...]]", statement))


class AiCostRepository(ScopedRepository):
    """The bill's AI lines and GPU lines, scoped as the bill is. FEAT-081, 083 and 084."""

    table: ClassVar[Table] = models.cost_focus_daily
    resource: ClassVar[str] = "cost_focus_daily"

    def _ai(self) -> Any:
        columns = self.table.c
        return or_(
            columns.ingest_source != CLOUD_BILL,
            columns.x_ai_model.is_not(None),
            columns.service_category == AI_CATEGORY,
        )

    def latest_period(self, scope: Scope) -> date | None:
        """The newest billing period holding an AI line this scope can see, or None for none."""
        statement = (
            self.scoped_select(scope)
            .with_only_columns(func.max(self.table.c.billing_period_start))
            .where(self._ai())
        )
        rows = _fetch(self, scope, statement)
        return rows[0][0] if rows else None

    def lines(self, scope: Scope, period: date) -> Sequence[Row[*tuple[Any, ...]]]:
        """Every AI line of the period this scope can see."""
        columns = self.table.c
        statement = (
            self.scoped_select(scope)
            .with_only_columns(
                columns.ingest_source,
                columns.provider_name,
                columns.billing_account_id,
                columns.sub_account_id,
                columns.region_id,
                columns.charge_period_start,
                columns.x_ai_model,
                columns.x_ai_token_type,
                columns.x_ai_tokens,
                columns.x_iam_principal,
                columns.resource_id,
                columns.tags,
                columns.effective_cost,
                columns.as_of,
                columns.collected_at,
            )
            .where(columns.billing_period_start == period, self._ai())
        )
        return _fetch(self, scope, statement)

    def latest_gpu_period(self, scope: Scope) -> date | None:
        """The newest billing period naming a GPU instance this scope can see, or None."""
        statement = (
            self.scoped_select(scope)
            .with_only_columns(func.max(self.table.c.billing_period_start))
            .where(self.table.c.x_usage_type.op("~*")(ACCELERATED_PATTERN))
        )
        rows = _fetch(self, scope, statement)
        return rows[0][0] if rows else None

    def gpu_lines(self, scope: Scope, period: date) -> Sequence[Row[*tuple[Any, ...]]]:
        """Every line of the period whose usage type may name an accelerated instance type."""
        columns = self.table.c
        statement = (
            self.scoped_select(scope)
            .with_only_columns(
                columns.sub_account_id,
                columns.region_id,
                columns.resource_id,
                columns.x_usage_type,
                columns.charge_period_start,
                columns.consumed_quantity,
                columns.effective_cost,
                columns.as_of,
                columns.collected_at,
            )
            .where(
                columns.billing_period_start == period,
                columns.x_usage_type.op("~*")(ACCELERATED_PATTERN),
            )
        )
        return _fetch(self, scope, statement)


class AiUsageRepository(ScopedRepository):
    """Tokens and requests per caller, scoped by the account each names. FEAT-082 and 083."""

    table: ClassVar[Table] = models.ai_usage_daily
    resource: ClassVar[str] = "ai_usage_daily"

    def between(self, scope: Scope, first: date, after: date) -> Sequence[Row[*tuple[Any, ...]]]:
        """Every row in `[first, after)` this scope can see."""
        columns = self.table.c
        statement = self.scoped_select(scope).where(
            columns.usage_date >= first, columns.usage_date < after
        )
        return _fetch(self, scope, statement)


class GpuUtilizationRepository(ScopedRepository):
    """A day of GPU utilization per instance, scoped by the account each names. FEAT-084."""

    table: ClassVar[Table] = models.gpu_utilization_daily
    resource: ClassVar[str] = "gpu_utilization_daily"

    def between(self, scope: Scope, first: date, after: date) -> Sequence[Row[*tuple[Any, ...]]]:
        """Every published day in `[first, after)` this scope can see."""
        columns = self.table.c
        statement = self.scoped_select(scope).where(
            columns.usage_date >= first, columns.usage_date < after
        )
        return _fetch(self, scope, statement)


class AiProviderAccountRepository(ScopedRepository):
    """The AI provider organizations a tenant connected. Payer wide: they belong to no account."""

    table: ClassVar[Table] = models.ai_provider_account
    resource: ClassVar[str] = "ai_provider_account"

    def active(self, scope: Scope) -> Sequence[Row[*tuple[Any, ...]]]:
        """The connected organizations, never the key's secret name."""
        columns = self.table.c
        statement = (
            self.scoped_select(scope)
            .with_only_columns(columns.provider, columns.organization_id, columns.name)
            .where(columns.active)
        )
        return _fetch(self, scope, statement)
