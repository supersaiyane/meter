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
from typing import Any, ClassVar, cast

from sqlalchemy import Row, Select, Table, func

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
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
