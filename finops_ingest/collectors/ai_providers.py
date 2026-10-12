"""An AI provider's cost and usage, for every organization a tenant connected. FEAT-083.

P13 spec section 5.5, TASK-P13-004 and 005. One collector per provider, run once a day for the
whole tenant: for each connected organization it reads the billing period to date from the
provider's cost report and usage report, writes the cost as FOCUS rows beside the cloud bill and
the usage beside Bedrock's, and removes what the provider withdrew from that organization's rows
and nothing else. The period is reread every day because both providers revise recent buckets.

**One organization failing never fails another.** Each is read on its own; a failure is typed in
`sync_error` under that organization's scope and the next is read. The unit fails only when every
organization failed, with the first cause, so the freshness screen shows a provider that cannot be
read at all as failed rather than as one that cost nothing. A tenant with no organization
connected reads nothing and writes nothing, which the screen shows as not connected.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import column, table, text

from finops_core.domain.ai import ProviderAccount
from finops_core.errors import CollectionError
from finops_core.ports.ai import AiProviderReports
from finops_ingest.ai_accounts import connected
from finops_ingest.collectors.ai_usage import retract_usage, write_usage
from finops_ingest.collectors.cost_focus import retract_account, write_cost_rows
from finops_ingest.collectors.cost_rollup import roll_up_period
from finops_ingest.registry import CollectorContext, CollectorOutcome

Clock = Callable[[], datetime]
Accounts = Callable[[Any, Any], Sequence[ProviderAccount]]
ReportsFor = Callable[[CollectorContext, ProviderAccount], AiProviderReports]

#: Upserted on the scope, like every other sync error.
FAILED = text(
    "INSERT INTO sync_error (error_id, tenant_id, collector, scope_key, error_type, "
    "detail, remediation, first_seen_at, last_seen_at, occurrences) "
    "VALUES (:id, :t, :c, :s, :type, :d, :r, :now, :now, 1) "
    "ON CONFLICT (tenant_id, collector, scope_key, error_type) DO UPDATE SET "
    "detail = EXCLUDED.detail, last_seen_at = EXCLUDED.last_seen_at, "
    "occurrences = sync_error.occurrences + 1"
)

_SYNC_ERROR = table("sync_error", column("tenant_id"), column("collector"), column("scope_key"))


def _system_clock() -> datetime:
    return datetime.now(UTC)


def period_of(end: datetime) -> date:
    """The billing period the window's last moment falls in."""
    last = end - timedelta(microseconds=1)
    return date(last.year, last.month, 1)


class AiProviderCollector:
    """One provider's reports for each organization the tenant connected."""

    def __init__(
        self,
        *,
        name: str,
        provider: str,
        reports_for: ReportsFor,
        accounts: Accounts | None = None,
        clock: Clock = _system_clock,
    ) -> None:
        self._name = name
        self._provider = provider
        self._reports_for = reports_for
        self._accounts = accounts or (lambda c, t: connected(c, t, provider))
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        if context.run_id is None:
            # Not a typed collection failure: the caller assembled the context incorrectly, and
            # rows carry the run id in a NOT NULL column that the restatements delete on.
            raise ValueError(f"{self._name} needs the run id from the ledger's claim")
        unit = context.unit
        period = period_of(unit.window_end)
        start = datetime.combine(period, time.min, tzinfo=UTC)
        end = unit.window_end
        written = removed = 0
        failures: list[CollectionError] = []
        accounts = tuple(self._accounts(context.connection, unit.tenant_id))
        for account in accounts:
            scope = f"{account.provider}:{account.organization_id}"
            try:
                reports = self._reports_for(context, account)
                costs = tuple(reports.costs(account, start, end))
                usage = tuple(reports.usage(account, start, end))
            except CollectionError as failure:
                self._record(context, scope, failure)
                failures.append(failure)
                continue
            at = self._clock()
            written += write_cost_rows(context, costs, source=self._provider, at=at)
            removed += retract_account(
                context, period=period, source=self._provider, account=account.organization_id
            )
            written += write_usage(context, usage, at)
            removed += retract_usage(
                context,
                provider=self._provider,
                account_id=account.organization_id,
                first=period,
                after=(end - timedelta(microseconds=1)).date() + timedelta(days=1),
            )
            self._clear(context, scope)
        if failures and len(failures) == len(accounts):
            raise failures[0]
        if len(failures) < len(accounts):
            # In the same transaction as the rows it aggregates, as the bill's collector does.
            roll_up_period(
                context.connection, tenant=unit.tenant_id, period=period, at=self._clock()
            )
        return CollectorOutcome(items_written=written, items_removed=removed)

    def _record(self, context: CollectorContext, scope: str, failure: CollectionError) -> None:
        context.connection.execute(
            FAILED,
            {
                "id": uuid4(),
                "t": context.unit.tenant_id,
                "c": self._name,
                "s": scope,
                "type": failure.cause,
                "d": failure.detail or failure.cause,
                "r": failure.remediation,
                "now": self._clock(),
            },
        )

    def _clear(self, context: CollectorContext, scope: str) -> None:
        context.connection.execute(
            _SYNC_ERROR.delete().where(
                _SYNC_ERROR.c.tenant_id == context.unit.tenant_id,
                _SYNC_ERROR.c.collector == self._name,
                _SYNC_ERROR.c.scope_key == scope,
            )
        )
