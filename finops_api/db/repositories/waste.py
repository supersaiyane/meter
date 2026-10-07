"""Reading recommendations, their events, what they saved, and the posture score.

Four repositories rather than one, along the same seam the tables follow. The one
that matters is that `RealizedSavingRepository` is separate: an estimate and a
realization are different kinds of number, and a single repository able to return
both is the first place somebody adds them together.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from sqlalchemy import Row, ScalarSelect, Select, Table, func, select

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_api.guards import scope_predicate
from finops_core.constants import TEAM_TAG
from finops_core.domain.tenant import Scope


def _fetch(
    repository: ScopedRepository, scope: Scope, statement: Select[*tuple[Any, ...]]
) -> Sequence[Row[*tuple[Any, ...]]]:
    """Run a select through the scoped path, projected or not.

    One helper rather than a cast at every call site. `with_only_columns` narrows
    the row type and the base class is typed for the wide one, so without this each
    caller would carry the same annotation noise.
    """
    return repository.fetch(scope, statement)


class RefusalRepository(ScopedRepository):
    """What a sizing rule examined and declined to recommend. FEAT-062, ADR-0027."""

    table: ClassVar[Table] = models.sizing_refusal
    resource: ClassVar[str] = "sizing_refusal"

    def latest(self, scope: Scope, limit: int = 200) -> Sequence[Row[*tuple[Any, ...]]]:
        """Every refusal this reader can see, the least observed first.

        Ordered by observation days ascending rather than by anything resembling severity,
        because a refusal has no money and ADR-0016 orders by money. The useful order is by how
        much the judgement rests on: a rule that declined after four days of history is the one
        a reader should question first, and one that declined after ninety is the one they can
        rely on.
        """
        statement = (
            self.scoped_select(scope)
            .order_by(
                self.table.c.observation_days.asc(),
                self.table.c.resource_id,
            )
            .limit(limit)
        )
        return _fetch(self, scope, statement)

    def counted(self, scope: Scope) -> int:
        """How many resources were examined and cleared, for the sentence above the list."""
        statement = self.scoped_select(scope).with_only_columns(
            func.count(func.distinct(self.table.c.resource_id))
        )
        rows = _fetch(self, scope, statement)
        return int(rows[0][0] or 0) if rows else 0


class RecommendationRepository(ScopedRepository):
    """What is worth changing, ranked by money. FEAT-028."""

    table: ClassVar[Table] = models.recommendation
    resource: ClassVar[str] = "recommendation"

    def _suggested_owner(self, scope: Scope) -> ScalarSelect[Any]:
        """The resource's team tag, from the inventory node naming it, as a suggestion. ISS-021.

        Joined on the provider's own identifier within the account, as `findings_for` joins, and
        confined by the node table's own scope rule, so a node outside the reader's access never
        suggests anything. Never stored: an owner is a person's decision, and a tag only says
        whom to ask. An empty tag suggests nobody. At most one node can match, because
        `uq_topology_node__provider_id` holds one node per resource in a tenant.
        """
        node = models.topology_node
        return (
            select(func.nullif(node.c.tags[TEAM_TAG].astext, ""))
            .where(node.c.tenant_id == self.table.c.tenant_id)
            .where(node.c.sub_account_id == self.table.c.sub_account_id)
            .where(node.c.provider_id == self.table.c.resource_id)
            .where(scope_predicate(node, scope))
            .correlate(self.table)
            .scalar_subquery()
        )

    def worst_first(
        self,
        scope: Scope,
        *,
        lifecycle: str | None = None,
        waste_class: str | None = None,
        owner: str | None = None,
        limit: int = 200,
    ) -> Sequence[Row[*tuple[Any, ...]]]:
        """Biggest money first, filterable.

        Ranked by the saving rather than by confidence, per ADR-0016. A list
        ordered by confidence puts a certain twenty dollars above an uncertain ten
        thousand, and only one of those is worth a morning.
        """
        statement = self.scoped_select(scope).add_columns(
            self._suggested_owner(scope).label("suggested_owner")
        )
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

    def one(self, scope: Scope, recommendation_id: Any) -> Row[*tuple[Any, ...]] | None:
        rows = _fetch(
            self,
            scope,
            self.scoped_select(scope)
            .add_columns(self._suggested_owner(scope).label("suggested_owner"))
            .where(self.table.c.recommendation_id == recommendation_id),
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

    def history(self, scope: Scope, recommendation_id: Any) -> Sequence[Row[*tuple[Any, ...]]]:
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

    def all_verdicts(self, scope: Scope, limit: int = 200) -> Sequence[Row[*tuple[Any, ...]]]:
        """Every verdict, including the inconclusive ones.

        Newest first rather than largest first, because this screen is read to
        find out whether the last thing done worked, not to rank anything.
        """
        return _fetch(
            self,
            scope,
            self.scoped_select(scope).order_by(self.table.c.window_after_end.desc()).limit(limit),
        )

    def totals(self, scope: Scope) -> Sequence[Row[*tuple[Any, ...]]]:
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


class ScoreRepository(ScopedRepository):
    """The posture score and its history. FEAT-043.

    Every read returns rows a caller has to join to their components, deliberately.
    There is no method returning a total on its own, because FEAT-043 ships only if
    the score decomposes and a convenient total is the first thing a screen would
    render alone.
    """

    table: ClassVar[Table] = models.finops_score
    resource: ClassVar[str] = "finops_score"

    def latest(self, scope: Scope, limit: int = 200) -> Sequence[Row[*tuple[Any, ...]]]:
        """The most recent score per subject.

        Newest first across subjects rather than one row per subject, because the
        screen shows a list of accounts and their current standing and the trend
        comes from `history`.
        """
        newest = (
            self.scoped_select(scope)
            .with_only_columns(self.table.c.sub_account_id, func.max(self.table.c.as_of))
            .group_by(self.table.c.sub_account_id)
            .subquery()
        )
        statement = (
            self.scoped_select(scope)
            .join(
                newest,
                (self.table.c.sub_account_id == newest.c.sub_account_id)
                & (self.table.c.as_of == newest.c[1]),
            )
            .order_by(self.table.c.total.asc())
            .limit(limit)
        )
        return _fetch(self, scope, statement)

    def history(
        self, scope: Scope, *, account: str, limit: int = 60
    ) -> Sequence[Row[*tuple[Any, ...]]]:
        """One subject's scores, newest first, for the trend."""
        statement = (
            self.scoped_select(scope)
            .where(self.table.c.sub_account_id == account)
            .order_by(self.table.c.as_of.desc())
            .limit(limit)
        )
        return _fetch(self, scope, statement)


class ScoreComponentRepository(ScopedRepository):
    """The parts of a score, which is the part FEAT-043 actually ships.

    Scoped through `finops_score`, so a component is exactly as reachable as the
    score it belongs to and not one row more.
    """

    table: ClassVar[Table] = models.finops_score_component
    resource: ClassVar[str] = "finops_score_component"

    def of(self, scope: Scope, score_ids: Sequence[Any]) -> Sequence[Row[*tuple[Any, ...]]]:
        """Every component of the given scores, in one read.

        A read per score would be a fan out over a list the screen already has, and
        at forty accounts that is forty queries to render one page.
        """
        if not score_ids:
            return ()
        statement = (
            self.scoped_select(scope)
            .where(self.table.c.score_id.in_(list(score_ids)))
            .order_by(self.table.c.score_id, self.table.c.name)
        )
        return _fetch(self, scope, statement)
