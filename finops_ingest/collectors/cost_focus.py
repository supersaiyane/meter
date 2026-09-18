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


RETRACT = text(
    "DELETE FROM cost_focus_daily WHERE tenant_id = :tenant "
    "AND billing_period_start = :period AND ingest_run_id <> :run"
)


class CostFocusCollector:
    """Reads one billing period, writes it, and removes what was withdrawn."""

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

        # Two independent things protect a half read period, and it is worth
        # knowing which is which. The worker runs a unit in one transaction, so
        # a read that fails part way rolls back everything including any
        # removal. That is the one doing the work in the deployed shape, and
        # reversing these two lines does not break the tests that exercise it.
        #
        # The ordering is the second. `_write` consumes the rows, so a read that
        # fails raises there and `_retract` is never reached at all. It matters
        # for any caller that does not wrap the unit in a transaction it will
        # roll back, and it costs nothing to keep, so the removal stays
        # downstream of finishing the read.
        # `test_the_collector_alone_removes_nothing_on_a_half_read` is the one
        # that fails if these are swapped.
        written = self._write(context, rows)
        removed = self._retract(context, period)
        return CollectorOutcome(items_written=written, items_removed=removed)

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

    def _retract(self, context: CollectorContext, period: Any) -> int:
        """Remove what the provider withdrew, and nothing else.

        AWS restates a billing period continuously and can restate a closed one.
        A line item can change size, which the upsert handles, and a line item
        can disappear. If nothing removes it, a charge AWS withdrew stays on
        Meter's bill forever, and the total drifts above the invoice by exactly
        the sum of every correction ever issued.

        The signal is the run id. A row this run saw carries this run's id,
        because the upsert set it. A row this run did not see kept an older one,
        and in a complete read the only reason a row goes unseen is that the
        provider stopped reporting it.

        Not a timestamp. Two runs inside one second are indistinguishable by a
        clock, so a `collected_at` predicate either removes nothing or removes
        both runs' work, depending on which way the comparison leans.

        All three predicates are load bearing. Without the tenant, one tenant's
        ingest removes another's rows. Without the period, ingesting August
        removes every earlier month in one statement, which is the worst
        outcome available to this file and the easiest to write.
        """
        result = context.connection.execute(
            RETRACT,
            {"tenant": context.unit.tenant_id, "period": period, "run": context.run_id},
        )
        return int(result.rowcount or 0)

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
