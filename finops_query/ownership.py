"""Who ran a query, and whether the figure beside it was measured or modelled.

Two jobs that belong together because they answer the same question about a
finding: how much of it is real.

**Attribution.** A CloudTrail event names a principal in one of five places
depending on how the caller authenticated, and `principal_from` reads them in
the order that yields something a person recognises. Getting this wrong does not
break anything visibly: it produces a finding with no owner, and ISS-021 records
what happens then, which is that nobody fixes it.

**Measurement.** `measure_logs_query` and `measure_metric_query` replace a
modelled run count, and where the data exists a modelled scan volume, with
observed numbers. The distinction is the point of the whole module. A modelled
Logs Insights cost rests on an assumed ingestion rate that can be an order of
magnitude out; a measured one is what the account actually did. Every figure
upgraded carries a reason saying so, because a number a reader cannot tell apart
from an estimate gets treated as an estimate, and then ignored.

Extracted from the prototype under the golden files, with no arithmetic
changed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from finops_query import policy

DAYS_PER_MONTH = 30.0
#: The binary step between byte units. A genuine domain constant rather than a
#: policy threshold: it is what a kilobyte is, not a number anybody tunes.
BYTES_PER_UNIT = 1024
BYTES_PER_GB = BYTES_PER_UNIT**3

LOGS_INSIGHTS = "logs_insights"
METRIC_ENGINES = ("metric_search", "metrics_insights")


def principal_from(event_detail: dict[str, Any]) -> str | None:
    """A human readable principal from a CloudTrail event, or None.

    Five sources, in order of how recognisable the answer is. An IAM user has a
    `userName`; an assumed role carries the session name at the end of
    `principalId`, which is usually a person under SSO; the session issuer names
    the role itself; the ARN's last segment is the fallback; and `type` is the
    last resort, which says "AssumedRole" and identifies nobody.

    Returning None rather than a placeholder is deliberate. An unowned finding
    should read as unowned, not as owned by somebody called "unknown".
    """
    identity = event_detail.get("userIdentity") or {}
    issuer = (identity.get("sessionContext") or {}).get("sessionIssuer") or {}

    return (
        identity.get("userName")
        or identity.get("principalId", "").split(":")[-1]
        or issuer.get("userName")
        or identity.get("arn", "").split("/")[-1]
        or identity.get("type")
        or None
    )


@dataclass
class Observed:
    """Executions actually seen, for one query."""

    runs: int = 0
    scanned_bytes: float = 0.0
    per_run_bytes: list[float] = field(default_factory=list)
    log_groups: set[str] = field(default_factory=set)

    def merge(self, other: dict[str, Any]) -> None:
        self.runs += other.get("runs", 0)
        self.scanned_bytes += other.get("bytes", 0.0)
        self.per_run_bytes.extend(other.get("runs_bytes", []))
        self.log_groups |= other.get("log_groups", set())


def match_observed(query: str, measured: dict[str, Any]) -> Observed | None:
    """The executions belonging to one panel query, or None.

    Exact normalised match first, because it is cheap and it covers most
    queries. A templated query then falls back to matching its own resolved
    executions by regex and merging them, which is the only way a panel storing
    `$region` collects the runs recorded against `eu-west-1`.

    Matched keys are recorded on the bundle so whatever is left over can be
    reported as ad hoc. A query somebody ran by hand is a real cost with no
    dashboard to attribute it to, and dropping it understates the account.
    """
    logs = measured.get("logs") or {}
    if not logs:
        return None

    matched: set[str] = measured.setdefault("_matched_keys", set())

    key = policy.normalise(query)
    exact = logs.get(key)
    if exact:
        matched.add(key)
        found = Observed()
        found.merge(exact)
        return found

    if not policy.has_template_vars(query):
        return None

    pattern = policy.match_pattern(query)
    if pattern is None:
        return None

    merged = Observed()
    hit = False
    for candidate, aggregate in logs.items():
        if pattern.fullmatch(candidate) or pattern.match(candidate):
            hit = True
            matched.add(candidate)
            merged.merge(aggregate)
    return merged if hit else None


@dataclass(frozen=True)
class Measurement:
    """What replaced a modelled figure, and what it was based on."""

    runs_per_day: float
    cost_month: float
    bytes_per_run: float
    bytes_measured: bool
    runs_total: int
    reason: str

    @property
    def cost_day(self) -> float:
        return self.cost_month / DAYS_PER_MONTH


def _metric_key(namespace: str, target_label: str, by_metric: dict[str, int]) -> str | None:
    """The GetMetricData bucket for a metric panel, if there is one.

    CloudTrail identifies a GetMetricData call by account and region, never by
    panel, so this matches on namespace and metric name instead. It is the
    weakest attribution in the module, and it is one of the reasons ISS-093
    exists.
    """
    wanted = (namespace or "").lower()
    label = (target_label or "").lower()
    if not wanted:
        return None

    for candidate in by_metric:
        candidate_namespace, _, metric = candidate.partition("|")
        if candidate_namespace == wanted and (metric in label or not label):
            return candidate
    return None


def measure_metric_query(
    namespace: str,
    target_label: str,
    measured: dict[str, Any],
    metrics_per_call: float,
    price_per_1000: float,
) -> Measurement | None:
    """Replace a modelled metric run count with observed GetMetricData calls."""
    by_metric = measured.get("gmd_by_metric") or {}
    key = _metric_key(namespace, target_label, by_metric)
    if key is None or by_metric[key] <= 0:
        return None

    days = max(measured["lookback_days"], 1)
    calls = by_metric[key]
    per_day = calls / days
    cost_month = metrics_per_call * per_day * DAYS_PER_MONTH * price_per_1000 / 1000.0

    return Measurement(
        runs_per_day=per_day,
        cost_month=cost_month,
        bytes_per_run=0.0,
        bytes_measured=False,
        runs_total=calls,
        reason=f"GetMetricData calls MEASURED from CloudTrail ({calls} in {days}d).",
    )


def measure_logs_query(
    query: str,
    modelled_bytes_per_run: float,
    measured: dict[str, Any],
    price_per_gb: float,
) -> Measurement | None:
    """Replace a modelled Logs Insights figure with what the account did.

    Two grades of answer, reported differently on purpose. When query history
    carries bytes scanned, both the run count and the scan volume are real and
    the assumed ingestion rate drops out of the figure entirely. When only
    CloudTrail is available the runs are real and the bytes are still modelled,
    which is better than nothing and is not the same thing as measured.
    """
    observed = match_observed(query, measured)
    if observed is None or observed.runs <= 0:
        return None

    days = max(measured["lookback_days"], 1)
    per_day = observed.runs / days

    if observed.scanned_bytes > 0 and observed.per_run_bytes:
        average = observed.scanned_bytes / len(observed.per_run_bytes)
        gb_per_run = average / BYTES_PER_GB
        return Measurement(
            runs_per_day=per_day,
            cost_month=gb_per_run * per_day * DAYS_PER_MONTH * price_per_gb,
            bytes_per_run=average,
            bytes_measured=True,
            runs_total=observed.runs,
            reason=(
                "Bytes scanned + runs MEASURED from Logs Insights query history "
                f"({observed.runs} runs, {human_bytes(average)}/run)."
            ),
        )

    gb_per_run = modelled_bytes_per_run / BYTES_PER_GB if modelled_bytes_per_run else 0.0
    return Measurement(
        runs_per_day=per_day,
        cost_month=gb_per_run * per_day * DAYS_PER_MONTH * price_per_gb,
        bytes_per_run=modelled_bytes_per_run,
        bytes_measured=False,
        runs_total=observed.runs,
        reason=f"Runs/day MEASURED ({observed.runs} runs over {days}d); bytes modelled.",
    )


def human_bytes(count: float) -> str:
    """Bytes as a person would write them."""
    if not count:
        return "0 B"

    units = ("B", "KB", "MB", "GB", "TB", "PB")
    index = 0
    size = float(count)
    while size >= BYTES_PER_UNIT and index < len(units) - 1:
        size /= BYTES_PER_UNIT
        index += 1
    return f"{size:,.1f} {units[index]}" if index else f"{int(size)} {units[index]}"
