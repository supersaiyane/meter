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

    def one(self, scope: Scope, finding_id: UUID) -> Row[tuple[object, ...]] | None:
        statement = self._joined(scope).where(self.table.c.finding_id == finding_id)
        rows = self.fetch(scope, statement)
        return rows[0] if rows else None


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
