"""Reading recommendations, their events, and what they actually saved.

Three repositories rather than one, along the same seam the tables follow. The one
that matters is that `RealizedSavingRepository` is separate: an estimate and a
realization are different kinds of number, and a single repository able to return
both is the first place somebody adds them together.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from sqlalchemy import Row, Select, Table, func

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_core.domain.tenant import Scope


def _fetch(
    repository: ScopedRepository, scope: Scope, statement: Select[tuple[Any, ...]]
) -> Sequence[Row[tuple[Any, ...]]]:
    """Run a select through the scoped path, projected or not.

    One helper rather than a cast at every call site. `with_only_columns` narrows
    the row type and the base class is typed for the wide one, so without this each
    caller would carry the same annotation noise.
    """
    return repository.fetch(scope, statement)


class RecommendationRepository(ScopedRepository):
    """What is worth changing, ranked by money. FEAT-028."""

    table: ClassVar[Table] = models.recommendation
    resource: ClassVar[str] = "recommendation"

    def worst_first(
        self,
        scope: Scope,
        *,
        lifecycle: str | None = None,
        waste_class: str | None = None,
        owner: str | None = None,
        limit: int = 200,
    ) -> Sequence[Row[tuple[Any, ...]]]:
        """Biggest money first, filterable.

        Ranked by the saving rather than by confidence, per ADR-0016. A list
        ordered by confidence puts a certain twenty dollars above an uncertain ten
        thousand, and only one of those is worth a morning.
        """
        statement = self.scoped_select(scope)
        if lifecycle is not None:
            statement = statement.where(self.table.c.lifecycle == lifecycle)
        if waste_class is not None:
            statement = statement.where(self.table.c.waste_class == waste_class)
        if owner is not None:
            statement = statement.where(self.table.c.owner == owner)
        return _fetch(
            self,
            scope,
            statement.order_by(self.table.c.estimated_monthly_saving.desc()).limit(limit),
        )

    def one(self, scope: Scope, recommendation_id: Any) -> Row[tuple[Any, ...]] | None:
        rows = _fetch(
            self,
            scope,
            self.scoped_select(scope).where(self.table.c.recommendation_id == recommendation_id),
        )
        return rows[0] if rows else None

    def accounts_seen(self, scope: Scope) -> int:
        """How many accounts this scope has recommendations for.

        The coverage banner counts accounts, and a count of recommendations in
        that slot has now been the defect three times. See `tasks/lessons.md`.
        """
        statement = self.scoped_select(scope).with_only_columns(
            func.count(func.distinct(self.table.c.sub_account_id))
        )
        rows = _fetch(self, scope, statement)
        return int(rows[0][0] or 0) if rows else 0

    def unowned(self, scope: Scope) -> int:
        """How many open recommendations nobody is responsible for.

        ISS-021's lesson is that an unowned finding is never fixed, so the count
        is surfaced rather than left for somebody to notice.
        """
        statement = (
            self.scoped_select(scope)
            .where(self.table.c.owner.is_(None))
            .where(self.table.c.lifecycle.in_(("OPEN", "ACCEPTED", "IN_PROGRESS")))
            .with_only_columns(func.count())
        )
        rows = _fetch(self, scope, statement)
        return int(rows[0][0] or 0) if rows else 0


class RecommendationEventRepository(ScopedRepository):
    """How a recommendation got where it is."""

    table: ClassVar[Table] = models.recommendation_event
    resource: ClassVar[str] = "recommendation_event"

    def history(self, scope: Scope, recommendation_id: Any) -> Sequence[Row[tuple[Any, ...]]]:
        return _fetch(
            self,
            scope,
            self.scoped_select(scope)
            .where(self.table.c.recommendation_id == recommendation_id)
            .order_by(self.table.c.occurred_at),
        )


class RealizedSavingRepository(ScopedRepository):
    """What actually appeared in the bill. FEAT-029.

    Its own repository, and the separation is the feature. An estimate and a
    realization are different kinds of number, and a repository able to return
    both is the first place somebody adds them together.
    """

    table: ClassVar[Table] = models.realized_saving
    resource: ClassVar[str] = "realized_saving"

    def all_verdicts(self, scope: Scope, limit: int = 200) -> Sequence[Row[tuple[Any, ...]]]:
        """Every verdict, including the inconclusive ones.

        Newest first rather than largest first, because this screen is read to
        find out whether the last thing done worked, not to rank anything.
        """
        return _fetch(
            self,
            scope,
            self.scoped_select(scope).order_by(self.table.c.window_after_end.desc()).limit(limit),
        )

    def totals(self, scope: Scope) -> Sequence[Row[tuple[Any, ...]]]:
        """Realized money by verdict.

        Grouped by verdict rather than summed, deliberately. A single realized
        total would be added to the estimated total by the first person who saw
        them side by side, and an inconclusive saving is not a saving.
        """
        statement = (
            self.scoped_select(scope)
            .with_only_columns(
                self.table.c.verdict,
                func.count(),
                func.coalesce(func.sum(self.table.c.cost_before - self.table.c.cost_after), 0),
            )
            .group_by(self.table.c.verdict)
        )
        return _fetch(self, scope, statement)
