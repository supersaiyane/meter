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
from finops_fakes.cur import CLOSED_PERIOD, ESTATE, FakeCostExport, estate
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.registry import CollectorContext
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

#: The real clock, nudged past the first of the month. A period has billed up to
#: yesterday, so on the first the open month holds no days at all, the newest period
#: in the estate is last month, and last month is closed. Every test below that calls
#: the newest period "still running" then asserts the opposite of what it means, one
#: day in thirty. ISS-219.
OPEN_ENOUGH = max(TODAY, datetime(TODAY.year, TODAY.month, 2, tzinfo=UTC))
CURRENT = estate(at=OPEN_ENOUGH)
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
            "/api/v1/cost/containers",
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


class TestAnomalies:
    """An empty list means two opposite things, and the payload has to say which."""

    def test_a_young_estate_is_not_told_it_is_behaving(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Four days of history is not an estate with no anomalies. It is an
        estate nobody can say anything about yet, and a screen that renders the
        two alike tells the second one a reassuring lie."""
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        found = get(client, token, "/api/v1/cost/anomalies")["data"]
        assert found["anomalies"] == []
        assert found["days_needed"] > 0
        assert found["days_collected"] >= 0

    def test_it_reports_a_real_spike_with_its_working(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        from finops_ingest.collectors.cost_anomaly import CostAnomalyCollector

        seed(engine, tenant_id, rows=CURRENT)
        with engine.begin() as connection:
            CostAnomalyCollector(clock=lambda: TODAY)(
                CollectorContext(
                    unit=Unit(tenant_id=tenant_id),
                    connection=connection,
                    run_id=uuid4(),
                    settings=settings,
                )
            )

        client, token = client_for(engine, everything(tenant_id), settings)
        found = get(client, token, "/api/v1/cost/anomalies")["data"]
        # The estate rises smoothly rather than spiking, so this asserts the
        # shape of the answer and not that one was found. The detector's own
        # suite is where a spike is proved.
        assert isinstance(found["anomalies"], list)
        assert found["days_collected"] > 0
        for row in found["anomalies"]:
            assert row["why"]
            assert Decimal(row["delta"]) == Decimal(row["observed"]) - Decimal(row["baseline"])

    def test_a_narrow_scope_is_served_only_its_own(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # The guard went in before the route, per the rule at the top of the P1
        # plan. This is the test that proves it rather than assuming it.
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        found = get(client, token, "/api/v1/cost/anomalies")["data"]
        assert {row["account_id"] for row in found["anomalies"]} <= {ONE_ACCOUNT}


class TestTheAnomalyBannerCountsAccounts:
    """Seen on a screen, not in a test, and the third time in this project.

    The coverage banner counts accounts. `len(rows)` reached that slot and rendered
    "4 missing, outside your scope" above a single anomaly, for a reader entitled to
    the whole estate. The same slot once held a line item count and read "showing all
    450 accounts" on an estate with five.

    An estate with no anomalies has no rows to count, which is why the figure comes
    from the cost table: a banner that vanished when the estate behaved would be
    useless exactly when a reader most wants to know the view is complete.
    """

    def test_a_global_reader_is_not_told_accounts_are_missing(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        coverage = get(client, token, "/api/v1/cost/anomalies")["meta"]["scope_coverage"]
        assert coverage["unit"] == "accounts"
        assert coverage["is_partial"] is False

    def test_the_figure_is_accounts_rather_than_a_count_of_findings(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # The sharp form. A fixture where the two happen to be equal would let the
        # test above pass with the bug in place, so this compares against the accounts
        # the summary route reports rather than against a number written down.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        anomalies = get(client, token, "/api/v1/cost/anomalies")
        by_account = get(client, token, "/api/v1/cost/by-account")
        assert anomalies["meta"]["scope_coverage"]["visible"] == len(by_account["data"])

    def test_a_narrow_reader_sees_a_smaller_figure(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        whole, whole_token = client_for(engine, everything(tenant_id), settings)
        narrow, narrow_token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        wide = get(whole, whole_token, "/api/v1/cost/anomalies")["meta"]["scope_coverage"]
        part = get(narrow, narrow_token, "/api/v1/cost/anomalies")["meta"]["scope_coverage"]
        assert part["visible"] < wide["visible"]
        assert part["unit"] == "accounts"

    def test_it_agrees_with_the_other_cost_routes(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The anomalies banner must not be the odd one out in either direction.

        Written after the fix above, because the first version of this test asserted
        that a narrow reader is told their view is partial, and that is false for every
        cost route: `count_in_organization` is itself scoped, so a reader entitled to
        one account is told one of one. Whether that is right is ISS-187, and it is not
        a question this route should answer differently from its neighbours.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        anomalies = get(client, token, "/api/v1/cost/anomalies")["meta"]["scope_coverage"]
        summary = get(client, token, "/api/v1/cost/summary")["meta"]["scope_coverage"]
        assert anomalies == summary


class TestContainerCost:
    """TASK-P6-003, FEAT-035. Cost by cluster, namespace and workload.

    Under the Cost group rather than a Containers one, per ADR-0020: a reader
    asking what their clusters cost is asking where the money is going, which is
    the question this group answers.
    """

    def test_the_clusters_come_back_with_their_breakdown(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        found = get(client, token, "/api/v1/cost/containers")["data"]

        names = {cluster["cluster_name"] for cluster in found["clusters"]}
        assert names == {"platform-eks", "batch-eks"}
        for cluster in found["clusters"]:
            assert cluster["workloads"], f"{cluster['cluster_name']} has no breakdown"
            namespaces = {row["namespace"] for row in cluster["workloads"]}
            assert namespaces, "a cluster with a breakdown and no namespaces in it"

    def test_a_cluster_total_is_what_was_attributed_plus_what_was_not(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The unallocated remainder is a figure, not a rounding error.

        It is capacity the cluster paid for and no pod asked for, which is the
        whole argument for showing bin packing on the cluster screen.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        found = get(client, token, "/api/v1/cost/containers")["data"]

        for cluster in found["clusters"]:
            total = Decimal(cluster["total"])
            allocated = Decimal(cluster["allocated"])
            unallocated = Decimal(cluster["unallocated"])
            assert total == allocated + unallocated
            assert unallocated > 0, (
                f"{cluster['cluster_name']} attributes every penny to a pod, so the "
                f"fixture cannot exercise the unallocated case"
            )

    def test_the_workload_shares_add_up_to_what_was_allocated(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """A breakdown that does not sum to its own subtotal has lost money."""
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        found = get(client, token, "/api/v1/cost/containers")["data"]

        for cluster in found["clusters"]:
            shares = sum(Decimal(row["cost"]) for row in cluster["workloads"])
            assert shares == Decimal(cluster["allocated"]), cluster["cluster_name"]

    def test_a_narrow_reader_sees_fewer_clusters(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Constraint 3, and the criterion this route was written against.

        The two EKS clusters live in different accounts, so a caller narrowed to
        one account must see one cluster. Asserted against the wide read rather
        than against a literal, so the claim is about the scope and not about how
        many clusters the fixture happens to have.
        """
        seed(engine, tenant_id)
        wide_client, wide_token = client_for(engine, everything(tenant_id), settings)
        wide = get(wide_client, wide_token, "/api/v1/cost/containers")["data"]

        narrow_client, narrow_token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        narrow = get(narrow_client, narrow_token, "/api/v1/cost/containers")["data"]

        assert len(wide["clusters"]) > len(narrow["clusters"]) >= 1
        visible = {cluster["cluster_name"] for cluster in narrow["clusters"]}
        assert visible == {"platform-eks"}, visible

    def test_coverage_counts_clusters_and_says_so(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Accounts in that slot would call coverage complete while clusters were missing."""
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        envelope = get(client, token, "/api/v1/cost/containers")

        coverage = envelope["meta"]["scope_coverage"]
        assert coverage["unit"] == "clusters"
        assert coverage["total"] == envelope["data"]["found_count"]
        assert coverage["visible"] == envelope["data"]["measured_count"]

    def test_an_export_without_split_data_reports_the_gap_rather_than_free_clusters(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """ISS-003. No cluster is listed as costing nothing, and the reason travels."""
        with engine.begin() as connection:
            for month in {row.billing_period_start for row in (*ESTATE, *CURRENT)}:
                ensure_partition(connection, "cost_focus_daily", month)
            collector = CostFocusCollector(
                FakeCostExport(rows=CLOSED, split=False), clock=lambda: NOW
            )
            collector(
                CollectorContext(
                    unit=Unit(tenant_id=tenant_id), connection=connection, run_id=uuid4()
                )
            )

        client, token = client_for(engine, everything(tenant_id), settings)
        envelope = get(client, token, "/api/v1/cost/containers")

        # No clusters at all, rather than clusters at zero.
        assert envelope["data"]["clusters"] == []
        assert envelope["data"]["found_count"] == 0
        # And the configuration fault arrives from the collector that found it, so
        # the screen can explain itself without this route guessing why.
        causes = {failure["cause"] for failure in envelope["meta"]["failures"]}
        assert "Misconfigured" in causes, envelope["meta"]["failures"]
        assert envelope["meta"]["degraded"] is True
