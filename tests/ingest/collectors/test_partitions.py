"""The parts of retention that need no container.

Split from the integration tests because a module level `pytestmark` applies to
the whole file, so these would have been deselected alongside the ones that need
a database, and a test nobody runs is a test that does not exist.
"""

from __future__ import annotations

from datetime import date

from finops_ingest.collectors.partitions import month_of, months_from, next_month, partition_name
from finops_ingest.collectors.retention import RETENTION_COLLECTORS
from finops_ingest.registry import DEFAULT_SCHEDULE, CollectorScope


def test_the_schedule_and_the_collectors_name_the_same_jobs() -> None:
    """Two lists of the same jobs is how one ends up implemented and never run."""
    scheduled = {
        entry.collector
        for entry in DEFAULT_SCHEDULE
        if entry.collector.startswith(("retention_", "partition_"))
    }
    assert scheduled == {collector.name for collector in RETENTION_COLLECTORS}


def test_retention_runs_at_organization_scope() -> None:
    """Per account would run the same work once per account over the same rows."""
    assert {c.scope for c in RETENTION_COLLECTORS} == {CollectorScope.ORGANIZATION}


def test_months_roll_over_a_year() -> None:
    assert next_month(date(2026, 12, 1)) == date(2027, 1, 1)
    assert months_from(date(2026, 11, 14), 4) == (
        date(2026, 11, 1),
        date(2026, 12, 1),
        date(2027, 1, 1),
        date(2027, 2, 1),
    )


def test_a_partition_name_round_trips_to_its_month() -> None:
    assert month_of(partition_name("cost_focus_daily", date(2026, 8, 1))) == date(2026, 8, 1)


def test_a_name_we_did_not_make_is_not_ours() -> None:
    """A hand made partition is left alone rather than removed."""
    assert month_of("cost_focus_daily_archive") is None


def test_registering_retention_adds_every_job() -> None:
    """The count is returned so a caller cannot register nothing and not notice."""
    from finops_ingest.collectors.retention import register_retention
    from finops_ingest.registry import CollectorRegistry

    registry = CollectorRegistry()
    added = register_retention(registry)

    assert added == len(RETENTION_COLLECTORS)
    assert registry.get("retention_audit").name == "retention_audit"
