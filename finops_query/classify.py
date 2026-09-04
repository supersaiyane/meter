"""What engine a Grafana target runs on, and what it runs against.

Separate from `cost_model.py` on purpose. Adding a sixth engine should mean
adding a branch here and a rate in settings, not touching the arithmetic that
turns runs and windows into money. In the prototype the two were one function
and a new engine meant editing the cost path, which is how a pricing bug gets
introduced by a change that was only meant to recognise a datasource.

Extracted faithfully from `_legacy/sample_lambda.py` under the golden files from
TASK-P2-001. Nothing here is improved. Two things look wrong and are recorded
rather than fixed: `classify_target` decides a CloudWatch target is Logs
Insights if the expression merely contains the word "filter", which matches a
metric maths expression using the `FILTER` function, and the datasource type is
copied into `engine` before it is known to be an engine name at all, so an
unrecognised datasource reports itself as one. ISS-132 and ISS-133.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: Grafana duration units, in seconds. `M` is a month of 30 days, which is the
#: prototype's own approximation and is kept.
UNIT_SECONDS: dict[str, int] = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "M": 2592000,
    "y": 31536000,
}

_RELATIVE = re.compile(r"now\s*-\s*(\d+)\s*([smhdwMy])")
_DURATION = re.compile(r"^(\d+)\s*([smhdwMy])$")

#: The engines the cost model prices. `unknown` is not in this set: it is
#: whatever the datasource called itself, which is the ISS-133 defect.
LOGS_INSIGHTS = "logs_insights"
METRICS_INSIGHTS = "metrics_insights"
METRIC_SEARCH = "metric_search"
PROMETHEUS = "prometheus"

BILLED_ENGINES = frozenset({LOGS_INSIGHTS, METRICS_INSIGHTS, METRIC_SEARCH})


@dataclass(frozen=True)
class Classification:
    """What one target is, as the cost model needs to see it."""

    engine: str
    query: str
    region: str | None
    log_groups: tuple[str, ...] = ()
    namespace: str | None = None
    target_label: str = ""

    def as_dict(self) -> dict[str, Any]:
        """The prototype's shape, for the golden files.

        Log groups are a list rather than a tuple here, because that is what the
        prototype produced and the goldens record it.
        """
        return {
            "engine": self.engine,
            "query": self.query,
            "region": self.region,
            "log_groups": list(self.log_groups),
            "namespace": self.namespace,
            "target_label": self.target_label,
        }


@dataclass
class PanelQuery:
    """One query found on a panel or an alert rule, before it is priced."""

    classification: Classification
    origin: str
    refresh_seconds: int
    range_seconds: int | None
    runs_per_day: float
    reasons: list[str] = field(default_factory=list)


def relative_range_seconds(time_from: Any) -> int | None:
    """A Grafana relative range like `now-7d`, in seconds, or None.

    None means an absolute range, which the cost model treats as an unknown
    window rather than as zero. Those are different: an unknown window falls
    back to one hour, and a zero window would price the query at nothing.
    """
    if not time_from or not isinstance(time_from, str):
        return None
    found = _RELATIVE.search(time_from)
    if found:
        return int(found.group(1)) * UNIT_SECONDS.get(found.group(2), 0)
    if time_from.strip() == "now/d":
        return 86400
    if time_from.strip() == "now/w":
        return 604800
    return None


def refresh_seconds(refresh: Any) -> int:
    """A Grafana refresh interval in seconds. Zero means no auto refresh.

    Zero rather than None, faithfully. The cost model tells the two apart by
    origin instead, which is why an alert rule with no interval gets a default
    and a panel with no refresh gets the manual loads assumption.
    """
    if not refresh or not isinstance(refresh, str):
        return 0
    found = _DURATION.match(refresh.strip())
    if found:
        return int(found.group(1)) * UNIT_SECONDS.get(found.group(2), 0)
    return 0


def log_groups_of(target: dict[str, Any]) -> tuple[str, ...]:
    """Every log group a CloudWatch target names, in order, deduplicated.

    Three different shapes, because Grafana has changed this twice: `logGroups`
    as objects, `logGroupNames` as strings, and a single `logGroupName`. All
    three are read, which is what lets an old dashboard be priced.
    """
    found: list[str] = []

    listed = target.get("logGroups")
    if isinstance(listed, list):
        for group in listed:
            if isinstance(group, dict):
                found.append(group.get("name") or group.get("arn") or "")
            elif isinstance(group, str):
                found.append(group)

    names = target.get("logGroupNames")
    if isinstance(names, list):
        found.extend(name for name in names if isinstance(name, str))

    single = target.get("logGroupName")
    if isinstance(single, str) and single:
        found.append(single)

    seen: set[str] = set()
    ordered: list[str] = []
    for group in found:
        cleaned = (group or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            ordered.append(cleaned)
    return tuple(ordered)


def _datasource_type(target: dict[str, Any], panel_datasource: Any) -> str:
    source = target.get("datasource") or panel_datasource or {}
    if isinstance(source, dict):
        return str(source.get("type") or "unknown")
    return str(source) or "unknown"


def _classify_cloudwatch(target: dict[str, Any]) -> Classification:
    """CloudWatch is three engines wearing one datasource name.

    The order of these branches is the behaviour. Logs Insights is tested first
    and its test is loose, so a metric target whose expression happens to
    contain "filter " is priced as a log scan. That is ISS-132 and it is kept.
    """
    query_mode = str(target.get("queryMode") or "").lower()
    expression = str(target.get("expression") or "")
    groups = log_groups_of(target)

    is_logs = (
        query_mode == "logs"
        or "fields " in expression.lower()
        or "filter " in expression.lower()
        or bool(groups)
    )
    if is_logs:
        return Classification(
            engine=LOGS_INSIGHTS,
            query=(expression or str(target.get("query") or "")).strip(),
            region=target.get("region"),
            log_groups=groups,
            target_label=", ".join(groups) or "(log groups not specified)",
        )

    if target.get("metricQueryType") == 1 or target.get("sqlExpression"):
        return Classification(
            engine=METRICS_INSIGHTS,
            query=(str(target.get("sqlExpression") or "") or expression).strip(),
            region=target.get("region"),
            namespace=target.get("namespace"),
            target_label=target.get("namespace") or "Metric Insights (SQL)",
        )

    metric = str(target.get("metricName") or "")
    namespace = target.get("namespace")
    return Classification(
        engine=METRIC_SEARCH,
        query=(expression or metric).strip(),
        region=target.get("region"),
        namespace=namespace,
        target_label=" ".join(x for x in [namespace, metric] if x) or "CloudWatch metric",
    )


def classify(target: dict[str, Any], panel_datasource: Any = None) -> Classification:
    """What engine this target runs on, and what it runs against."""
    kind = _datasource_type(target, panel_datasource)

    if kind == "cloudwatch":
        return _classify_cloudwatch(target)

    if kind == PROMETHEUS:
        return Classification(
            engine=PROMETHEUS,
            query=str(target.get("expr") or "").strip(),
            region=target.get("region"),
            target_label="Prometheus",
        )

    # Anything else keeps the datasource name as its engine, which means an
    # unrecognised datasource reports an engine that no rate exists for. It is
    # priced at zero rather than refused. ISS-133.
    query = (
        target.get("expr")
        or target.get("expression")
        or target.get("query")
        or target.get("rawSql")
        or ""
    )
    return Classification(
        engine=kind,
        query=str(query).strip(),
        region=target.get("region"),
        target_label=kind,
    )


def iter_panels(panels: Any) -> Any:
    """Every panel, flattening rows.

    A row is a container, not a panel, and its children are one level down. A
    version of this that did not recurse would silently price nothing on any
    dashboard that uses rows, which is most of them.
    """
    for panel in panels or []:
        if panel.get("type") == "row":
            yield from iter_panels(panel.get("panels", []))
        else:
            yield panel
