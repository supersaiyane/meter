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

from collections.abc import Callable, Mapping
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
from finops_query.ownership import (
    Measurement,
    measure_logs_query,
    measure_metric_query,
    resolve_owner,
)
from finops_query.policy import normalise, query_key

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


def rates_from(settings: Any) -> Rates:
    """Build the model's rates from configuration.

    The cost model deliberately knows nothing about `Settings`, so that the
    arithmetic has no opinion about where a number came from. Something still
    has to do the binding, and this is the layer that wires the collector, so it
    happens here rather than there.

    Every one of these is an assumption a modelled figure rests on, which is why
    they are configuration and why the figure carries the assumption with it.
    """
    return Rates(
        logs_scan_price_per_gb=float(settings.query_logs_scan_price_per_gb),
        metrics_price_per_1000=float(settings.query_metrics_price_per_1000),
        manual_loads_per_day=settings.query_manual_loads_per_day,
        viewing_hours_per_day=settings.query_viewing_hours_per_day,
        metrics_per_call=settings.query_metrics_per_call,
        default_ingest_gb_per_day=settings.query_default_ingest_gb_per_day,
        assumed_query_seconds=settings.query_assumed_query_seconds,
        refresh_warn_seconds=settings.query_refresh_warn_seconds,
        refresh_crit_seconds=settings.query_refresh_crit_seconds,
        timerange_warn_hours=settings.query_timerange_warn_hours,
        timerange_crit_hours=settings.query_timerange_crit_hours,
        quota_logs_concurrent=settings.query_quota_logs_concurrent,
        quota_getmetricdata_tps=settings.query_quota_getmetricdata_tps,
    )


#: `IngestRate` is per hour, because `_logs_insights_cost` multiplies it by a
#: window measured in hours. The setting is per day. Getting this conversion
#: wrong overstates every Logs Insights figure by exactly 24, which is large
#: enough to be obvious in a total and small enough to look like a bad dashboard.
HOURS_PER_DAY = 24.0


def default_ingest_rate(settings: Any) -> IngestRate:
    """The fallback used when ingestion cannot be measured for a log group.

    A Logs Insights scan estimate is this multiplied by the window, so it is the
    assumption the whole Logs Insights cost rests on. TASK-P2-013 replaces it
    with a measurement where one exists.

    Returns GB per hour. The setting is GB per day, and the division is the
    whole point of this function existing rather than passing the setting
    straight through.
    """
    per_hour = float(settings.query_default_ingest_gb_per_day) / HOURS_PER_DAY

    def rate(_account: str, _region: str) -> float:
        return per_hour

    return rate


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
        evidence: Any = None,
        lookback_days: int = 30,
    ) -> None:
        self._surface = surface
        # Optional. Without it every figure stays modelled, which is a normal
        # state and not a degraded one: FEAT-013 upgrades findings, it does not
        # gate them.
        self._evidence = evidence
        self._lookback_days = lookback_days
        self._rates = rates
        self._ingest_rate = ingest_rate
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        tenant_id = context.unit.tenant_id
        now = self._clock()
        written = 0
        instances = tuple(self._surface.discover())
        # Once per run, not once per instance. CloudTrail records an execution
        # against the account it ran in, not against the tool that issued it, so
        # a self hosted Grafana querying CloudWatch appears in the same trail as
        # a managed one. Asking per instance would fetch the same window
        # repeatedly and would answer nothing for an instance that carries no
        # account of its own.
        observed = self._observations(instances)

        for instance in instances:
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
            folder_map = self._folder_map(context, tenant_id, instance_pk)
            for definition in definitions:
                written += self._write_definition(
                    context, tenant_id, instance_pk, definition, now, observed, folder_map
                )

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

    # -- ownership ---------------------------------------------------------

    @staticmethod
    def _folder_map(context: CollectorContext, tenant_id: Any, instance_pk: Any) -> dict[str, str]:
        """Folder to owner, as a person entered it.

        Read per instance rather than joined per finding, because it is small,
        it is the highest priority source, and a join would make the ownership
        of a finding depend on the order rows came back in.
        """
        rows = context.connection.execute(
            text(
                "SELECT folder_uid, owner_email FROM folder_team_map "
                "WHERE tenant_id = :tenant AND instance_id = :instance"
            ),
            {"tenant": tenant_id, "instance": instance_pk},
        ).all()
        return {str(folder): str(email) for folder, email in rows}

    # -- evidence ----------------------------------------------------------

    def _observations(self, instances: tuple[SurfaceInstance, ...]) -> Mapping[str, Any] | None:
        """What this estate's account was seen executing, or None.

        None means unobserved, and every finding then stays modelled. It never
        means zero runs: a query nobody watched is not a query nobody ran, and
        writing zero would turn an absence of evidence into a claim about the
        world.
        """
        if self._evidence is None:
            return None
        # The account and region of the first instance that names one. A run
        # covers one account, and an instance that carries no account of its own
        # still queries CloudWatch inside it.
        account_id = next((a for a in (self._account_of(i) for i in instances) if a), "")
        region = next((r for r in (self._region_of(i) for i in instances) if r), "")
        try:
            bundle: Mapping[str, Any] = self._evidence.observations(
                account_id=account_id,
                region=region,
                lookback_days=self._lookback_days,
            )
            return bundle
        except CollectionError:
            # Evidence that could not be read leaves the figures modelled. It
            # does not fail the run, because a modelled estate is still worth
            # reporting and an aborted one is not.
            return None

    def _measure(
        self, definition: QueryDefinition, observed: Mapping[str, Any] | None, modelled_bytes: float
    ) -> Measurement | None:
        """The observed figure for one definition, or None if nothing saw it."""
        if observed is None:
            return None
        if definition.engine == LOGS_INSIGHTS:
            return measure_logs_query(
                definition.query,
                modelled_bytes,
                dict(observed),
                self._rates.logs_scan_price_per_gb,
            )
        if definition.engine in (METRIC_SEARCH, METRICS_INSIGHTS):
            # A metric panel names its namespace in targets, and CloudTrail
            # identifies GetMetricData by account and region rather than by
            # panel, which is why this attribution is the weakest here.
            namespace = definition.targets[0] if definition.targets else ""
            return measure_metric_query(
                namespace,
                definition.element,
                dict(observed),
                self._rates.metrics_per_call,
                self._rates.metrics_price_per_1000,
            )
        return None

    # -- definitions and findings -----------------------------------------

    def _write_definition(
        self,
        context: CollectorContext,
        tenant_id: Any,
        instance_pk: Any,
        definition: QueryDefinition,
        now: datetime,
        observed: Mapping[str, Any] | None = None,
        folder_map: Mapping[str, str] | None = None,
    ) -> int:
        origin = "ALERT_RULE" if definition.origin is QueryOrigin.ALERT else "PANEL"
        query_pk = context.connection.execute(
            text(
                "INSERT INTO query_definition (query_id, tenant_id, instance_id, origin, "
                "dashboard_uid, dashboard_title, folder_uid, panel_id, ref_id, engine, "
                "query_text, fingerprint, query_key, target, refresh_seconds, range_seconds, "
                "last_editor, as_of, collected_at) VALUES (:id, :tenant, :instance, :origin, "
                ":uid, :title, :folder, :panel, :ref, :engine, :query_text, :fp, :qkey, "
                "CAST(:target AS JSONB), :refresh, :range, :editor, :as_of, :now) "
                "ON CONFLICT (tenant_id, instance_id, fingerprint) DO UPDATE SET "
                "query_text = EXCLUDED.query_text, query_key = EXCLUDED.query_key, "
                "dashboard_title = EXCLUDED.dashboard_title, folder_uid = EXCLUDED.folder_uid, "
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
                "folder": definition.folder_uid or None,
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

        self._write_finding(context, tenant_id, query_pk, definition, now, observed, folder_map)
        return 2

    def _write_finding(
        self,
        context: CollectorContext,
        tenant_id: Any,
        query_pk: Any,
        definition: QueryDefinition,
        now: datetime,
        observed: Mapping[str, Any] | None = None,
        folder_map: Mapping[str, str] | None = None,
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

        # The overlay. A measurement replaces the modelled run count, the cost,
        # and where query history carried them the scanned bytes as well. Absent
        # evidence leaves every one of them alone.
        measured = self._measure(definition, observed, cost.bytes_per_run)
        provenance = "measured" if measured else "modelled"
        runs = measured.runs_per_day if measured else per_day
        cost_month = measured.cost_month if measured else cost.cost_month
        scan_bytes = measured.bytes_per_run if measured else cost.bytes_per_run
        # NULL for a modelled row and a count for a measured one. The schema
        # refuses either half on its own, which is what stops a figure claiming
        # a provenance it does not have.
        measured_runs = measured.runs_total if measured else None

        # Folder map, then last editor, then whoever CloudTrail saw run it. No
        # default: a wrongly assigned owner is ignored by the person it reaches
        # and never reaches the person who could act.
        principals = (observed or {}).get("principal_by_query") or {}
        owner = resolve_owner(
            folder_uid=definition.folder_uid,
            folder_map=folder_map or {},
            last_editor=definition.last_run_by,
            principal=principals.get(normalise(definition.query)),
        )
        why = " ".join(cost.why) or "No cost driver identified."
        if measured:
            # The reason says which grade of measurement this is: runs and bytes
            # observed, or runs observed with bytes still modelled. A reader who
            # cannot tell those apart treats both as an estimate.
            why = f"{measured.reason} {why}".strip()
        context.connection.execute(
            text(
                "INSERT INTO query_finding (finding_id, tenant_id, query_id, run_date, "
                "runs_per_day, scan_bytes_per_run, cost_month_usd, provenance, measured_runs, "
                "severity, owner_email, owner_source, why, as_of, collected_at) "
                "VALUES (:id, :tenant, :query, :day, "
                ":per_day, :scan, :cost, :provenance, :measured_runs, :severity, "
                ":owner_email, :owner_source, :why, :as_of, :now) "
                "ON CONFLICT (tenant_id, query_id, run_date) DO UPDATE SET "
                "runs_per_day = EXCLUDED.runs_per_day, "
                "scan_bytes_per_run = EXCLUDED.scan_bytes_per_run, "
                "cost_month_usd = EXCLUDED.cost_month_usd, "
                "provenance = EXCLUDED.provenance, measured_runs = EXCLUDED.measured_runs, "
                "severity = EXCLUDED.severity, owner_email = EXCLUDED.owner_email, "
                "owner_source = EXCLUDED.owner_source, "
                "why = EXCLUDED.why, as_of = EXCLUDED.as_of, "
                "collected_at = EXCLUDED.collected_at"
            ),
            {
                "id": uuid4(),
                "tenant": tenant_id,
                "query": query_pk,
                "day": now.date(),
                "per_day": round(runs, 2),
                "scan": int(scan_bytes),
                "cost": cost_month,
                "provenance": provenance,
                "measured_runs": measured_runs,
                "severity": cost.risk_level,
                # Both together or neither. An owner with no source could not be
                # argued with, and a source with no owner says nothing.
                "owner_email": owner.email,
                "owner_source": owner.source,
                # The prose that makes a finding actionable rather than a number.
                "why": why,
                "as_of": definition.as_of,
                "now": now,
            },
        )


def _targets_json(definition: QueryDefinition) -> str:
    import json

    return json.dumps({"targets": list(definition.targets), "region": definition.region})
