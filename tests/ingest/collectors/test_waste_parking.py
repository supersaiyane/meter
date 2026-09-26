"""Parking findings, over a real database.

FEAT-054, TASK-P3-021. The fold has its own suite against lists, `tests/query/test_parking.py`,
and it owns the three refusals. What this asks is whether the right rows reach the database
and whether the ones that do say something a reader can act on.

Two cases carry this file. The saving excludes storage, because a finding that claimed the
whole monthly cost would overstate every parking recommendation in the product by the storage
share and a reader who reconciled it against their bill would stop believing the screen. And
a resource that published nothing is written to `sync_error` rather than passed over, because
an estate where nothing publishes hourly metrics produces no findings and a run reporting
none found would present a configuration gap as good news.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.metrics import MetricPoint
from finops_core.ports.metrics import MetricRequest
from finops_ingest.collectors.waste_parking import Parkable, WasteParkingCollector
from finops_ingest.registry import CollectorContext
from finops_query.parking import HOURS_IN_WEEK

pytestmark = pytest.mark.integration

# A Monday, so hour of week zero is the first reading.
MONDAY = datetime(2026, 9, 7, 0, 0, tzinfo=UTC)
NOW = MONDAY + timedelta(days=14)
ACCOUNT = AccountKey(provider=Provider.AWS, account_id="fake-platform-a")

#: Quiet from 22:00 to 04:00 every day. Six hours a night, seven nights, 42 a week.
NIGHTS = frozenset(hour for hour in range(HOURS_IN_WEEK) if hour % 24 in (22, 23, 0, 1, 2, 3))


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


class FakeHourlyMetrics:
    """Hourly readings for the resources named, and nothing for the rest.

    Absence is the interesting half, so a resource simply left out of `quiet_hours` with
    `publishes=False` returns no series at all, which is what an instance without detailed
    monitoring does.
    """

    def __init__(
        self, series: Mapping[str, frozenset[int]], *, silent: frozenset[str] = frozenset()
    ):
        self._series = series
        self._silent = silent
        self.period_seconds: int | None = None

    def read_many(
        self,
        requests: Iterable[MetricRequest],
        window_start: datetime,
        window_end: datetime,
        period_seconds: int,
    ) -> Mapping[str, tuple[MetricPoint, ...]]:
        # Recorded so a test can assert the collector asked for hourly resolution. The fold
        # is only meaningful at 3600 and nothing else in the stack would notice a caller that
        # inherited a five minute or a daily default.
        self.period_seconds = period_seconds
        # The window is honoured rather than ignored, so the fortnight comes from
        # `parking_observation_days` and a setting cut to one week makes the collector refuse
        # here as it would in production. The first draft generated a fixed fortnight whatever
        # was asked for, which made the observation window untested.
        step = timedelta(seconds=period_seconds)
        found: dict[str, tuple[MetricPoint, ...]] = {}
        for request in requests:
            if request.key in self._silent:
                continue
            quiet = self._series.get(request.key, frozenset())
            points = []
            at = window_start
            while at < window_end:
                hour = at.weekday() * 24 + at.hour
                points.append(
                    MetricPoint(
                        account_key=ACCOUNT,
                        namespace=request.namespace,
                        metric_name=request.metric_name,
                        statistic=request.statistic,
                        unit="Percent",
                        value=Decimal("2") if hour in quiet else Decimal("60"),
                        at=at,
                        as_of=at,
                        collected_at=at,
                    )
                )
                at += step
            found[request.key] = tuple(points)
        return found


def parkable(resource: str = "i-nightly", storage: str | None = "12.0000") -> Parkable:
    return Parkable(
        account_id="fake-platform-a",
        region_id="eu-west-1",
        resource_id=resource,
        hourly_rate=Decimal("0.1000"),
        storage_monthly_cost=None if storage is None else Decimal(storage),
    )


def collect(
    engine: Engine,
    tenant: UUID,
    settings: Settings,
    *,
    candidates: list[Parkable] | None = None,
    metrics: FakeHourlyMetrics | None = None,
) -> int:
    chosen = candidates if candidates is not None else [parkable()]
    source = metrics if metrics is not None else FakeHourlyMetrics({"i-nightly": NIGHTS})
    with engine.begin() as connection:
        outcome = WasteParkingCollector(source, lambda _c: chosen, clock=lambda: NOW)(
            CollectorContext(
                unit=Unit(tenant_id=tenant),
                connection=connection,
                run_id=uuid4(),
                settings=settings,
            )
        )
    return int(outcome.items_written)


def rows(engine: Engine, tenant: UUID) -> dict[str, tuple[Decimal, str, str]]:
    with engine.connect() as connection:
        return {
            row[0]: (row[1], row[2], row[3])
            for row in connection.execute(
                text(
                    "SELECT resource_id, estimated_monthly_saving, rationale, waste_class "
                    "FROM recommendation WHERE tenant_id = :t AND source = 'METER'"
                ),
                {"t": tenant},
            )
        }


def test_a_nightly_window_becomes_one_finding(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    assert collect(engine, tenant_id, settings) == 1
    saving, rationale, waste_class = rows(engine, tenant_id)["i-nightly"]
    assert waste_class == "PARKABLE_WINDOW"
    # 42 hours a week, 52 over 12 weeks a month, at 0.10 an hour.
    assert saving == Decimal("18.2000")
    assert "2 observed weeks" in rationale


def test_the_saving_excludes_the_storage_and_the_rationale_says_so(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The case this file exists for. A stopped instance still holds its volumes, so a finding
    claiming the whole monthly cost would overstate every parking recommendation by the
    storage share, and a reader reconciling it against their bill would stop believing it."""
    collect(engine, tenant_id, settings)
    _saving, rationale, _ = rows(engine, tenant_id)["i-nightly"]
    assert "Storage of 12.0000 USD a month continues while it is stopped" in rationale
    assert "not part of this saving" in rationale


def test_an_unknown_storage_cost_is_said_rather_than_omitted(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Not known is a different claim from nothing, and leaving the sentence out entirely
    would let a reader assume the saving is the whole bill."""
    collect(engine, tenant_id, settings, candidates=[parkable(storage=None)])
    _saving, rationale, _ = rows(engine, tenant_id)["i-nightly"]
    assert "What continues to be charged while it is stopped is not known" in rationale


def test_every_time_in_the_rationale_is_labelled_utc(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """ISS-206. Meter holds no tenant timezone, so a bare 22:00 would be read as local time by
    whoever opens the screen, and the whole point of naming a window is that somebody acts."""
    collect(engine, tenant_id, settings)
    _saving, rationale, _ = rows(engine, tenant_id)["i-nightly"]
    assert "UTC" in rationale
    assert "Meter holds no timezone for this tenant" in rationale


def test_the_collector_asks_for_hourly_resolution(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The fold is only meaningful at an hourly period, and nothing else in the stack would
    notice a caller that inherited a five minute or a daily default."""
    metrics = FakeHourlyMetrics({"i-nightly": NIGHTS})
    collect(engine, tenant_id, settings, metrics=metrics)
    assert metrics.period_seconds == 3600


def test_a_resource_publishing_nothing_is_recorded_rather_than_passed_over(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The second case this file exists for. An estate where nothing publishes hourly metrics
    produces no findings, and a run that reported none found would present a configuration
    gap as good news."""
    metrics = FakeHourlyMetrics({}, silent=frozenset({"i-nightly"}))
    assert collect(engine, tenant_id, settings, metrics=metrics) == 0
    with engine.connect() as connection:
        error = connection.execute(
            text(
                "SELECT error_type, detail FROM sync_error "
                "WHERE tenant_id = :t AND collector = 'waste_parking'"
            ),
            {"t": tenant_id},
        ).one()
    assert error[0] == "NoData"
    assert "published no hourly metrics" in error[1]


def test_a_busy_resource_writes_nothing_at_all(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    metrics = FakeHourlyMetrics({"i-nightly": frozenset()})
    assert collect(engine, tenant_id, settings, metrics=metrics) == 0
    assert rows(engine, tenant_id) == {}


def test_a_resource_quiet_all_week_writes_nothing_here(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """It is IDLE_INSTANCE, which says delete it. Two findings on one resource, one saying
    schedule it and one saying delete it, is a pair a reader cannot act on."""
    metrics = FakeHourlyMetrics({"i-nightly": frozenset(range(HOURS_IN_WEEK))})
    assert collect(engine, tenant_id, settings, metrics=metrics) == 0
    assert rows(engine, tenant_id) == {}


def test_the_finding_opens_with_exactly_one_lifecycle_event(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Run twice. The second run updates the finding rather than opening a second one, and it
    does not append a second opening event to something already open."""
    collect(engine, tenant_id, settings)
    collect(engine, tenant_id, settings)
    with engine.connect() as connection:
        events = connection.execute(
            text(
                "SELECT count(*) FROM recommendation_event e "
                "JOIN recommendation r ON r.recommendation_id = e.recommendation_id "
                "WHERE r.tenant_id = :t AND r.source_reference = 'parking:i-nightly'"
            ),
            {"t": tenant_id},
        ).scalar_one()
    assert events == 1
    assert len(rows(engine, tenant_id)) == 1


def test_it_refuses_to_run_without_settings(engine: Engine, tenant_id: UUID) -> None:
    """Four of its rules decide what gets flagged on somebody's production schedule.
    Defaulting them would put a threshold nobody chose onto a finding that asks an engineer
    to stop a workload."""
    with engine.begin() as connection, pytest.raises(ValueError, match="configuration"):
        WasteParkingCollector(FakeHourlyMetrics({}), lambda _c: [parkable()], clock=lambda: NOW)(
            CollectorContext(
                unit=Unit(tenant_id=tenant_id),
                connection=connection,
                run_id=uuid4(),
                settings=None,
            )
        )


def test_a_shorter_observation_window_refuses_rather_than_folding_one_week(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The observation window is a setting, and this is what it buys. Cut to seven days, the
    fortnight becomes one week, one week holds exactly one of each weekday, and the collector
    writes nothing rather than calling one bank holiday the normal shape of the week."""
    one_week = settings.model_copy(update={"parking_observation_days": 7})
    assert collect(engine, tenant_id, one_week) == 0
    assert rows(engine, tenant_id) == {}
