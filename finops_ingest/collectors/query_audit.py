"""The six hourly survey of every saved query, and what each one costs.

One unit, organization scope. It walks every instance the surface can see,
writes what it found, and prices it.

Three behaviours here are the reason the collector exists rather than a script.

**An instance it could not read does not fail the run.** It is written with
`reachable` false and its typed cause, so the interface can list it and state
the exclusion. A run that aborted on the first unreadable workspace would report
nothing about the nine it could read, and a run that skipped it silently would
report a smaller estate as if it were the whole one.

**It is idempotent.** Three runs in one day leave one `query_finding` per query
per day, because the write is an upsert keyed on the day. A collector that
appended would triple every cost on the front page by dinner time.

**Every figure it writes is modelled and says so.** `measured_runs` stays null
until TASK-P2-013 lands the overlay, and the schema refuses a modelled row that
claims otherwise.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.query import QueryDefinition, QueryOrigin, SurfaceInstance
from finops_core.errors import CollectionError
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.classify import (
    LOGS_INSIGHTS,
    METRIC_SEARCH,
    METRICS_INSIGHTS,
    PROMETHEUS,
    Classification,
)
from finops_query.cost_model import ALERT, PANEL, IngestRate, Rates, price, runs_per_day
from finops_query.policy import query_key

COLLECTOR = "query_audit"

Clock = Callable[[], datetime]

#: The engine names the database accepts, from the P2 spec section 5. An engine
#: this project has never heard of is stored as OTHER and priced at zero rather
#: than dropped, per ISS-133: a query nobody can price still costs money and
#: still belongs in the list.
_ENGINE_COLUMN: dict[str, str] = {
    LOGS_INSIGHTS: "LOGS_INSIGHTS",
    METRIC_SEARCH: "METRIC_SEARCH",
    METRICS_INSIGHTS: "METRIC_INSIGHTS",
    PROMETHEUS: "PROMQL",
}

#: How a `SurfaceKind` is written down. The column vocabulary predates the enum
#: and both are closed, so the mapping is explicit rather than a string slice.
_KIND_COLUMN: dict[str, str] = {
    "managed_grafana": "AMG",
    "self_hosted_grafana": "SELF_HOSTED",
    "grafana_cloud": "CLOUD",
}


def _system_clock() -> datetime:
    return datetime.now(UTC)


class QueryAuditCollector:
    """Surveys every instance, writes its definitions, and prices them."""

    def __init__(
        self,
        surface: Any,
        rates: Rates,
        ingest_rate: IngestRate,
        clock: Clock = _system_clock,
    ) -> None:
        self._surface = surface
        self._rates = rates
        self._ingest_rate = ingest_rate
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        tenant_id = context.unit.tenant_id
        now = self._clock()
        written = 0

        for instance in self._surface.discover():
            instance_pk = self._write_instance(context, tenant_id, instance, now)
            written += 1
            if not instance.reachable:
                # Already recorded as unreachable with its cause. Reading it
                # would raise, and the run continues without it.
                continue
            try:
                definitions = tuple(self._surface.list_queries(instance))
            except CollectionError as failure:
                # One workspace we could not read is not a failed run. It is a
                # stated exclusion, which is the only honest way to report a
                # total drawn from part of an estate.
                self._mark_unreadable(context, instance_pk, failure, now)
                continue
            for definition in definitions:
                written += self._write_definition(context, tenant_id, instance_pk, definition, now)

        return CollectorOutcome(items_written=written)

    # -- instances ---------------------------------------------------------

    def _write_instance(
        self,
        context: CollectorContext,
        tenant_id: Any,
        instance: SurfaceInstance,
        now: datetime,
    ) -> Any:
        row = context.connection.execute(
            text(
                "INSERT INTO grafana_instance (instance_id, tenant_id, kind, name, endpoint, "
                "account_id, region_id, reachable, unreachable_reason, as_of, collected_at) "
                "VALUES (:id, :tenant, :kind, :name, :endpoint, :account, :region, "
                ":reachable, :reason, :now, :now) "
                "ON CONFLICT (tenant_id, endpoint) DO UPDATE SET "
                "name = EXCLUDED.name, kind = EXCLUDED.kind, reachable = EXCLUDED.reachable, "
                "unreachable_reason = EXCLUDED.unreachable_reason, as_of = EXCLUDED.as_of, "
                "collected_at = EXCLUDED.collected_at "
                "RETURNING instance_id"
            ),
            {
                "id": uuid4(),
                "tenant": tenant_id,
                "kind": _KIND_COLUMN.get(str(instance.kind), "CLOUD"),
                "name": instance.name,
                "endpoint": instance.location,
                # AMG rows carry their location and the others must not pretend
                # to, which the table enforces.
                "account": self._account_of(instance),
                "region": self._region_of(instance),
                "reachable": instance.reachable,
                "reason": instance.unreachable_cause,
                "now": now,
            },
        ).one()
        return row[0]

    @staticmethod
    def _account_of(instance: SurfaceInstance) -> str | None:
        if _KIND_COLUMN.get(str(instance.kind)) != "AMG":
            return None
        # A synthetic instance for a region that could not be listed carries
        # `aws:account:region` as its identifier, which is where the pair lives.
        parts = instance.surface_id.split(":")
        return parts[1] if len(parts) == 3 else instance.surface_id

    @staticmethod
    def _region_of(instance: SurfaceInstance) -> str | None:
        if _KIND_COLUMN.get(str(instance.kind)) != "AMG":
            return None
        parts = instance.surface_id.split(":")
        return parts[2] if len(parts) == 3 else instance.location

    def _mark_unreadable(
        self, context: CollectorContext, instance_pk: Any, failure: CollectionError, now: datetime
    ) -> None:
        context.connection.execute(
            text(
                "UPDATE grafana_instance SET reachable = false, unreachable_reason = :reason, "
                "collected_at = :now WHERE instance_id = :id"
            ),
            {"reason": type(failure).__name__, "now": now, "id": instance_pk},
        )

    # -- definitions and findings -----------------------------------------

    def _write_definition(
        self,
        context: CollectorContext,
        tenant_id: Any,
        instance_pk: Any,
        definition: QueryDefinition,
        now: datetime,
    ) -> int:
        origin = "ALERT_RULE" if definition.origin is QueryOrigin.ALERT else "PANEL"
        query_pk = context.connection.execute(
            text(
                "INSERT INTO query_definition (query_id, tenant_id, instance_id, origin, "
                "dashboard_uid, dashboard_title, folder_uid, panel_id, ref_id, engine, "
                "query_text, fingerprint, query_key, target, refresh_seconds, range_seconds, "
                "last_editor, as_of, collected_at) VALUES (:id, :tenant, :instance, :origin, "
                ":uid, :title, NULL, :panel, :ref, :engine, :query_text, :fp, :qkey, "
                "CAST(:target AS JSONB), :refresh, :range, :editor, :as_of, :now) "
                "ON CONFLICT (tenant_id, instance_id, fingerprint) DO UPDATE SET "
                "query_text = EXCLUDED.query_text, query_key = EXCLUDED.query_key, "
                "dashboard_title = EXCLUDED.dashboard_title, "
                "panel_id = EXCLUDED.panel_id, refresh_seconds = EXCLUDED.refresh_seconds, "
                "range_seconds = EXCLUDED.range_seconds, last_editor = EXCLUDED.last_editor, "
                "as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at "
                "RETURNING query_id"
            ),
            {
                "id": uuid4(),
                "tenant": tenant_id,
                "instance": instance_pk,
                "origin": origin,
                "uid": definition.container_id or None,
                "title": definition.container or None,
                "panel": definition.element or None,
                "ref": definition.ref_id or None,
                "engine": _ENGINE_COLUMN.get(definition.engine, "OTHER"),
                "query_text": definition.query,
                "fp": definition.fingerprint,
                "qkey": query_key(definition.engine, definition.query, definition.targets),
                "target": _targets_json(definition),
                # An alert rule runs on its own schedule, and the table refuses a
                # panel that has no refresh.
                "refresh": None if origin == "ALERT_RULE" else definition.refresh_seconds,
                # An absolute range is an unknown window rather than a zero one,
                # but the column is NOT NULL, so an unknown is written as zero
                # and the cost model is given None so it does not price it.
                "range": definition.window_seconds or 0,
                "editor": definition.last_run_by,
                "as_of": definition.as_of,
                "now": now,
            },
        ).one()[0]

        self._write_finding(context, tenant_id, query_pk, definition, now)
        return 2

    def _write_finding(
        self,
        context: CollectorContext,
        tenant_id: Any,
        query_pk: Any,
        definition: QueryDefinition,
        now: datetime,
    ) -> None:
        origin = ALERT if definition.origin is QueryOrigin.ALERT else PANEL
        classification = Classification(
            engine=definition.engine,
            query=definition.query,
            region=definition.region,
            log_groups=definition.targets,
        )
        per_day = runs_per_day(
            definition.refresh_seconds,
            origin,
            self._rates,
            alert_interval_seconds=definition.refresh_seconds or None,
        )
        cost = price(
            classification,
            origin,
            definition.refresh_seconds,
            definition.window_seconds,
            per_day,
            self._rates,
            self._ingest_rate,
            definition.region or "",
        )
        context.connection.execute(
            text(
                "INSERT INTO query_finding (finding_id, tenant_id, query_id, run_date, "
                "runs_per_day, scan_bytes_per_run, cost_month_usd, provenance, measured_runs, "
                "severity, why, as_of, collected_at) VALUES (:id, :tenant, :query, :day, "
                ":per_day, :scan, :cost, 'modelled', NULL, :severity, :why, :as_of, :now) "
                "ON CONFLICT (tenant_id, query_id, run_date) DO UPDATE SET "
                "runs_per_day = EXCLUDED.runs_per_day, "
                "scan_bytes_per_run = EXCLUDED.scan_bytes_per_run, "
                "cost_month_usd = EXCLUDED.cost_month_usd, severity = EXCLUDED.severity, "
                "why = EXCLUDED.why, as_of = EXCLUDED.as_of, "
                "collected_at = EXCLUDED.collected_at"
            ),
            {
                "id": uuid4(),
                "tenant": tenant_id,
                "query": query_pk,
                "day": now.date(),
                "per_day": round(per_day, 2),
                "scan": int(cost.bytes_per_run),
                "cost": cost.cost_month,
                "severity": cost.risk_level,
                # The prose that makes a finding actionable rather than a number.
                "why": " ".join(cost.why) or "No cost driver identified.",
                "as_of": definition.as_of,
                "now": now,
            },
        )


def _targets_json(definition: QueryDefinition) -> str:
    import json

    return json.dumps({"targets": list(definition.targets), "region": definition.region})
