"""What AWS is blind to, from the metrics it publishes.

Reads one batch of series for the whole estate, asks `finops_query.waste` about
each, and writes the ones worth a row into the same `recommendation` table the AWS
findings land in.

Three decisions.

**Idle is asked before oversized.** An instance doing nothing is idle, and the
action is to turn it off. The rightsizing arithmetic will also happily report it,
as an instance that could be very much smaller, and that recommendation is true
and useless: nobody shrinks a machine they could delete. Asking in the other order
produces a screen full of rightsizings for dead instances.

**An absent series is skipped, loudly.** The port returns nothing for a resource
that published no metrics, and that is not a resource at zero utilization. The
count of skipped instances is returned so the run ledger records it, because an
estate where half the instances publish nothing is a configuration problem rather
than an estate with no waste.

**Auto Scaling groups are recommended once, not once per instance.** FEAT-026's
binding rule. Twenty identical instances behind one group produce one
recommendation naming the group, because twenty rows telling somebody the same
thing is how a screen gets ignored.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.waste import Source, confidence_of
from finops_core.ports.metrics import MetricRequest
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.severity import severity_for, thresholds_from
from finops_query.waste import Estimate, idle, rightsize_cpu

COLLECTOR = "waste_compute"
SCOPE = "billing"

NAMESPACE = "AWS/EC2"
CPU = "CPUUtilization"

#: Memory is not an EC2 metric. The CloudWatch agent publishes it under its own
#: namespace, so an instance without the agent has no memory series at all, which
#: is unobserved rather than fine. FEAT-026.
AGENT_NAMESPACE = "CWAgent"
MEMORY = "mem_used_percent"

#: How a memory request is keyed, so it cannot collide with the CPU request for
#: the same instance in a batch the port returns as one mapping.
MEMORY_KEY = "memory:"

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Candidate:
    """One thing the collector was asked to look at."""

    resource_id: str
    account_id: str
    region_id: str
    observation_days: int
    monthly_cost: Decimal
    credit_balance: Decimal | None = None
    #: Where the instance belongs to a group, the group is what gets recommended.
    scaling_group: str | None = None


WRITE = text(
    "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, source, "
    "source_reference, waste_class, resource_id, region_id, estimated_monthly_saving, "
    "confidence, severity, observation_days, lifecycle, owner, ticket_reference, "
    "rationale, as_of, collected_at) "
    "VALUES (:id, :tenant, :account, :source, :reference, :waste_class, :resource, :region, "
    ":saving, :confidence, :severity, :days, 'OPEN', NULL, NULL, :rationale, :now, :now) "
    "ON CONFLICT (tenant_id, source, source_reference) DO UPDATE SET "
    "estimated_monthly_saving = EXCLUDED.estimated_monthly_saving, "
    "waste_class = EXCLUDED.waste_class, confidence = EXCLUDED.confidence, "
    "severity = EXCLUDED.severity, observation_days = EXCLUDED.observation_days, "
    "rationale = EXCLUDED.rationale, as_of = EXCLUDED.as_of, "
    "collected_at = EXCLUDED.collected_at, "
    "lifecycle = CASE WHEN recommendation.lifecycle IN ('OPEN', 'DISMISSED') "
    "THEN 'OPEN' ELSE recommendation.lifecycle END"
)

FIRST_EVENT = text(
    "INSERT INTO recommendation_event (event_id, recommendation_id, tenant_id, "
    "from_lifecycle, to_lifecycle, actor, reason, occurred_at, as_of, collected_at) "
    "SELECT :id, r.recommendation_id, :tenant, NULL, 'OPEN', :actor, NULL, :now, :now, :now "
    "FROM recommendation r "
    "WHERE r.tenant_id = :tenant AND r.source = :source AND r.source_reference = :reference "
    "AND NOT EXISTS ("
    "  SELECT 1 FROM recommendation_event e WHERE e.recommendation_id = r.recommendation_id"
    ")"
)


#: Recorded rather than silent. An estate where half the instances publish nothing
#: is a configuration problem, and a run reporting "no waste found" would hide it.
#: Upserted on the scope, like every other sync error, so a persistent gap shows as
#: one row with a rising count rather than one row per run.
UNOBSERVED_ERROR = text(
    "INSERT INTO sync_error (error_id, tenant_id, collector, scope_key, error_type, "
    "detail, remediation, first_seen_at, last_seen_at, occurrences) "
    "VALUES (:id, :t, :c, :s, 'NoData', :d, :r, :now, :now, 1) "
    "ON CONFLICT (tenant_id, collector, scope_key, error_type) DO UPDATE SET "
    "detail = EXCLUDED.detail, last_seen_at = EXCLUDED.last_seen_at, "
    "occurrences = sync_error.occurrences + 1"
)


class WasteComputeCollector:
    """Our own findings, from metrics the provider publishes."""

    def __init__(
        self,
        metrics: Any,
        candidates: Callable[[CollectorContext], Sequence[Candidate]],
        clock: Clock = _system_clock,
    ) -> None:
        self._metrics = metrics
        # Passed in rather than discovered here, because which resources exist is
        # an inventory question and this collector's job is the arithmetic. P4
        # will supply a real one.
        self._candidates = candidates
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        if context.settings is None:
            # Severity comes from the money, per ADR-0016, and the boundaries are
            # settings. Defaulting them would put a severity nobody chose onto a
            # screen, which is the same refusal `cost_anomaly` makes.
            raise ValueError(
                "waste_compute needs settings. Its severity boundaries are "
                "configuration, not constants."
            )

        now = self._clock()
        thresholds = thresholds_from(context.settings)
        candidates = self._candidates(context)
        window_end = now
        window_start = now - timedelta(
            days=max((c.observation_days for c in candidates), default=0)
        )

        # Two series per instance in one batch. Memory is asked for because a CPU
        # only judgement cannot tell an oversized instance from a memory bound one,
        # and an instance whose work is memory work has a quiet CPU for a reason.
        # Batched rather than fetched per instance, because GetMetricData is charged
        # per metric requested and a second round trip would double the requests
        # without reducing the metrics.
        series = self._metrics.read_many(
            [
                MetricRequest(
                    key=candidate.resource_id,
                    account=AccountKey(provider=Provider.AWS, account_id=candidate.account_id),
                    region=candidate.region_id,
                    namespace=NAMESPACE,
                    metric_name=CPU,
                    dimensions={"InstanceId": candidate.resource_id},
                    statistic="Average",
                )
                for candidate in candidates
            ]
            + [
                MetricRequest(
                    key=f"{MEMORY_KEY}{candidate.resource_id}",
                    account=AccountKey(provider=Provider.AWS, account_id=candidate.account_id),
                    region=candidate.region_id,
                    namespace=AGENT_NAMESPACE,
                    metric_name=MEMORY,
                    dimensions={"InstanceId": candidate.resource_id},
                    statistic="Maximum",
                )
                for candidate in candidates
            ],
            window_start,
            window_end,
        )

        written = 0
        unobserved = 0
        seen_groups: set[str] = set()

        for candidate in candidates:
            points = series.get(candidate.resource_id)
            if points is None:
                # Not zero. An instance publishing nothing may be perfectly busy.
                unobserved += 1
                continue

            # One recommendation per Auto Scaling group, per FEAT-026. Twenty rows
            # saying the same thing is how a screen gets ignored.
            if candidate.scaling_group is not None:
                if candidate.scaling_group in seen_groups:
                    continue
                seen_groups.add(candidate.scaling_group)

            values = [point.value for point in points]
            # Absent, not zero. An instance with no agent has no memory series, and
            # the judgement says so rather than assuming there is room.
            memory = series.get(f"{MEMORY_KEY}{candidate.resource_id}")
            peak = max((point.value for point in memory), default=None) if memory else None
            estimate = self._judge(candidate, values, peak)
            if estimate is None:
                continue
            self._write(context, candidate, estimate, thresholds, now)
            written += 1

        if unobserved:
            # Recorded rather than silent. An estate where half the instances
            # publish nothing is a configuration problem, and a run that reported
            # "no waste found" would hide it.
            context.connection.execute(
                UNOBSERVED_ERROR,
                {
                    "id": uuid4(),
                    "t": context.unit.tenant_id,
                    "c": COLLECTOR,
                    "s": SCOPE,
                    "d": f"{unobserved} resources published no metrics and were not judged",
                    "r": (
                        "Check that detailed monitoring is enabled for these resources. "
                        "Until it is they are neither judged nor reported as wasteful."
                    ),
                    "now": now,
                },
            )

        return CollectorOutcome(items_written=written)

    def _judge(
        self,
        candidate: Candidate,
        values: list[Decimal],
        memory_peak_percent: Decimal | None,
    ) -> Estimate | None:
        """Idle first, then oversized.

        An instance doing nothing is idle and the action is to turn it off. The
        rightsizing arithmetic would also report it, truthfully and uselessly:
        nobody shrinks a machine they could delete.

        The idle question does not consult memory, deliberately. An instance nobody
        is using is worth turning off whatever its memory footprint was, and a
        memory bound instance is not idle in the first place: its CPU is quiet and
        its p95 is not.
        """
        gone = idle(
            utilization_percent=values,
            observation_days=candidate.observation_days,
            monthly_cost=candidate.monthly_cost,
        )
        if gone.is_worth_acting_on:
            return gone

        smaller = rightsize_cpu(
            utilization_percent=values,
            observation_days=candidate.observation_days,
            monthly_cost=candidate.monthly_cost,
            credit_balance=candidate.credit_balance,
            memory_peak_percent=memory_peak_percent,
        )
        return smaller if smaller.is_worth_acting_on else None

    def _write(
        self,
        context: CollectorContext,
        candidate: Candidate,
        estimate: Estimate,
        thresholds: Any,
        now: datetime,
    ) -> None:
        target = candidate.scaling_group or candidate.resource_id
        reference = f"meter:{target}:{estimate.waste_class.value}"
        context.connection.execute(
            WRITE,
            {
                "id": uuid4(),
                "tenant": context.unit.tenant_id,
                "account": candidate.account_id,
                "source": Source.METER.value,
                "reference": reference,
                "waste_class": estimate.waste_class.value,
                "resource": target,
                "region": candidate.region_id,
                "saving": estimate.monthly_saving,
                "confidence": confidence_of(candidate.observation_days).value,
                "severity": severity_for(estimate.monthly_saving, thresholds),
                "days": candidate.observation_days,
                "rationale": estimate.reason,
                "now": now,
            },
        )
        context.connection.execute(
            FIRST_EVENT,
            {
                "id": uuid4(),
                "tenant": context.unit.tenant_id,
                "source": Source.METER.value,
                "reference": reference,
                "actor": f"collector:{COLLECTOR}",
                "now": now,
            },
        )
