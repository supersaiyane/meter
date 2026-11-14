"""Rebuilding the tree, and the two windows where a careless version lies.

A rebuild without a transaction leaves a moment where the organization is empty,
and an empty organization renders as zero cost to whoever reads it then. A
delete of a departed account takes its cost history with it and shrinks the
denominator behind every total.

Both are invisible after the fact, which is why both are tested against a real
database rather than reasoned about.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.account import AccountKey, AccountStatus, CloudAccount, Provider
from finops_core.domain.org import OrgNode, OrgNodeType
from finops_core.errors import NoData
from finops_ingest.collectors.org_tree import OrgTreeCollector, compute_paths
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext

AT = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
ROOT = "r-root"
UNIT_ID = "ou-platform"


def node(node_id: str, node_type: OrgNodeType, parent: str | None) -> OrgNode:
    return OrgNode(
        node_id=node_id,
        node_type=node_type,
        name=node_id,
        parent_id=parent,
        provider=Provider.AWS,
        as_of=AT,
        collected_at=AT,
    )


def account(account_id: str, status: AccountStatus = AccountStatus.ACTIVE) -> CloudAccount:
    return CloudAccount(
        key=AccountKey(provider=Provider.AWS, account_id=account_id),
        name=f"account-{account_id}",
        status=status,
        parent_node_id=UNIT_ID,
        as_of=AT,
        collected_at=AT,
    )


class StubDiscovery:
    def __init__(self, nodes: tuple[OrgNode, ...], accounts: tuple[CloudAccount, ...]) -> None:
        self._nodes = nodes
        self._accounts = accounts

    def describe_organization(self) -> tuple[OrgNode, ...]:
        return self._nodes

    def list_accounts(self) -> tuple[CloudAccount, ...]:
        return self._accounts


def tree_of(*account_ids: str) -> StubDiscovery:
    nodes = [node(ROOT, OrgNodeType.ROOT, None), node(UNIT_ID, OrgNodeType.OU, ROOT)]
    nodes += [node(i, OrgNodeType.ACCOUNT, UNIT_ID) for i in account_ids]
    return StubDiscovery(tuple(nodes), tuple(account(i) for i in account_ids))


def unit_for(tenant: UUID) -> WorkUnit:
    return WorkUnit(
        tenant_id=tenant,
        collector="org_tree",
        window_start=AT,
        window_end=AT,
    )


def rows(engine: Engine, table_name: str, tenant: UUID) -> list[dict[str, object]]:
    with engine.connect() as connection:
        result = connection.execute(
            text(f"SELECT * FROM {table_name} WHERE tenant_id = :t"), {"t": tenant}
        ).mappings()
        return [dict(row) for row in result]


def collect(engine: Engine, tenant: UUID, discovery: StubDiscovery) -> int:
    with engine.begin() as connection:
        outcome = OrgTreeCollector(discovery, clock=lambda: AT)(
            CollectorContext(unit=unit_for(tenant), connection=connection)
        )
    return outcome.items_written


# --- paths, with no database -------------------------------------------------


def test_paths_and_depths_are_computed_from_the_root() -> None:
    nodes = [
        node(ROOT, OrgNodeType.ROOT, None),
        node(UNIT_ID, OrgNodeType.OU, ROOT),
        node("111122223333", OrgNodeType.ACCOUNT, UNIT_ID),
    ]
    paths = compute_paths(nodes)
    assert paths[ROOT] == ("/r-root", 0)
    assert paths[UNIT_ID] == ("/r-root/ou-platform", 1)
    assert paths["111122223333"] == ("/r-root/ou-platform/111122223333", 2)


def test_a_cycle_is_refused_rather_than_walked_forever() -> None:
    nodes = [node("a", OrgNodeType.OU, "b"), node("b", OrgNodeType.OU, "a")]
    with pytest.raises(NoData, match="cycle"):
        compute_paths(nodes)


# --- against a real database -------------------------------------------------


@pytest.mark.integration
def test_the_tree_and_the_accounts_are_written(engine: Engine, tenant_id: UUID) -> None:
    written = collect(engine, tenant_id, tree_of("111122223333", "444455556666"))
    assert written == 6
    nodes = rows(engine, "org_node", tenant_id)
    assert len(nodes) == 4
    assert {row["node_type"] for row in nodes} == {"ROOT", "OU", "ACCOUNT"}
    assert len(rows(engine, "cloud_account", tenant_id)) == 2


@pytest.mark.integration
def test_paths_and_depths_reach_the_database(engine: Engine, tenant_id: UUID) -> None:
    collect(engine, tenant_id, tree_of("111122223333"))
    by_id = {row["node_id"]: row for row in rows(engine, "org_node", tenant_id)}
    assert by_id[ROOT]["depth"] == 0
    assert by_id["111122223333"]["depth"] == 2
    assert by_id["111122223333"]["path"] == "/r-root/ou-platform/111122223333"


@pytest.mark.integration
def test_a_reader_never_sees_a_half_rebuilt_tree(engine: Engine, tenant_id: UUID) -> None:
    """The old tree stands until the whole replacement commits."""
    collect(engine, tenant_id, tree_of("111122223333"))
    before = {row["node_id"] for row in rows(engine, "org_node", tenant_id)}

    class Exploding(StubDiscovery):
        def list_accounts(self) -> tuple[CloudAccount, ...]:
            raise RuntimeError("the call died half way through the rebuild")

    with pytest.raises(RuntimeError), engine.begin() as connection:
        OrgTreeCollector(Exploding(tree_of("999").describe_organization(), ()), clock=lambda: AT)(
            CollectorContext(unit=unit_for(tenant_id), connection=connection)
        )

    assert {row["node_id"] for row in rows(engine, "org_node", tenant_id)} == before


@pytest.mark.integration
def test_a_rerun_replaces_the_tree_rather_than_duplicating_it(
    engine: Engine, tenant_id: UUID
) -> None:
    collect(engine, tenant_id, tree_of("111122223333"))
    collect(engine, tenant_id, tree_of("111122223333"))
    assert len(rows(engine, "org_node", tenant_id)) == 3


@pytest.mark.integration
def test_a_new_account_appears_with_no_human_step(engine: Engine, tenant_id: UUID) -> None:
    """This is the P0 definition of done for onboarding."""
    collect(engine, tenant_id, tree_of("111122223333"))
    collect(engine, tenant_id, tree_of("111122223333", "444455556666"))
    found = {row["account_id"]: row["status"] for row in rows(engine, "cloud_account", tenant_id)}
    assert found == {"111122223333": "ACTIVE", "444455556666": "ACTIVE"}


@pytest.mark.integration
def test_accounts_are_upserted_rather_than_duplicated(engine: Engine, tenant_id: UUID) -> None:
    collect(engine, tenant_id, tree_of("111122223333"))
    collect(engine, tenant_id, tree_of("111122223333"))
    assert len(rows(engine, "cloud_account", tenant_id)) == 1


@pytest.mark.integration
def test_a_departed_account_is_marked_not_deleted(engine: Engine, tenant_id: UUID) -> None:
    """Its cost history has to outlive its membership."""
    collect(engine, tenant_id, tree_of("111122223333", "444455556666"))
    collect(engine, tenant_id, tree_of("111122223333"))
    found = {row["account_id"]: row["status"] for row in rows(engine, "cloud_account", tenant_id)}
    assert found == {"111122223333": "ACTIVE", "444455556666": "DEPARTED"}


@pytest.mark.integration
def test_a_departed_account_that_returns_becomes_active_again(
    engine: Engine, tenant_id: UUID
) -> None:
    collect(engine, tenant_id, tree_of("111122223333", "444455556666"))
    collect(engine, tenant_id, tree_of("111122223333"))
    collect(engine, tenant_id, tree_of("111122223333", "444455556666"))
    found = {row["account_id"]: row["status"] for row in rows(engine, "cloud_account", tenant_id)}
    assert found["444455556666"] == "ACTIVE"


@pytest.mark.integration
def test_an_empty_discovery_is_refused_rather_than_applied(engine: Engine, tenant_id: UUID) -> None:
    """Applying it would mark every account departed in one transaction."""
    collect(engine, tenant_id, tree_of("111122223333"))
    with pytest.raises(NoData, match="no accounts"), engine.begin() as connection:
        OrgTreeCollector(StubDiscovery((), ()), clock=lambda: AT)(
            CollectorContext(unit=unit_for(tenant_id), connection=connection)
        )
    found = {row["account_id"]: row["status"] for row in rows(engine, "cloud_account", tenant_id)}
    assert found == {"111122223333": "ACTIVE"}


@pytest.mark.integration
def test_one_tenant_rebuild_does_not_touch_another(engine: Engine, tenant_id: UUID) -> None:
    other = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenant (tenant_id, name) VALUES (:id, :name)"),
            {"id": other, "name": f"tenant-{other}"},
        )
    collect(engine, other, tree_of("111122223333"))
    collect(engine, tenant_id, tree_of("444455556666"))
    assert {row["node_id"] for row in rows(engine, "org_node", other)} >= {"111122223333"}
    assert len(rows(engine, "org_node", other)) == 3


# --- the cadence that makes "within one hour" true ---------------------------


@pytest.mark.integration
def test_the_default_schedule_makes_the_hourly_claim_real(engine: Engine, tenant_id: UUID) -> None:
    """ADR-0012. The interval is data, and it arrives with the tenant."""
    from finops_ingest.registry import HOURLY, install_default_schedule

    with engine.begin() as connection:
        assert install_default_schedule(connection, tenant_id, updated_by="onboarding") == 2

    schedule = {row["collector"]: row for row in rows(engine, "collector_schedule", tenant_id)}
    assert set(schedule) == {"org_tree", "account_health"}
    for entry in schedule.values():
        assert entry["cadence_seconds"] == HOURLY
        assert entry["reason"], "a cadence without a reason cannot be safely changed"
        assert entry["is_enabled"] is True


@pytest.mark.integration
def test_installing_the_schedule_twice_does_not_undo_an_operator_change(
    engine: Engine, tenant_id: UUID
) -> None:
    """A deliberate slow down must survive a redeploy."""
    from finops_ingest.registry import install_default_schedule

    with engine.begin() as connection:
        install_default_schedule(connection, tenant_id, updated_by="onboarding")
        connection.execute(
            text(
                "UPDATE collector_schedule SET cadence_seconds = 21600 "
                "WHERE tenant_id = :t AND collector = 'org_tree'"
            ),
            {"t": tenant_id},
        )
    with engine.begin() as connection:
        assert install_default_schedule(connection, tenant_id, updated_by="redeploy") == 0

    schedule = {row["collector"]: row for row in rows(engine, "collector_schedule", tenant_id)}
    assert schedule["org_tree"]["cadence_seconds"] == 21600
