"""What Meter publishes about itself, and deliberately nothing more.

`docs/10-OBSERVABILITY.md` names four SLOs and refuses a custom metric per
collector, because a metric nobody reads costs money per metric per month and
this product exists to point at exactly that kind of spend. So this module
publishes the smallest set the four SLOs and the ten alerts need, and every
metric here is named by an alarm in `infra/terraform/hub/observability.tf`.

Three of the four SLOs are measured by things AWS already emits: load balancer
latency, load balancer 5xx, and queue depth. Only SLO 1, collection freshness,
has no AWS equivalent, because it is a fact about the data rather than about the
service. It is the one this module exists for, and it is the one that catches
the failure specific to this product: a collector that stopped while the API
kept answering, cheerfully, with month old numbers.

Dimensions are bounded on purpose. A metric dimensioned by scope key would
create one metric per account per region per collector, which at three hundred
accounts is thousands of metrics and a bill that would appear on Meter's own
front page. The stalled count is dimensioned by collector only, and the scope
that is actually stalled is found in `sync_error`, which the runbook says to
read first.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from finops_core.constants import STALE_AFTER_CADENCE_MULTIPLE

#: The namespace the task role is allowed to write to, and nothing else. The
#: IAM policy carries the same string as a condition.
NAMESPACE = "Meter"

#: How far behind its cadence a scope has to be before it counts as stalled for
#: the alarm, as opposed to for the freshness screen. Three, where the screen
#: uses two, so the page fires strictly later than the screen turns amber.
#: Paging on the same threshold the screen shows would page for something an
#: operator can already see and is already looking at.
STALL_ALERT_CADENCE_MULTIPLE = 3

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Measurement:
    """One datum, ready for PutMetricData."""

    name: str
    value: float
    unit: str
    dimensions: dict[str, str]

    def as_datum(self, at: datetime) -> dict[str, Any]:
        return {
            "MetricName": self.name,
            "Value": self.value,
            "Unit": self.unit,
            "Timestamp": at,
            "Dimensions": [{"Name": k, "Value": v} for k, v in sorted(self.dimensions.items())],
        }


def stalled_scopes(
    connection: Any, multiple: int = STALL_ALERT_CADENCE_MULTIPLE
) -> tuple[Any, ...]:
    """Every collector and scope pair whose watermark has not advanced in time.

    Asked of the watermark rather than of the run ledger, deliberately. A run
    that succeeded while every account inside it returned AccessDenied is a
    successful run and a watermark that did not move, and this product's
    characteristic failure is exactly that: the machinery reporting health while
    the data stops. `docs/10-OBSERVABILITY.md` calls this SLO 1 and calls the
    other three ordinary.
    """
    return tuple(
        connection.execute(
            text(
                "SELECT s.collector, count(*) AS stalled, count(*) FILTER (WHERE true) AS total "
                "FROM collector_schedule s JOIN ingest_watermark w "
                "  ON w.tenant_id = s.tenant_id AND w.collector = s.collector "
                "WHERE s.is_enabled "
                "  AND EXTRACT(EPOCH FROM (now() - w.as_of)) > s.cadence_seconds * :multiple "
                "GROUP BY s.collector ORDER BY s.collector"
            ),
            {"multiple": multiple},
        ).mappings()
    )


def scope_totals(connection: Any) -> tuple[Any, ...]:
    """How many scopes each enabled collector has, stalled or not.

    The denominator for the widespread alarm. Counting it from the stalled set
    would always report one hundred percent stalled, which is ISS-016 in a
    different place: a fraction whose denominator comes from the numerator.
    """
    return tuple(
        connection.execute(
            text(
                "SELECT s.collector, count(*) AS total "
                "FROM collector_schedule s JOIN ingest_watermark w "
                "  ON w.tenant_id = s.tenant_id AND w.collector = s.collector "
                "WHERE s.is_enabled GROUP BY s.collector ORDER BY s.collector"
            )
        ).mappings()
    )


def freshness_measurements(connection: Any) -> tuple[Measurement, ...]:
    """The three SLO 1 metrics, from one pass over the watermarks.

    `StalledScopes` and `TotalScopes` are published even when the stalled count
    is zero. A metric that is only published when something is wrong cannot be
    alarmed on absence, and an alarm that never fires because the metric stopped
    arriving is the failure this whole module exists to prevent.
    """
    totals = {row["collector"]: int(row["total"]) for row in scope_totals(connection)}
    stalled = {row["collector"]: int(row["stalled"]) for row in stalled_scopes(connection)}

    measurements: list[Measurement] = []
    for collector, total in sorted(totals.items()):
        behind = stalled.get(collector, 0)
        dimensions = {"Collector": collector}
        measurements.append(Measurement("StalledScopes", float(behind), "Count", dimensions))
        measurements.append(Measurement("TotalScopes", float(total), "Count", dimensions))
        measurements.append(
            Measurement(
                "StalledScopePercent",
                0.0 if total == 0 else 100.0 * behind / total,
                "Percent",
                dimensions,
            )
        )
    return tuple(measurements)


def publish(
    cloudwatch: Any,
    measurements: Sequence[Measurement],
    clock: Clock = _system_clock,
    namespace: str = NAMESPACE,
) -> int:
    """Send the measurements. Returns how many were sent.

    PutMetricData takes at most a thousand data points per call, and the count
    here is three per enabled collector, so one call is always enough today. The
    batching is here anyway because the alternative is discovering the limit
    when a collector is added and metrics silently stop.
    """
    if not measurements:
        return 0

    at = clock()
    sent = 0
    batch_size = 1000
    for start in range(0, len(measurements), batch_size):
        batch = measurements[start : start + batch_size]
        cloudwatch.put_metric_data(
            Namespace=namespace,
            MetricData=[measurement.as_datum(at) for measurement in batch],
        )
        sent += len(batch)
    return sent


def screen_and_alert_thresholds() -> tuple[int, int]:
    """The two multiples, returned together so a test can hold them apart.

    The screen turns amber at two cadences and the page fires at three. If these
    ever became equal, an operator would be paged for something already visible
    on a screen they are looking at, which is how a page gets muted.
    """
    return STALE_AFTER_CADENCE_MULTIPLE, STALL_ALERT_CADENCE_MULTIPLE
