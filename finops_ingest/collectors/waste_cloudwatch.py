"""The cheap wins in the service that bills for watching.

Two checks, and one deliberately missing.

**A log group with no retention policy keeps everything forever.** That is almost
never what anybody intended: it is the default, and the default is a decision
nobody made. The saving is the storage above a sensible retention, priced from the
region rather than from a constant.

**An alarm stuck in insufficient data is watching a metric that has gone.** For an
hour that is normal, and flagging it would teach a reader to skim. For a month it
is an alarm nobody will ever be woken by, giving false assurance that something is
covered.

**Unqueried log groups are not checked, and ISS-189 says why.** FEAT-027 asks for
high ingest groups with no queries in 90 days. P2 records which Logs Insights
queries ran and what they scanned, but not which log groups they named: the group
is inside the query text, and extracting it means parsing the query language for a
purpose the parser was not built for. Guessing would produce a recommendation to
delete logs somebody is reading, which is the most damaging output this whole
product could produce, so the check waits for a signal rather than an inference.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.waste import Source, WasteClass, confidence_of
from finops_core.errors import NoData
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.severity import severity_for, thresholds_from
from finops_query.waste import FLOOR_USD

COLLECTOR = "waste_cloudwatch"
SCOPE = "billing"

#: What a log group would be kept for if anybody had chosen. Thirty days covers
#: an incident review and a month end, which is what most groups are actually for.
#: It is the assumption the saving rests on and the rationale says so.
ASSUMED_RETENTION_DAYS = 30

#: An alarm in insufficient data for an hour is normal. For this long it is an
#: alarm nobody will be woken by, and the false assurance is the cost.
STALE_ALARM_DAYS = 30

BYTES_PER_GB = Decimal(1024**3)

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


WRITE = text(
    "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, source, "
    "source_reference, waste_class, resource_id, region_id, estimated_monthly_saving, "
    "confidence, severity, observation_days, lifecycle, owner, ticket_reference, "
    "rationale, as_of, collected_at) "
    "VALUES (:id, :tenant, :account, :source, :reference, :waste_class, :resource, :region, "
    ":saving, :confidence, :severity, :days, 'OPEN', NULL, NULL, :rationale, :now, :now) "
    "ON CONFLICT (tenant_id, source, source_reference) DO UPDATE SET "
    "estimated_monthly_saving = EXCLUDED.estimated_monthly_saving, "
    "confidence = EXCLUDED.confidence, severity = EXCLUDED.severity, "
    "observation_days = EXCLUDED.observation_days, rationale = EXCLUDED.rationale, "
    "as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at, "
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


class WasteCloudWatchCollector:
    """FEAT-027. The module with no instances to size."""

    def __init__(self, estate: Any, clock: Clock = _system_clock) -> None:
        self._estate = estate
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        if context.settings is None:
            raise ValueError(
                "waste_cloudwatch needs settings. Its severity boundaries are "
                "configuration, not constants."
            )
        now = self._clock()
        thresholds = thresholds_from(context.settings)
        written = 0
        written += self._retention(context, thresholds, now)
        written += self._alarms(context, thresholds, now)
        return CollectorOutcome(items_written=written)

    def _retention(self, context: CollectorContext, thresholds: Any, now: datetime) -> int:
        try:
            price = self._estate.storage_price_per_gb_month()
        except NoData:
            # A saving computed from an invented price is worse than no saving.
            # The check is skipped and the run continues with the alarms.
            return 0

        written = 0
        for group in self._estate.log_groups():
            if group.retention_days is not None:
                continue
            age_days = max((now - group.created_at).days, 0)
            if age_days <= ASSUMED_RETENTION_DAYS:
                # Nothing is being kept beyond the assumed retention yet, so
                # there is nothing to save by setting one.
                continue

            gigabytes = Decimal(group.stored_bytes) / BYTES_PER_GB
            # The fraction of what is stored that is older than the retention
            # nobody set. Straight line, which assumes an even ingest rate and
            # says so in the rationale.
            beyond = Decimal(age_days - ASSUMED_RETENTION_DAYS) / Decimal(age_days)
            saving = (gigabytes * beyond * price).quantize(Decimal("0.01"))
            if saving < FLOOR_USD:
                continue

            self._write(
                context,
                account=group.account_id,
                region=group.region_id,
                resource=group.name,
                waste_class=WasteClass.LOG_GROUP_NO_RETENTION,
                saving=saving,
                days=age_days,
                rationale=(
                    f"no retention policy, {gigabytes:.1f} GB stored over {age_days} days. "
                    f"At a {ASSUMED_RETENTION_DAYS} day retention roughly {beyond * 100:.0f} "
                    f"percent of it would expire, assuming an even ingest rate"
                ),
                thresholds=thresholds,
                now=now,
            )
            written += 1
        return written

    def _alarms(self, context: CollectorContext, thresholds: Any, now: datetime) -> int:
        written = 0
        cutoff = now - timedelta(days=STALE_ALARM_DAYS)
        for alarm in self._estate.alarms():
            if alarm.state != "INSUFFICIENT_DATA" or alarm.state_changed_at > cutoff:
                continue
            stale_days = max((now - alarm.state_changed_at).days, 0)
            self._write(
                context,
                account=alarm.account_id,
                region=alarm.region_id,
                resource=alarm.name,
                waste_class=WasteClass.ALARM_INSUFFICIENT_DATA,
                # Alarms are nearly free. The money is not the point of this
                # finding and the rationale says what is: an alarm nobody will be
                # woken by, giving false assurance that something is covered.
                saving=Decimal("0.00"),
                days=stale_days,
                rationale=(
                    f"in the insufficient data state for {stale_days} days. It is watching a "
                    "metric that no longer reports, so it will never fire and the coverage it "
                    "appears to give is not there"
                ),
                thresholds=thresholds,
                now=now,
            )
            written += 1
        return written

    def _write(
        self,
        context: CollectorContext,
        *,
        account: str,
        region: str,
        resource: str,
        waste_class: WasteClass,
        saving: Decimal,
        days: int,
        rationale: str,
        thresholds: Any,
        now: datetime,
    ) -> None:
        reference = f"meter:{resource}:{waste_class.value}"
        for statement in (WRITE, FIRST_EVENT):
            context.connection.execute(
                statement,
                {
                    "id": uuid4(),
                    "tenant": context.unit.tenant_id,
                    "account": account,
                    "source": Source.METER.value,
                    "reference": reference,
                    "waste_class": waste_class.value,
                    "resource": resource,
                    "region": region,
                    "saving": saving,
                    "confidence": confidence_of(days).value,
                    "severity": severity_for(saving, thresholds),
                    "days": days,
                    "rationale": rationale,
                    "actor": f"collector:{COLLECTOR}",
                    "now": now,
                },
            )
