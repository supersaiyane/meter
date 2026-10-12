"""How busy the GPU instances the bill names were, per account, Region and day. FEAT-084.

P13 spec section 5.6, TASK-P13-006. Which instances to ask about comes from the bill rather than a
describe call: the EC2 line items in this account and Region, for the day, whose usage type names
an accelerated instance type. So nothing is asked about an instance nobody paid for, and the
collector needs no permission beyond the CloudWatch reads it already had.

An instance whose agent published nothing has no row, which the screen reads as not published. A
rerun of a day replaces that day's rows for the account and Region, so an instance that stopped
publishing leaves the table rather than keeping yesterday's figure under today's date.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from finops_core.domain.ai import GpuUtilization, accelerated_instance_type
from finops_core.errors import SchemaDrift
from finops_core.ports.ai import GpuMetrics
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "gpu_utilization"

Clock = Callable[[], datetime]

#: The bill's EC2 instances in this account and Region whose charge overlaps the window, with the
#: usage type that says what they are. Filtered to accelerated types in Python, by the domain's
#: own reading of a usage type, so the database and the screen cannot disagree about which are.
BILLED = text(
    "SELECT DISTINCT resource_id, x_usage_type FROM cost_focus_daily "
    "WHERE tenant_id = :tenant AND sub_account_id = :account AND region_id = :region "
    "AND resource_id LIKE 'i-%' AND x_usage_type IS NOT NULL "
    "AND charge_period_start < :end AND charge_period_end > :start"
)

UPSERT = text(
    "INSERT INTO gpu_utilization_daily (tenant_id, ingest_run_id, account_id, region_id, "
    "instance_id, usage_date, gpu_count, average_percent, peak_percent, samples, as_of, "
    "collected_at) VALUES (:tenant, :run, :account, :region, :instance, :day, :gpus, :average, "
    ":peak, :samples, :as_of, :collected_at) "
    "ON CONFLICT ON CONSTRAINT pk_gpu_utilization_daily DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, gpu_count = EXCLUDED.gpu_count, "
    "average_percent = EXCLUDED.average_percent, peak_percent = EXCLUDED.peak_percent, "
    "samples = EXCLUDED.samples, as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
)

#: Each predicate is load bearing, as the bill's restatement's are: without the account or the
#: Region one unit removes another's rows, and without the dates one day's rerun removes them all.
RETRACT = text(
    "DELETE FROM gpu_utilization_daily WHERE tenant_id = :tenant AND account_id = :account "
    "AND region_id = :region AND usage_date >= :first AND usage_date < :after "
    "AND ingest_run_id <> :run"
)


def _system_clock() -> datetime:
    return datetime.now(UTC)


class GpuUtilizationCollector:
    """One account and Region's GPU instances, read for the unit's window."""

    def __init__(self, metrics: GpuMetrics, clock: Clock = _system_clock) -> None:
        self._metrics = metrics
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        if context.run_id is None:
            raise ValueError("gpu_utilization needs the run id from the ledger's claim")
        unit = context.unit
        if unit.account is None or unit.region is None:
            raise SchemaDrift(
                scope_key=unit.scope_key,
                collector=COLLECTOR,
                detail="a GPU utilization unit arrived without an account or a Region",
            )
        account, region = unit.account, str(unit.region)
        instances = self._billed(context, account.account_id, region)
        rows: Iterable[GpuUtilization] = ()
        if instances:
            rows = self._metrics.utilization(
                account, region, instances, unit.window_start, unit.window_end
            )
        written = self._write(context, rows)
        last = (unit.window_end - timedelta(microseconds=1)).date()
        removed = context.connection.execute(
            RETRACT,
            {
                "tenant": unit.tenant_id,
                "account": account.account_id,
                "region": region,
                "first": unit.window_start.date(),
                "after": last + timedelta(days=1),
                "run": context.run_id,
            },
        ).rowcount
        return CollectorOutcome(items_written=written, items_removed=int(removed or 0))

    def _billed(self, context: CollectorContext, account: str, region: str) -> list[str]:
        unit = context.unit
        rows = context.connection.execute(
            BILLED,
            {
                "tenant": unit.tenant_id,
                "account": account,
                "region": region,
                "start": unit.window_start,
                "end": unit.window_end,
            },
        ).all()
        return sorted({row[0] for row in rows if accelerated_instance_type(row[1])})

    def _write(self, context: CollectorContext, rows: Iterable[GpuUtilization]) -> int:
        at = self._clock()
        batch: list[dict[str, Any]] = [
            {
                "tenant": context.unit.tenant_id,
                "run": context.run_id,
                "account": row.account_id,
                "region": row.region_id,
                "instance": row.instance_id,
                "day": row.usage_date,
                "gpus": row.gpu_count,
                "average": row.average_percent,
                "peak": row.peak_percent,
                "samples": row.samples,
                "as_of": row.as_of,
                "collected_at": max(at, row.as_of),
            }
            for row in rows
        ]
        if batch:
            context.connection.execute(UPSERT, batch)
        return len(batch)
