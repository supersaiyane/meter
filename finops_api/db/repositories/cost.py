"""Reading the bill, always through a scope.

Every method here takes a `Scope` and none of them can be persuaded not to.
`cost_focus_daily` is the widest table in the schema and the most damaging to
leak, so it is scoped twice like everything else: the route's dependency
resolves the scope, and `scoped_select` builds a predicate a caller cannot
express their way out of.

**Which measure.** Everything here reports `effective_cost`, which is amortized
cost. The roadmap made that decision and this does not reopen it. `billed_cost`
comes back alongside it so a reconciliation against an invoice has something to
reconcile with, and the two are separate columns rather than one column with a
mode, because a number whose meaning depends on a parameter is a number that
gets labelled wrongly eventually.

**Which period.** Nothing here guesses. A caller names the billing period or
asks `latest_period` what the newest one is. A repository that quietly defaulted
to "this month" would answer a different question in the first minute of a new
month than it did in the last minute of the old one.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any, ClassVar, cast

from sqlalchemy import Row, Select, Table, func, select

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_api.guards import require_scope, scoped_select
from finops_core.domain.platform import UNALLOCATED
from finops_core.domain.tenant import Scope

#: Columns a caller may group by. Named rather than accepted as a string,
#: because a grouping column arriving from a request is an injection unless
#: something refuses everything that is not on a list this short.
GROUPABLE: dict[str, str] = {
    "service": "service_name",
    "account": "sub_account_id",
    "region": "region_id",
}

#: How many months the comparison view reaches back. Thirty, matching the query
#: findings trend, so two screens do not quietly mean different things by the
#: word recently.
TREND_DAYS = 30


def _fetch(
    repository: ScopedRepository, scope: Scope, statement: Any
) -> Sequence[Row[tuple[Any, ...]]]:
    """Run a projected read through the audited path.

    `with_only_columns` produces a `Select` typed to its exact columns, and
    `fetch` is declared for the general one. The cast lives here once rather
    than at every call site, and it is a cast and not a signature change on the
    base class because loosening that signature would loosen it for the eight
    repositories that do not need it.
    """
    return repository.fetch(scope, cast("Select[tuple[object, ...]]", statement))


class CostRepository(ScopedRepository):
    """The cost surface's reads. FEAT-021 and FEAT-022."""

    table: ClassVar[Table] = models.cost_focus_daily
    resource: ClassVar[str] = "cost_focus_daily"

    def latest_period(self, scope: Scope) -> date | None:
        """The newest billing period this scope can see.

        None means the scope has no cost at all, which is a different answer
        from a period totalling zero, and the route keeps the two apart.
        """
        statement = self.scoped_select(scope).with_only_columns(
            func.max(self.table.c.billing_period_start)
        )
        rows = _fetch(self, scope, statement)
        return rows[0][0] if rows else None

    def for_resource(self, scope: Scope, resource_id: str, period: date) -> Decimal | None:
        """What one resource cost in one billing period, effective.

        FEAT-053. None where no charge joined, and None is not zero: a resource with no line
        item in the period is one the bill does not mention, which happens for a resource
        created after the period closed, for one whose charges land under a parent, and for
        one whose identifier the export spells differently. A zero there would tell a reader
        the thing is free.

        Effective rather than billed, because effective is the primary measure everywhere per
        the roadmap, and a page mixing the two would let somebody compare this resource
        against a total drawn the other way.
        """
        statement = (
            self.scoped_select(scope)
            .with_only_columns(func.sum(self.table.c.effective_cost))
            .where(self.table.c.billing_period_start == period)
            .where(self.table.c.resource_id == resource_id)
        )
        rows = _fetch(self, scope, statement)
        found = rows[0][0] if rows else None
        return None if found is None else Decimal(found)

    def accounts_in(self, scope: Scope, period: date) -> int:
        """How many accounts this scope can see spending in the period.

        The coverage banner's whole job is to say when a total was drawn from
        part of an estate, so the number beside the word accounts has to be
        accounts. The line item count went there first and rendered as
        "showing all 450 accounts" on an estate with five.
        """
        statement = (
            self.scoped_select(scope)
            .with_only_columns(func.count(func.distinct(self.table.c.sub_account_id)))
            .where(self.table.c.billing_period_start == period)
        )
        rows = _fetch(self, scope, statement)
        return int(rows[0][0] or 0) if rows else 0

    def period_total(self, scope: Scope, period: date) -> Sequence[Row[tuple[Any, ...]]]:
        """One row: effective, billed, line items and both timestamps.

        Both timestamps, per constraint 10. `as_of` is the oldest charge in the
        period, because a period is only as current as its least current line
        item, and `collected_at` is the most recent fetch.
        """
        statement = self.scoped_select(scope).with_only_columns(
            func.coalesce(func.sum(self.table.c.effective_cost), 0),
            func.coalesce(func.sum(self.table.c.billed_cost), 0),
            func.count(),
            func.min(self.table.c.as_of),
            func.max(self.table.c.collected_at),
        )
        return _fetch(self, scope, statement.where(self.table.c.billing_period_start == period))

    def grouped(self, scope: Scope, period: date, dimension: str) -> Sequence[Row[tuple[Any, ...]]]:
        """Worst first, by service, account or region.

        The dimension is looked up rather than interpolated. A grouping column
        taken from a request and dropped into SQL is an injection, and the list
        is short enough that refusing everything off it costs nothing.
        """
        column = self.table.c[GROUPABLE[dimension]]
        labelled = func.coalesce(column, UNALLOCATED)
        statement = (
            self.scoped_select(scope)
            .with_only_columns(
                labelled,
                func.sum(self.table.c.effective_cost),
                func.sum(self.table.c.billed_cost),
                func.count(),
            )
            .where(self.table.c.billing_period_start == period)
            .group_by(labelled)
            .order_by(func.sum(self.table.c.effective_cost).desc())
        )
        return _fetch(self, scope, statement)

    def containers(self, scope: Scope, period: date) -> Sequence[Row[tuple[Any, ...]]]:
        """Cost at the container grain: cluster, namespace and workload.

        The same table, the same scope predicate and the same repository as every
        other cost read, because split cost allocation is columns on rows this
        already returns. A second read path over the same money is how two screens
        come to disagree about a total.

        `split_cost` and not `effective_cost`. The money on these rows lives in the
        split column; their `effective_cost` is zero because the charge is already
        counted on the node line. Summing the wrong one would report every cluster
        as free.
        """
        table = self.table
        namespace = func.coalesce(table.c.eks_namespace, UNALLOCATED)
        workload = func.coalesce(table.c.eks_workload_name, UNALLOCATED)
        statement = (
            self.scoped_select(scope)
            .with_only_columns(
                table.c.eks_cluster_name,
                namespace,
                workload,
                func.coalesce(func.max(table.c.eks_workload_type), ""),
                func.coalesce(func.sum(table.c.split_cost), 0),
                func.count(),
            )
            .where(table.c.billing_period_start == period)
            .where(table.c.eks_cluster_name.isnot(None))
            .where(table.c.split_cost.isnot(None))
            .group_by(table.c.eks_cluster_name, namespace, workload)
            .order_by(func.sum(table.c.split_cost).desc())
        )
        return _fetch(self, scope, statement)

    def cluster_totals(self, scope: Scope, period: date) -> Sequence[Row[tuple[Any, ...]]]:
        """Per cluster: what was attributed, what was not, and how many rows.

        Separate from `containers` rather than derived from it, because a cluster
        whose breakdown is absent still has a total and still has to be listed. A
        reader seeing nine clusters where they have ten learns nothing about the
        tenth, and the tenth is the one worth asking about.
        """
        table = self.table
        statement = (
            self.scoped_select(scope)
            .with_only_columns(
                table.c.eks_cluster_name,
                func.coalesce(func.sum(table.c.split_cost), 0),
                func.coalesce(func.sum(table.c.unused_cost), 0),
                func.count(table.c.split_cost),
                func.min(table.c.as_of),
                func.max(table.c.collected_at),
            )
            .where(table.c.billing_period_start == period)
            .where(table.c.eks_cluster_name.isnot(None))
            .group_by(table.c.eks_cluster_name)
            .order_by(func.coalesce(func.sum(table.c.split_cost), 0).desc())
        )
        return _fetch(self, scope, statement)

    def clusters_in(self, scope: Scope, period: date) -> int:
        """How many clusters this caller can see any charge for.

        The denominator of the coverage figure on the container cost screen, and a
        repository method rather than `len(rows)` because a row count in that slot
        has been the defect three times. See tasks/lessons.md.
        """
        statement = self.scoped_select(scope).with_only_columns(
            func.count(func.distinct(self.table.c.eks_cluster_name))
        )
        rows = _fetch(
            self,
            scope,
            statement.where(self.table.c.billing_period_start == period).where(
                self.table.c.eks_cluster_name.isnot(None)
            ),
        )
        return int(rows[0][0]) if rows else 0

    def for_export(self, scope: Scope, period: date, key: str) -> Sequence[Row[tuple[Any, ...]]]:
        """One row per account, service and tag value, for the file finance opens.

        The same table, the same scope predicate and the same unallocated bucket as
        every screen. That is the point rather than a convenience: a file generated
        from a second query shape is a file that can disagree with the screen, and
        the gap between an export and an invoice is the first thing finance finds.

        Grouped three ways instead of one, so the file can be pivoted. Summing the
        effective cost column of the whole file therefore equals the period total on
        `/cost/summary`, which `tests/api/test_cost_export.py` asserts by doing
        exactly that.
        """
        account = func.coalesce(self.table.c.sub_account_id, UNALLOCATED)
        tagged = func.coalesce(self.table.c.tags[key].astext, UNALLOCATED)
        statement = (
            self.scoped_select(scope)
            .with_only_columns(
                account,
                self.table.c.service_name,
                tagged,
                func.sum(self.table.c.effective_cost),
                func.sum(self.table.c.billed_cost),
                func.count(),
            )
            .where(self.table.c.billing_period_start == period)
            .group_by(account, self.table.c.service_name, tagged)
            .order_by(func.sum(self.table.c.effective_cost).desc())
        )
        return _fetch(self, scope, statement)

    def by_tag(self, scope: Scope, period: date, key: str) -> Sequence[Row[tuple[Any, ...]]]:
        """Allocation: charges grouped by one tag key, with an explicit bucket
        for everything nobody tagged.

        The unallocated bucket is a row like any other. It is never folded into
        a total and never dropped, because an allocation view that quietly
        loses what it cannot attribute reports a smaller estate than exists, and
        the gap between it and the invoice is the first thing finance finds.
        """
        tagged = func.coalesce(self.table.c.tags[key].astext, UNALLOCATED)
        statement = (
            self.scoped_select(scope)
            .with_only_columns(
                tagged,
                func.sum(self.table.c.effective_cost),
                func.sum(self.table.c.billed_cost),
                func.count(),
            )
            .where(self.table.c.billing_period_start == period)
            .group_by(tagged)
            .order_by(func.sum(self.table.c.effective_cost).desc())
        )
        return _fetch(self, scope, statement)

    def daily(self, scope: Scope, period: date) -> Sequence[Row[tuple[Any, ...]]]:
        """Effective cost per day inside one billing period, oldest first.

        The chart on `/cost`. Ordered here rather than in the browser, because
        a page sorted in the frontend orders the page and not the estate.
        """
        day = func.date(self.table.c.charge_period_start)
        statement = (
            self.scoped_select(scope)
            .with_only_columns(day, func.sum(self.table.c.effective_cost))
            .where(self.table.c.billing_period_start == period)
            .group_by(day)
            .order_by(day)
        )
        return _fetch(self, scope, statement)


class AnomalyRepository(ScopedRepository):
    """Days that did not look like the days before them. FEAT-023."""

    table: ClassVar[Table] = models.cost_anomaly
    resource: ClassVar[str] = "cost_anomaly"

    def worst_first(self, scope: Scope, limit: int = 50) -> Sequence[Row[tuple[Any, ...]]]:
        """Biggest move first, newest day breaking the tie.

        Ranked by the money rather than by the ratio, per ADR-0016. A screen
        ordered by ratio puts a two cent service that tripled above a service
        that cost eight hundred dollars more than it should have.
        """
        statement = (
            self.scoped_select(scope)
            .order_by(self.table.c.delta.desc(), self.table.c.day.desc())
            .limit(limit)
        )
        return _fetch(self, scope, statement)

    def accounts_judged(self, scope: Scope) -> int:
        """How many accounts this scope has cost for, and therefore could be judged.

        The coverage banner counts accounts, so the number beside the word accounts
        has to be accounts. Passing `len(rows)` there rendered "4 missing, outside
        your scope" above a single anomaly for a reader who could see everything,
        which is the third time a row count has reached that slot in this project.

        Read from the cost table rather than from this one, for the same reason
        `judged_days` is: an estate with no anomalies has no rows here to count, and a
        banner that vanished when the estate behaved would be useless exactly when a
        reader most wants to know the view is complete.
        """
        daily = models.cost_focus_daily
        # Through the guard's own constructor rather than a hand rolled select. It is
        # the only thing that stamps the applied mark, and a query built any other way
        # is the case `assert_scoped` exists to catch.
        statement = scoped_select(daily, scope).with_only_columns(
            func.count(func.distinct(daily.c.sub_account_id))
        )
        rows = self._connection.execute(statement).all()
        return int(rows[0][0] or 0) if rows else 0

    def judged_days(self, scope: Scope) -> int:
        """How many distinct days this scope has cost for.

        The screen needs it to tell two empty tables apart: an estate that is
        behaving, and an estate nobody can say anything about yet. Read from
        the cost table rather than from this one, because an estate with no
        anomalies has no rows here to count.
        """
        daily = models.cost_focus_daily
        statement = select(func.count(func.distinct(func.date(daily.c.charge_period_start)))).where(
            daily.c.tenant_id == require_scope(scope).tenant_id
        )
        rows = self._connection.execute(statement).all()
        return int(rows[0][0] or 0) if rows else 0


class CommitmentRepository(ScopedRepository):
    """What was committed and how much of it was consumed. FEAT-024.

    Utilization only. Coverage is `CommitmentCoverageRepository`, because it is a
    fact about a slice of the estate rather than about a commitment, and one
    repository reading both tables would be one place where a screen could pair
    utilization from one window with coverage from another.
    """

    table: ClassVar[Table] = models.commitment_use
    resource: ClassVar[str] = "commitment_use"

    def latest_window(self, scope: Scope) -> date | None:
        """The most recent window anything was reported for, or None.

        None means no commitment has ever been collected for this scope, which the
        route turns into a typed refusal rather than into a page of zeroes.
        """
        statement = self.scoped_select(scope).with_only_columns(func.max(self.table.c.window_start))
        rows = _fetch(self, scope, statement)
        return rows[0][0] if rows and rows[0][0] is not None else None

    def worst_first(self, scope: Scope, window_start: date) -> Sequence[Row[tuple[Any, ...]]]:
        """Every commitment in the window, most wasted money first.

        Ranked by the waste rather than by utilization, per ADR-0016. A ranking by
        percentage puts a ten dollar reservation at forty percent above a ten
        thousand dollar plan at ninety five, and only one of those is worth a
        morning.
        """
        statement = (
            self.scoped_select(scope)
            .where(self.table.c.window_start == window_start)
            .order_by(self.table.c.wasted.desc(), self.table.c.commitment_id)
        )
        return _fetch(self, scope, statement)


class BudgetRepository(ScopedRepository):
    """Budgets as collected. FEAT-060.

    `PayerWide` per ADR-0025, like the commitment tables: a budget is set at the payer and the
    API reporting it is a payer API, so a narrowed reader reads nothing rather than a number
    that is not theirs.
    """

    table: ClassVar[Table] = models.budget
    resource: ClassVar[str] = "budget"

    def latest_period(self, scope: Scope) -> date | None:
        """The most recent period any budget covers.

        The fallback when no cost has been collected, which is the case a budget screen exists
        for: an estate whose first ingest has not run still has budgets, and answering 404
        would tell a reader their budgets do not exist.
        """
        statement = self.scoped_select(scope).with_only_columns(func.max(self.table.c.period_start))
        found = self._connection.execute(statement).scalar_one_or_none()
        return found

    def for_period(self, scope: Scope, period: date) -> Sequence[Row[tuple[Any, ...]]]:
        """Every budget covering a period, largest limit first.

        By limit rather than by status, because status is computed per request and ordering by
        something the database does not hold would mean fetching everything and sorting in
        Python, which is the same work with a worse name. The screen re orders by status
        itself, where it already has the statuses.
        """
        statement = (
            self.scoped_select(scope)
            .where(self.table.c.period_start <= period)
            .where(self.table.c.period_end > period)
            .order_by(self.table.c.limit_amount.desc(), self.table.c.name)
        )
        return _fetch(self, scope, statement)


class CommitmentActionRepository(ScopedRepository):
    """Coverage gaps as findings somebody owns. FEAT-055.

    `PayerWide` in the guard, like the coverage it derives from, per ADR-0025. A finding
    inherits the scoping of the fact it was computed from rather than the scoping of the table
    it resembles, so a narrowed reader reads nothing here and the screen says why.
    """

    table: ClassVar[Table] = models.commitment_action
    resource: ClassVar[str] = "commitment_action"

    def worst_first(self, scope: Scope) -> Sequence[Row[tuple[Any, ...]]]:
        """Every open action, most money first, per ADR-0016.

        Not filtered to a window. A coverage gap is upserted on its dimension rather than its
        window, so there is one current row per dimension and the newest window is already the
        one stored. Filtering by window here would hide a finding whose gap had not been
        recomputed this month.
        """
        statement = (
            self.scoped_select(scope)
            .where(self.table.c.lifecycle == "OPEN")
            .order_by(self.table.c.estimated_monthly_saving.desc(), self.table.c.dimension_value)
        )
        return _fetch(self, scope, statement)


class CommitmentCoverageRepository(ScopedRepository):
    """How much of the eligible estate was on a commitment, per dimension."""

    table: ClassVar[Table] = models.commitment_coverage
    resource: ClassVar[str] = "commitment_coverage"

    def slices(self, scope: Scope, window_start: date) -> Sequence[Row[tuple[Any, ...]]]:
        """Coverage rows in the window, most uncovered money first.

        Ordered by the money left uncovered rather than by the coverage fraction.
        Two reasons, and the second is the one that matters. Money is what ADR-0016
        ranks by, and a percentage of a small eligible total is not an action. And
        the fraction has a zero denominator whenever nothing was eligible, which
        PostgreSQL raises on rather than sorting last, so ordering by it would make
        the screen fail exactly on the estate that has least to show.
        """
        uncovered = self.table.c.eligible_spend - self.table.c.covered_spend
        statement = (
            self.scoped_select(scope)
            .where(self.table.c.window_start == window_start)
            .order_by(uncovered.desc(), self.table.c.dimension_value)
        )
        return _fetch(self, scope, statement)


class MonthlyCostRepository(ScopedRepository):
    """The derived monthly shape, for setting one period beside another.

    Separate from `CostRepository` because it reads a different table at a
    different grain. A repository that silently switched tables depending on the
    question would make it impossible to say which one a number came from.
    """

    table: ClassVar[Table] = models.cost_focus_monthly
    resource: ClassVar[str] = "cost_focus_monthly"

    def months(self, scope: Scope, limit: int = TREND_DAYS) -> Sequence[Row[tuple[Any, ...]]]:
        """Each billing month and what it cost, newest first."""
        statement = (
            self.scoped_select(scope)
            .with_only_columns(
                self.table.c.billing_month,
                func.sum(self.table.c.effective_cost),
                func.sum(self.table.c.billed_cost),
                func.sum(self.table.c.line_items),
            )
            .group_by(self.table.c.billing_month)
            .order_by(self.table.c.billing_month.desc())
            .limit(limit)
        )
        return _fetch(self, scope, statement)


def previous_month(period: date) -> date:
    """The billing period before this one.

    Here rather than inside a route, because December to January is the case a
    route gets wrong once and is then wrong about every January.
    """
    if period.month == 1:
        return date(period.year - 1, 12, 1)
    return date(period.year, period.month - 1, 1)
