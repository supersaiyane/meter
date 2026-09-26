"""The recursive traversal, against a real database, because that is the only proof.

Three things here cannot be reasoned about from the source. A cycle either terminates or the
connection hangs. A recursive term without its own scope predicate walks out of the caller's
scope and the answer looks entirely normal. And a depth bound applied in the wrong place
returns the right nodes with the wrong depths, which the cap then sorts by.

The estate below is deliberately small and deliberately awkward: a VPC with two subnets, a
security group that references itself, a pair of groups that reference each other, and one
edge leaving the account into a VPC nobody can read.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_api.db.repositories.base import AccessContext
from finops_api.db.repositories.topology import WALK, WALK_INWARD, TopologyRepository
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.tenant import Scope
from finops_core.domain.topology import CoverageState, EdgeKind, NodeKind, node_id_for
from finops_query.graph import Bounds, IncompleteGraphError

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 26, 6, 0, tzinfo=UTC)
FETCHED = datetime(2026, 9, 26, 6, 5, tzinfo=UTC)
MINE = "111122223333"
THEIRS = "444455556666"
REGION = "eu-west-1"

INSERT_ACCOUNT = text(
    "INSERT INTO cloud_account (account_pk, tenant_id, provider, account_id, name, status, "
    "as_of, collected_at) VALUES (:pk, :t, 'aws', :account, :account, 'ACTIVE', :at, :at) "
    "ON CONFLICT DO NOTHING"
)

INSERT_RUN = text(
    "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, idempotency_key, "
    "status, as_of_window_start, as_of_window_end) "
    "VALUES (:run, :t, 'inventory', 'scope', :key, 'SUCCEEDED', :at, :at)"
)

INSERT_NODE = text(
    "INSERT INTO topology_node (node_id, tenant_id, ingest_run_id, sub_account_id, "
    "provider_id, node_kind, resource_type, region_id, availability_zone, name, as_of, "
    "collected_at) VALUES (:node, :t, :run, :account, :provider, :kind, 'AWS::EC2::VPC', "
    ":region, NULL, :name, :at, :fetched)"
)

INSERT_EDGE = text(
    "INSERT INTO topology_edge (edge_id, tenant_id, ingest_run_id, from_node_id, to_node_id, "
    "edge_kind, is_cross_account, source, sub_account_id, region_id, as_of, collected_at) "
    "VALUES (:edge, :t, :run, :frm, :to, :kind, :cross, 'CONFIG_RELATIONSHIP', :account, "
    ":region, :at, :fetched)"
)

INSERT_COVERAGE = text(
    "INSERT INTO graph_coverage (coverage_id, tenant_id, ingest_run_id, sub_account_id, "
    "region_id, state, cause, node_count, edge_count, as_of, collected_at) "
    "VALUES (:c, :t, :run, :account, :region, :state, :cause, 1, 1, :at, :fetched)"
)

CLEAR_AUDIT = text("DELETE FROM audit_event WHERE tenant_id = :t")


def arn(account: str, name: str) -> str:
    return f"arn:aws:ec2:{REGION}:{account}:vpc/{name}"


def identifier(tenant: UUID, account: str, name: str) -> UUID:
    return node_id_for(tenant_id=tenant, provider_id=arn(account, name))


@pytest.fixture
def estate(engine: Engine, tenant_id: UUID) -> UUID:
    """A small awkward estate, including both cycles and one edge out of the account."""
    with engine.begin() as connection:
        run = uuid4()
        for account in (MINE, THEIRS):
            connection.execute(
                INSERT_ACCOUNT,
                {"pk": uuid4(), "t": tenant_id, "account": account, "at": NOW},
            )
        connection.execute(INSERT_RUN, {"run": run, "t": tenant_id, "key": str(run), "at": NOW})

        def add_node(account: str, name: str, kind: NodeKind = NodeKind.VPC) -> None:
            connection.execute(
                INSERT_NODE,
                {
                    "node": identifier(tenant_id, account, name),
                    "t": tenant_id,
                    "run": run,
                    "account": account,
                    "provider": arn(account, name),
                    "kind": kind.value,
                    "region": REGION,
                    "name": name,
                    "at": NOW,
                    "fetched": FETCHED,
                },
            )

        def add_edge(
            origin: tuple[str, str],
            target: tuple[str, str],
            kind: EdgeKind = EdgeKind.CONTAINS,
            *,
            cross: bool = False,
        ) -> None:
            connection.execute(
                INSERT_EDGE,
                {
                    "edge": uuid4(),
                    "t": tenant_id,
                    "run": run,
                    "frm": identifier(tenant_id, *origin),
                    "to": identifier(tenant_id, *target),
                    "kind": kind.value,
                    "cross": cross,
                    "account": origin[0],
                    "region": REGION,
                    "at": NOW,
                    "fetched": FETCHED,
                },
            )

        for name in ("vpc", "subnet-a", "subnet-b", "sg-self", "sg-app", "sg-db", "instance"):
            add_node(MINE, name)
        add_node(THEIRS, "far")

        add_edge((MINE, "vpc"), (MINE, "subnet-a"))
        add_edge((MINE, "vpc"), (MINE, "subnet-b"))
        add_edge((MINE, "subnet-a"), (MINE, "instance"))
        add_edge((MINE, "instance"), (MINE, "sg-app"), EdgeKind.ATTACHED_TO)
        # A group that references itself, which is the ordinary way an estate lets a tier
        # talk to itself, and the case a naive recursion never returns from.
        add_edge((MINE, "sg-self"), (MINE, "sg-self"), EdgeKind.PERMITS)
        add_edge((MINE, "vpc"), (MINE, "sg-self"))
        # A two node cycle, which array containment handles and a visited set held per row
        # rather than per path would not.
        add_edge((MINE, "sg-app"), (MINE, "sg-db"), EdgeKind.PERMITS)
        add_edge((MINE, "sg-db"), (MINE, "sg-app"), EdgeKind.PERMITS)
        # Out of the account, to a VPC this estate's own coverage says is unreadable.
        add_edge((MINE, "vpc"), (THEIRS, "far"), EdgeKind.PEERS_WITH, cross=True)

        for account, state, cause in (
            (MINE, "COMPLETE", None),
            (THEIRS, "PARTIAL", "AccessDenied"),
        ):
            connection.execute(
                INSERT_COVERAGE,
                {
                    "c": uuid4(),
                    "t": tenant_id,
                    "run": run,
                    "account": account,
                    "region": REGION,
                    "state": state,
                    "cause": cause,
                    "at": NOW,
                    "fetched": FETCHED,
                },
            )
    return tenant_id


def repo(connection: Any) -> TopologyRepository:
    return TopologyRepository(connection, AccessContext(request_id="test"))


def global_scope(tenant: UUID) -> Scope:
    return Scope(tenant_id=tenant, is_global=True, accounts=frozenset())


def narrow_scope(tenant: UUID, *accounts: str) -> Scope:
    return Scope(
        tenant_id=tenant,
        is_global=False,
        accounts=frozenset(
            AccountKey(provider=Provider.AWS, account_id=account) for account in accounts
        ),
    )


def walk(engine: Engine, tenant: UUID, scope: Scope, root: str, **kwargs: Any) -> Any:
    with engine.begin() as connection:
        return repo(connection).subgraph(scope, root_id=identifier(tenant, MINE, root), **kwargs)


# --- the cycle terminates ---------------------------------------------------


def test_a_security_group_that_references_itself_terminates(engine: Engine, estate: UUID) -> None:
    """The case TASK-P4-007 names. Either this returns or the connection hangs, which is why
    it is here and not in the pure test."""
    graph = walk(engine, estate, global_scope(estate), "sg-self")
    assert [node.name for node in graph.nodes] == ["sg-self"]
    assert graph.depth_reached == 0


def test_a_pair_of_groups_referencing_each_other_terminates(engine: Engine, estate: UUID) -> None:
    """The two node cycle. Array containment on the path handles it; a visited set held per
    row rather than per path would not."""
    graph = walk(engine, estate, global_scope(estate), "sg-app")
    assert {node.name for node in graph.nodes} == {"sg-app", "sg-db"}


def test_the_whole_awkward_estate_walks_without_hanging(engine: Engine, estate: UUID) -> None:
    graph = walk(engine, estate, global_scope(estate), "vpc")
    assert {node.name for node in graph.nodes} == {
        "vpc",
        "subnet-a",
        "subnet-b",
        "sg-self",
        "sg-app",
        "sg-db",
        "instance",
        "far",
    }


# --- the bounds ------------------------------------------------------------


def test_the_depth_bound_stops_the_walk(engine: Engine, estate: UUID) -> None:
    graph = walk(engine, estate, global_scope(estate), "vpc", bounds=Bounds(max_depth=1))
    assert {node.name for node in graph.nodes} == {"vpc", "subnet-a", "subnet-b", "sg-self", "far"}
    assert graph.depth_reached == 1


def test_a_depth_of_nought_returns_the_root_alone(engine: Engine, estate: UUID) -> None:
    graph = walk(engine, estate, global_scope(estate), "vpc", bounds=Bounds(max_depth=0))
    assert [node.name for node in graph.nodes] == ["vpc"]
    assert graph.edges == ()


def test_the_node_cap_truncates_and_says_so(engine: Engine, estate: UUID) -> None:
    graph = walk(engine, estate, global_scope(estate), "vpc", bounds=Bounds(max_nodes=3))
    assert len(graph.nodes) == 3
    assert graph.is_truncated
    assert graph.omitted_nodes >= 1


def test_a_root_that_does_not_exist_is_an_empty_subgraph(engine: Engine, estate: UUID) -> None:
    with engine.begin() as connection:
        graph = repo(connection).subgraph(global_scope(estate), root_id=uuid4())
    assert graph.nodes == ()
    assert graph.coverage == ()


# --- the scope, which is enforced inside the recursion ----------------------


def test_a_narrow_scope_does_not_walk_out_of_its_accounts(engine: Engine, estate: UUID) -> None:
    """The assertion the recursive term's own scope predicate exists for. Without it the walk
    crosses the cross account edge into a VPC the caller was not granted, and the answer looks
    entirely normal."""
    graph = walk(engine, estate, narrow_scope(estate, MINE), "vpc")
    assert "far" not in {node.name for node in graph.nodes}
    assert {node.account_key.account_id for node in graph.nodes} == {MINE}


def test_the_cross_account_edge_survives_as_a_boundary_under_a_narrow_scope(
    engine: Engine, estate: UUID
) -> None:
    """An edge Meter cannot follow is not an absent edge. The reader sees that the VPC peers
    with something, and the coverage row for the other account says why they cannot see it."""
    graph = walk(engine, estate, narrow_scope(estate, MINE), "vpc")
    peers = [edge for edge in graph.edges if edge.edge_kind is EdgeKind.PEERS_WITH]
    assert len(peers) == 1
    assert peers[0].is_cross_account
    assert peers[0].to_node_id not in {node.node_id for node in graph.nodes}


def test_an_empty_scope_reads_nothing_rather_than_everything(engine: Engine, estate: UUID) -> None:
    """The fail closed case. Empty means nothing, not everything."""
    scope = Scope(tenant_id=estate, is_global=False, accounts=frozenset())
    graph = walk(engine, estate, scope, "vpc")
    assert graph.nodes == ()
    assert graph.edges == ()


def test_a_scope_for_another_account_cannot_reach_this_root(engine: Engine, estate: UUID) -> None:
    graph = walk(engine, estate, narrow_scope(estate, THEIRS), "vpc")
    assert graph.nodes == ()


# --- coverage travels with the answer ---------------------------------------


def test_coverage_names_only_the_slices_the_answer_touched(engine: Engine, estate: UUID) -> None:
    """A banner naming eleven regions when the map shows two is one a reader learns to
    dismiss, and the point of the banner is that it is not dismissed."""
    graph = walk(engine, estate, narrow_scope(estate, MINE), "vpc")
    assert {entry.account_key.account_id for entry in graph.coverage} == {MINE}
    assert graph.incomplete_slices == ()


def test_a_global_walk_carries_the_partial_slice_it_crossed(engine: Engine, estate: UUID) -> None:
    graph = walk(engine, estate, global_scope(estate), "vpc")
    (incomplete,) = graph.incomplete_slices
    assert incomplete.account_key.account_id == THEIRS
    assert incomplete.state is CoverageState.PARTIAL
    assert not graph.is_whole
    with pytest.raises(IncompleteGraphError, match=THEIRS):
        graph.require_whole()


def test_the_estate_wide_banner_lists_every_incomplete_slice_in_scope(
    engine: Engine, estate: UUID
) -> None:
    with engine.begin() as connection:
        found = repo(connection).incomplete(global_scope(estate))
    assert [entry.account_key.account_id for entry in found] == [THEIRS]
    with engine.begin() as connection:
        narrowed = repo(connection).incomplete(narrow_scope(estate, MINE))
    assert narrowed == ()


# --- the reverse walk ------------------------------------------------------


def test_the_inward_walk_finds_what_reaches_a_resource(engine: Engine, estate: UUID) -> None:
    """FEAT-044's question, which is the same walk with the arrow reversed."""
    graph = walk(engine, estate, global_scope(estate), "instance", inward=True)
    assert {node.name for node in graph.nodes} == {"instance", "subnet-a", "vpc"}


def test_the_inward_walk_is_not_the_outward_one(engine: Engine, estate: UUID) -> None:
    outward = walk(engine, estate, global_scope(estate), "instance")
    inward = walk(engine, estate, global_scope(estate), "instance", inward=True)
    assert {node.name for node in outward.nodes} != {node.name for node in inward.nodes}


def test_the_two_statements_differ_only_in_their_direction() -> None:
    """A second literal rather than the direction as a parameter, because a join column
    chosen by a bound value is not something PostgreSQL will plan. This is what keeps the two
    in step: everything but the three direction lines is identical."""
    assert WALK != WALK_INWARD
    normalised = WALK_INWARD.replace("e.to_node_id = r.node_id", "e.from_node_id = r.node_id")
    normalised = normalised.replace(
        "        e.from_node_id,\n        r.depth + 1,\n        r.path || e.from_node_id",
        "        e.to_node_id,\n        r.depth + 1,\n        r.path || e.to_node_id",
    )
    normalised = normalised.replace(
        "NOT (e.from_node_id = ANY(r.path))", "NOT (e.to_node_id = ANY(r.path))"
    )
    assert normalised == WALK


def test_the_walk_is_audited_once(engine: Engine, estate: UUID) -> None:
    """One audit row for the whole traversal. Four would make the log unreadable at exactly
    the moment somebody is reading it."""
    with engine.begin() as connection:
        connection.execute(CLEAR_AUDIT, {"t": estate})
    walk(engine, estate, global_scope(estate), "vpc")
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT resource, is_global_read FROM audit_event WHERE tenant_id = :t "
                "AND resource = 'topology_node'"
            ),
            {"t": estate},
        ).all()
    assert len(rows) == 1
    assert rows[0].is_global_read is True
