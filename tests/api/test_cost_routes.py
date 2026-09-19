"""The four cost routes, called rather than imported.

A test that imports a route proves nothing. TASK-P2-021 wrote six routes that
imported cleanly, passed their tests, and returned 500 on every real call,
because the tables they read were not in `SCOPED_TABLES`. That is the standing
lesson in `tasks/lessons.md`, and it is why every test here goes through the
client.

The questions that matter most are not the totals. They are whether an open
period says so, whether a narrow scope is served less than a global one, and
whether a tenant with no cost gets an answer that cannot be mistaken for zero
spend.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.platform import UNALLOCATED
from finops_core.domain.tenant import Scope
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.registry import CollectorContext
from finops_providers.fake.cur import CLOSED_PERIOD, ESTATE, FakeCostExport, estate
from tests.api.test_query_routes import auth, client_for

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
CLOSED = tuple(row for row in ESTATE if row.billing_period_start == CLOSED_PERIOD)
ONE_ACCOUNT = "fake-platform-a"

#: An estate built at the real clock, because the route asks the real clock
#: whether a period is still accruing. The module level `ESTATE` is pinned to
#: 2026-08, so its open month stopped being open the day that month ended, and
#: a test asserting otherwise against it would be asserting the date.
TODAY = datetime.now(UTC)
CURRENT = estate(at=TODAY)
CURRENT_PERIOD = max(row.billing_period_start for row in CURRENT)
STILL_RUNNING = tuple(row for row in CURRENT if row.billing_period_start == CURRENT_PERIOD)
FINISHED_PERIOD = max(
    row.billing_period_start for row in CURRENT if row.billing_period_start < CURRENT_PERIOD
)
FINISHED = tuple(row for row in CURRENT if row.billing_period_start == FINISHED_PERIOD)


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


def seed(engine: Engine, tenant: UUID, rows: tuple[Any, ...] = CLOSED) -> None:
    with engine.begin() as connection:
        for month in {row.billing_period_start for row in (*ESTATE, *CURRENT)}:
            ensure_partition(connection, "cost_focus_daily", month)
        collector = CostFocusCollector(FakeCostExport(rows=rows), clock=lambda: NOW)
        collector(
            CollectorContext(unit=Unit(tenant_id=tenant), connection=connection, run_id=uuid4())
        )


def everything(tenant: UUID) -> Scope:
    return Scope(tenant_id=tenant, is_global=True, accounts=frozenset())


def only(tenant: UUID, account: str) -> Scope:
    return Scope(
        tenant_id=tenant,
        is_global=False,
        accounts=frozenset({AccountKey(provider=Provider.AWS, account_id=account)}),
    )


def get(client: TestClient, token: str, path: str) -> dict[str, Any]:
    response = client.get(path, headers=auth(token))
    assert response.status_code == 200, f"{path} returned {response.status_code}: {response.text}"
    result = response.json()
    assert isinstance(result, dict)
    return result


def effective(client: TestClient, token: str) -> Decimal:
    return Decimal(get(client, token, "/api/v1/cost/summary")["data"]["current"]["effective_cost"])


class TestEveryRouteIsReachable:
    """The first thing TASK-P2-021 proved was worth checking on its own."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/cost/summary",
            "/api/v1/cost/by-service",
            "/api/v1/cost/by-account",
            "/api/v1/cost/trend",
            "/api/v1/cost/allocation?tag=team",
        ],
    )
    def test_it_answers_two_hundred_with_an_envelope(
        self, engine: Engine, tenant_id: UUID, settings: Settings, path: str
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        payload = get(client, token, path)
        assert "data" in payload
        assert "meta" in payload

    def test_every_figure_carries_both_timestamps(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # Constraints 4 and 10. A number with no `as_of` is a number with no
        # claim about when it was true.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        meta = get(client, token, "/api/v1/cost/summary")["meta"]
        assert meta["as_of"]
        assert meta["collected_at"]


class TestAnOpenPeriodSaysSo:
    def test_a_finished_month_is_not_open(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id, rows=FINISHED)
        client, token = client_for(engine, everything(tenant_id), settings)
        current = get(client, token, "/api/v1/cost/summary")["data"]["current"]
        assert current["is_open"] is False

    def test_a_month_still_running_is(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The label the whole screen hangs on.

        The fake estate's open month holds 23 days against the closed one's 31,
        so its total is lower. A reader comparing the two unwarned concludes
        that spending collapsed.
        """
        seed(engine, tenant_id, rows=STILL_RUNNING)
        client, token = client_for(engine, everything(tenant_id), settings)
        current = get(client, token, "/api/v1/cost/summary")["data"]["current"]
        assert current["is_open"] is True


class TestScope:
    def test_a_narrow_scope_is_served_less_than_a_global_one(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Scope is enforced twice. This is the route half."""
        seed(engine, tenant_id)
        wide, wide_token = client_for(engine, everything(tenant_id), settings)
        whole = effective(wide, wide_token)

        narrow, narrow_token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        mine = effective(narrow, narrow_token)

        assert 0 < mine < whole

    def test_by_account_shows_a_narrow_scope_only_its_own(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        rows = get(client, token, "/api/v1/cost/by-account")["data"]
        assert {row["name"] for row in rows} == {ONE_ACCOUNT}


class TestAnAbsenceIsNotAZero:
    def test_a_tenant_with_no_cost_is_told_so(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Not an empty period and not a zero.

        Zero spend is a claim. An estate nobody has collected is an absence,
        and the two must not render the same, per constraint 5.
        """
        client, token = client_for(engine, everything(tenant_id), settings)
        assert client.get("/api/v1/cost/summary", headers=auth(token)).status_code == 404

    def test_no_previous_period_gives_no_change_rather_than_no_movement(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """A change computed against a month nobody collected would be a number
        invented out of an absence, and it would read as an estate that had
        appeared from nothing."""
        seed(engine, tenant_id, rows=CLOSED)
        client, token = client_for(engine, everything(tenant_id), settings)
        summary = get(client, token, "/api/v1/cost/summary")["data"]
        assert summary["previous"] is None
        assert summary["change"] is None


class TestTheGroupingsAgree:
    def test_by_service_sums_to_the_summary(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        total = effective(client, token)
        rows = get(client, token, "/api/v1/cost/by-service")["data"]
        assert sum((Decimal(row["effective_cost"]) for row in rows), Decimal(0)) == total

    def test_the_trend_sums_to_the_summary_and_runs_oldest_first(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        total = effective(client, token)
        days = get(client, token, "/api/v1/cost/trend")["data"]
        assert sum((Decimal(day["effective_cost"]) for day in days), Decimal(0)) == total
        assert [day["day"] for day in days] == sorted(day["day"] for day in days)

    def test_allocation_includes_the_unallocated_bucket(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        rows = get(client, token, "/api/v1/cost/allocation?tag=team")["data"]
        assert UNALLOCATED in {row["name"] for row in rows}

    def test_allocation_without_a_tag_is_refused(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # There is no sensible default tag key. Guessing one would group the
        # estate by something nobody asked for and label it their allocation.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        assert client.get("/api/v1/cost/allocation", headers=auth(token)).status_code == 422
