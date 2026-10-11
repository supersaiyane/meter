"""Every verified saving credited to its owner, their team and who closed it. FEAT-078.

TASK-P11-006, P11 spec section 5.5. Daily. Reads only what Meter already holds, FEAT-029's
verdicts in `realized_saving`, the recommendation's owner, the actor of its DONE event and the
strongest team any source names for its resource, and makes no AWS call.

**One credit per VERIFIED saving, and nothing else.** An INCONCLUSIVE or REGRESSED verdict earns
nothing, because the ledger is only worth trusting if nothing in it is a guess. The saving is
FEAT-029's own, the before window's cost less the after window's, thirty days each, measured.

**Who is credited is fixed when the credit is first written.** The owner the recommendation had
when it was marked DONE, which no later move changes, since only verification moves it on; the
team its strongest team suggestion named then, the catalogue's, a tag's, or failing both the
resource's `team` tag, as the recommendation's `suggested_owner` reads; and the person who moved
it to DONE. Later runs refresh the figure and its dates and leave the names alone, so a team
reorganised next quarter does not take this quarter's saving with it.

**A verdict that stops being VERIFIED takes its credit with it.** FEAT-029 judges again every run
and a verdict moves only if late rows in the bill change a window, but a credit whose saving no
longer verifies is withdrawn rather than left standing. A saving whose recommendation has no
owner is credited to nobody: the ledger credits only an owner a person assigned, spec section 5.1.

**Every month it holds**, TASK-P11-007. Each closed month after a credited saving verified is
judged by `finops_query.ledger` against the cost before the change at FEAT-029's daily rate, from
the resource's charges that month and whether the account's bill holds any rows for it at all:
HELD with its saving, REGRESSED, which stops the credit there, or UNOBSERVED, never nought. Every
run judges every month again, so late rows in the bill correct a month, and a month no longer
judged, after a regression or under a withdrawn credit, is removed before its credit can be.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from finops_core.constants import TEAM_TAG
from finops_core.domain.ownership import ORDER, OwnerKind
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.ledger import Billed, MonthHeld, closed_months, held, next_month

COLLECTOR = "savings_ledger"

#: The suggestion sources, strongest first, as the recommendation lists them.
_STRONGEST = " ".join(f"WHEN '{source.value}' THEN {at}" for at, source in enumerate(ORDER))

#: Every verified saving with an owner, its figure, who closed it and the team named for it.
VERIFIED = text(
    "SELECT s.realized_id, s.recommendation_id, r.sub_account_id, r.owner, "
    "s.cost_before - s.cost_after AS saving, s.window_after_end AS verified_on, s.as_of, "
    "(SELECT e.actor FROM recommendation_event e WHERE e.tenant_id = s.tenant_id "
    "AND e.recommendation_id = s.recommendation_id AND e.to_lifecycle = 'DONE' "
    "ORDER BY e.occurred_at DESC LIMIT 1) AS closed_by, "
    "COALESCE("
    "(SELECT o.owner FROM resource_owner o WHERE o.tenant_id = r.tenant_id "
    "AND o.sub_account_id = r.sub_account_id AND o.resource_id = r.resource_id "
    f"AND o.owner_kind = '{OwnerKind.TEAM.value}' ORDER BY CASE o.source {_STRONGEST} END "
    "LIMIT 1), "
    "(SELECT NULLIF(n.tags ->> :team_tag, '') FROM topology_node n "
    "WHERE n.tenant_id = r.tenant_id AND n.sub_account_id = r.sub_account_id "
    "AND n.provider_id = r.resource_id)) AS team "
    "FROM realized_saving s JOIN recommendation r "
    "ON r.recommendation_id = s.recommendation_id AND r.tenant_id = s.tenant_id "
    "WHERE s.tenant_id = :t AND s.verdict = 'VERIFIED' AND r.owner IS NOT NULL "
    "ORDER BY s.realized_id"
)

#: A credit written once; a later run refreshes its figure and dates, never its names.
CREDIT = text(
    "INSERT INTO savings_credit (credit_id, tenant_id, ingest_run_id, sub_account_id, "
    "recommendation_id, realized_id, owner, team, closed_by, verified_monthly_saving, "
    "verified_on, as_of, collected_at) VALUES (:id, :t, :run, :account, :recommendation, "
    ":realized, :owner, :team, :closed_by, :saving, :verified_on, :as_of, :now) "
    "ON CONFLICT (realized_id) DO UPDATE SET ingest_run_id = EXCLUDED.ingest_run_id, "
    "verified_monthly_saving = EXCLUDED.verified_monthly_saving, "
    "verified_on = EXCLUDED.verified_on, as_of = EXCLUDED.as_of, "
    "collected_at = EXCLUDED.collected_at"
)

#: The credits whose saving no longer verifies.
WITHDRAW = text(
    "DELETE FROM savings_credit c WHERE c.tenant_id = :t AND NOT EXISTS ("
    "SELECT 1 FROM realized_saving s JOIN recommendation r "
    "ON r.recommendation_id = s.recommendation_id AND r.tenant_id = s.tenant_id "
    "WHERE s.realized_id = c.realized_id AND s.verdict = 'VERIFIED' AND r.owner IS NOT NULL)"
)

#: Every credit whose saving still verifies, with what its months are measured against: the
#: before window's cost a day, as FEAT-029 measured it.
CREDITED = text(
    "SELECT c.credit_id, c.sub_account_id, c.verified_on, r.resource_id, "
    "s.cost_before / (s.window_before_end - s.window_before_start) AS daily_before "
    "FROM savings_credit c JOIN realized_saving s ON s.realized_id = c.realized_id "
    "AND s.verdict = 'VERIFIED' JOIN recommendation r ON r.recommendation_id = c.recommendation_id "
    "AND r.owner IS NOT NULL WHERE c.tenant_id = :t ORDER BY c.credit_id"
)

#: Each month's cost for the resource, and how many rows the account's bill holds that month.
BILLED = text(
    "SELECT date_trunc('month', date(charge_period_start))::date AS month, "
    "COALESCE(SUM(effective_cost) FILTER (WHERE resource_id = :resource), 0) AS cost, "
    "COUNT(*) AS billed_rows FROM cost_focus_daily "
    "WHERE tenant_id = :t AND sub_account_id = :account "
    "AND date(charge_period_start) >= :first AND date(charge_period_start) < :end GROUP BY 1"
)

#: One month judged; a later run judges it again.
MONTH = text(
    "INSERT INTO savings_credit_month (month_pk, tenant_id, ingest_run_id, sub_account_id, "
    "credit_id, month, state, cost, saving, as_of, collected_at) VALUES (:pk, :t, :run, "
    ":account, :credit, :month, :state, :cost, :saving, :as_of, :now) "
    "ON CONFLICT (credit_id, month) DO UPDATE SET ingest_run_id = EXCLUDED.ingest_run_id, "
    "state = EXCLUDED.state, cost = EXCLUDED.cost, saving = EXCLUDED.saving, "
    "as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
)

#: The months this run did not judge: after a regression, or under a credit being withdrawn.
STALE_MONTHS = text(
    "DELETE FROM savings_credit_month WHERE tenant_id = :t AND ingest_run_id <> :run"
)

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


class SavingsLedgerCollector:
    """One credit per verified saving, kept while it verifies."""

    def __init__(self, *, clock: Clock = _system_clock) -> None:
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        now = self._clock()
        tenant = context.unit.tenant_id
        found = list(context.connection.execute(VERIFIED, {"t": tenant, "team_tag": TEAM_TAG}))
        if found:
            context.connection.execute(CREDIT, [_credit(context, one, now) for one in found])
        months = _months(context, now)
        if months:
            context.connection.execute(MONTH, months)
        # Months first: a withdrawn credit's months were not rewritten above, so they go here,
        # and only then can the credit itself.
        stale = context.connection.execute(STALE_MONTHS, {"t": tenant, "run": context.run_id})
        removed = stale.rowcount + context.connection.execute(WITHDRAW, {"t": tenant}).rowcount
        return CollectorOutcome(items_written=len(found) + len(months), items_removed=removed)


def _months(context: CollectorContext, now: datetime) -> list[dict[str, Any]]:
    """Every closed month since each credited saving verified, judged against the bill."""
    today = now.date()
    rows: list[dict[str, Any]] = []
    for credit in list(context.connection.execute(CREDITED, {"t": context.unit.tenant_id})):
        closed = closed_months(credit.verified_on, today)
        if not closed:
            continue
        billed = {
            row.month: Billed(cost=Decimal(row.cost), rows=int(row.billed_rows))
            for row in context.connection.execute(
                BILLED,
                {
                    "t": context.unit.tenant_id,
                    "account": credit.sub_account_id,
                    "resource": credit.resource_id,
                    "first": closed[0],
                    "end": next_month(closed[-1]),
                },
            )
        }
        daily = Decimal(credit.daily_before)
        rows.extend(
            _month(context, credit, one, now)
            for one in held(credit.verified_on, today, daily, billed)
        )
    return rows


def _month(context: CollectorContext, credit: Any, one: MonthHeld, now: datetime) -> dict[str, Any]:
    # True at the source once the month closed: its last day billed by then.
    closed_at = datetime.combine(next_month(one.month), time(), tzinfo=UTC)
    return {
        "pk": uuid4(),
        "t": context.unit.tenant_id,
        "run": context.run_id,
        "account": credit.sub_account_id,
        "credit": credit.credit_id,
        "month": one.month,
        "state": one.state.value,
        "cost": one.cost,
        "saving": one.saving,
        "as_of": closed_at,
        "now": max(now, closed_at),
    }


def _credit(context: CollectorContext, one: Any, now: datetime) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "t": context.unit.tenant_id,
        "run": context.run_id,
        "account": one.sub_account_id,
        "recommendation": one.recommendation_id,
        "realized": one.realized_id,
        "owner": one.owner,
        "team": one.team,
        "closed_by": one.closed_by,
        "saving": one.saving,
        "verified_on": one.verified_on,
        "as_of": one.as_of,
        # A clock behind the verdict's would otherwise record it read before it was true.
        "now": max(now, one.as_of),
    }
