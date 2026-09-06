"""Reading query findings and the instances they came from.

Both go through `ScopedRepository`, so a route that forgets the scope dependency
still cannot read another tenant's rows. That is constraint 3: the scope is
enforced twice, and this is the second place.

The instance count is the one thing here that needs saying. An instance Meter
could not read has an **unknown** number of queries, not zero, so the count is
null for an unreachable row rather than a count that happens to come back as
none. A zero would make an estate look smaller than it is, which is the failure
the whole instances screen exists to prevent.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Row, func, select

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_api.guards import require_scope, scope_predicate
from finops_core.domain.tenant import Scope
from finops_query.severity import ENGINE_SCAN


class QueryFindingRepository(ScopedRepository):
    """Findings, ranked by what they cost."""

    table = models.query_finding
    resource = "query_finding"

    def _joined(self, scope: Scope) -> Any:
        """Findings with the definition they belong to.

        Started from the scoped select, so the tenant predicate comes from the
        guard rather than from this method remembering to add it.
        """
        definition = models.query_definition
        return (
            self.scoped_select(scope)
            .add_columns(
                definition.c.dashboard_uid,
                definition.c.dashboard_title,
                definition.c.folder_uid,
                definition.c.panel_id,
                definition.c.engine,
                definition.c.origin,
                definition.c.refresh_seconds,
                definition.c.range_seconds,
                definition.c.query_text,
                definition.c.target,
                definition.c.last_editor,
                # A remediation addresses an element on a surface, so it needs
                # the surface's own identifier for it and the instance it lives
                # on. Neither is the database identity, and writing to that
                # addresses an element the surface has never heard of.
                definition.c.fingerprint,
                definition.c.instance_id,
            )
            .join(definition, definition.c.query_id == self.table.c.query_id)
        )

    def ranked(self, scope: Scope) -> Sequence[Row[tuple[object, ...]]]:
        """Every finding, most expensive first.

        Ordered in the database rather than in the route, because
        `ix_query_finding__cost` exists for exactly this and sorting rows in
        Python would order the page rather than the estate.
        """
        statement = self._joined(scope).order_by(self.table.c.cost_month_usd.desc())
        return self.fetch(scope, statement)

    def grouped(self, scope: Scope) -> Sequence[Row[tuple[object, ...]]]:
        """Findings summed by cause, worst group first.

        ADR-0016: four hundred findings at 15 USD each are LOW individually and
        6,000 USD together, and a dollar threshold that cannot see that lets a
        systemic problem hide as four hundred trivial rows. Grouping happens
        before ranking, which is why it is a query rather than a fold over a
        page that has already been ordered and truncated.

        Summed in the database for the same reason the list is ordered there: a
        sum over the rows a route happened to fetch is a sum over the page.
        """
        cause = func.coalesce(self.table.c.cause, ENGINE_SCAN).label("cause")
        statement: Any = (
            self.scoped_select(scope)
            .with_only_columns(
                cause,
                func.count().label("findings"),
                func.sum(self.table.c.cost_month_usd).label("monthly_cost"),
                func.max(self.table.c.as_of).label("as_of"),
                func.max(self.table.c.collected_at).label("collected_at"),
            )
            .group_by(cause)
            .order_by(func.sum(self.table.c.cost_month_usd).desc())
        )
        return self.fetch(scope, statement)

    def latest_change(self, scope: Scope, finding_id: UUID) -> Row[tuple[object, ...]] | None:
        """The most recent change on this finding that has not been reverted.

        Most recent, because a finding can be remediated more than once and an
        undo restores the last state, not an arbitrary earlier one. Undoing out
        of order would restore a state that a later change already replaced.
        """
        change = models.remediation_change
        statement: Any = (
            select(change.c.change_id, change.c.kind, change.c.applied_at)
            .select_from(change.join(self.table, self.table.c.query_id == change.c.query_id))
            .where(
                scope_predicate(self.table, require_scope(scope)),
                self.table.c.finding_id == finding_id,
                change.c.reverted_at.is_(None),
            )
            .order_by(change.c.applied_at.desc())
            .limit(1)
        )
        rows = self._connection.execute(statement).all()
        return rows[0] if rows else None

    def one(self, scope: Scope, finding_id: UUID) -> Row[tuple[object, ...]] | None:
        statement = self._joined(scope).where(self.table.c.finding_id == finding_id)
        rows = self.fetch(scope, statement)
        return rows[0] if rows else None


class AdhocQueryRepository(ScopedRepository):
    """The Logs Insights executions no panel and no alert rule claims.

    FEAT-051. Scoped by the account the query ran in, directly rather than
    through a workspace, because a query somebody typed into the console
    belongs to no workspace.
    """

    table = models.query_adhoc
    resource = "query_adhoc"

    def most_expensive(self, scope: Scope) -> Sequence[Row[tuple[object, ...]]]:
        """Worst first, which is the only order this list is useful in.

        Cost then runs, matching the prototype this was recovered from. Two
        queries that cost the same are ranked by how often they ran, because
        the repeated one is the habit worth a conversation.
        """
        statement = self.scoped_select(scope).order_by(
            self.table.c.cost_usd.desc(), self.table.c.runs.desc()
        )
        return self.fetch(scope, statement)


class SurfaceInstanceRepository(ScopedRepository):
    """Every place queries live, including the ones that could not be read."""

    table = models.grafana_instance
    resource = "grafana_instance"

    def unreachable(self, scope: Scope) -> Sequence[Row[tuple[object, ...]]]:
        """The workspaces that could not be read, with their typed cause.

        The envelope reports these as failures. Without them a page could say a
        third of the estate is missing and offer no reason, and the only reason
        the interface had a word for was the wrong one: it said the missing part
        was outside the reader's scope when the workspace had returned
        AccessDenied to Meter itself. Sending a reader to request a permission
        they already hold is worse than saying nothing. ISS-152.
        """
        statement = self.scoped_select(scope).where(self.table.c.reachable.is_(False))
        return self.fetch(scope, statement)

    def coverage(self, scope: Scope) -> tuple[int, int]:
        """Workspaces read, over workspaces the tenant has.

        The denominator of `scope_coverage` for every query route, and the
        reason it is here rather than counting the rows a route returns. A
        findings list drawn from one of two workspaces is not a complete
        answer, and counting only what came back would report it as one. That
        is ISS-016 in a new place.

        The numerator excludes unreachable workspaces even though the instances
        route still lists them, because listing a workspace Meter could not read
        is how the gap is reported, not evidence that it was covered.

        Like `count_in_organization`, the denominator is confined to the tenant
        and returns a number rather than rows, so it cannot become a way of
        reading out of scope data.
        """
        confirmed = require_scope(scope)
        readable = self._connection.execute(
            select(func.count())
            .select_from(self.table)
            .where(scope_predicate(self.table, confirmed), self.table.c.reachable)
        ).scalar_one()
        total = self._connection.execute(
            select(func.count())
            .select_from(self.table)
            .where(self.table.c.tenant_id == confirmed.tenant_id)
        ).scalar_one()
        return int(readable), int(total)

    def all_with_counts(self, scope: Scope) -> Sequence[Row[tuple[object, ...]]]:
        definition = models.query_definition
        counted = (
            select(
                definition.c.instance_id,
                func.count(definition.c.query_id).label("query_count"),
            )
            .where(definition.c.tenant_id == scope.tenant_id)
            .group_by(definition.c.instance_id)
            .subquery()
        )
        statement = (
            self.scoped_select(scope)
            .add_columns(counted.c.query_count)
            .join(counted, counted.c.instance_id == self.table.c.instance_id, isouter=True)
            .order_by(self.table.c.name)
        )
        return self.fetch(scope, statement)
