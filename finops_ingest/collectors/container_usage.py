"""Clusters and reservations for one account in one region.

Account scoped, like the quota collector and for the same reason: a cluster lives in
an account, so one unit is one account and one region. That is also what gives
partial failure for free, per constraint 5. The worker runs each unit in its own
transaction and catches only `CollectionError`, so one account whose clusters cannot
be read records a typed failure against its own scope while the others still land.
Nothing here needs to catch anything for that to be true, and an `except Exception`
here would turn an unknown bug into a permanently quiet one.

**A cluster that could not be measured is written, not skipped.** Cluster rows are
written whatever the reservation read produced, because a cluster with no readable
workloads has no usage rows at all and skipping it would leave it absent from the
product rather than listed as unmeasurable. That is the whole reason
`container_cluster` is a separate table.

**Retraction keys on the run, never on a timestamp.** Two runs inside one second are
indistinguishable by clock and the run id is exact. The writes happen before the
retraction, so a read that failed part way raises before anything is removed.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.containers import ClusterSlice, OomStatus, ReservationVsUse
from finops_core.domain.waste import Source, confidence_of
from finops_core.errors import SchemaDrift
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.containers import KIND, ContainerSizing, is_sized_here, size_workload
from finops_query.severity import DEFAULT_THRESHOLDS, Thresholds, severity_for, thresholds_from

COLLECTOR = "container_usage"

WRITE_CLUSTER = text(
    "INSERT INTO container_cluster (cluster_row_id, tenant_id, ingest_run_id, "
    "sub_account_id, region_id, cluster_name, platform, enhanced_observability, "
    "request_unavailable_reason, node_count, spot_ratio, packing_efficiency, as_of, "
    "collected_at) VALUES (:pk, :tenant, :run, :account, :region, :cluster, :platform, "
    ":enhanced, :reason, :nodes, :spot, :packing, :as_of, :collected_at) "
    "ON CONFLICT (tenant_id, sub_account_id, region_id, cluster_name) DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, platform = EXCLUDED.platform, "
    "enhanced_observability = EXCLUDED.enhanced_observability, "
    "request_unavailable_reason = EXCLUDED.request_unavailable_reason, "
    "node_count = EXCLUDED.node_count, spot_ratio = EXCLUDED.spot_ratio, "
    "packing_efficiency = EXCLUDED.packing_efficiency, as_of = EXCLUDED.as_of, "
    "collected_at = EXCLUDED.collected_at"
)

WRITE_USAGE = text(
    "INSERT INTO container_usage (usage_row_id, tenant_id, ingest_run_id, "
    "sub_account_id, region_id, cluster_name, namespace, workload, workload_kind, "
    "launch_type, cpu_requested_millicores, cpu_used_p99_millicores, "
    "memory_requested_mib, memory_used_peak_mib, was_oom_killed, observation_days, "
    "as_of, collected_at) VALUES (:pk, :tenant, :run, :account, :region, :cluster, "
    ":namespace, :workload, :kind, :launch, :cpu_req, :cpu_used, :mem_req, :mem_used, "
    ":oom, :days, :as_of, :collected_at) "
    "ON CONFLICT (tenant_id, sub_account_id, region_id, cluster_name, namespace, workload) "
    "DO UPDATE SET ingest_run_id = EXCLUDED.ingest_run_id, "
    "workload_kind = EXCLUDED.workload_kind, launch_type = EXCLUDED.launch_type, "
    "cpu_requested_millicores = EXCLUDED.cpu_requested_millicores, "
    "cpu_used_p99_millicores = EXCLUDED.cpu_used_p99_millicores, "
    "memory_requested_mib = EXCLUDED.memory_requested_mib, "
    "memory_used_peak_mib = EXCLUDED.memory_used_peak_mib, "
    "was_oom_killed = EXCLUDED.was_oom_killed, "
    "observation_days = EXCLUDED.observation_days, as_of = EXCLUDED.as_of, "
    "collected_at = EXCLUDED.collected_at"
)

#: Rows this slice no longer reports. Keyed on the run and never on a timestamp,
#: because two runs inside one second cannot be told apart by a clock. Scoped to the
#: unit's own account and region, so a run for one slice cannot remove another's
#: rows: the quota collector had to be fixed for exactly that, where a regional run
#: wiped the rows a previous region had written.
RETRACT_USAGE = text(
    "DELETE FROM container_usage WHERE tenant_id = :tenant "
    "AND sub_account_id = :account AND region_id = :region AND ingest_run_id <> :run"
)

RETRACT_CLUSTERS = text(
    "DELETE FROM container_cluster WHERE tenant_id = :tenant "
    "AND sub_account_id = :account AND region_id = :region AND ingest_run_id <> :run"
)


#: How far back a workload's cost is summed to state a monthly figure. Thirty days of
#: measured split cost, so the saving is a share of money the bill actually shows.
COST_WINDOW_DAYS = 30

#: A workload's measured cost over the window. Not coalesced: a sum over no rows is
#: null, which is how "no cost is attributed" stays distinct from a cost of zero.
WORKLOAD_COST = text(
    "SELECT SUM(split_cost) FROM cost_focus_daily WHERE tenant_id = :tenant "
    "AND sub_account_id = :account AND eks_cluster_name = :cluster "
    "AND eks_namespace = :namespace AND eks_workload_name = :workload "
    "AND charge_period_start >= :since"
)

#: Into P3's table, with P3's statement shape. There is no second recommendation table,
#: and the lifecycle clause is P3's too: the source owns the money, Meter owns the
#: lifecycle, so a recommendation somebody accepted is not reopened by the next run.
WRITE_RECOMMENDATION = text(
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

#: The birth event, once. The table allows exactly one null `from_lifecycle` per
#: recommendation, so this is guarded rather than written every run.
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

#: Examined and declined, FEAT-062. Never a zero saving in the recommendation list,
#: where it would rank as the least valuable action rather than the absence of one.
WRITE_REFUSAL = text(
    "INSERT INTO sizing_refusal (refusal_id, tenant_id, ingest_run_id, sub_account_id, "
    "region_id, resource_id, waste_class, reason, observation_days, as_of, collected_at) "
    "VALUES (:id, :tenant, :run, :account, :region, :resource, :waste_class, :reason, "
    ":days, :now, :now) "
    "ON CONFLICT (tenant_id, resource_id, waste_class) DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, reason = EXCLUDED.reason, "
    "observation_days = EXCLUDED.observation_days, as_of = EXCLUDED.as_of, "
    "collected_at = EXCLUDED.collected_at"
)


def _system_clock() -> datetime:
    return datetime.now(UTC)


Clock = Callable[[], datetime]


def _oom_column(status: OomStatus) -> bool | None:
    """The three member enum as the nullable column holds it.

    Null for unobserved, which is the only mapping that keeps that apart from not
    killed. The reverse direction is `OomStatus.from_observation`, so both halves of
    the translation are one line each and each sits beside its own reasoning.
    """
    if status is OomStatus.UNOBSERVED:
        return None
    return status is OomStatus.KILLED


class ContainerUsageCollector:
    """Clusters and reservations for one account in one region."""

    def __init__(self, source: Any, clock: Clock = _system_clock) -> None:
        self._source = source
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        if context.run_id is None:
            # Not a typed collection failure. Nothing about the provider is wrong,
            # the caller assembled the context incorrectly, and a collection error
            # here would be recorded against the scope and send somebody to AWS.
            raise ValueError(
                "container_usage needs the run id from the ledger's claim. Rows carry "
                "it in a NOT NULL column and the retraction deletes on it."
            )

        unit = context.unit
        if unit.account is None or unit.region is None:
            raise SchemaDrift(
                scope_key=unit.scope_key,
                collector=COLLECTOR,
                detail="a container unit arrived without an account or a region",
            )

        account = unit.account
        region = str(unit.region)
        clusters = tuple(self._source.list_clusters(account, region))
        reservations = tuple(self._source.reservations(account, region))

        written = 0
        for cluster in clusters:
            self._write_cluster(context, cluster, account.account_id, region)
            written += 1
        for reservation in reservations:
            self._write_usage(context, reservation, account.account_id, region)
            written += 1

        # Sized after the slice is written, from the reservations already in hand. EC2
        # backed workloads only: a Fargate task is sized by the matrix in TASK-P6-008,
        # because only certain task sizes can be ordered.
        thresholds = (
            thresholds_from(context.settings)
            if context.settings is not None
            else DEFAULT_THRESHOLDS
        )
        now = self._clock()
        for reservation in reservations:
            if not is_sized_here(reservation):
                continue
            cost = self._monthly_cost(context, reservation, account.account_id, now)
            sizing = size_workload(reservation=reservation, monthly_cost=cost)
            if sizing.estimate.is_worth_acting_on:
                self._write_recommendation(
                    context, reservation, sizing, account.account_id, region, thresholds, now
                )
                written += 1
            else:
                # Not counted. A refusal is not an item for anybody's queue, and counting
                # it would inflate a number a reader takes as findings.
                self._write_refusal(context, reservation, sizing, account.account_id, region, now)

        removed = self._retract(context, account.account_id, region)
        return CollectorOutcome(items_written=written, items_removed=max(removed, 0))

    def _write_cluster(
        self, context: CollectorContext, cluster: ClusterSlice, account: str, region: str
    ) -> None:
        context.connection.execute(
            WRITE_CLUSTER,
            {
                "pk": uuid4(),
                "tenant": context.unit.tenant_id,
                "run": context.run_id,
                "account": account,
                "region": region,
                "cluster": cluster.cluster_name,
                "platform": cluster.platform,
                "enhanced": cluster.enhanced_observability,
                "reason": cluster.unmeasurable_reason,
                "nodes": cluster.node_count,
                "spot": cluster.spot_ratio,
                "packing": cluster.packing_efficiency,
                "as_of": cluster.as_of,
                "collected_at": cluster.collected_at,
            },
        )

    def _write_usage(
        self,
        context: CollectorContext,
        reservation: ReservationVsUse,
        account: str,
        region: str,
    ) -> None:
        workload = reservation.workload
        context.connection.execute(
            WRITE_USAGE,
            {
                "pk": uuid4(),
                "tenant": context.unit.tenant_id,
                "run": context.run_id,
                "account": account,
                "region": region,
                "cluster": workload.cluster_name,
                "namespace": workload.namespace,
                "workload": workload.name,
                "kind": workload.kind,
                "launch": workload.launch_type.value,
                "cpu_req": reservation.cpu_requested_millicores,
                "cpu_used": reservation.cpu_used_p99_millicores,
                "mem_req": reservation.memory_requested_mib,
                "mem_used": reservation.memory_used_peak_mib,
                # Null for unobserved. The one place the enum becomes a column.
                "oom": _oom_column(reservation.oom_status),
                "days": reservation.observation_days,
                "as_of": reservation.as_of,
                "collected_at": reservation.collected_at,
            },
        )

    def _monthly_cost(
        self,
        context: CollectorContext,
        reservation: ReservationVsUse,
        account: str,
        now: datetime,
    ) -> Decimal | None:
        """The workload's measured split cost over the window, or None if it has none.

        None rather than zero, because a sum over no rows is the absence of a figure: the
        export carries no split cost allocation, ISS-003, or the cost collector has not
        run yet. Either way the honest outcome is a refusal naming the gap, and a zero
        here would instead refuse it as a workload too cheap to bother with.
        """
        workload = reservation.workload
        value = context.connection.execute(
            WORKLOAD_COST,
            {
                "tenant": context.unit.tenant_id,
                "account": account,
                "cluster": workload.cluster_name,
                "namespace": workload.namespace,
                "workload": workload.name,
                "since": now - timedelta(days=COST_WINDOW_DAYS),
            },
        ).scalar_one()
        return None if value is None else Decimal(value)

    def _write_recommendation(
        self,
        context: CollectorContext,
        reservation: ReservationVsUse,
        sizing: ContainerSizing,
        account: str,
        region: str,
        thresholds: Thresholds,
        now: datetime,
    ) -> None:
        workload = reservation.workload
        reference = f"meter:{workload.key}:{KIND.value}"
        saving = sizing.estimate.monthly_saving
        context.connection.execute(
            WRITE_RECOMMENDATION,
            {
                "id": uuid4(),
                "tenant": context.unit.tenant_id,
                "account": account,
                "source": Source.METER.value,
                "reference": reference,
                "waste_class": KIND.value,
                "resource": workload.key,
                "region": region,
                "saving": saving,
                # Confidence from the history and severity from the money, never one
                # from the other. ADR-0016.
                "confidence": confidence_of(reservation.observation_days).value,
                "severity": severity_for(saving, thresholds),
                "days": reservation.observation_days,
                "rationale": sizing.estimate.reason,
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

    def _write_refusal(
        self,
        context: CollectorContext,
        reservation: ReservationVsUse,
        sizing: ContainerSizing,
        account: str,
        region: str,
        now: datetime,
    ) -> None:
        context.connection.execute(
            WRITE_REFUSAL,
            {
                "id": uuid4(),
                "tenant": context.unit.tenant_id,
                "run": context.run_id,
                "account": account,
                "region": region,
                "resource": reservation.workload.key,
                "waste_class": KIND.value,
                "reason": sizing.estimate.reason,
                "days": reservation.observation_days,
                "now": now,
            },
        )

    def _retract(self, context: CollectorContext, account: str, region: str) -> int:
        """Remove what this slice no longer reports, in this slice only."""
        params = {
            "tenant": context.unit.tenant_id,
            "account": account,
            "region": region,
            "run": context.run_id,
        }
        usage = context.connection.execute(RETRACT_USAGE, params).rowcount
        clusters = context.connection.execute(RETRACT_CLUSTERS, params).rowcount
        return int(usage or 0) + int(clusters or 0)
