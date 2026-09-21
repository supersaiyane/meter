"""Bringing AWS's own findings into our table and our lifecycle.

Three services, one table, and three rules that are all about not losing what a
human did.

**A withdrawn recommendation is dismissed, not deleted.** When AWS stops reporting
a finding, the row stays and moves to `DISMISSED` with a reason naming the
withdrawal. Deleting it would take its whole event log with it, and the event log
is the only record that somebody accepted it in March and nothing happened.

**A recommendation a human has touched is not reopened.** The provider owns the
finding; we own the lifecycle. A re read that reset an `ACCEPTED` row to `OPEN`
every six hours would make the screen useless and the acceptance meaningless.

**One service failing does not fail the others.** Compute Optimizer needs an opt
in, Trusted Advisor needs a support tier, and an estate may have one and not the
other. Each is read in its own try, its refusal is recorded, and the rest continue.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.waste import Lifecycle, Recommendation, Source
from finops_core.errors import CollectionError, NotOptedIn
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "recommendations"
SCOPE = "billing"

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


#: Lifecycles a re read may overwrite. Everything else has been touched by a
#: person, and the provider does not get to undo that.
UNTOUCHED = (Lifecycle.OPEN.value, Lifecycle.DISMISSED.value)

WRITE = text(
    "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, source, "
    "source_reference, waste_class, resource_id, region_id, estimated_monthly_saving, "
    "confidence, severity, observation_days, lifecycle, owner, ticket_reference, "
    "rationale, as_of, collected_at) "
    "VALUES (:id, :tenant, :account, :source, :reference, :waste_class, :resource, :region, "
    ":saving, :confidence, :severity, :days, :lifecycle, NULL, NULL, :rationale, :as_of, :now) "
    "ON CONFLICT (tenant_id, source, source_reference) DO UPDATE SET "
    "estimated_monthly_saving = EXCLUDED.estimated_monthly_saving, "
    "confidence = EXCLUDED.confidence, severity = EXCLUDED.severity, "
    "observation_days = EXCLUDED.observation_days, rationale = EXCLUDED.rationale, "
    "waste_class = EXCLUDED.waste_class, as_of = EXCLUDED.as_of, "
    "collected_at = EXCLUDED.collected_at, "
    # The lifecycle is ours. A provider re read refreshes the money and the
    # working and leaves where the recommendation got to alone, unless nobody has
    # moved it, in which case reopening a previously withdrawn finding is right.
    "lifecycle = CASE WHEN recommendation.lifecycle IN ('OPEN', 'DISMISSED') "
    "THEN 'OPEN' ELSE recommendation.lifecycle END"
)

#: The first event of a recommendation's life. Written only when the row is new,
#: because the constraint allows exactly one null `from_lifecycle` per row.
FIRST_EVENT = text(
    "INSERT INTO recommendation_event (event_id, recommendation_id, tenant_id, "
    "from_lifecycle, to_lifecycle, actor, reason, occurred_at, as_of, collected_at) "
    "SELECT :id, r.recommendation_id, :tenant, NULL, 'OPEN', :actor, :reason, :now, :now, :now "
    "FROM recommendation r "
    "WHERE r.tenant_id = :tenant AND r.source = :source AND r.source_reference = :reference "
    "AND NOT EXISTS ("
    "  SELECT 1 FROM recommendation_event e WHERE e.recommendation_id = r.recommendation_id"
    ")"
)

#: What this run did not see. Dismissed rather than deleted.
#:
#: A CTE rather than a plain UPDATE with RETURNING, and the reason is not style.
#: Postgres returns the **new** row from RETURNING, so `RETURNING lifecycle` on
#: this statement yields 'DISMISSED' for every row, and the event written from it
#: would read "DISMISSED to DISMISSED" for every withdrawal. The old value has to
#: be captured before the write, which is what the first arm does.
#:
#: `IN_PROGRESS` is deliberately absent from the filter. If somebody is actively
#: doing the work, a provider that stopped reporting the finding has most likely
#: noticed the work, and dismissing it out from under them would lose the fact
#: that it was being done.
WITHDRAW = text(
    "WITH going AS ("
    "  SELECT recommendation_id, lifecycle AS was FROM recommendation"
    "  WHERE tenant_id = :tenant AND source = :source"
    "    AND lifecycle IN ('OPEN', 'ACCEPTED')"
    "    AND source_reference <> ALL(:seen)"
    "  FOR UPDATE"
    "), done AS ("
    "  UPDATE recommendation r SET lifecycle = 'DISMISSED', collected_at = :now"
    "  FROM going g WHERE r.recommendation_id = g.recommendation_id"
    "  RETURNING r.recommendation_id"
    ") SELECT recommendation_id, was FROM going"
)

WITHDRAW_EVENT = text(
    "INSERT INTO recommendation_event (event_id, recommendation_id, tenant_id, "
    "from_lifecycle, to_lifecycle, actor, reason, occurred_at, as_of, collected_at) "
    "VALUES (:id, :recommendation, :tenant, :from, 'DISMISSED', :actor, :reason, :now, :now, :now)"
)


class RecommendationCollector:
    """Reads three services and writes one table."""

    def __init__(self, provider: Any, clock: Clock = _system_clock) -> None:
        self._provider = provider
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        now = self._clock()
        written = 0
        for source, read in (
            (Source.COMPUTE_OPTIMIZER, self._provider.compute_optimizer),
            (Source.COST_OPTIMIZATION_HUB, self._provider.cost_optimization_hub),
            (Source.TRUSTED_ADVISOR, self._provider.trusted_advisor),
        ):
            written += self._one_source(context, source, read, now)
        return CollectorOutcome(items_written=written)

    def _one_source(
        self,
        context: CollectorContext,
        source: Source,
        read: Callable[[], Iterable[Recommendation]],
        now: datetime,
    ) -> int:
        try:
            found = tuple(read())
        except NotOptedIn:
            # An expected state. The estate is correctly configured and has fewer
            # signals, and nothing is withdrawn: a service that was never on has
            # not stopped reporting anything.
            return 0
        except CollectionError:
            # Typed and real. The run continues with the other two services, and
            # the dispatcher records the failure. Withdrawing here would dismiss
            # every finding from a service that merely timed out.
            raise

        for item in found:
            self._write(context, item, now)

        self._withdraw(context, source, [item.source_reference for item in found], now)
        return len(found)

    def _write(self, context: CollectorContext, item: Recommendation, now: datetime) -> None:
        context.connection.execute(
            WRITE,
            {
                "id": uuid4(),
                "tenant": context.unit.tenant_id,
                "account": item.sub_account_id,
                "source": item.source.value,
                "reference": item.source_reference,
                "waste_class": item.waste_class.value,
                "resource": item.resource_id,
                "region": item.region_id,
                "saving": item.estimated_monthly_saving,
                "confidence": item.confidence.value,
                "severity": item.severity,
                "days": item.observation_days,
                "lifecycle": Lifecycle.OPEN.value,
                "rationale": item.rationale,
                "as_of": item.as_of,
                "now": now,
            },
        )
        context.connection.execute(
            FIRST_EVENT,
            {
                "id": uuid4(),
                "tenant": context.unit.tenant_id,
                "source": item.source.value,
                "reference": item.source_reference,
                "actor": f"collector:{COLLECTOR}",
                "reason": None,
                "now": now,
            },
        )

    def _withdraw(
        self, context: CollectorContext, source: Source, seen: list[str], now: datetime
    ) -> None:
        """Dismiss what this run did not see, keeping the row and its history."""
        gone = context.connection.execute(
            WITHDRAW,
            {
                "tenant": context.unit.tenant_id,
                "source": source.value,
                # An empty list is a real answer: the service returned nothing, so
                # everything it previously reported has been withdrawn.
                "seen": seen or [""],
                "now": now,
            },
        ).all()
        for row in gone:
            context.connection.execute(
                WITHDRAW_EVENT,
                {
                    "id": uuid4(),
                    "recommendation": row[0],
                    "tenant": context.unit.tenant_id,
                    "from": row[1],
                    "actor": f"collector:{COLLECTOR}",
                    "reason": f"{source.value} no longer reports this finding",
                    "now": now,
                },
            )
