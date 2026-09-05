"""The query audit collector, against a real database.

The three behaviours asserted here are the ones a script would get wrong: a
workspace it cannot read must not fail the run, the same day surveyed three
times must leave one finding, and every figure written must say it is modelled.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, text

from finops_core.errors import AccessDenied
from finops_ingest.collectors.query_audit import (
    COLLECTOR,
    QueryAuditCollector,
    default_ingest_rate,
)
from finops_ingest.registry import DEFAULT_SCHEDULE, CollectorContext
from finops_providers.fake.evidence import FakeQueryEvidence
from finops_providers.fake.surface import FakeQuerySurface
from finops_query.cost_model import Rates
from finops_query.parser import GrafanaQueryParser

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 31, 6, 0, tzinfo=UTC)

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


def ingest_rate(_account: str, _region: str) -> float:
    return 10.0


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID
    scope_key: str = "organization"


def run(engine: Engine, tenant: UUID, surface: Any) -> int:
    collector = QueryAuditCollector(surface, RATES, ingest_rate, clock=lambda: NOW)
    with engine.begin() as connection:
        outcome = collector(CollectorContext(unit=Unit(tenant_id=tenant), connection=connection))
    return outcome.items_written


def count(engine: Engine, table: str, tenant: UUID) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"), {"t": tenant}
            ).scalar_one()
        )


def test_it_is_registered_at_six_hours_with_a_reason() -> None:
    # ADR-0012: cadence is data, and a cadence nobody can explain is a number
    # nobody can safely change.
    entry = next(e for e in DEFAULT_SCHEDULE if e.collector == COLLECTOR)
    assert entry.cadence_seconds == 21600
    assert len(entry.reason) > 80


def test_it_writes_the_estate_and_prices_what_it_read(engine: Engine, tenant_id: UUID) -> None:
    run(engine, tenant_id, FakeQuerySurface())
    assert count(engine, "grafana_instance", tenant_id) == 3
    # The fake holds two queries on one reachable instance, and none on the other.
    assert count(engine, "query_definition", tenant_id) == 3
    assert count(engine, "query_finding", tenant_id) == 3


def test_every_figure_it_writes_is_modelled_and_says_so(engine: Engine, tenant_id: UUID) -> None:
    # The measured overlay is TASK-P2-013. Until then a run that claimed a
    # measured count would be rejected by the schema, which is the point.
    run(engine, tenant_id, FakeQuerySurface())
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT provenance, measured_runs FROM query_finding WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).all()
    assert rows
    assert all(provenance == "modelled" and measured is None for provenance, measured in rows)


def test_an_unreachable_instance_is_recorded_and_does_not_fail_the_run(
    engine: Engine, tenant_id: UUID
) -> None:
    # A run that aborted on the first unreadable workspace would report nothing
    # about the ones it could read.
    run(engine, tenant_id, FakeQuerySurface())
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT reachable, unreachable_reason FROM grafana_instance "
                "WHERE tenant_id = :t AND name = 'meter-prod-eu-west-1'"
            ),
            {"t": tenant_id},
        ).one()
    assert row[0] is False
    assert row[1] == "AccessDenied"


def test_an_instance_that_fails_mid_read_is_marked_and_the_run_continues(
    engine: Engine, tenant_id: UUID
) -> None:
    reachable = [i for i in FakeQuerySurface().discover() if i.reachable]
    surface = FakeQuerySurface(failures={reachable[0].scope_key: AccessDenied})
    run(engine, tenant_id, surface)

    with engine.connect() as connection:
        marked = connection.execute(
            text(
                "SELECT unreachable_reason FROM grafana_instance "
                "WHERE tenant_id = :t AND name = :name"
            ),
            {"t": tenant_id, "name": reachable[0].name},
        ).scalar_one()
    assert marked == "AccessDenied"
    # All three instances still written, so the estate is not silently smaller.
    assert count(engine, "grafana_instance", tenant_id) == 3


def test_three_runs_in_one_day_leave_one_finding_per_query(engine: Engine, tenant_id: UUID) -> None:
    # A collector that appended would triple every cost on the front page by
    # dinner time.
    for _ in range(3):
        run(engine, tenant_id, FakeQuerySurface())
    assert count(engine, "query_definition", tenant_id) == 3
    assert count(engine, "query_finding", tenant_id) == 3
    assert count(engine, "grafana_instance", tenant_id) == 3


def test_an_alert_is_counted_over_the_whole_day_and_a_panel_is_not(
    engine: Engine, tenant_id: UUID
) -> None:
    """The two use different formulas, which is the point.

    An alert runs on its interval whether anybody is watching, so it is counted
    over 24 hours. A panel is counted over the viewing hours only.

    This does not mean an alert always outruns a panel. The fixture's panel
    refreshes every 10 seconds and beats a 60 second alert, and the first
    version of this test asserted otherwise, which encoded a belief that is not
    true in general.
    """
    run(engine, tenant_id, FakeQuerySurface())
    with engine.connect() as connection:
        rows: dict[str, Any] = dict(
            connection.execute(
                text(
                    "SELECT CASE WHEN d.origin = 'ALERT_RULE' THEN 'ALERT_RULE' "
                    "ELSE d.panel_id END, f.runs_per_day FROM query_finding f "
                    "JOIN query_definition d ON d.query_id = f.query_id "
                    "WHERE f.tenant_id = :t"
                ),
                {"t": tenant_id},
            ).all()  # type: ignore[arg-type]
        )
    # 86400 / 60, the whole day.
    assert float(rows["ALERT_RULE"]) == pytest.approx(1440.0)
    # 8 viewing hours / 10 seconds, not the whole day. Selected by panel rather
    # than by origin, because the estate holds more than one panel and keying a
    # dict on origin would silently keep whichever row came back last.
    assert float(rows["Error rate by service"]) == pytest.approx(
        RATES.viewing_hours_per_day * 3600 / 10
    )


def test_every_finding_carries_prose_saying_what_drives_the_cost(
    engine: Engine, tenant_id: UUID
) -> None:
    run(engine, tenant_id, FakeQuerySurface())
    with engine.connect() as connection:
        whys = (
            connection.execute(
                text("SELECT why FROM query_finding WHERE tenant_id = :t"), {"t": tenant_id}
            )
            .scalars()
            .all()
        )
    assert whys
    assert all(why.strip() for why in whys)


def test_every_definition_is_written_with_its_query_key(engine: Engine, tenant_id: UUID) -> None:
    # TASK-P2-013 attaches measured evidence by this key, so a null one is a
    # definition no measurement can ever reach.
    run(engine, tenant_id, FakeQuerySurface())
    with engine.connect() as connection:
        keys = (
            connection.execute(
                text("SELECT query_key FROM query_definition WHERE tenant_id = :t"),
                {"t": tenant_id},
            )
            .scalars()
            .all()
        )
    assert keys
    assert all(key for key in keys)
    # The fixture's panel and alert run the same text against the same log
    # group, so those two share a key, which is the designed behaviour rather
    # than a collision. The third query is worded differently and keeps its own.
    # attaching the evidence to both is the honest answer. They keep separate
    # fingerprints, so neither definition is lost.
    assert len(set(keys)) == 2
    with engine.connect() as connection:
        prints = (
            connection.execute(
                text("SELECT fingerprint FROM query_definition WHERE tenant_id = :t"),
                {"t": tenant_id},
            )
            .scalars()
            .all()
        )
    assert len(set(prints)) == 3


def test_the_default_ingest_rate_is_per_hour_not_per_day() -> None:
    """The unit conversion, pinned.

    `_logs_insights_cost` multiplies this by a window in hours, so the callable
    must return GB per hour while the setting is GB per day. Passing the setting
    straight through overstates every Logs Insights figure by exactly 24, which
    is large enough to be obvious in a total and small enough to be mistaken for
    one very bad dashboard.
    """

    class Settings:
        query_default_ingest_gb_per_day = 48.0

    rate = default_ingest_rate(Settings())
    assert rate("111122223333", "eu-west-2") == 2.0


# --- the measured overlay, FEAT-013 -------------------------------------------


def run_with_evidence(engine: Engine, tenant: UUID, evidence: Any) -> int:
    collector = QueryAuditCollector(
        FakeQuerySurface(), RATES, ingest_rate, clock=lambda: NOW, evidence=evidence
    )
    with engine.begin() as connection:
        outcome = collector(CollectorContext(unit=Unit(tenant_id=tenant), connection=connection))
    return outcome.items_written


def findings(engine: Engine, tenant: UUID) -> list[Any]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    "SELECT d.panel_id, f.provenance, f.measured_runs, f.runs_per_day, f.why "
                    "FROM query_finding f JOIN query_definition d ON d.query_id = f.query_id "
                    "WHERE f.tenant_id = :t ORDER BY d.panel_id"
                ),
                {"t": tenant},
            ).all()
        )


@pytest.mark.integration
def test_a_matched_finding_is_promoted_to_measured(engine: Engine, tenant_id: UUID) -> None:
    run_with_evidence(engine, tenant_id, FakeQueryEvidence(GrafanaQueryParser()))
    promoted = [row for row in findings(engine, tenant_id) if row[1] == "measured"]
    assert promoted, "the observed panel query should have been promoted"
    for _element, _provenance, measured_runs, _runs, why in promoted:
        # The schema refuses a measured row without a count, so this is also
        # proof the write was accepted rather than silently skipped.
        assert measured_runs and measured_runs > 0
        assert "MEASURED" in why


@pytest.mark.integration
def test_an_unmatched_finding_stays_modelled(engine: Engine, tenant_id: UUID) -> None:
    """A normal state, not a degraded one.

    The evidence here is for a query the estate does not contain. Note that the
    fake estate's panel and alert deliberately share their query text, so
    evidence matching one matches both: proving this needs observations that
    match neither, rather than a fixture where one happens to be unobserved.
    """
    unrelated = FakeQueryEvidence(
        GrafanaQueryParser(),
        logs={
            "fields @timestamp | filter service = 'billing'": {
                "runs": 99,
                "bytes": 0.0,
                "runs_bytes": [],
                "log_groups": {"/aws/lambda/billing"},
            }
        },
    )
    run_with_evidence(engine, tenant_id, unrelated)
    rows = findings(engine, tenant_id)
    assert rows
    for _panel, provenance, measured_runs, _runs, _why in rows:
        assert provenance == "modelled"
        assert measured_runs is None


@pytest.mark.integration
def test_absent_evidence_is_not_zero_runs(engine: Engine, tenant_id: UUID) -> None:
    """The rule the task states as a Do not.

    With no evidence source at all, every finding keeps its modelled run count.
    A collector that wrote zero would be claiming the query never ran, when the
    truth is that nobody watched.
    """
    run_with_evidence(engine, tenant_id, None)
    rows = findings(engine, tenant_id)
    assert rows
    for _element, provenance, measured_runs, runs, _why in rows:
        assert provenance == "modelled"
        assert measured_runs is None
        assert float(runs) > 0


@pytest.mark.integration
def test_evidence_that_cannot_be_read_leaves_the_run_standing(
    engine: Engine, tenant_id: UUID
) -> None:
    # A modelled estate is still worth reporting. An aborted one is not.
    run_with_evidence(
        engine, tenant_id, FakeQueryEvidence(GrafanaQueryParser(), failure=AccessDenied)
    )
    rows = findings(engine, tenant_id)
    assert rows
    assert all(provenance == "modelled" for _e, provenance, *_r in rows)


@pytest.mark.integration
def test_a_measured_figure_says_which_grade_of_measurement_it_is(
    engine: Engine, tenant_id: UUID
) -> None:
    """Runs and bytes observed reads differently from runs observed alone.

    A reader who cannot tell those apart treats both as an estimate, and then
    ignores both.
    """
    run_with_evidence(engine, tenant_id, FakeQueryEvidence(GrafanaQueryParser()))
    whys = [row[4] for row in findings(engine, tenant_id) if row[1] == "measured"]
    assert whys
    assert any("Bytes scanned + runs MEASURED" in why for why in whys)


@pytest.mark.integration
def test_running_twice_with_evidence_still_leaves_one_finding(
    engine: Engine, tenant_id: UUID
) -> None:
    # The upsert has to carry provenance and measured_runs too, or a second run
    # would leave a measured row with a modelled count beside it.
    for _ in range(2):
        run_with_evidence(engine, tenant_id, FakeQueryEvidence(GrafanaQueryParser()))
    assert len(findings(engine, tenant_id)) == 3
