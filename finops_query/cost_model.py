"""What a Grafana query costs, and why.

Extracted from `_legacy/sample_lambda.py` under the golden files from
TASK-P2-001, with no formula changed. Where a formula looks wrong it is
recorded as an issue and left alone: changing it here would move a number in
the same commit that moved the code, and the golden diff would then be
unreadable. Every one of these figures is **modelled**, never measured, until
TASK-P2-020 back tests the model against a bill and publishes the accuracy.
ISS-093 until it does.

The arithmetic is three separate questions and they are kept separate.

How often does it run. A panel runs only while somebody is looking at it, so
its rate is the viewing assumption divided by the refresh interval. An alert
rule runs on its own interval regardless of viewers, which is why an alert on a
one minute interval outruns a dashboard nobody has open by two orders of
magnitude.

What does one run cost. Logs Insights is billed per GB scanned, so its cost is
ingestion multiplied by window multiplied by price, and the window is the lever
nobody expects. The metric engines are billed per metric requested, which does
not depend on the window at all.

How close is it to a quota. Separate from cost on purpose: a dashboard can
exhaust the Logs Insights concurrency quota while costing very little, and that
failure looks nothing like an expensive one.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from finops_query.classify import (
    LOGS_INSIGHTS,
    METRIC_SEARCH,
    METRICS_INSIGHTS,
    PROMETHEUS,
    Classification,
)

#: Days in a billing month, as the prototype used it. An approximation, and the
#: same one every figure here rests on, so it is named rather than repeated.
DAYS_PER_MONTH = 30.0
SECONDS_PER_HOUR = 3600.0
SECONDS_PER_DAY = 86400.0
BYTES_PER_GB = 1024**3

#: The window assumed when a dashboard uses an absolute time range, in hours.
#: One hour, which understates almost every real absolute range. It is the
#: prototype's choice and it is kept.
UNKNOWN_WINDOW_HOURS = 1.0

#: An alert rule with no interval declared. Grafana's own default.
DEFAULT_ALERT_INTERVAL_SECONDS = 60

#: Points contributed to the risk score. These were bare numbers in a chain of
#: comparisons, which is a policy hidden in an expression. They are not settings
#: because they are not tenant configurable: they are the definition of the
#: score, and the thresholds that read them are what a tenant tunes.
ENGINE_SCORE = {LOGS_INSIGHTS: 40, METRICS_INSIGHTS: 25, METRIC_SEARCH: 12}
WIDE_WINDOW_SCORE = 15
VERY_WIDE_WINDOW_SCORE = 30
ALERT_SCORE = 20
FAST_REFRESH_SCORE = 15
VERY_FAST_REFRESH_SCORE = 30

#: Score at or above which each level starts.
CRITICAL_AT = 80
HIGH_AT = 55
MEDIUM_AT = 30

PANEL = "panel"
ALERT = "alert"


@dataclass(frozen=True)
class Rates:
    """Everything the model prices with, and nothing it decides for itself.

    Built from `Settings` rather than read from it directly, so the arithmetic
    below has no opinion about where a number came from and a test can price a
    query without constructing a whole deployment configuration.
    """

    logs_scan_price_per_gb: float
    metrics_price_per_1000: float
    manual_loads_per_day: float
    viewing_hours_per_day: float
    metrics_per_call: float
    default_ingest_gb_per_day: float
    assumed_query_seconds: float
    refresh_warn_seconds: int
    refresh_crit_seconds: int
    timerange_warn_hours: float
    timerange_crit_hours: float
    quota_logs_concurrent: int
    quota_getmetricdata_tps: int

    @classmethod
    def from_settings(cls, settings: Any) -> Rates:
        return cls(
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


@dataclass(frozen=True)
class QuotaImpact:
    """How much of a service quota this one query consumes.

    Reported separately from cost because the two fail differently. A query at
    ninety percent of the Logs Insights concurrency quota is about to start
    failing for everyone in the account, whatever it costs.
    """

    kind: str | None
    pct: float
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "pct": self.pct, "detail": self.detail}


#: Given a region and a log group, how many GB per hour it ingests. Passed in
#: rather than measured here, because measuring means a CloudWatch call and this
#: module has no business opening a client. The fallback is the caller's to
#: decide, which is what lets the whole model run offline against a fixture.
#: Returns **GB per hour**, because the window it is multiplied by below is
#: measured in hours. A caller handing this a per day figure overstates every
#: Logs Insights cost by 24.
IngestRate = Callable[[str, str], float]


def human_refresh(seconds: int) -> str:
    """A refresh interval as a person would write it.

    The prototype returned an em dash for zero, which this project's writing
    rules forbid and which is unreachable from the cost model: every call site
    is guarded by a truthiness test on the same value. A test asserts that,
    so dropping the branch does not change a single golden file.
    """
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def human_window(seconds: int) -> str:
    """A window as a person would write it, largest exact unit first."""
    for label, size in (
        ("y", 31536000),
        ("w", 604800),
        ("d", 86400),
        ("h", 3600),
        ("m", 60),
        ("s", 1),
    ):
        if seconds >= size and seconds % size == 0:
            return f"{seconds // size}{label}"
    return f"{seconds}s"


def runs_per_day(
    refresh_seconds: int,
    origin: str,
    rates: Rates,
    alert_interval_seconds: int | None = None,
) -> float:
    """How often this query actually runs.

    The single largest term in every figure this module produces, and the one
    most often got wrong by hand: a panel is assumed to run only while somebody
    is watching, and an alert rule runs on its interval forever.
    """
    if origin == ALERT:
        interval = alert_interval_seconds or DEFAULT_ALERT_INTERVAL_SECONDS
        return SECONDS_PER_DAY / interval
    if refresh_seconds and refresh_seconds > 0:
        return (rates.viewing_hours_per_day * SECONDS_PER_HOUR) / refresh_seconds
    return rates.manual_loads_per_day


def _logs_insights_cost(
    classification: Classification,
    window_hours: float | None,
    per_day: float,
    rates: Rates,
    ingest_rate: IngestRate,
    region: str,
) -> tuple[float, float, list[str]]:
    """Scan volume multiplied by price. The window is the lever."""
    hours = window_hours if window_hours is not None else UNKNOWN_WINDOW_HOURS
    groups = classification.log_groups or ("(unspecified)",)

    gb_per_run = sum(ingest_rate(region, group) * hours for group in groups)
    bytes_per_run = gb_per_run * BYTES_PER_GB
    cost_month = gb_per_run * per_day * DAYS_PER_MONTH * rates.logs_scan_price_per_gb

    reasons = ["Logs Insights is billed per GB scanned."]
    return bytes_per_run, cost_month, reasons


def _metric_cost(engine: str, per_day: float, rates: Rates) -> tuple[float, list[str]]:
    """Billed per metric requested, so the window does not enter into it."""
    cost_month = (
        rates.metrics_per_call * per_day * DAYS_PER_MONTH * rates.metrics_price_per_1000 / 1000.0
    )
    reasons = ["Billed per metric requested per GetMetricData call."]
    if engine == METRICS_INSIGHTS:
        reasons.append("Metric Insights (SQL) can scan many metrics per run.")
    return cost_month, reasons


def _window_reason(
    window_seconds: int | None, window_hours: float | None, rates: Rates
) -> str | None:
    if not window_hours or window_seconds is None:
        return None
    if window_hours >= rates.timerange_crit_hours:
        return f"Very wide window ({human_window(window_seconds)}) scans a large volume each run."
    if window_hours >= rates.timerange_warn_hours:
        return f"Wide window ({human_window(window_seconds)}) increases scan per run."
    return None


def _refresh_reason(refresh: int, origin: str, rates: Rates) -> str | None:
    if origin == ALERT:
        return "Alert rule: runs 24x7 regardless of viewers."
    if refresh and refresh <= rates.refresh_crit_seconds:
        return f"Very fast auto-refresh ({human_refresh(refresh)}) re-runs the query continuously."
    if refresh and refresh <= rates.refresh_warn_seconds:
        return f"Fast auto-refresh ({human_refresh(refresh)}) multiplies run count."
    if not refresh and origin == PANEL:
        return "No auto-refresh; assumed manual loads/day."
    return None


def quota_impact(engine: str, per_day: float, rates: Rates) -> QuotaImpact:
    """Pressure on a service quota, which is not the same as cost."""
    if engine == LOGS_INSIGHTS:
        query_seconds_per_day = per_day * rates.assumed_query_seconds
        budget = rates.quota_logs_concurrent * SECONDS_PER_DAY
        pct = (query_seconds_per_day / budget * 100.0) if budget else 0.0
        return QuotaImpact(
            kind="Logs Insights concurrency",
            pct=pct,
            detail=(
                f"~{per_day:,.0f} runs/day x {rates.assumed_query_seconds:g}s "
                f"vs {rates.quota_logs_concurrent} concurrent-query quota"
            ),
        )
    if engine in (METRIC_SEARCH, METRICS_INSIGHTS):
        calls_per_sec = per_day / SECONDS_PER_DAY
        pct = (
            (calls_per_sec / rates.quota_getmetricdata_tps * 100.0)
            if rates.quota_getmetricdata_tps
            else 0.0
        )
        return QuotaImpact(
            kind="GetMetricData TPS",
            pct=pct,
            detail=(f"~{calls_per_sec:.3f} calls/s vs {rates.quota_getmetricdata_tps} TPS quota"),
        )
    return QuotaImpact(kind=None, pct=0.0, detail="")


def risk_level(
    engine: str,
    refresh: int,
    window_seconds: int | None,
    origin: str,
    rates: Rates,
) -> str:
    """A level to rank rows by, computed from shape rather than from money.

    Deliberately not derived from `cost_month`, even though it is named after
    it in the prototype. A Logs Insights query on a fast refresh over a wide
    window is a risk whatever today's modelled figure says, because the figure
    rests on an ingestion assumption that may be an order of magnitude out.
    """
    score = ENGINE_SCORE.get(engine, 0)

    if window_seconds:
        hours = window_seconds / SECONDS_PER_HOUR
        if hours >= rates.timerange_crit_hours:
            score += VERY_WIDE_WINDOW_SCORE
        elif hours >= rates.timerange_warn_hours:
            score += WIDE_WINDOW_SCORE

    if origin == ALERT:
        score += ALERT_SCORE
    elif refresh and refresh <= rates.refresh_crit_seconds:
        score += VERY_FAST_REFRESH_SCORE
    elif refresh and refresh <= rates.refresh_warn_seconds:
        score += FAST_REFRESH_SCORE

    if score >= CRITICAL_AT:
        return "CRITICAL"
    if score >= HIGH_AT:
        return "HIGH"
    if score >= MEDIUM_AT:
        return "MEDIUM"
    return "LOW"


@dataclass(frozen=True)
class Cost:
    """What one query costs, with the reasoning that produced it."""

    bytes_per_run: float
    cost_month: float
    cost_day: float
    why: tuple[str, ...]
    quota: QuotaImpact
    risk_level: str


def price(
    classification: Classification,
    origin: str,
    refresh: int,
    window_seconds: int | None,
    per_day: float,
    rates: Rates,
    ingest_rate: IngestRate,
    region: str,
) -> Cost:
    """Price one classified query. No IO, no clock, no client."""
    engine = classification.engine
    window_hours = (window_seconds / SECONDS_PER_HOUR) if window_seconds else None

    bytes_per_run = 0.0
    cost_month = 0.0
    reasons: list[str] = []

    if engine == LOGS_INSIGHTS:
        bytes_per_run, cost_month, reasons = _logs_insights_cost(
            classification, window_hours, per_day, rates, ingest_rate, region
        )
        window_reason = _window_reason(window_seconds, window_hours, rates)
        if window_reason:
            reasons.append(window_reason)
    elif engine in (METRIC_SEARCH, METRICS_INSIGHTS):
        cost_month, reasons = _metric_cost(engine, per_day, rates)
    elif engine == PROMETHEUS:
        reasons = ["Prometheus/AMP query, no CloudWatch scan cost."]

    refresh_reason = _refresh_reason(refresh, origin, rates)
    if refresh_reason:
        reasons.append(refresh_reason)

    return Cost(
        bytes_per_run=bytes_per_run,
        cost_month=cost_month,
        cost_day=cost_month / DAYS_PER_MONTH,
        why=tuple(reasons),
        quota=quota_impact(engine, per_day, rates),
        risk_level=risk_level(engine, refresh, window_seconds, origin, rates),
    )
