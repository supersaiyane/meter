"""The extracted model priced against the prototype it came from.

TASK-P2-002's acceptance is that every golden file reproduces exactly through
the new modules. It does, with one divergence, and that divergence is
enumerated below rather than absorbed by a loose comparison.

The prototype writes an em dash into one reason string. This project's writing
rules forbid the character anywhere, and the frozen copy is exempt only because
it is frozen. New code is not exempt, so the extracted model writes a comma.
That is the whole of the difference: one punctuation mark in one string, named
here, and any other difference at all fails.

Enumerating it matters. A comparison that normalised punctuation before
comparing would also hide a real change to a reason string, and the reasons are
the part of a finding a person actually reads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from finops_query import classify, cost_model
from finops_query.cost_model import Rates
from tests.query.conftest import REGION

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDEN = FIXTURES / "golden"
DASHBOARDS = FIXTURES / "dashboards"

#: The character this whole divergence is about, built rather than typed.
#: CLAUDE.md makes the same point about its own writing rules: reproducing the
#: literal here would make `make check-writing` fail on the file that documents
#: the rule, which is what happened the first time the rule was written down.
EM_DASH = "\u2014"

#: The one string the extraction could not carry over verbatim, and why.
#: Written as an explicit pair so the test compares everything else exactly.
KNOWN_DIVERGENCES: dict[str, str] = {
    f"Prometheus/AMP query {EM_DASH} no CloudWatch scan cost.": (
        "Prometheus/AMP query, no CloudWatch scan cost."
    ),
}


def expected(name: str) -> Any:
    return json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))


def reconcile(reason: str) -> str:
    """Apply the one recorded divergence, and nothing else."""
    return KNOWN_DIVERGENCES.get(reason, reason)


def price_target(
    target: dict[str, Any],
    panel_datasource: Any,
    origin: str,
    refresh: int,
    window_seconds: int | None,
    rates: Rates,
    fallback_ingest: cost_model.IngestRate,
    alert_interval: int | None = None,
) -> tuple[classify.Classification, cost_model.Cost]:
    found = classify.classify(target, panel_datasource)
    per_day = cost_model.runs_per_day(refresh, origin, rates, alert_interval)
    return found, cost_model.price(
        found, origin, refresh, window_seconds, per_day, rates, fallback_ingest, REGION
    )


def dashboard_names() -> list[str]:
    return sorted(p.stem for p in DASHBOARDS.glob("*.json"))


@pytest.mark.parametrize("name", dashboard_names())
def test_the_extracted_model_reproduces_the_golden(
    name: str, rates: Rates, fallback_ingest: cost_model.IngestRate
) -> None:
    """Field by field against the prototype's own recorded output."""
    source = json.loads((DASHBOARDS / f"{name}.json").read_text(encoding="utf-8"))
    dashboard = source["dashboard"]
    golden = expected(f"dashboard-{name}")

    refresh = classify.refresh_seconds(dashboard.get("refresh"))
    window = classify.relative_range_seconds((dashboard.get("time") or {}).get("from"))

    produced: list[dict[str, Any]] = []
    for panel in classify.iter_panels(dashboard.get("panels", [])):
        for target in panel.get("targets", []) or []:
            if target.get("hide"):
                continue
            found = classify.classify(target, panel.get("datasource"))
            if not found.query and found.engine == "unknown":
                continue
            _, cost = price_target(
                target, panel.get("datasource"), "panel", refresh, window, rates, fallback_ingest
            )
            produced.append(
                {
                    "engine": found.engine,
                    "query": found.query,
                    "log_groups": list(found.log_groups),
                    "namespace": found.namespace,
                    "target_label": found.target_label,
                    "bytes_per_run": cost.bytes_per_run,
                    "cost_month": cost.cost_month,
                    "cost_day": cost.cost_day,
                    "why": list(cost.why),
                    "quota_impact": cost.quota.as_dict(),
                    "risk_level": cost.risk_level,
                }
            )

    assert len(produced) == len(golden["findings"]), f"{name}: different number of findings"

    for mine, theirs in zip(produced, golden["findings"], strict=True):
        for field in ("engine", "query", "log_groups", "namespace", "target_label"):
            assert mine[field] == theirs[field], f"{name}: {field}"
        for field in ("bytes_per_run", "cost_month", "cost_day"):
            assert mine[field] == theirs[field], f"{name}: {field}"
        assert mine["risk_level"] == theirs["risk_level"], f"{name}: risk_level"
        assert mine["quota_impact"] == theirs["quota_impact"], f"{name}: quota_impact"
        assert mine["why"] == [reconcile(r) for r in theirs["why"]], f"{name}: why"


def test_the_only_divergence_is_the_one_that_is_recorded() -> None:
    """The exemption cannot quietly grow.

    Each recorded divergence has to be a string that really appears in a golden
    file, and its replacement has to be one the extraction really produces.
    Without this, an entry could be added to make any failure disappear.

    Checked against the goldens rather than against the prototype, which
    TASK-P2-003 deleted. The goldens are now the only surviving record of what
    that code emitted, which is the reason they are not regenerated: doing so
    would erase the evidence that this string was ever different.
    """
    recorded = "\n".join(path.read_text(encoding="utf-8") for path in sorted(GOLDEN.glob("*.json")))
    extracted = Path("finops_query/cost_model.py").read_text(encoding="utf-8")

    assert len(KNOWN_DIVERGENCES) == 1
    for original, replacement in KNOWN_DIVERGENCES.items():
        # json.dumps escapes the character, which is how it sits in the goldens.
        assert original.replace(EM_DASH, "\\u2014") in recorded, f"no golden contains {original!r}"
        assert replacement in extracted, f"the extraction does not contain {replacement!r}"
        assert EM_DASH in original, "an em dash is the only accepted reason to diverge"
        assert EM_DASH not in replacement


def test_the_alert_rules_reproduce_their_golden(
    rates: Rates, fallback_ingest: cost_model.IngestRate
) -> None:
    rules = json.loads((FIXTURES / "alerts" / "alert-rules.json").read_text(encoding="utf-8"))
    golden = expected("alerts")

    produced: list[dict[str, Any]] = []
    for rule in rules:
        interval = classify.refresh_seconds(rule.get("interval") or "") or 60
        for data in rule.get("data", []) or []:
            model = data.get("model", {}) or {}
            found = classify.classify(model, model.get("datasource"))
            if not found.query and found.engine in ("unknown", "__expr__"):
                continue
            window = None
            relative = data.get("relativeTimeRange") or {}
            if relative.get("from"):
                window = int(relative["from"])
            _, cost = price_target(
                model,
                model.get("datasource"),
                "alert",
                interval,
                window,
                rates,
                fallback_ingest,
                interval,
            )
            produced.append(
                {
                    "engine": found.engine,
                    "cost_month": cost.cost_month,
                    "risk_level": cost.risk_level,
                    "why": list(cost.why),
                }
            )

    assert len(produced) == len(golden)
    for mine, theirs in zip(produced, golden, strict=True):
        assert mine["engine"] == theirs["engine"]
        assert mine["cost_month"] == theirs["cost_month"]
        assert mine["risk_level"] == theirs["risk_level"]
        assert mine["why"] == [reconcile(r) for r in theirs["why"]]


# --- the model's own behaviour, stated rather than inferred ------------------


def test_a_panel_runs_only_while_it_is_watched(rates: Rates) -> None:
    """Two hours of viewing at a thirty second refresh is 240 runs, not 2,880.

    The difference between those two numbers is the difference between a
    finding worth acting on and a figure nobody believes.
    """
    assert cost_model.runs_per_day(30, "panel", rates) == 240.0


def test_an_alert_runs_whether_anybody_is_watching_or_not(rates: Rates) -> None:
    assert cost_model.runs_per_day(0, "alert", rates, 60) == 1440.0


def test_an_alert_with_no_interval_takes_grafana_s_default(rates: Rates) -> None:
    assert cost_model.runs_per_day(0, "alert", rates, None) == 1440.0


def test_a_panel_with_no_refresh_falls_back_to_manual_loads(rates: Rates) -> None:
    assert cost_model.runs_per_day(0, "panel", rates) == rates.manual_loads_per_day


def test_the_window_does_not_enter_into_a_metric_price(
    rates: Rates, fallback_ingest: cost_model.IngestRate
) -> None:
    """Metric engines are billed per metric requested. A wider window on a
    metric panel costs nothing extra, and treating it as if it did is the
    mistake this separation exists to prevent."""
    metric = classify.Classification(engine="metric_search", query="", region=None)
    narrow = cost_model.price(metric, "panel", 60, 3600, 120.0, rates, fallback_ingest, REGION)
    wide = cost_model.price(metric, "panel", 60, 604800, 120.0, rates, fallback_ingest, REGION)

    assert narrow.cost_month == wide.cost_month


def test_the_window_multiplies_a_logs_insights_price(
    rates: Rates, fallback_ingest: cost_model.IngestRate
) -> None:
    """And on Logs Insights it multiplies directly, which is the finding the
    whole product exists to surface."""
    logs = classify.Classification(
        engine="logs_insights", query="", region=None, log_groups=("/app/api",)
    )
    one_hour = cost_model.price(logs, "panel", 60, 3600, 120.0, rates, fallback_ingest, REGION)
    one_week = cost_model.price(logs, "panel", 60, 604800, 120.0, rates, fallback_ingest, REGION)

    assert one_week.cost_month == pytest.approx(one_hour.cost_month * 168)


def test_an_absolute_window_is_not_priced_as_zero(
    rates: Rates, fallback_ingest: cost_model.IngestRate
) -> None:
    """None means unknown, not none. Pricing it at zero would make every
    dashboard using an absolute range look free."""
    logs = classify.Classification(
        engine="logs_insights", query="", region=None, log_groups=("/app/api",)
    )
    cost = cost_model.price(logs, "panel", 60, None, 120.0, rates, fallback_ingest, REGION)

    assert cost.cost_month > 0


def test_the_zero_branch_of_human_refresh_is_unreachable_from_the_model(
    rates: Rates, fallback_ingest: cost_model.IngestRate
) -> None:
    """Which is what makes dropping the prototype's em dash safe.

    Every call site is guarded by a truthiness test on the same value, so a zero
    never reaches the formatter. If that ever stops being true, this fails
    rather than an em dash appearing in the product.
    """
    for engine in ("logs_insights", "metric_search", "prometheus"):
        found = classify.Classification(engine=engine, query="", region=None)
        for origin in ("panel", "alert"):
            cost = cost_model.price(found, origin, 0, 3600, 10.0, rates, fallback_ingest, REGION)
            assert not any(EM_DASH in reason for reason in cost.why)


def test_quota_pressure_is_reported_separately_from_cost(rates: Rates) -> None:
    """A query can exhaust a quota while costing very little, and that failure
    looks nothing like an expensive one."""
    impact = cost_model.quota_impact("logs_insights", 2880.0, rates)

    assert impact.kind == "Logs Insights concurrency"
    assert impact.pct > 0


def test_an_unpriced_engine_reports_no_quota_pressure(rates: Rates) -> None:
    assert cost_model.quota_impact("prometheus", 2880.0, rates).kind is None


def test_neither_module_exceeds_the_file_ceiling() -> None:
    """800 lines, from the coding style rules. Checked because the whole point
    of this task was splitting a 2,740 line file."""
    for name in ("cost_model.py", "classify.py"):
        path = Path("finops_query") / name
        assert len(path.read_text(encoding="utf-8").splitlines()) < 800, name
