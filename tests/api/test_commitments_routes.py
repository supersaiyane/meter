"""The commitment routes, read through the API as a person reads them. P14, FEAT-086 to 090.

TASK-P14-004 first: the effective savings rate by billing month, measured from the bill. The fake
estate's bill is collected for two months, one of them with every List Cost removed, and read by a
reader of the whole estate and by one narrowed to an account.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from functools import partial
from operator import add
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine

from finops_core.config import Settings
from finops_core.domain.cost import CostRecord
from finops_fakes.cur import CLOSED_PERIOD, ESTATE, FakeCostExport
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext
from finops_query.savings_rate import NO_LIST_COST
from tests.api.test_query_routes import client_for
from tests.api.test_waste_routes import everything, get, only

pytestmark = pytest.mark.integration

RATE = "/api/v1/commitments/savings-rate"
EARLIER = CLOSED_PERIOD.replace(month=CLOSED_PERIOD.month - 1)
ACCOUNT = "fake-platform-a"


def month(period: Any) -> tuple[CostRecord, ...]:
    return tuple(row for row in ESTATE if row.billing_period_start == period)


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


@pytest.fixture
def billed(engine: Engine, tenant_id: UUID) -> UUID:
    unlisted = tuple(replace(row, list_cost=None) for row in month(EARLIER))
    for rows in (unlisted, month(CLOSED_PERIOD)):
        last = max(row.charge_period_start for row in rows)
        work = WorkUnit(
            tenant_id=tenant_id,
            collector="cost_focus",
            window_start=last,
            window_end=last + timedelta(days=1),
        )
        collector = CostFocusCollector(
            FakeCostExport(rows=rows), clock=partial(add, last, timedelta(days=2))
        )
        with engine.begin() as connection:
            ensure_partition(connection, "cost_focus_daily", rows[0].billing_period_start)
            collector(CollectorContext(unit=work, connection=connection, run_id=uuid4()))
    return tenant_id


def expected(rows: tuple[CostRecord, ...]) -> Decimal:
    listed = [row for row in rows if row.list_cost is not None and row.charge_category == "Usage"]
    effective = sum((row.effective_cost for row in listed), Decimal(0))
    return (
        Decimal(1) - effective / sum((row.list_cost or 0 for row in listed), Decimal(0))
    ).quantize(Decimal("0.0001"))


def read(engine: Engine, settings: Settings, tenant: UUID, account: str = "") -> Any:
    scope = only(tenant, account) if account else everything(tenant)
    client, token = client_for(engine, scope, settings)
    return get(client, token, RATE)


def test_the_rate_is_measured_from_the_bills_own_sums(
    engine: Engine, settings: Settings, billed: UUID
) -> None:
    found = read(engine, settings, billed)
    by_period = {one["period"]: one for one in found["data"]["months"]}
    closed = by_period[CLOSED_PERIOD.isoformat()]
    assert Decimal(closed["rate"]) == expected(month(CLOSED_PERIOD))
    assert (closed["rate_basis"], closed["reason"], closed["lines_without_list_cost"]) == (
        "measured",
        None,
        0,
    )
    assert found["meta"]["as_of"] is not None and found["meta"]["collected_at"] is not None


def test_a_month_whose_lines_carry_no_list_cost_has_no_rate_never_nought(
    engine: Engine, settings: Settings, billed: UUID
) -> None:
    by_period = {one["period"]: one for one in read(engine, settings, billed)["data"]["months"]}
    earlier = by_period[EARLIER.isoformat()]
    assert (earlier["rate"], earlier["reason"]) == (None, NO_LIST_COST)
    assert earlier["lines"] == earlier["lines_without_list_cost"] > 0
    assert Decimal(earlier["effective_cost_without_list_cost"]) > 0


def test_a_narrowed_reader_reads_the_rate_of_their_own_accounts(
    engine: Engine, settings: Settings, billed: UUID
) -> None:
    found = read(engine, settings, billed, account=ACCOUNT)
    by_period = {one["period"]: one for one in found["data"]["months"]}
    own = tuple(row for row in month(CLOSED_PERIOD) if row.sub_account_id == ACCOUNT)
    assert Decimal(by_period[CLOSED_PERIOD.isoformat()]["rate"]) == expected(own)


def test_a_tenant_with_no_bill_has_no_months_rather_than_rates_of_nought(
    engine: Engine, settings: Settings, tenant_id: UUID
) -> None:
    assert read(engine, settings, tenant_id)["data"]["months"] == []
