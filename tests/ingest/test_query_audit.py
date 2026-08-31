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
from finops_ingest.collectors.query_audit import COLLECTOR, QueryAuditCollector
from finops_ingest.registry import DEFAULT_SCHEDULE, CollectorContext
from finops_providers.fake.surface import FakeQuerySurface
from finops_query.cost_model import Rates

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
    assert count(engine, "query_definition", tenant_id) == 2
    assert count(engine, "query_finding", tenant_id) == 2


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
    assert count(engine, "query_definition", tenant_id) == 2
    assert count(engine, "query_finding", tenant_id) == 2
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
                    "SELECT d.origin, f.runs_per_day FROM query_finding f "
                    "JOIN query_definition d ON d.query_id = f.query_id "
                    "WHERE f.tenant_id = :t"
                ),
                {"t": tenant_id},
            ).all()  # type: ignore[arg-type]
        )
    # 86400 / 60, the whole day.
    assert float(rows["ALERT_RULE"]) == pytest.approx(1440.0)
    # 8 viewing hours / 10 seconds, not the whole day.
    assert float(rows["PANEL"]) == pytest.approx(RATES.viewing_hours_per_day * 3600 / 10)


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
