"""The bounds, the cap and the coverage that travels with a subgraph.

Pure, because all of it is. The recursive statement lives in the repository and its own
test covers termination against a real database; what is asserted here is everything the
statement cannot express, and the case that matters most is the one where a caller asks a
question a partial graph cannot answer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.topology import (
    CoverageCause,
    CoverageState,
    Edge,
    EdgeKind,
    GraphCoverage,
    Node,
    NodeKind,
    node_id_for,
)
from finops_query.graph import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_NODES,
    MAX_ALLOWED_DEPTH,
    MAX_ALLOWED_NODES,
    Bounds,
    IncompleteGraphError,
    Subgraph,
    assemble,
)

TENANT = UUID("11111111-1111-1111-1111-111111111111")
ACCOUNT = AccountKey(provider=Provider.AWS, account_id="111122223333")
OTHER = AccountKey(provider=Provider.AWS, account_id="444455556666")
REGION = "eu-west-1"
NOW = datetime(2026, 9, 26, 6, 0, tzinfo=UTC)
FETCHED = datetime(2026, 9, 26, 6, 5, tzinfo=UTC)


def node(name: str, *, account: AccountKey = ACCOUNT, region: str | None = REGION) -> Node:
    provider_id = f"arn:aws:ec2:{region or 'global'}:{account.account_id}:vpc/{name}"
    return Node(
        node_id=node_id_for(tenant_id=TENANT, provider_id=provider_id),
        account_key=account,
        provider_id=provider_id,
        node_kind=NodeKind.VPC,
        resource_type="AWS::EC2::VPC",
        region_id=region,
        availability_zone=None,
        name=name,
        tags={},
        as_of=NOW,
        collected_at=FETCHED,
    )


def link(origin: Node, target: Node, *, cross: bool = False) -> Edge:
    return Edge(
        from_node_id=origin.node_id,
        to_node_id=target.node_id,
        edge_kind=EdgeKind.CONTAINS,
        is_cross_account=cross,
        source="CONFIG_RELATIONSHIP",
        as_of=NOW,
        collected_at=FETCHED,
    )


def coverage(
    *,
    account: AccountKey = ACCOUNT,
    region: str | None = REGION,
    state: CoverageState = CoverageState.COMPLETE,
    cause: CoverageCause | None = None,
) -> GraphCoverage:
    return GraphCoverage(
        account_key=account,
        region_id=region,
        state=state,
        cause=cause,
        node_count=3,
        edge_count=2,
        as_of=NOW,
        collected_at=FETCHED,
    )


# --- the bounds are parameters with defaults, not literals -------------------


def test_the_defaults_are_the_documented_numbers() -> None:
    assert Bounds() == Bounds(max_depth=DEFAULT_MAX_DEPTH, max_nodes=DEFAULT_MAX_NODES)
    assert DEFAULT_MAX_NODES == 2000


def test_a_bound_beyond_the_ceiling_is_refused() -> None:
    """A bound any caller can widen without limit is not a bound."""
    with pytest.raises(ValueError, match="exceeds the ceiling"):
        Bounds(max_depth=MAX_ALLOWED_DEPTH + 1)
    with pytest.raises(ValueError, match="exceeds the ceiling"):
        Bounds(max_nodes=MAX_ALLOWED_NODES + 1)


def test_a_cap_below_one_is_refused() -> None:
    """It would return nothing at all, which a caller would read as an empty estate."""
    with pytest.raises(ValueError, match="below one"):
        Bounds(max_nodes=0)


def test_the_fetch_limit_is_one_more_than_the_cap() -> None:
    """A statement limited to exactly the cap returns the same thing for an estate of two
    thousand and an estate of two million, and the difference is the one a reader needs."""
    assert Bounds(max_nodes=10).fetch_limit == 11


# --- the depth bound --------------------------------------------------------


def test_a_node_beyond_the_depth_bound_is_dropped() -> None:
    near, far = node("near"), node("far")
    graph = assemble(
        root_id=near.node_id,
        found=((near, 0), (far, 3)),
        edges=(link(near, far),),
        coverage=(coverage(),),
        bounds=Bounds(max_depth=1),
    )
    assert [one.name for one in graph.nodes] == ["near"]
    assert graph.edges == ()
    assert graph.depth_reached == 0


def test_the_depth_reached_is_how_far_the_walk_got_not_the_bound() -> None:
    root, second = node("root"), node("second")
    graph = assemble(
        root_id=root.node_id,
        found=((root, 0), (second, 1)),
        edges=(),
        coverage=(coverage(),),
        bounds=Bounds(max_depth=4),
    )
    assert graph.depth_reached == 1


# --- the cap is reported, never silent ---------------------------------------


def test_hitting_the_cap_reports_how_many_did_not_fit() -> None:
    """A map that quietly drew nine hundred of a thousand nodes is indistinguishable from an
    estate with nine hundred, which is the same failure as a refused region drawn as an
    empty one."""
    nodes = tuple((node(f"n{index:03d}"), 1) for index in range(10))
    graph = assemble(
        root_id=nodes[0][0].node_id,
        found=nodes,
        edges=(),
        coverage=(coverage(),),
        bounds=Bounds(max_nodes=4),
    )
    assert len(graph.nodes) == 4
    assert graph.omitted_nodes == 6
    assert graph.is_truncated


def test_nothing_omitted_is_not_truncated() -> None:
    root = node("root")
    graph = assemble(root_id=root.node_id, found=((root, 0),), edges=(), coverage=(coverage(),))
    assert graph.omitted_nodes == 0
    assert not graph.is_truncated


def test_the_cap_keeps_the_nearest_nodes_and_is_deterministic() -> None:
    """Keeping an arbitrary subset would make the map change shape between refreshes with
    nothing having changed in the estate."""
    root = node("root")
    one_hop = [node(f"b{index}") for index in range(3)]
    two_hop = [node(f"c{index}") for index in range(3)]
    found = ((root, 0), *((one, 1) for one in one_hop), *((two, 2) for two in two_hop))
    first = assemble(
        root_id=root.node_id, found=found, edges=(), coverage=(), bounds=Bounds(max_nodes=3)
    )
    second = assemble(
        root_id=root.node_id,
        found=tuple(reversed(found)),
        edges=(),
        coverage=(),
        bounds=Bounds(max_nodes=3),
    )
    assert [one.name for one in first.nodes] == [one.name for one in second.nodes]
    assert first.nodes[0].name == "root"
    assert all(str(one.name).startswith(("root", "b")) for one in first.nodes)


def test_an_edge_to_a_node_the_cap_cut_is_dropped() -> None:
    """It would draw as a line to nowhere, and the cap's own report is what tells the reader
    why."""
    root, kept, cut = node("aaa"), node("bbb"), node("zzz")
    graph = assemble(
        root_id=root.node_id,
        found=((root, 0), (kept, 1), (cut, 1)),
        edges=(link(root, kept), link(root, cut)),
        coverage=(),
        bounds=Bounds(max_nodes=2),
    )
    assert len(graph.nodes) == 2
    assert [edge.to_node_id for edge in graph.edges] == [kept.node_id]
    assert graph.omitted_nodes == 1


def test_an_edge_to_a_node_that_was_never_fetched_is_kept() -> None:
    """A boundary rather than a casualty of the cap. The far end of a cross account edge is
    the most interesting thing on the map, and an edge pointing at a node with no row is how
    the schema says the interior is unknown."""
    root = node("root")
    beyond = node("beyond", account=OTHER)
    graph = assemble(
        root_id=root.node_id,
        found=((root, 0),),
        edges=(link(root, beyond, cross=True),),
        coverage=(coverage(),),
    )
    assert len(graph.edges) == 1
    assert graph.edges[0].is_cross_account
    assert graph.omitted_nodes == 0


# --- coverage is part of the return type ------------------------------------


def test_coverage_comes_back_with_the_answer() -> None:
    root = node("root")
    graph = assemble(root_id=root.node_id, found=((root, 0),), edges=(), coverage=(coverage(),))
    assert len(graph.coverage) == 1
    assert graph.incomplete_slices == ()
    assert graph.is_whole


def test_an_incomplete_slice_is_named_rather_than_counted() -> None:
    root = node("root")
    graph = assemble(
        root_id=root.node_id,
        found=((root, 0),),
        edges=(),
        coverage=(
            coverage(),
            coverage(
                region="eu-north-1",
                state=CoverageState.PARTIAL,
                cause=CoverageCause.ACCESS_DENIED,
            ),
        ),
    )
    (incomplete,) = graph.incomplete_slices
    assert incomplete.region_id == "eu-north-1"
    assert incomplete.cause is CoverageCause.ACCESS_DENIED
    assert not graph.is_whole


def test_a_subgraph_over_complete_slices_that_hit_the_cap_is_not_whole_either() -> None:
    """Both halves of `is_whole`. A caller scoring a change against a truncated answer would
    be scoring the first two thousand neighbours of a resource with more."""
    nodes = tuple((node(f"n{index}"), 1) for index in range(5))
    graph = assemble(
        root_id=nodes[0][0].node_id,
        found=nodes,
        edges=(),
        coverage=(coverage(),),
        bounds=Bounds(max_nodes=2),
    )
    assert graph.incomplete_slices == ()
    assert not graph.is_whole


# --- require_whole, which is what FEAT-044 calls ----------------------------


def test_require_whole_returns_the_subgraph_when_it_is_whole() -> None:
    root = node("root")
    graph = assemble(root_id=root.node_id, found=((root, 0),), edges=(), coverage=(coverage(),))
    assert graph.require_whole() is graph


def test_require_whole_refuses_a_partial_slice_and_names_it() -> None:
    """The P3 specification section 12: a blast radius score refuses against a PARTIAL or
    UNREAD slice rather than scoring what it can see, because a change that looks contained
    and is not is the one wrong answer nobody checks."""
    root = node("root")
    graph = assemble(
        root_id=root.node_id,
        found=((root, 0),),
        edges=(),
        coverage=(
            coverage(account=OTHER, state=CoverageState.PARTIAL, cause=CoverageCause.ACCESS_DENIED),
        ),
    )
    with pytest.raises(IncompleteGraphError) as raised:
        graph.require_whole()
    message = str(raised.value)
    assert OTHER.account_id in message
    assert "AccessDenied" in message
    assert "not an absent edge" in message
    # The subgraph travels with the error, so a caller that wants to render the partial
    # answer with a banner can, and one that wants to refuse can.
    assert raised.value.subgraph is graph


def test_require_whole_refuses_an_unread_slice_too() -> None:
    root = node("root")
    graph = assemble(
        root_id=root.node_id,
        found=((root, 0),),
        edges=(),
        coverage=(
            GraphCoverage(
                account_key=ACCOUNT,
                region_id="ap-south-1",
                state=CoverageState.UNREAD,
                cause=CoverageCause.NOT_YET_ATTEMPTED,
                node_count=0,
                edge_count=0,
                as_of=NOW,
                collected_at=FETCHED,
            ),
        ),
    )
    with pytest.raises(IncompleteGraphError, match="UNREAD"):
        graph.require_whole()


def test_require_whole_names_the_truncation_when_that_is_the_only_problem() -> None:
    nodes = tuple((node(f"n{index}"), 1) for index in range(5))
    graph = assemble(
        root_id=nodes[0][0].node_id,
        found=nodes,
        edges=(),
        coverage=(coverage(),),
        bounds=Bounds(max_nodes=2),
    )
    with pytest.raises(IncompleteGraphError, match="did not fit under the cap"):
        graph.require_whole()


# --- the empty answer -------------------------------------------------------


def test_an_empty_walk_is_an_empty_subgraph_rather_than_an_error() -> None:
    """A root with no neighbours is a legitimate answer, and a root nobody can read is an
    empty one. Neither is an exception, because the coverage rows are what tell them
    apart."""
    root_id = node("root").node_id
    graph = assemble(root_id=root_id, found=(), edges=(), coverage=())
    assert graph.nodes == ()
    assert graph.depth_reached == 0
    assert graph.is_whole


def test_a_negative_omission_count_is_refused() -> None:
    with pytest.raises(ValueError, match="never negative"):
        Subgraph(
            root_id=node("root").node_id,
            nodes=(),
            edges=(),
            coverage=(),
            depth_reached=0,
            omitted_nodes=-1,
        )
