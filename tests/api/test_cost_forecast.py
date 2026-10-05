"""The spend forecast, called through the client. FEAT-066, TASK-P8-008.

The forecast's arithmetic is proved against known series in `tests/query/test_forecast.py`. What
is proved here is the wiring: that the route forecasts from exactly the line items the scope may
see, summed by UTC day, with a collected day that billed nothing as a zero. So every assertion
recomputes the answer with the same functions over the seeded rows and asks the route to agree,
whether the answer is a range or a refusal.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from finops_api.routes.forecast import HISTORY_MONTHS, months_before
from finops_core.config import Settings
from finops_core.domain.cost import CostRecord
from finops_fakes.cur import FakeCostExport, estate
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.registry import CollectorContext
from finops_query.forecast import MIN_HELD_OUT, Outcome, ahead, month_end
from tests.api.test_cost_routes import (
    CURRENT,
    NOW,
    ONE_ACCOUNT,
    OPEN_ENOUGH,
    Unit,
    everything,
    only,
)
from tests.api.test_query_routes import auth, client_for

pytestmark = pytest.mark.integration

PATH = "/api/v1/cost/forecast"

#: Eight months, enough for the forecast to be tested and then shown or refused on its merits.
LONG = estate(at=OPEN_ENOUGH, periods=8)


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


def seed(engine: Engine, tenant: UUID, rows: tuple[CostRecord, ...]) -> None:
    """One collector run per billing month, oldest first, the way a backfill arrives."""
    months = sorted({row.billing_period_start for row in rows})
    with engine.begin() as connection:
        for month in months:
            ensure_partition(connection, "cost_focus_daily", month)
    for month in months:
        export = FakeCostExport(
            rows=tuple(row for row in rows if row.billing_period_start == month), split=False
        )
        with engine.begin() as connection:
            CostFocusCollector(export, clock=lambda: NOW)(
                CollectorContext(unit=Unit(tenant_id=tenant), connection=connection, run_id=uuid4())
            )


def expected(rows: Iterable[CostRecord]) -> tuple[Outcome, tuple[Outcome, ...], date]:
    """The forecast, computed here from the seeded rows by the functions the route calls."""
    mine = list(rows)
    by_day: dict[date, Decimal] = {}
    for row in mine:
        day = row.charge_period_start.astimezone(UTC).date()
        by_day[day] = by_day.get(day, Decimal(0)) + row.effective_cost
    last = max(row.charge_period_start for row in mine).astimezone(UTC).date()
    month_start = datetime.now(UTC).date().replace(day=1)
    first = min(row.billing_period_start for row in mine)
    start = max(first, months_before(month_start, HISTORY_MONTHS))
    daily = {
        start + timedelta(days=offset): by_day.get(start + timedelta(days=offset), Decimal(0))
        for offset in range((last - start).days + 1)
    }
    cut = last + timedelta(days=1)
    return month_end(daily, month_start, cut), ahead(daily, month_start, cut), last


def forecast(client: TestClient, token: str) -> dict[str, Any]:
    response = client.get(PATH, headers=auth(token))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert isinstance(data, dict)
    return data


def agrees(got: dict[str, Any], want: Outcome) -> None:
    """The route said what the same function says about the same days."""
    assert got["month"] == want.month.isoformat()
    assert got["withheld"] == want.withheld
    assert got["held_out"] == sum(1 for test in want.tests if test.usable)
    if want.figure is None:
        assert got["figure"] is None
    else:
        assert got["figure"] is not None
        assert Decimal(got["figure"]["low"]) == want.figure.low
        assert Decimal(got["figure"]["high"]) == want.figure.high


@pytest.fixture
def long_estate(engine: Engine, tenant_id: UUID, settings: Settings) -> tuple[TestClient, str]:
    seed(engine, tenant_id, LONG)
    return client_for(engine, everything(tenant_id), settings)


class TestTheForecast:
    def test_is_the_forecast_of_exactly_the_line_items_in_scope(
        self, long_estate: tuple[TestClient, str]
    ) -> None:
        data = forecast(*long_estate)
        month, later, last = expected(LONG)
        assert data["billed_through"] == last.isoformat()
        agrees(data["month_end"], month)
        assert len(data["ahead"]) == len(later)
        for got, want in zip(data["ahead"], later, strict=True):
            agrees(got, want)

    def test_says_it_is_a_forecast_and_names_its_method(
        self, long_estate: tuple[TestClient, str]
    ) -> None:
        data = forecast(*long_estate)
        assert data["provenance"] == "forecast"
        assert data["method"] == "weekday profile"
        assert data["interval_percent"] == 80
        assert Decimal(data["max_median_miss"]) == Decimal("0.15")
        assert data["min_held_out"] == MIN_HELD_OUT

    def test_draws_billed_days_then_the_band_and_never_both_on_one_day(
        self, long_estate: tuple[TestClient, str]
    ) -> None:
        data = forecast(*long_estate)
        days = data["days"]
        assert not any(day["billed"] is not None and day["low"] is not None for day in days)
        figure = data["month_end"]["figure"]
        if figure is not None:
            banded = [day for day in days if day["low"] is not None]
            assert Decimal(banded[-1]["low"]) == Decimal(figure["low"])
            assert Decimal(banded[-1]["high"]) == Decimal(figure["high"])
        assert len(data["backtest"]) == data["month_end"]["held_out"]

    def test_a_narrow_scope_is_forecast_from_its_own_accounts_only(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id, LONG)
        client, token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        month, _, _ = expected(row for row in LONG if row.sub_account_id == ONE_ACCOUNT)
        agrees(forecast(client, token)["month_end"], month)


class TestTheRefusals:
    def test_three_months_is_too_short_to_test_and_it_says_so_rather_than_guess(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id, CURRENT)
        client, token = client_for(engine, everything(tenant_id), settings)
        data = forecast(client, token)
        assert data["month_end"]["figure"] is None
        assert f"tested on {MIN_HELD_OUT} complete months" in data["month_end"]["withheld"]
        assert all(month["figure"] is None for month in data["ahead"])
        assert all(row["low"] is None for row in data["backtest"])

    def test_a_tenant_with_no_cost_is_told_so_rather_than_shown_zero(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        client, token = client_for(engine, everything(tenant_id), settings)
        assert client.get(PATH, headers=auth(token)).status_code == 404
