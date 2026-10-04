"""The container guard, then the two routes it protects. TASK-P6-009.

The guard first and at the repository, because constraint 3 says scope is enforced in
two places and a route that forgot its dependency must still not read out of scope.
So the out of scope read is asserted against the repositories directly, with no route
involved, and only then are the routes asserted to return the envelope and count
coverage in clusters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_api.db import models
from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.containers import (
    ContainerClusterRepository,
    ContainerUsageRepository,
)
from finops_api.guards import SCOPED_TABLES, ByAccount
from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.tenant import Scope
from finops_fakes import fixtures
from finops_fakes.containers import CLUSTERS, FakeContainerSource
from finops_ingest.collectors.container_usage import ContainerUsageCollector
from finops_ingest.registry import CollectorContext
from tests.api.test_query_routes import auth, client_for

pytestmark = pytest.mark.integration

P6_TABLES = ("container_cluster", "container_usage")
ACCOUNTS = tuple(sorted({cluster.account_id for cluster in CLUSTERS}))
ONE = "fake-platform-a"


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID
    account: AccountKey
    region: str

    @property
    def scope_key(self) -> str:
        return f"{self.account}:{self.region}"


def seed(engine: Engine, tenant: UUID) -> None:
    """Every fake cluster, through the real collector rather than written by hand."""
    for account_id in ACCOUNTS:
        key = AccountKey(provider=Provider.AWS, account_id=account_id)
        with engine.begin() as connection:
            ContainerUsageCollector(FakeContainerSource())(
                CollectorContext(
                    unit=Unit(tenant_id=tenant, account=key, region=fixtures.REGION),
                    connection=connection,
                    run_id=uuid4(),
                )
            )


def everything(tenant: UUID) -> Scope:
    return Scope(tenant_id=tenant, is_global=True, accounts=frozenset())


def only(tenant: UUID, *accounts: str) -> Scope:
    return Scope(
        tenant_id=tenant,
        is_global=False,
        accounts=frozenset(AccountKey(provider=Provider.AWS, account_id=a) for a in accounts),
    )


CONTEXT = AccessContext(request_id="test")


class TestEveryP6TableHasARule:
    @pytest.mark.parametrize("name", P6_TABLES)
    def test_it_is_in_scoped_tables_by_its_account(self, name: str) -> None:
        """In before any route, so a route that forgets its dependency still cannot leak."""
        assert SCOPED_TABLES[name] == ByAccount("sub_account_id")

    @pytest.mark.parametrize("name", P6_TABLES)
    def test_the_account_column_it_names_exists(self, name: str) -> None:
        assert "sub_account_id" in models.metadata.tables[name].columns


class TestAnOutOfScopeReadIsRefused:
    """At the repository, with no route in the way. Constraint 3's second place."""

    def test_a_narrow_reader_sees_only_its_own_accounts_clusters(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        seed(engine, tenant_id)
        with engine.connect() as connection:
            wide = ContainerClusterRepository(connection, CONTEXT).clusters(everything(tenant_id))
            narrow = ContainerClusterRepository(connection, CONTEXT).clusters(only(tenant_id, ONE))
        assert len(wide) > len(narrow) >= 1
        assert {row.sub_account_id for row in narrow} == {ONE}

    def test_usage_rows_are_confined_the_same_way(self, engine: Engine, tenant_id: UUID) -> None:
        seed(engine, tenant_id)
        with engine.connect() as connection:
            narrow = ContainerUsageRepository(connection, CONTEXT).reservations(
                only(tenant_id, ONE)
            )
        assert narrow
        assert {row.sub_account_id for row in narrow} == {ONE}

    def test_a_scope_naming_no_account_reads_nothing_rather_than_everything(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """Empty means nothing, which is the fail closed case."""
        seed(engine, tenant_id)
        nobody = Scope(tenant_id=tenant_id, is_global=False, accounts=frozenset())
        with engine.connect() as connection:
            assert ContainerClusterRepository(connection, CONTEXT).clusters(nobody) == []
            assert ContainerUsageRepository(connection, CONTEXT).reservations(nobody) == []

    def test_another_tenants_clusters_are_never_visible(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        seed(engine, tenant_id)
        # A real second tenant, made the way the fixture makes one. Reading as a tenant
        # that does not exist fails on the audit row's foreign key before it reads, which
        # would prove the audit works rather than that the tenant filter does.
        other_tenant = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO tenant (tenant_id, name) VALUES (:id, :name)"),
                {"id": other_tenant, "name": f"tenant-{other_tenant}"},
            )
        with engine.connect() as connection:
            other = ContainerClusterRepository(connection, CONTEXT).clusters(
                everything(other_tenant)
            )
        assert other == []


def get(client: Any, token: str, path: str) -> dict[str, Any]:
    response = client.get(path, headers=auth(token))
    assert response.status_code == 200, f"{path} returned {response.status_code}: {response.text}"
    body = response.json()
    assert isinstance(body, dict)
    return body


class TestTheWasteRoute:
    def test_every_cluster_is_listed_including_the_one_without_requests(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        data = get(client, token, "/api/v1/waste/containers")["data"]
        names = {cluster["cluster_name"] for cluster in data["clusters"]}
        assert names == {cluster.name for cluster in CLUSTERS}
        plain = next(c for c in data["clusters"] if not c["enhanced_observability"])
        assert plain["request_unavailable_reason"]
        for workload in plain["workloads"]:
            # No request, never a request of zero, and an unobserved kill.
            assert workload["cpu_requested_millicores"] is None
            assert workload["oom_status"] == "UNOBSERVED"

    def test_request_and_use_are_two_figures_never_one_percentage(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Spec section 9. There is no efficiency field to read, by construction."""
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        data = get(client, token, "/api/v1/waste/containers")["data"]
        workload = next(w for c in data["clusters"] for w in c["workloads"])
        assert "cpu_requested_millicores" in workload and "cpu_used_p99_millicores" in workload
        assert not any("efficiency" in key or "percent" in key for key in workload)

    def test_coverage_counts_clusters_with_readable_requests(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        envelope = get(client, token, "/api/v1/waste/containers")
        coverage = envelope["meta"]["scope_coverage"]
        assert coverage["unit"] == "clusters"
        assert coverage["visible"] == envelope["data"]["measured_count"]
        assert coverage["total"] == envelope["data"]["found_count"]
        assert envelope["data"]["measured_count"] < envelope["data"]["found_count"]


class TestTheInventoryRoute:
    def test_spot_and_packing_are_shown_where_the_fleet_is_readable(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        data = get(client, token, "/api/v1/inventory/clusters")["data"]
        measured = [c for c in data["clusters"] if c["packing_efficiency"] is not None]
        assert measured
        for cluster in measured:
            assert cluster["spot_ratio"] is not None
            assert cluster["unmeasurable_reason"] is None

    def test_a_fargate_cluster_says_it_has_no_fleet_rather_than_an_unreadable_one(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        data = get(client, token, "/api/v1/inventory/clusters")["data"]
        fargate = next(c for c in data["clusters"] if c["platform"] == "ECS")
        assert fargate["packing_efficiency"] is None
        assert "without nodes" in fargate["unmeasurable_reason"]

    def test_coverage_counts_only_clusters_with_nodes(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """A Fargate cluster's missing packing is not a gap and must not degrade the screen."""
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        envelope = get(client, token, "/api/v1/inventory/clusters")
        with_nodes = sum(1 for c in envelope["data"]["clusters"] if c["platform"] != "ECS")
        assert envelope["data"]["found_count"] == with_nodes
        assert envelope["meta"]["scope_coverage"]["unit"] == "clusters"

    def test_a_narrow_reader_sees_fewer_clusters_through_the_route(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        wide_client, wide_token = client_for(engine, everything(tenant_id), settings)
        narrow_client, narrow_token = client_for(engine, only(tenant_id, ONE), settings)
        wide = get(wide_client, wide_token, "/api/v1/inventory/clusters")["data"]["clusters"]
        narrow = get(narrow_client, narrow_token, "/api/v1/inventory/clusters")["data"]["clusters"]
        assert len(wide) > len(narrow) >= 1
        assert {c["account_id"] for c in narrow} == {ONE}
