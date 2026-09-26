"""Coverage gaps, written as findings somebody owns.

FEAT-055, TASK-P1-022. The arithmetic is in `finops_query/commitment.py` and is pure; this
module reads the coverage rows the commitment collector already writes and turns each gap into
a recommendation with an owner, a lifecycle and a realized saving measured afterwards.

**It reads our own table, not a provider.** `commitment_coverage` is written by FEAT-019 from
the bill, so this collector makes no API call and costs nothing per run. That is why its
cadence follows the collector it reads rather than being an interval of its own choosing.

**It is not a second view of the commitments screen.** That screen reports coverage, which is a
fact nobody owns. This produces a finding, which has an owner and a lifecycle and gets worked.
A chart is read once a quarter.

**It writes `commitment_action` rather than `recommendation`, and ADR-0025 is the whole
argument.** A commitment is bought at the payer and its coverage cannot be apportioned, which
is why `commitment_coverage` is `PayerWide`. A finding derived from a payer wide fact is payer
wide, and `recommendation` is scoped by account: writing these rows into it would have meant
stamping an account on a payer wide figure, and whoever held that account would then read the
organization's commitment position through a findings list. A finding inherits the scoping of
the fact it was computed from, not the scoping of the table it resembles.

**The severity comes from the money, ADR-0016, and the risk from the class.** A commitment is
the least reversible thing in the product: nothing stops to buy one, which is exactly why it
reads as safe, and it obligates its whole term whether or not the usage continues.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.waste import confidence_of
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.commitment import assess, rationale
from finops_query.severity import severity_for, thresholds_from

COLLECTOR = "commitment_actions"
SCOPE = "billing"

#: The latest window per dimension, because coverage is written once per window and an estate
#: with six months of history holds six rows per dimension. Recommending against the oldest
#: would be advising on a baseline that has since changed.
#: Upserted on the dimension, not the window. A coverage row arrives per window, and keying on
#: the window would open a second finding every month and leave last month's looking abandoned
#: while somebody was still working it. The lifecycle survives the update unless it had been
#: dismissed, which is the rule `recommendation`'s own upsert follows: a gap that reappears
#: after somebody decided it was not worth closing is a new decision, and one they accepted is
#: theirs to keep.
WRITE = text(
    "INSERT INTO commitment_action (action_id, tenant_id, ingest_run_id, commitment_type, "
    "dimension, dimension_value, window_start, window_end, eligible_spend, covered_spend, "
    "estimated_monthly_saving, usage_floor_percent, term_months, confidence, severity, "
    "lifecycle, owner, ticket_reference, rationale, as_of, collected_at) "
    "VALUES (:id, :tenant, :run, :type, :dim, :value, :start, :end, :eligible, :covered, "
    ":saving, :floor, :term, :confidence, :severity, 'OPEN', NULL, NULL, :rationale, :now, "
    ":now) "
    "ON CONFLICT (tenant_id, commitment_type, dimension, dimension_value) DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, window_start = EXCLUDED.window_start, "
    "window_end = EXCLUDED.window_end, eligible_spend = EXCLUDED.eligible_spend, "
    "covered_spend = EXCLUDED.covered_spend, "
    "estimated_monthly_saving = EXCLUDED.estimated_monthly_saving, "
    "usage_floor_percent = EXCLUDED.usage_floor_percent, "
    "term_months = EXCLUDED.term_months, confidence = EXCLUDED.confidence, "
    "severity = EXCLUDED.severity, rationale = EXCLUDED.rationale, "
    "as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at, "
    "lifecycle = CASE WHEN commitment_action.lifecycle IN ('OPEN', 'DISMISSED') "
    "THEN 'OPEN' ELSE commitment_action.lifecycle END"
)

LATEST = text(
    "SELECT DISTINCT ON (commitment_type, dimension, dimension_value) "
    "commitment_type, dimension, dimension_value, window_start, window_end, "
    "eligible_spend, covered_spend "
    "FROM commitment_coverage WHERE tenant_id = :tenant "
    "ORDER BY commitment_type, dimension, dimension_value, window_end DESC"
)


def _system_clock() -> datetime:
    return datetime.now(UTC)


Clock = Callable[[], datetime]


class CommitmentActionsCollector:
    """A coverage gap, as something somebody is accountable for closing."""

    def __init__(self, clock: Clock = _system_clock) -> None:
        # No source. Everything it needs is in our own tables, which is why this is the one
        # collector in the product with no adapter and no cost per run.
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        settings = context.settings
        if settings is None:
            # The discount rate is an assumption about a price nobody has been quoted and the
            # term decides how long a wrong decision lasts. Defaulting either would put a
            # number nobody chose behind advice to commit real money.
            raise ValueError(
                "commitment_actions needs settings. Its discount rate, its term and its "
                "minimum saving are configuration, not constants."
            )

        now = self._clock()
        thresholds = thresholds_from(settings)
        rows = context.connection.execute(LATEST, {"tenant": context.unit.tenant_id}).all()

        written = 0
        for row in rows:
            found = assess(
                eligible=row.eligible_spend,
                covered=row.covered_spend,
                window_start=row.window_start,
                window_end=row.window_end,
                discount_percent=settings.commitment_discount_percent,
                term_months=settings.commitment_term_months,
                minimum_monthly_saving=settings.commitment_minimum_monthly_saving_usd,
            )
            if found is None:
                # Four different refusals, all of which mean there is nothing honest to say.
                # `finops_query/commitment.py` documents which.
                continue

            context.connection.execute(
                WRITE,
                {
                    "id": uuid4(),
                    "tenant": context.unit.tenant_id,
                    "run": context.run_id,
                    "type": row.commitment_type,
                    "dim": row.dimension,
                    "value": str(row.dimension_value),
                    "start": found.window_start,
                    "end": found.window_end,
                    # The measured inputs, stored beside the modelled output, so a reader a
                    # year later can check the arithmetic rather than take it.
                    "eligible": found.eligible,
                    "covered": found.covered,
                    "saving": found.monthly_saving,
                    "floor": found.usage_floor_percent,
                    "term": found.term_months,
                    # From the length of the window, like every other finding's. It says how
                    # long we watched and nothing about how large the number is, ADR-0016.
                    "confidence": confidence_of((found.window_end - found.window_start).days).value,
                    "severity": severity_for(found.monthly_saving, thresholds),
                    "rationale": rationale(
                        found,
                        dimension=row.dimension,
                        dimension_value=str(row.dimension_value),
                    ),
                    "now": now,
                },
            )
            written += 1

        return CollectorOutcome(items_written=written)
