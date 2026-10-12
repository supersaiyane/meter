"""Tokens and requests per caller, written to `ai_usage_daily`, P13 spec sections 5.4 and 6.

`BedrockInvocationsCollector` reads one account and Region's invocation logs for the unit's window,
a day, TASK-P13-003. The writer and the restatement below are shared with the OpenAI and Anthropic
collectors, TASK-P13-004 and 005, which write the same table from their usage reports.

**A source restates only what it read.** A rerun of a window replaces that window's rows for that
provider, account and, for Bedrock, Region: a caller who stopped appearing in the logs leaves the
table, and nothing outside the window, another Region or another provider is touched. The run id
is the signal, as it is for the bill: a row this run wrote carries its id, and a row in the window
that does not was not seen again. The scoping predicates are each load bearing, in the same way as
the cost collector's, `finops_ingest/collectors/cost_focus.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import text

from finops_core.domain.ai import AiUsage
from finops_core.errors import SchemaDrift
from finops_core.ports.ai import InvocationLogs
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "bedrock_invocations"
#: The source this collector writes and restates, as the table names it.
BEDROCK = "bedrock"

Clock = Callable[[], datetime]

_COLUMNS = (
    "tenant_id",
    "ingest_run_id",
    "provider",
    "account_id",
    "usage_date",
    "model",
    "workspace",
    "api_key_id",
    "caller",
    "application",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "requests",
    "as_of",
    "collected_at",
)
#: The primary key, which an upsert never updates.
_KEY = frozenset(
    {
        "tenant_id",
        "provider",
        "account_id",
        "usage_date",
        "model",
        "workspace",
        "api_key_id",
        "caller",
        "application",
    }
)

UPSERT = text(
    "INSERT INTO ai_usage_daily ("
    + ", ".join(_COLUMNS)
    + ") VALUES ("
    + ", ".join(f":{column}" for column in _COLUMNS)
    + ") ON CONFLICT ON CONSTRAINT pk_ai_usage_daily DO UPDATE SET "
    + ", ".join(f"{column} = EXCLUDED.{column}" for column in _COLUMNS if column not in _KEY)
)

#: Every predicate is load bearing. Without the provider or the account, one source's rerun removes
#: another's rows; without the dates, a rerun of one day removes every other day; and without the
#: workspace, where a source reads one at a time, a rerun of one Region removes the others.
RETRACT = text(
    "DELETE FROM ai_usage_daily WHERE tenant_id = :tenant AND provider = :provider "
    "AND account_id = :account AND usage_date >= :first AND usage_date < :after "
    "AND (CAST(:workspace AS TEXT) IS NULL OR workspace = :workspace) "
    "AND ingest_run_id <> :run"
)


def _system_clock() -> datetime:
    return datetime.now(UTC)


def write_usage(context: CollectorContext, rows: Iterable[AiUsage], at: datetime) -> int:
    """Upsert the rows under this run, for this tenant. Returns how many were written."""
    batch: list[dict[str, Any]] = []
    for row in rows:
        values = {column: getattr(row, column) for column in _COLUMNS if column != "ingest_run_id"}
        # The tenant and the run are this run's, not whatever the adapter put on the row, and
        # `collected_at` is when Meter fetched it, never earlier than when it was true.
        values["tenant_id"] = context.unit.tenant_id
        values["ingest_run_id"] = context.run_id
        values["collected_at"] = max(at, row.as_of)
        batch.append(values)
    if batch:
        context.connection.execute(UPSERT, batch)
    return len(batch)


def retract_usage(
    context: CollectorContext,
    *,
    provider: str,
    account_id: str,
    first: date,
    after: date,
    workspace: str | None = None,
) -> int:
    """Remove what this provider stopped reporting in `[first, after)`, and nothing else."""
    result = context.connection.execute(
        RETRACT,
        {
            "tenant": context.unit.tenant_id,
            "provider": provider,
            "account": account_id,
            "first": first,
            "after": after,
            "workspace": workspace,
            "run": context.run_id,
        },
    )
    return int(result.rowcount or 0)


def days_of(start: datetime, end: datetime) -> tuple[date, date]:
    """The first day of a window and the day after its last, for a half open date range."""
    last = (end - timedelta(microseconds=1)).date()
    return start.date(), last + timedelta(days=1)


class BedrockInvocationsCollector:
    """One account and Region's invocation logs for the unit's window, as daily aggregates."""

    def __init__(self, source: InvocationLogs, clock: Clock = _system_clock) -> None:
        self._source = source
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        if context.run_id is None:
            # Not a typed collection failure: the caller assembled the context incorrectly, and
            # rows carry the run id in a NOT NULL column that the restatement deletes on.
            raise ValueError("bedrock_invocations needs the run id from the ledger's claim")
        unit = context.unit
        if unit.account is None or unit.region is None:
            raise SchemaDrift(
                scope_key=unit.scope_key,
                collector=COLLECTOR,
                detail="an invocation logs unit arrived without an account or a Region",
            )
        region = str(unit.region)
        rows = tuple(self._source.usage(unit.account, region, unit.window_start, unit.window_end))
        written = write_usage(context, rows, self._clock())
        first, after = days_of(unit.window_start, unit.window_end)
        removed = retract_usage(
            context,
            provider=BEDROCK,
            account_id=unit.account.account_id,
            first=first,
            after=after,
            workspace=region,
        )
        return CollectorOutcome(items_written=written, items_removed=removed)
