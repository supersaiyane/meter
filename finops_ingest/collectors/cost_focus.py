"""The bill, written to `cost_focus_daily` one billing period at a time.

The table was migrated in P0 and nothing has ever written to it. This is the
writer.

**What makes a line item itself.** The primary key is
`(tenant_id, billing_period_start, source_fingerprint)`, and the fingerprint is
computed by the adapter from the columns that identify the charge, never from
the columns that state its size. That is what lets AWS restate a month all the
way through it: a corrected row upserts onto the row it corrects instead of
landing beside it. `finops_core.domain.cost.source_fingerprint` is the one
implementation, shared by both adapters, because two implementations of an
identity is how a duplicate is created.

**The run id is the run's.** Every row carries the `ingest_run_id` of the run
that last wrote it, and the restatement delete in TASK-P1-005 keys on exactly
that. A collector inventing its own would be writing a number that names no run
and then deleting on a fiction, so this refuses to run without one.

**Partitions are not created here.** `cost_focus_daily` is partitioned by
billing period and `partition_maintenance` creates the partitions ahead of use.
A period with no partition fails, loudly, at the database, which is constraint
11 working: the invariant is a schema rule, and application code that quietly
created the missing partition would be the convention that eventually is not
there.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from finops_core.domain.cost import CostRecord
from finops_core.errors import NoData
from finops_ingest.collectors.partitions import next_month
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "cost_focus"
SCOPE = "billing"

#: Rows per statement. Large enough that a month is a handful of round trips,
#: small enough that one statement's parameters stay a readable size in a log.
BATCH = 500

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


COLUMNS = (
    "tenant_id",
    "ingest_run_id",
    "source_fingerprint",
    "as_of",
    "collected_at",
    "billing_account_id",
    "sub_account_id",
    "billing_period_start",
    "billing_period_end",
    "charge_period_start",
    "charge_period_end",
    "provider_name",
    "publisher_name",
    "invoice_issuer_name",
    "service_name",
    "service_category",
    "resource_id",
    "resource_name",
    "region_id",
    "availability_zone",
    "charge_category",
    "charge_description",
    "sku_id",
    "pricing_quantity",
    "consumed_quantity",
    "consumed_unit",
    "billed_cost",
    "effective_cost",
    "list_cost",
    "contracted_cost",
    "commitment_discount_id",
    "commitment_discount_type",
    "commitment_discount_status",
)

#: Everything except the key. A restated row changes any of these, including
#: `ingest_run_id`, which is what tells the retraction pass in TASK-P1-005 that
#: this row was seen again.
_UPDATABLE = tuple(
    column
    for column in COLUMNS
    if column not in ("tenant_id", "billing_period_start", "source_fingerprint")
)

UPSERT = text(
    "INSERT INTO cost_focus_daily ("
    + ", ".join(COLUMNS)
    + ", tags) VALUES ("
    + ", ".join(f":{column}" for column in COLUMNS)
    + ", CAST(:tags AS jsonb)) "
    "ON CONFLICT (tenant_id, billing_period_start, source_fingerprint) DO UPDATE SET "
    + ", ".join(f"{column} = EXCLUDED.{column}" for column in _UPDATABLE)
    + ", tags = EXCLUDED.tags"
)


class CostFocusCollector:
    """Reads one billing period and writes it, idempotently."""

    def __init__(self, export: Any, clock: Clock = _system_clock) -> None:
        self._export = export
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        if context.run_id is None:
            # Not a typed collection failure. Nothing about the provider is
            # wrong, the caller assembled the context incorrectly, and a
            # collection error here would be recorded against the scope and
            # send somebody to look at AWS.
            raise ValueError(
                "cost_focus needs the run id from the ledger's claim. Rows carry it "
                "in a NOT NULL column and the restatement pass deletes on it."
            )

        period = self._export.latest_available_period()
        if period is None:
            # The export is there and has published nothing. Said rather than
            # returned as a successful run of zero rows, because a run that
            # succeeded and wrote nothing reads on the freshness screen as an
            # estate that spent nothing.
            raise NoData(
                scope_key=SCOPE,
                collector=COLLECTOR,
                detail="the export exists and has published no billing period yet",
            )

        rows = self._export.read_period(period, next_month(period))
        return CollectorOutcome(items_written=self._write(context, rows))

    def _write(self, context: CollectorContext, rows: Iterable[CostRecord]) -> int:
        at = self._clock()
        written = 0
        batch: list[dict[str, Any]] = []
        for row in rows:
            batch.append(self._parameters(row, context, at))
            if len(batch) >= BATCH:
                context.connection.execute(UPSERT, batch)
                written += len(batch)
                batch = []
        if batch:
            context.connection.execute(UPSERT, batch)
            written += len(batch)
        return written

    def _parameters(
        self, row: CostRecord, context: CollectorContext, at: datetime
    ) -> dict[str, Any]:
        values = {column: getattr(row, column) for column in COLUMNS}
        # The tenant and the run are this run's, not whatever the adapter put on
        # the record. An adapter has no way to know which tenant it is reading
        # for, and the fake fills both in so its rows are constructible.
        values["tenant_id"] = context.unit.tenant_id
        values["ingest_run_id"] = context.run_id
        # `as_of` stays the adapter's: it is when the charge was true at the
        # source. `collected_at` is ours: when we fetched it. Constraint 10, and
        # conflating them is what makes a stale number look fresh.
        values["collected_at"] = at
        values["tags"] = json.dumps(dict(row.tags))
        return values
