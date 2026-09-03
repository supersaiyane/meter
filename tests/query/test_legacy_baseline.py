"""What the prototype does today, pinned before anything changes it.

This is TASK-P2-001 and it asserts nothing about whether the prototype is
correct. Several of these goldens almost certainly record behaviour that is
wrong, and that is the point: the next three tasks take the file apart, and the
only way to know that the extraction preserved behaviour is to have written the
behaviour down first.

So the rule while these files exist is that a golden file is never regenerated
in the same commit as the change it was meant to catch. When a golden changes,
the diff is the evidence, and it belongs in the commit message.

Only two entry points are pinned: `analyze_dashboard` and `analyze_alert_rules`.
They are the only parts of the file reachable without AWS, because every other
path opens a client. Pinning the rest would mean mocking boto3 in a baseline
test, and a baseline whose shape is decided by the mocks is not a baseline.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.query.conftest import REGION

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DASHBOARDS = FIXTURES / "dashboards"
ALERTS = FIXTURES / "alerts"
GOLDEN = FIXTURES / "golden"

#: Set to regenerate. Deliberately awkward to type, and deliberately not a
#: pytest flag: regenerating should be a decision somebody made on purpose,
#: not something that happens because a flag was left on in a shell history.
REGENERATE = os.environ.get("METER_REGENERATE_GOLDEN") == "yes-i-mean-it"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def compare(name: str, produced: Any) -> None:
    """Assert against the golden, or write it when regenerating.

    A missing golden fails rather than being created quietly. A test that
    creates its own expectation on first run passes on every first run, which
    includes the run after somebody deletes the file to make a failure go away.
    """
    path = GOLDEN / f"{name}.json"
    rendered = json.dumps(produced, indent=2, sort_keys=True, default=str) + "\n"

    if REGENERATE:
        path.write_text(rendered, encoding="utf-8")
        pytest.skip(f"regenerated {path.name}")

    assert path.exists(), (
        f"{path.name} does not exist. Generate it with "
        "METER_REGENERATE_GOLDEN=yes-i-mean-it pytest tests/query, and commit it "
        "in a change that does not also alter the prototype."
    )
    assert rendered == path.read_text(encoding="utf-8"), (
        f"{name} no longer reproduces its golden file. If the change is intended, "
        "regenerate and put the diff in the commit message."
    )


def dashboard_names() -> list[str]:
    return sorted(p.stem for p in DASHBOARDS.glob("*.json"))


@pytest.mark.parametrize("name", dashboard_names())
def test_a_dashboard_reproduces_its_golden(
    name: str, legacy: ModuleType, cfg: Any, ingest_cache: dict[tuple[str, str], float]
) -> None:
    produced = legacy.analyze_dashboard(
        load(DASHBOARDS / f"{name}.json"),
        None,
        REGION,
        ingest_cache,
        cfg,
    )
    compare(f"dashboard-{name}", produced)


def test_the_alert_rules_reproduce_their_golden(
    legacy: ModuleType, cfg: Any, ingest_cache: dict[tuple[str, str], float]
) -> None:
    produced = legacy.analyze_alert_rules(
        load(ALERTS / "alert-rules.json"),
        None,
        REGION,
        ingest_cache,
        cfg,
    )
    compare("alerts", produced)


# --- what the fixture set has to cover ---------------------------------------


def test_every_engine_is_represented(
    legacy: ModuleType, cfg: Any, ingest_cache: dict[tuple[str, str], float]
) -> None:
    """A baseline that never exercises an engine pins nothing about it, and the
    extraction that breaks it would pass."""
    engines = set()
    for name in dashboard_names():
        result = legacy.analyze_dashboard(
            load(DASHBOARDS / f"{name}.json"), None, REGION, ingest_cache, cfg
        )
        engines |= {finding["engine"] for finding in result["findings"]}

    assert {"logs_insights", "metric_search", "metrics_insights", "prometheus"} <= engines


def test_there_are_at_least_twelve_dashboards() -> None:
    """The acceptance criterion. Counted so that deleting one is a decision."""
    assert len(dashboard_names()) >= 12


def test_the_prototype_is_not_asked_for_anything_it_cannot_answer_offline(cfg: Any) -> None:
    """The two switches that keep this offline, asserted rather than assumed.

    If `measure_ingestion` were ever true here, the fallback would be replaced
    by a CloudWatch call, the goldens would depend on a real account, and the
    suite would fail in a way that looks like a code change.
    """
    assert cfg["measure_ingestion"] is False
    assert cfg["measure_executions"] is False


def test_a_session_is_never_used(
    legacy: ModuleType, cfg: Any, ingest_cache: dict[tuple[str, str], float]
) -> None:
    """None is passed as the session, so any AWS call raises rather than
    silently succeeding against ambient credentials."""

    class Exploding:
        def __getattr__(self, name: str) -> Any:
            raise AssertionError(f"the analysis path reached AWS through .{name}")

    for name in dashboard_names():
        legacy.analyze_dashboard(
            load(DASHBOARDS / f"{name}.json"), Exploding(), REGION, ingest_cache, cfg
        )
