"""Reading the savings ledger: each credit, its resource and the months it held. FEAT-078.

TASK-P11-008. One read, through the credit table's own scope rule, constraint 3, with the
recommendation's resource and the credit's months each read through their own tables' rules, so a
reader narrowed to one account sees that account's credits and nothing of another's. The months
come back as a JSON list with their money as text, so a figure is never rounded through a float.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from sqlalchemy import Row, Table, Text, cast, func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_api.guards import scope_predicate
from finops_core.domain.tenant import Scope


class SavingsCreditRepository(ScopedRepository):
    """Credits for verified savings, and the months each held. FEAT-078."""

    table: ClassVar[Table] = models.savings_credit
    resource: ClassVar[str] = "savings_credit"

    def every(self, scope: Scope) -> Sequence[Row[*tuple[Any, ...]]]:
        """Every credit this reader can see, with its resource and its months, oldest first."""
        credit, month, finding = self.table, models.savings_credit_month, models.recommendation
        resource = (
            select(finding.c.resource_id)
            .where(
                finding.c.recommendation_id == credit.c.recommendation_id,
                scope_predicate(finding, scope),
            )
            .correlate(credit)
            .scalar_subquery()
        )
        item = func.jsonb_build_object(
            "month", month.c.month,
            "state", month.c.state,
            "cost", cast(month.c.cost, Text),
            "saving", cast(month.c.saving, Text),
            "as_of", month.c.as_of,
            "collected_at", month.c.collected_at,
        )  # fmt: skip
        months = (
            select(func.jsonb_agg(aggregate_order_by(item, month.c.month)))
            .where(month.c.credit_id == credit.c.credit_id, scope_predicate(month, scope))
            .correlate(credit)
            .scalar_subquery()
        )
        statement = (
            self.scoped_select(scope)
            .add_columns(resource.label("resource_id"), months.label("months"))
            .order_by(credit.c.verified_on, credit.c.credit_id)
        )
        rows: Sequence[Row[*tuple[Any, ...]]] = self.fetch(scope, statement)
        return rows
