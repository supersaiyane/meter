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
from finops_core.domain.insight import Provenance
from finops_core.domain.tenant import Scope
from finops_query.severity import ENGINE_SCAN


def latest_audit_only(table: Any, scope: Scope, *identity: str) -> Any:
    """Confine a read to the most recent audit of each thing. ISS-175, ISS-177.

    Every audit table keeps one row per thing per day, which is what makes a
    history possible at all. A list that does not filter on the day therefore
    reports each thing once per day audited and sums its cost that many times
    over. One day of data hides it completely: the bug appears on the second
    day and grows by one estate per day after that.

    Per thing rather than one global maximum, because something that stopped
    being audited still has a last known state, and dropping it would make the
    estate look smaller and tidier than it is.

    `identity` names the columns that say which thing a row is about, which is
    the table's own uniqueness key without `run_date`. Getting it wrong here
    does not fail, it silently drops rows, so it is stated per table rather
    than guessed from the schema.
    """
    latest = table.alias("latest")
    return table.c.run_date == (
        select(func.max(latest.c.run_date))
        .where(
            latest.c.tenant_id == require_scope(scope).tenant_id,
            *[latest.c[column] == table.c[column] for column in identity],
        )
        .scalar_subquery()
    )


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

    #: What the sparkline is documented to draw. Thirty days is the shape, and
    #: sending more would be paying for pixels nobody renders.
    TREND_DAYS = 30

    def history_for_all(self, scope: Scope) -> Sequence[Row[tuple[object, ...]]]:
        """Every query's cost per day, for the list. ISS-172.

        One statement rather than one per row. The list holds tens of findings,
        and a read per row would be the N plus one this repository exists to
        avoid, on the screen whose whole job is to be scanned quickly.

        Bounded to the last `TREND_DAYS`, which is the window the sparkline is
        documented to draw. An unbounded read would grow forever and be
        truncated in the browser instead, which is a slower way of doing the
        same thing and hides where the limit is.
        """
        confirmed = require_scope(scope)
        # date minus integer, which the database evaluates as days. Written this
        # way rather than as an INTERVAL literal so it needs no raw SQL and no
        # import this module did not already have.
        cutoff = func.current_date() - self.TREND_DAYS
        statement: Any = (
            select(
                self.table.c.query_id,
                self.table.c.run_date,
                self.table.c.cost_month_usd,
                self.table.c.provenance,
            )
            .where(
                scope_predicate(self.table, confirmed),
                self.table.c.run_date >= cutoff,
            )
            .order_by(self.table.c.query_id, self.table.c.run_date)
        )
        return self._connection.execute(statement).all()

    def daily_totals(self, scope: Scope) -> Sequence[Row[tuple[object, ...]]]:
        """Every audited query's monthly cost, summed per day over the last `TREND_DAYS`.

        Every query audited on a day rather than today's queries only. A dashboard deleted
        after a fix leaves its earlier days here, so the fall it caused shows as a fall instead
        of the dashboard vanishing from its own past. Each day carries its stalest timestamps,
        the same rule a set of facts follows everywhere else.
        """
        confirmed = require_scope(scope)
        cutoff = func.current_date() - self.TREND_DAYS
        statement: Any = (
            select(
                self.table.c.run_date,
                func.sum(self.table.c.cost_month_usd).label("cost_month_usd"),
                func.count().label("queries"),
                func.bool_and(self.table.c.provenance == Provenance.MEASURED.value).label(
                    "measured"
                ),
                func.min(self.table.c.as_of).label("as_of"),
                func.min(self.table.c.collected_at).label("collected_at"),
            )
            .where(
                scope_predicate(self.table, confirmed),
                self.table.c.run_date >= cutoff,
            )
            .group_by(self.table.c.run_date)
            .order_by(self.table.c.run_date)
        )
        return self._connection.execute(statement).all()

    def _latest_only(self, scope: Scope) -> Any:
        """Confine a read to each query's most recent audit. ISS-175."""
        return latest_audit_only(self.table, scope, "query_id")

    def ranked(self, scope: Scope) -> Sequence[Row[tuple[object, ...]]]:
        """Every finding, most expensive first.

        Ordered in the database rather than in the route, because
        `ix_query_finding__cost` exists for exactly this and sorting rows in
        Python would order the page rather than the estate.
        """
        statement = (
            self._joined(scope)
            .where(self._latest_only(scope))
            .order_by(self.table.c.cost_month_usd.desc())
        )
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

        Confined to each query's latest audit, ISS-175. Without that the sum
        added every day the collector had run, so a group of twelve panels read
        as twenty four and its cost doubled with the estate's age rather than
        with the estate.
        """
        cause = func.coalesce(self.table.c.cause, ENGINE_SCAN).label("cause")
        statement: Any = (
            self.scoped_select(scope)
            .where(self._latest_only(scope))
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

    def history(self, scope: Scope, finding_id: UUID) -> Sequence[Row[tuple[object, ...]]]:
        """What this query has cost on each day it was audited. ISS-172.

        The table already held this and nothing read it. The audit upserts on
        `(tenant_id, query_id, run_date)`, so every day it runs leaves one row
        per query, and the history is a side effect of idempotency rather than
        something anybody had to build.

        Keyed on the query rather than the finding, because a finding is one
        query on one day. Asking what a finding cost last week is asking about
        the query behind it, and joining on `finding_id` would return a single
        row and call it a trend.

        Oldest first, which is the order a line is drawn in. Provenance travels
        with each point, because a series that mixes measured and modelled days
        is not one series and a reader has to be able to see the seam.
        """
        confirmed = require_scope(scope)
        query_id = (
            select(self.table.c.query_id)
            .where(
                scope_predicate(self.table, confirmed),
                self.table.c.finding_id == finding_id,
            )
            .scalar_subquery()
        )
        statement: Any = (
            select(
                self.table.c.run_date,
                self.table.c.cost_month_usd,
                self.table.c.provenance,
            )
            .where(
                scope_predicate(self.table, confirmed),
                self.table.c.query_id == query_id,
            )
            .order_by(self.table.c.run_date)
        )
        return self._connection.execute(statement).all()

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
        statement = (
            self.scoped_select(scope)
            # ISS-177. The table is keyed on the day, the same as
            # `query_finding`, and a list that ignores that reports a week of
            # audits as a week of separate queries.
            .where(latest_audit_only(self.table, scope, "account_id", "region_id", "fingerprint"))
            .order_by(self.table.c.cost_usd.desc(), self.table.c.runs.desc())
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
