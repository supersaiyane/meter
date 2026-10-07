"""Every collector that exists has a cadence, and every cadence explains itself.

This file exists because five collectors did not. `commitment` and `cost_anomaly`
from P1, and `recommendations`, `waste_compute` and `waste_cloudwatch` from P3, were
each written, tested and merged without an entry in `DEFAULT_SCHEDULE`, and
`due_collectors` reads that table and nothing else. So all five imported cleanly,
passed their own tests, and never ran. ISS-190.

Their tests called them directly, which is the same hollow signal as a test pinned
to a screen path that shipped: the thing under test worked and the wiring did not,
and only the wiring was in production. So the list here is derived from the source
rather than restated, because a list that has to be kept in step by hand is the
defect it is meant to catch.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from finops_ingest.registry import DAILY, DEFAULT_SCHEDULE, SIX_HOURLY, ScheduleEntry

COLLECTORS = Path(__file__).resolve().parents[2] / "finops_ingest" / "collectors"

#: The module level constant each collector names itself with, for example
#: `COLLECTOR = "waste_compute"`.
NAME = re.compile(r'^COLLECTOR = "([a-z_]+)"$', re.MULTILINE)


def collector_names() -> frozenset[str]:
    """Every name declared under `finops_ingest/collectors/`.

    Read from the files rather than imported, so a collector whose import fails
    still shows up as one needing a cadence. Retention and partition jobs live in
    one module each and declare their names differently, so they are covered by
    `scheduled_names` below rather than found here.
    """
    found: set[str] = set()
    for module in COLLECTORS.glob("*.py"):
        if module.name == "__init__.py":
            continue
        found.update(NAME.findall(module.read_text()))
    return frozenset(found)


def scheduled_names() -> frozenset[str]:
    return frozenset(entry.collector for entry in DEFAULT_SCHEDULE)


def test_the_scan_finds_the_collectors_that_exist() -> None:
    """The gate's own input, checked before the gate is trusted.

    A regex that matched nothing would make the test below pass for every possible
    state of the schedule, which is the failure mode of every source scanning
    check. The floor is the count at the time of writing, so adding a collector
    does not have to come back here.
    """
    found = collector_names()
    assert len(found) >= 10, f"the scan found only {sorted(found)}"
    assert "waste_compute" in found
    assert "cost_focus" in found


def test_every_collector_has_a_cadence() -> None:
    missing = collector_names() - scheduled_names()
    assert not missing, (
        f"these collectors have no DEFAULT_SCHEDULE entry, so due_collectors will "
        f"never return them and they will never run: {sorted(missing)}"
    )


def test_no_cadence_names_a_collector_that_does_not_exist() -> None:
    """The other direction, which is a different bug.

    An entry for a collector nobody can run installs a row whose `finished_at`
    stays null forever, and the freshness screen reports it as permanently stale.
    The retention and partition jobs are the exception: they are several collectors
    inside two modules and do not each declare a `COLLECTOR` constant.
    """
    from finops_ingest.registry import governed_by_retention_flag

    unknown = {
        name for name in worker_names() - collector_names() if not governed_by_retention_flag(name)
    }
    assert not unknown, f"scheduled but not implemented: {sorted(unknown)}"


def worker_names() -> frozenset[str]:
    return frozenset(entry.collector for entry in DEFAULT_SCHEDULE if entry.runs_in == "worker")


def test_a_cadence_the_api_runs_names_what_the_api_runs() -> None:
    """ADR-0033. The scheduled reports are looked at by the API, not by a collector, so their
    cadence names the API's runner, and nothing else may claim to run there."""
    from finops_api.exports.scheduled import COLLECTOR

    in_the_api = {entry.collector for entry in DEFAULT_SCHEDULE if entry.runs_in == "api"}
    assert in_the_api == {COLLECTOR}
    assert {entry.runs_in for entry in DEFAULT_SCHEDULE} == {"worker", "api"}


def test_the_migration_installs_the_cadence_the_registry_declares() -> None:
    """Migration 0029 installs the runner's row for the tenants that existed before it, and
    `install_default_schedule` for every tenant after, so the two must say the same thing."""
    import importlib.util

    from finops_api.exports.scheduled import COLLECTOR

    migration = Path(__file__).resolve().parents[2] / "migrations/versions/0029_report_schedule.py"
    spec = importlib.util.spec_from_file_location("migration_0029", migration)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entry = next(e for e in DEFAULT_SCHEDULE if e.collector == COLLECTOR)
    declared = (entry.cadence_seconds, entry.reason, entry.est_cost_per_run)
    installed = (module._CADENCE_SECONDS, module._REASON, module._COST_PER_RUN)
    assert installed == declared


@pytest.mark.parametrize("entry", DEFAULT_SCHEDULE, ids=lambda e: e.collector)
def test_every_cadence_explains_itself(entry: ScheduleEntry) -> None:
    """ADR-0012 and constraint 9.

    A cadence nobody can explain is a number nobody can safely change, and the
    first thing anyone does with an unexplained interval under cost pressure is
    double it. The length floor is crude and deliberate: it refuses a reason of
    "daily" without arguing about prose.
    """
    assert len(entry.reason) > 80, f"{entry.collector} has a reason nobody can act on"
    assert entry.cadence_seconds > 0
    # A cost is a decision, so it is stated even when it is zero. An absent cost
    # reads as unknown, and an unknown cost is the one nobody puts in a budget.
    assert entry.est_cost_per_run


def test_the_p3_cadences_are_the_ones_the_specification_asks_for() -> None:
    """Checked against the spec rather than against somebody's judgement.

    P3 section 7 sets the AWS native source and realized savings daily, and the
    bespoke collectors and the score every six hours. The expensive one is
    `waste_compute`, because GetMetricData is charged per metric requested and the
    batched read asks for four per instance over fourteen days, so its entry has to
    carry the trade rather than only the number. ISS-194 keeps that argument open.
    """
    by_name = {entry.collector: entry for entry in DEFAULT_SCHEDULE}
    for name in ("recommendations", "realized_savings"):
        assert by_name[name].cadence_seconds == DAILY, name
    for name in ("waste_compute", "waste_cloudwatch", "finops_score"):
        assert by_name[name].cadence_seconds == SIX_HOURLY, name
    assert by_name["waste_compute"].est_cost_per_run != "0"
    assert "GetMetricData" in by_name["waste_compute"].reason
