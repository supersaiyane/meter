"""How busy the GPU instances the bill names were, written per day. TASK-P13-006, FEAT-084.

The collector asks only about the accelerated instances the bill names in the unit's account and
Region, writes a row for each that published, none for one that did not, and a rerun of a day
removes an instance that stopped publishing from that day and from nothing else.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.ai import GpuUtilization
from finops_fakes import fixtures
from finops_fakes.ai import FakeGpuMetrics
from finops_fakes.cur import CLOSED_PERIOD, ESTATE, GPU_INSTANCES, FakeCostExport
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.gpu_utilization import GpuUtilizationCollector
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext, CollectorOutcome

pytestmark = pytest.mark.integration

CLOSED = tuple(row for row in ESTATE if row.billing_period_start == CLOSED_PERIOD)
DAY = max(row.charge_period_start for row in CLOSED)
NOW = DAY + timedelta(days=1, hours=6)
ACCOUNT = GPU_INSTANCES[0].account


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


@dataclass
class Spy:
    """The fake's metrics, recording what it was asked about."""

    asked: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    only: frozenset[str] | None = None

    def utilization(
        self,
        account: AccountKey,
        region: str,
        instances: Sequence[str],
        start: datetime,
        end: datetime,
    ) -> Iterable[GpuUtilization]:
        self.asked.append((region, tuple(instances)))
        rows = FakeGpuMetrics(at=NOW).utilization(account, region, instances, start, end)
        return [row for row in rows if self.only is None or row.instance_id in self.only]


def unit(tenant: UUID, account: str = ACCOUNT, region: str = fixtures.REGION) -> WorkUnit:
    return WorkUnit(
        tenant_id=tenant,
        collector="gpu_utilization",
        window_start=DAY,
        window_end=DAY + timedelta(days=1),
        account=AccountKey(provider=Provider.AWS, account_id=account),
        region=region,
    )


def bill(engine: Engine, tenant: UUID, ai: bool = True) -> None:
    with engine.begin() as connection:
        ensure_partition(connection, "cost_focus_daily", CLOSED_PERIOD)
        CostFocusCollector(FakeCostExport(rows=CLOSED, ai=ai), clock=lambda: NOW)(
            CollectorContext(unit=unit(tenant), connection=connection, run_id=uuid4())
        )


def run(engine: Engine, work: WorkUnit, metrics: Any) -> CollectorOutcome:
    with engine.begin() as connection:
        return GpuUtilizationCollector(metrics, clock=lambda: NOW)(
            CollectorContext(unit=work, connection=connection, run_id=uuid4())
        )


def rows(engine: Engine, tenant: UUID) -> list[Any]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    "SELECT instance_id, usage_date, gpu_count, average_percent, peak_percent "
                    "FROM gpu_utilization_daily WHERE tenant_id = :t ORDER BY instance_id"
                ),
                {"t": tenant},
            ).all()
        )


def test_the_instances_the_bill_names_are_asked_about_and_the_published_one_lands(
    engine: Engine, tenant_id: UUID
) -> None:
    bill(engine, tenant_id)
    spy = Spy()
    outcome = run(engine, unit(tenant_id), spy)

    assert spy.asked == [(fixtures.REGION, ("i-fakegpu0001", "i-fakegpu0002"))]
    found = rows(engine, tenant_id)
    assert [(row.instance_id, row.usage_date) for row in found] == [
        ("i-fakegpu0001", DAY.date())
    ], "the instance that publishes nothing has no row"
    assert outcome.items_written == 1


def test_an_account_whose_bill_names_no_gpu_asks_nothing(engine: Engine, tenant_id: UUID) -> None:
    bill(engine, tenant_id)
    spy = Spy()
    assert run(engine, unit(tenant_id, account="fake-product-b"), spy) == CollectorOutcome()
    assert spy.asked == []


def test_a_bill_without_usage_types_asks_nothing(engine: Engine, tenant_id: UUID) -> None:
    bill(engine, tenant_id, ai=False)
    spy = Spy()
    run(engine, unit(tenant_id), spy)
    assert spy.asked == []


def test_a_rerun_removes_an_instance_that_stopped_publishing_and_only_that(
    engine: Engine, tenant_id: UUID
) -> None:
    bill(engine, tenant_id)
    run(engine, unit(tenant_id), Spy())
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO gpu_utilization_daily (tenant_id, ingest_run_id, account_id, "
                "region_id, instance_id, usage_date, gpu_count, average_percent, peak_percent, "
                "samples, as_of, collected_at) VALUES (:t, :r, :a, 'us-fake-2', 'i-elsewhere', "
                ":d, 1, 5, 9, 10, :at, :at)"
            ),
            {"t": tenant_id, "r": uuid4(), "a": ACCOUNT, "d": DAY.date(), "at": NOW},
        )

    outcome = run(engine, unit(tenant_id), Spy(only=frozenset()))

    assert outcome.items_removed == 1
    assert [row.instance_id for row in rows(engine, tenant_id)] == ["i-elsewhere"]
