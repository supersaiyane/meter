"""The detector over a real table.

The arithmetic has its own suite on lists. What this asks is whether the right
days reach it: the day being judged excluded from its own baseline, a pair with
too little history left alone, and a second run leaving one row rather than two.

The estate here is built rather than inserted. A test that writes the anomaly
straight into `cost_anomaly` and then checks it is there is testing an insert. A
test that lays down a flat estate and one expensive day is testing the detector,
and reads like the situation it stands for.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_ingest.collectors.cost_anomaly import CostAnomalyCollector
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.registry import CollectorContext
from finops_query.anomaly import MINIMUM_HISTORY

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 20, 6, 0, tzinfo=UTC)
ACCOUNT = "111122223333"
SERVICE = "AmazonEC2"
STEADY = [Decimal("100.00")] * MINIMUM_HISTORY


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


def lay_down(
    engine: Engine,
    tenant: UUID,
    daily: list[Decimal],
    *,
    service: str = SERVICE,
    account: str = ACCOUNT,
) -> None:
    """One row per day, oldest first, ending yesterday.

    Ending yesterday rather than today because a period still accruing has a
    part day in it, and a part day reads as a fall rather than a spike.
    """
    end = NOW.date() - timedelta(days=1)
    with engine.begin() as connection:
        for offset, cost in enumerate(reversed(daily)):
            day = end - timedelta(days=offset)
            period = date(day.year, day.month, 1)
            ensure_partition(connection, "cost_focus_daily", period)
            start = datetime(day.year, day.month, day.day, tzinfo=UTC)
            connection.execute(
                text(
                    "INSERT INTO cost_focus_daily (tenant_id, ingest_run_id, "
                    "source_fingerprint, as_of, collected_at, billing_account_id, "
                    "sub_account_id, billing_period_start, billing_period_end, "
                    "charge_period_start, charge_period_end, provider_name, service_name, "
                    "charge_category, billed_cost, effective_cost, tags) "
                    "VALUES (:t, :run, :fp, :at, :at, 'payer', :account, :period, :period_end, "
                    ":start, :end, 'Fake', :service, 'Usage', :cost, :cost, '{}'::jsonb)"
                ),
                {
                    "t": tenant,
                    "run": uuid4(),
                    "fp": f"{account}:{service}:{day}",
                    "at": NOW,
                    "account": account,
                    "period": period,
                    "period_end": date(
                        period.year + (period.month // 12), (period.month % 12) + 1, 1
                    ),
                    "start": start,
                    "end": start + timedelta(days=1),
                    "service": service,
                    "cost": cost,
                },
            )


def detect(engine: Engine, tenant: UUID, settings: Settings) -> int:
    with engine.begin() as connection:
        outcome = CostAnomalyCollector(clock=lambda: NOW)(
            CollectorContext(
                unit=Unit(tenant_id=tenant),
                connection=connection,
                run_id=uuid4(),
                settings=settings,
            )
        )
    return int(outcome.items_written)


def anomalies(engine: Engine, tenant: UUID) -> list[tuple[str, Decimal, Decimal]]:
    with engine.connect() as connection:
        return [
            (row[0], row[1], row[2])
            for row in connection.execute(
                text(
                    "SELECT service_name, observed, delta FROM cost_anomaly "
                    "WHERE tenant_id = :t ORDER BY delta DESC"
                ),
                {"t": tenant},
            )
        ]


class TestItFindsARealSpike:
    def test_a_day_well_above_its_own_past_is_reported(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        lay_down(engine, tenant_id, [*STEADY, Decimal("900.00")])
        assert detect(engine, tenant_id, settings) == 1

        found = anomalies(engine, tenant_id)
        assert found[0][1] == Decimal("900.0000000000")
        assert found[0][2] == Decimal("800.0000000000")

    def test_the_row_carries_its_working(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # A verdict a reader cannot argue with is one they have to take on
        # trust, and nobody takes a cost alert on trust twice.
        lay_down(engine, tenant_id, [*STEADY, Decimal("900.00")])
        detect(engine, tenant_id, settings)
        with engine.connect() as connection:
            why = connection.execute(
                text("SELECT why FROM cost_anomaly WHERE tenant_id = :t"), {"t": tenant_id}
            ).scalar_one()
        assert "+800.00" in why
        assert "100.00" in why

    def test_a_steady_estate_produces_nothing(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        lay_down(engine, tenant_id, [*STEADY, Decimal("101.00")])
        assert detect(engine, tenant_id, settings) == 0
        assert anomalies(engine, tenant_id) == []


class TestTheDemoEstateIsFoundByTheDetector:
    """TASK-P1-019, and the only test in this file that uses the real fixture.

    Every other test here lays down a flat series and one expensive day, which is the
    right shape for asking whether the arithmetic reaches the right rows. This one
    asks a different question: does the estate `make seed` actually writes contain
    something this detector finds, without being told where to look.

    It matters because the demo's credibility rests on it. A row written straight into
    `cost_anomaly` would show a finding the detector never made, and the first question
    anybody asks in a demo is whether the product found it or somebody typed it.
    """

    def test_the_seeded_estate_produces_a_finding(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        from finops_ingest.collectors.cost_focus import CostFocusCollector
        from finops_providers.fake import cur
        from finops_providers.fake.cur import FakeCostExport

        at = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
        rows = cur.estate(at=at)
        period = max(row.billing_period_start for row in rows)
        with engine.begin() as connection:
            ensure_partition(connection, "cost_focus_daily", period)
            CostFocusCollector(
                FakeCostExport(rows=tuple(r for r in rows if r.billing_period_start == period)),
                clock=lambda: at,
            )(
                CollectorContext(
                    unit=Unit(tenant_id=tenant_id), connection=connection, run_id=uuid4()
                )
            )

        with engine.begin() as connection:
            outcome = CostAnomalyCollector(clock=lambda: at)(
                CollectorContext(
                    unit=Unit(tenant_id=tenant_id),
                    connection=connection,
                    run_id=uuid4(),
                    settings=settings,
                )
            )

        assert int(outcome.items_written) >= 1
        with engine.connect() as connection:
            found = connection.execute(
                text(
                    "SELECT sub_account_id, service_name, day FROM cost_anomaly "
                    "WHERE tenant_id = :t ORDER BY delta DESC"
                ),
                {"t": tenant_id},
            ).all()
        # The pair and the day the estate put wrong, not any pair on any day.
        assert (cur.SPIKE_ACCOUNT, cur.SPIKE_SERVICE, cur.spike_day(at)) == (
            found[0][0],
            found[0][1],
            found[0][2],
        )

    def test_the_same_estate_without_its_spike_produces_nothing(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The half that stops the test above passing for the wrong reason.

        An estate whose every pair drifts upward slowly could produce a finding from
        the drift alone, and then the test above would pass with the spike removed. It
        must not.
        """
        from finops_ingest.collectors.cost_focus import CostFocusCollector
        from finops_providers.fake import cur
        from finops_providers.fake.cur import FakeCostExport

        at = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
        rows = cur.estate(at=at, spike=False)
        period = max(row.billing_period_start for row in rows)
        with engine.begin() as connection:
            ensure_partition(connection, "cost_focus_daily", period)
            CostFocusCollector(
                FakeCostExport(rows=tuple(r for r in rows if r.billing_period_start == period)),
                clock=lambda: at,
            )(
                CollectorContext(
                    unit=Unit(tenant_id=tenant_id), connection=connection, run_id=uuid4()
                )
            )

        with engine.begin() as connection:
            outcome = CostAnomalyCollector(clock=lambda: at)(
                CollectorContext(
                    unit=Unit(tenant_id=tenant_id),
                    connection=connection,
                    run_id=uuid4(),
                    settings=settings,
                )
            )
        assert int(outcome.items_written) == 0


class TestItRefusesWithoutHistory:
    def test_a_pair_with_too_few_days_is_left_alone(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Not a row saying no. An empty table for a young estate is correct,
        and the screen is what has to tell a reader why it is empty."""
        short = [Decimal("100.00")] * (MINIMUM_HISTORY - 2)
        lay_down(engine, tenant_id, [*short, Decimal("900.00")])
        assert detect(engine, tenant_id, settings) == 0

    def test_one_pair_being_young_does_not_stop_another_being_judged(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        lay_down(engine, tenant_id, [*STEADY, Decimal("900.00")], service="AmazonEC2")
        lay_down(engine, tenant_id, [Decimal("50.00"), Decimal("500.00")], service="AmazonRDS")
        assert detect(engine, tenant_id, settings) == 1
        assert [row[0] for row in anomalies(engine, tenant_id)] == ["AmazonEC2"]


class TestTheDayIsNotInItsOwnBaseline:
    def test_the_whole_move_is_reported_as_the_delta(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Including the day under test drags the baseline toward it, which
        makes the detector least sensitive exactly when the move is largest.
        The sharp check is that `delta` is the full move rather than a fraction
        of it.
        """
        lay_down(engine, tenant_id, [*STEADY, Decimal("900.00")])
        detect(engine, tenant_id, settings)
        with engine.connect() as connection:
            baseline, delta = connection.execute(
                text("SELECT baseline, delta FROM cost_anomaly WHERE tenant_id = :t"),
                {"t": tenant_id},
            ).one()
        assert baseline == Decimal("100.0000000000")
        assert delta == Decimal("800.0000000000")


class TestRunningItTwice:
    def test_the_second_run_replaces_rather_than_duplicates(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # Four runs a day would otherwise show a reader the same spike four
        # times, and they would stop believing the count.
        lay_down(engine, tenant_id, [*STEADY, Decimal("900.00")])
        detect(engine, tenant_id, settings)
        detect(engine, tenant_id, settings)
        assert len(anomalies(engine, tenant_id)) == 1


class TestScope:
    def test_one_tenant_does_not_see_another(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        neighbour = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO tenant (tenant_id, name) VALUES (:id, :name)"),
                {"id": neighbour, "name": f"tenant-{neighbour}"},
            )
        lay_down(engine, neighbour, [*STEADY, Decimal("900.00")])
        lay_down(engine, tenant_id, [*STEADY, Decimal("101.00")])

        assert detect(engine, tenant_id, settings) == 0
        assert anomalies(engine, tenant_id) == []
