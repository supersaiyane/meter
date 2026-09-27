"""Budgets, read from the payer and never written to it.

FEAT-060. The rule is in `finops_core/domain/budget.py` and is pure; this module reads the
provider's budgets and stores them.

**It stores what was read and nothing derived.** Not the actual, not the status, not the
percentage. Status depends on where today falls in the period, so a stored one is wrong by the
next morning and would be wrong in the direction nobody checks: a budget stored green on the
first of the month stays green while the month is spent.

**A budget it cannot join is stored anyway.** An estate with ten budgets over tag expressions
is not an estate with no budgets, and the count of what cannot be tracked is the first thing a
finance reader wants. Storing it with `UNSUPPORTED` is what lets the screen say so.

**Nothing is retracted.** A budget deleted at the provider keeps its row for the period it
covered, because last month's budget is what last month's spend was judged against and
removing it would silently rewrite that judgement. Periods are the unit here, not runs.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.budget import Budget
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "budgets"
SCOPE = "billing"

#: Upserted on the budget and its period. A limit revised mid month updates the row rather
#: than doubling it, and a budget that runs every month keeps one row per month rather than
#: one row forever that silently forgets what last month's limit was.
WRITE = text(
    "INSERT INTO budget (budget_pk, tenant_id, ingest_run_id, budget_id, name, scope, "
    "scope_value, limit_amount, currency, period_start, period_end, as_of, collected_at) "
    "VALUES (:pk, :tenant, :run, :budget_id, :name, :scope, :value, :limit, :currency, "
    ":start, :end, :at, :at) "
    "ON CONFLICT (tenant_id, budget_id, period_start) DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, name = EXCLUDED.name, scope = EXCLUDED.scope, "
    "scope_value = EXCLUDED.scope_value, limit_amount = EXCLUDED.limit_amount, "
    "currency = EXCLUDED.currency, period_end = EXCLUDED.period_end, "
    "as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
)

#: Recorded rather than silent, like every other collector's shortfall. An estate where every
#: budget is a tag expression produces a screen with nothing on it, and the reason belongs
#: somewhere a reader can find it.
UNJOINABLE = text(
    "INSERT INTO sync_error (error_id, tenant_id, collector, scope_key, error_type, "
    "detail, remediation, first_seen_at, last_seen_at, occurrences) "
    "VALUES (:id, :t, :c, :s, 'NoData', :d, :r, :now, :now, 1) "
    "ON CONFLICT (tenant_id, collector, scope_key, error_type) DO UPDATE SET "
    "detail = EXCLUDED.detail, last_seen_at = EXCLUDED.last_seen_at, "
    "occurrences = sync_error.occurrences + 1"
)


def _system_clock() -> datetime:
    return datetime.now(UTC)


Clock = Callable[[], datetime]


class BudgetCollector:
    """The payer's budgets, stored as read."""

    def __init__(self, source: Any, clock: Clock = _system_clock) -> None:
        self._source = source
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        now = self._clock()
        written = 0
        unjoinable = 0

        for budget in self._source.budgets():
            self._write(context, budget, now)
            written += 1
            if budget.scope.value == "UNSUPPORTED":
                unjoinable += 1

        if unjoinable:
            context.connection.execute(
                UNJOINABLE,
                {
                    "id": uuid4(),
                    "t": context.unit.tenant_id,
                    "c": COLLECTOR,
                    "s": SCOPE,
                    "d": (
                        f"{unjoinable} budgets are drawn around something this product cannot "
                        "reproduce, so no spend is compared against them"
                    ),
                    "r": (
                        "Usually a tag or a filter expression, a budget over several accounts, "
                        "or one measuring usage rather than cost. They are listed on the "
                        "budgets screen with no status, which is the honest answer: a budget "
                        "matched against the wrong spend is worse than one with no number."
                    ),
                    "now": now,
                },
            )

        return CollectorOutcome(items_written=written)

    def _write(self, context: CollectorContext, budget: Budget, now: datetime) -> None:
        context.connection.execute(
            WRITE,
            {
                "pk": uuid4(),
                "tenant": context.unit.tenant_id,
                "run": context.run_id,
                "budget_id": budget.budget_id,
                "name": budget.name,
                "scope": budget.scope.value,
                "value": budget.scope_value,
                "limit": budget.limit,
                "currency": budget.currency,
                "start": budget.period_start,
                "end": budget.period_end,
                # The provider's own `as_of` rather than the clock, because a budget is true
                # from when the provider says it is. `collected_at` is ours.
                "at": now,
            },
        )
