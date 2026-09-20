"""Writing what was committed and what it covered.

Two reads and two upserts, in one transaction. The port's two methods stay two
here rather than being merged into a single row per commitment, because a coverage
figure attached to a commitment is a number nobody measured. See
`finops_core/ports/commitment.py`.

**A window is replaced, never accumulated.** Both upserts key on the window, so a
second run over the same month replaces its rows. Four runs a day would otherwise
show a reader the same wasted dollar four times, and they would stop believing the
total, which is the one figure on the screen they can act on immediately.

**A commitment that has gone is still reported.** The port returns expired
commitments and this writes them, because the money was spent and the coverage gap
the expiry leaves is the finding. Filtering them here would make the estate look
like it never had the commitment.

**`NoData` is not a failure to write nothing about.** A payer holding no
commitments is a fact, and it is reported as zero rows written rather than as a
typed failure, because the screen's job in that case is to say the estate has no
commitments rather than to say a collection broke.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from finops_core.errors import NoData
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "commitment"
SCOPE = "billing"

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


def _month_containing(day: date) -> tuple[date, date]:
    """The whole month a day falls in, with an exclusive end.

    A whole month rather than a rolling window. A commitment's obligation is stated
    per month, and a window straddling two of them reports a utilization figure
    that matches neither invoice.
    """
    start = date(day.year, day.month, 1)
    end = date(start.year + start.month // 12, start.month % 12 + 1, 1)
    return start, end


WRITE_USE = text(
    "INSERT INTO commitment_use (use_id, tenant_id, ingest_run_id, commitment_id, "
    "commitment_type, status, term_start, term_end, window_start, window_end, "
    "committed, used, wasted, as_of, collected_at) "
    "VALUES (:id, :tenant, :run, :commitment, :type, :status, :term_start, :term_end, "
    ":window_start, :window_end, :committed, :used, :wasted, :as_of, :collected_at) "
    "ON CONFLICT (tenant_id, commitment_id, window_start) DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, commitment_type = EXCLUDED.commitment_type, "
    "status = EXCLUDED.status, term_start = EXCLUDED.term_start, term_end = EXCLUDED.term_end, "
    "window_end = EXCLUDED.window_end, committed = EXCLUDED.committed, used = EXCLUDED.used, "
    "wasted = EXCLUDED.wasted, as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
)

WRITE_COVERAGE = text(
    "INSERT INTO commitment_coverage (coverage_id, tenant_id, ingest_run_id, commitment_type, "
    "dimension, dimension_value, window_start, window_end, eligible_spend, covered_spend, "
    "as_of, collected_at) "
    "VALUES (:id, :tenant, :run, :type, :dimension, :value, :window_start, :window_end, "
    ":eligible, :covered, :as_of, :collected_at) "
    "ON CONFLICT (tenant_id, commitment_type, dimension, dimension_value, window_start) "
    "DO UPDATE SET ingest_run_id = EXCLUDED.ingest_run_id, window_end = EXCLUDED.window_end, "
    "eligible_spend = EXCLUDED.eligible_spend, covered_spend = EXCLUDED.covered_spend, "
    "as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
)


class CommitmentCollector:
    """Reads a month of commitment utilization and coverage, and writes both."""

    def __init__(self, report: Any, clock: Clock = _system_clock) -> None:
        self._report = report
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        if context.run_id is None:
            # Both tables carry the run in a NOT NULL column. A collector
            # generating its own would be writing a number that names no run, and
            # the ledger could not later say which run produced a figure somebody
            # is disputing.
            raise ValueError(
                "commitment needs the run id from the ledger's claim. Its rows "
                "carry it in a NOT NULL column."
            )

        window_start, window_end = _month_containing(self._clock().date())
        written = self._write_use(context, window_start, window_end)
        written += self._write_coverage(context, window_start, window_end)
        return CollectorOutcome(items_written=written)

    def _write_use(self, context: CollectorContext, window_start: date, window_end: date) -> int:
        try:
            uses = tuple(self._report.utilization(window_start, window_end))
        except NoData:
            # The payer holds no commitments. Nothing to write and nothing wrong.
            return 0

        for use in uses:
            context.connection.execute(
                WRITE_USE,
                {
                    "id": uuid4(),
                    "tenant": context.unit.tenant_id,
                    "run": context.run_id,
                    "commitment": use.commitment_id,
                    "type": use.commitment_type,
                    "status": use.status,
                    "term_start": use.term_start,
                    "term_end": use.term_end,
                    "window_start": use.window_start,
                    "window_end": use.window_end,
                    "committed": use.committed,
                    "used": use.used,
                    # From the entity, which already refused a row whose three
                    # numbers disagree, and constrained again in the database.
                    "wasted": use.wasted,
                    "as_of": use.as_of,
                    "collected_at": use.collected_at,
                },
            )
        return len(uses)

    def _write_coverage(
        self, context: CollectorContext, window_start: date, window_end: date
    ) -> int:
        try:
            found = tuple(self._report.coverage(window_start, window_end))
        except NoData:
            # Nothing in the window was eligible for a commitment. A fact about the
            # estate, not a failed read.
            return 0

        for slice_ in found:
            context.connection.execute(
                WRITE_COVERAGE,
                {
                    "id": uuid4(),
                    "tenant": context.unit.tenant_id,
                    "run": context.run_id,
                    "type": slice_.commitment_type,
                    "dimension": slice_.dimension,
                    "value": slice_.dimension_value,
                    "window_start": slice_.window_start,
                    "window_end": slice_.window_end,
                    "eligible": slice_.eligible_spend,
                    "covered": slice_.covered_spend,
                    "as_of": slice_.as_of,
                    "collected_at": slice_.collected_at,
                },
            )
        return len(found)
