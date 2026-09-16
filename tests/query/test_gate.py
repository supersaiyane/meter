"""The CI policy gate. TASK-P2-018, FEAT-014.

The gate is the only part of P2 that acts before the money is spent. These tests
are mostly about what it must NOT refuse, because a gate that blocks a pipeline
for a reason nobody accepts is a gate somebody deletes.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from finops_query.cost_model import Rates
from finops_query.gate import DEFAULT_RULE, Rule, check

# Loaded by path, not imported as a package, because `scripts/` deliberately is
# not one and importing it as `scripts.ci.check_dashboards` makes mypy resolve
# one file under two module names. `tests/scripts/test_seed_demo.py` says the
# same thing, and this is the third place to hit it.
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_dashboards.py"
_spec = importlib.util.spec_from_file_location("check_dashboards", SCRIPT)
assert _spec is not None and _spec.loader is not None
cli = importlib.util.module_from_spec(_spec)
sys.modules["check_dashboards"] = cli
_spec.loader.exec_module(cli)

RATES = Rates(
    logs_scan_price_per_gb=0.005,
    metrics_price_per_1000=0.01,
    manual_loads_per_day=4.0,
    viewing_hours_per_day=8.0,
    metrics_per_call=10.0,
    default_ingest_gb_per_day=10.0,
    assumed_query_seconds=3.0,
    refresh_warn_seconds=60,
    refresh_crit_seconds=15,
    timerange_warn_hours=168.0,
    timerange_crit_hours=720.0,
    quota_logs_concurrent=30,
    quota_getmetricdata_tps=50,
)


def ingest(_log_group: str, _region: str) -> float:
    return 10.0 / 24.0


def dashboard(refresh: str = "10s", window: str = "now-30d", **panel: Any) -> dict[str, Any]:
    target = {
        "queryMode": "Logs",
        "region": "eu-west-2",
        "expression": "fields @timestamp | filter @message like /ERROR/",
        "logGroups": [{"arn": "arn:aws:logs:eu-west-2:1:log-group:/x"}],
    }
    return {
        "title": "Platform overview",
        "refresh": refresh,
        "time": {"from": window},
        "panels": [
            {
                "title": "Error rate",
                "type": "timeseries",
                "datasource": {"type": "cloudwatch"},
                "targets": [target],
                **panel,
            }
        ],
    }


def test_a_fast_refresh_over_a_wide_window_is_refused() -> None:
    (violation,) = check(dashboard(), rates=RATES, ingest_rate=ingest)
    assert violation.panel == "Error rate"
    # The money is the argument. A message that says a panel breaks a rule is a
    # conversation about policy; one that says what it costs gets fixed.
    assert violation.monthly_cost > 0
    assert "a month" in str(violation)


def test_a_fast_refresh_over_a_narrow_window_is_allowed() -> None:
    # Half the rule is not the rule. Refusing this would block every operational
    # dashboard in the organization.
    assert check(dashboard(window="now-1h"), rates=RATES, ingest_rate=ingest) == ()


def test_a_wide_window_on_a_slow_refresh_is_allowed() -> None:
    assert check(dashboard(refresh="15m"), rates=RATES, ingest_rate=ingest) == ()


def test_a_dashboard_with_no_refresh_is_allowed() -> None:
    # Nobody is holding it open. It costs what a person opening it costs.
    assert check(dashboard(refresh=""), rates=RATES, ingest_rate=ingest) == ()


def test_the_rule_can_be_tightened() -> None:
    """Rules come from settings so a tenant can tighten them.

    An organization that decides five minutes is too fast over a day gets to say
    so, and the same dashboard is then refused.
    """
    strict = Rule(max_refresh_seconds=600, max_window_hours=1.0)
    assert check(dashboard(refresh="5m", window="now-6h"), rates=RATES, ingest_rate=ingest) == ()
    assert check(
        dashboard(refresh="5m", window="now-6h"), rates=RATES, ingest_rate=ingest, rule=strict
    )


def test_a_file_it_cannot_read_is_not_a_violation(tmp_path: Path) -> None:
    # The gate refuses what it can prove is wrong. Failing on an unparseable
    # file would make every unrelated JSON in a repository a pipeline failure.
    broken = tmp_path / "notes.json"
    broken.write_text("not json at all")
    assert cli.load(broken) is None


def test_matching_no_dashboard_is_not_a_pass(tmp_path: Path) -> None:
    """The most common way a gate ends up protecting nothing.

    A glob that matched nothing exits 2 rather than 0, so a misconfigured
    pipeline is loud rather than green.
    """
    empty = tmp_path / "nothing.json"
    empty.write_text("{}")
    assert cli.main([str(empty)]) == 2


def test_the_command_fails_the_build_rather_than_warning(tmp_path: Path) -> None:
    # ISS-096. A gate that warns is ignored regardless of its reach.
    path = tmp_path / "dash.json"
    path.write_text(json.dumps(dashboard()))
    assert cli.main([str(path)]) == 1


def test_a_clean_dashboard_passes(tmp_path: Path) -> None:
    path = tmp_path / "dash.json"
    path.write_text(json.dumps(dashboard(window="now-1h")))
    assert cli.main([str(path)]) == 0


def test_the_default_rule_is_the_one_the_task_names() -> None:
    assert DEFAULT_RULE.max_refresh_seconds == 60
    assert DEFAULT_RULE.max_window_hours == 24.0
