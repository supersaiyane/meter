"""The graph, over the wire, with what it could not see in the same payload.

Three routes. The shape worth noticing is that `SubgraphOut` carries its coverage, so a
screen cannot draw the map without having been handed the list of slices the map is
missing. That is section 6 of the P4 specification reaching the wire: a map that renders
without knowing which slices were unreadable draws them as sparse, and sparse is
indistinguishable from well connected on a diagram.

**The coverage banner counts slices, not accounts and not rows.** `scope_coverage` is
accounts on most routes because most routes read a number per account. A graph is read per
account and region, so a view over eleven of twelve regions is partial in a way counting
accounts cannot express, and a row count in that slot has been the defect three times, per
`tasks/lessons.md`. The unit travels on the wire for the same reason the query routes' does:
the route knows what it counted and the interface was guessing.

**The node cap is enforced here as well as in the query layer.** A caller may ask for a
smaller bound and may not ask for a larger one than the ceiling. Both places check, because
the route is where a caller's number arrives and the query layer is where the default lives,
and a ceiling in only one of them is a ceiling somebody routes around.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.topology import TopologyRepository
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import (
    CoverageOutList,
    EdgeOut,
    Envelope,
    InventoryRootOut,
    InventoryRootsOut,
    NodeOut,
    SliceCoverageOut,
    SubgraphOut,
)
from finops_core.domain.tenant import Scope
from finops_core.domain.topology import CoverageState, Edge, GraphCoverage, Node
from finops_query.graph import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_NODES,
    MAX_ALLOWED_DEPTH,
    MAX_ALLOWED_NODES,
    Bounds,
    Subgraph,
)

router = APIRouter(prefix=API_PREFIX, tags=["inventory"])

#: What a caller gets for a root nothing has collected. A 404 says the node does not exist,
#: which is the honest answer and is not the same as an empty graph: an empty graph would
#: say the resource is connected to nothing.
NO_SUCH_NODE = "No node with that identifier is visible in this scope."


def _node_out(node: Node) -> NodeOut:
    return NodeOut(
        node_id=node.node_id,
        provider_id=node.provider_id,
        account_id=node.account_key.account_id,
        node_kind=node.node_kind.value,
        resource_type=node.resource_type,
        region_id=node.region_id,
        availability_zone=node.availability_zone,
        name=node.name,
        as_of=node.as_of,
        collected_at=node.collected_at,
    )


def _edge_out(edge: Edge, drawn: set[UUID]) -> EdgeOut:
    return EdgeOut(
        from_node_id=edge.from_node_id,
        to_node_id=edge.to_node_id,
        edge_kind=edge.edge_kind.value,
        is_cross_account=edge.is_cross_account,
        source=edge.source,
        # Computed here rather than stored, because it is a property of this payload and not
        # of the estate: the same edge leaves the graph in one map and is interior in
        # another, depending on where the walk was rooted and how far it went.
        leaves_the_graph=edge.to_node_id not in drawn,
    )


def _coverage_out(entry: GraphCoverage) -> SliceCoverageOut:
    return SliceCoverageOut(
        account_id=entry.account_key.account_id,
        region_id=entry.region_id,
        state=entry.state.value,
        cause=None if entry.cause is None else entry.cause.value,
        node_count=entry.node_count,
        edge_count=entry.edge_count,
        as_of=entry.as_of,
        collected_at=entry.collected_at,
    )


def _subgraph_out(graph: Subgraph, bounds: Bounds) -> SubgraphOut:
    drawn = {node.node_id for node in graph.nodes}
    return SubgraphOut(
        root_id=graph.root_id,
        nodes=tuple(_node_out(node) for node in graph.nodes),
        edges=tuple(_edge_out(edge, drawn) for edge in graph.edges),
        coverage=tuple(_coverage_out(entry) for entry in graph.coverage),
        depth_reached=graph.depth_reached,
        max_depth=bounds.max_depth,
        omitted_nodes=graph.omitted_nodes,
        omitted_is_exact=graph.omitted_is_exact,
        max_nodes=bounds.max_nodes,
    )


def _slice_coverage(graph: Subgraph) -> tuple[int, int]:
    """Complete slices out of slices crossed, which is what the banner counts.

    Accounts would be the wrong denominator here and a row count would be worse. A map drawn
    from eleven complete regions and one refused one is eleven twelfths of an answer, and
    expressing that as one of one accounts is the banner saying nothing.
    """
    total = len(graph.coverage)
    complete = sum(1 for entry in graph.coverage if entry.state is CoverageState.COMPLETE)
    return complete, total


@router.get("/inventory/topology/{node_id}", response_model=Envelope[SubgraphOut])
def subgraph(
    node_id: UUID,
    depth: int = Query(default=DEFAULT_MAX_DEPTH, ge=0, le=MAX_ALLOWED_DEPTH),
    nodes: int = Query(default=DEFAULT_MAX_NODES, ge=1, le=MAX_ALLOWED_NODES),
    inward: bool = Query(
        default=False,
        description="Reverse the arrow: what reaches this resource rather than what it reaches.",
    ),
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[SubgraphOut]:
    """Everything within `depth` hops of one node, with the coverage of its slices.

    A 404 for a root nothing has collected, because an empty graph would say the resource is
    connected to nothing, which is a different and unearned claim.
    """
    bounds = Bounds(max_depth=depth, max_nodes=nodes)
    graph = TopologyRepository(connection, context).subgraph(
        scope, root_id=node_id, bounds=bounds, inward=inward
    )
    if not graph.nodes:
        raise HTTPException(status_code=404, detail=NO_SUCH_NODE)
    visible, total = _slice_coverage(graph)
    meta = build_meta(
        connection,
        scope,
        context,
        visible=visible,
        rows=graph.nodes,
        # Slices, not accounts and not rows. See the module docstring.
        coverage=(visible, total),
        coverage_unit="slices",
    )
    return Envelope(data=_subgraph_out(graph, bounds), meta=meta)


@router.get("/inventory/coverage", response_model=Envelope[CoverageOutList])
def coverage(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[CoverageOutList]:
    """Every slice a reader can see that is not COMPLETE.

    The estate wide banner, before anybody has picked a root. An empty list here means every
    enrolled slice was read whole, which is a claim the collector earns by writing a row for
    each one on every run rather than one only when something fails.
    """
    repository = TopologyRepository(connection, context)
    incomplete = repository.incomplete(scope)
    total = repository.slice_count(scope)
    found = CoverageOutList(incomplete=tuple(_coverage_out(entry) for entry in incomplete))
    meta = build_meta(
        connection,
        scope,
        context,
        visible=total - len(incomplete),
        rows=incomplete,
        coverage=(total - len(incomplete), total),
        coverage_unit="slices",
    )
    return Envelope(data=found, meta=meta)


@router.get("/inventory/roots", response_model=Envelope[InventoryRootsOut])
def roots(
    node_kind: str | None = Query(default=None, description="Narrow to one kind of resource."),
    limit: int = Query(default=200, ge=1, le=1000),
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[InventoryRootsOut]:
    """Nodes a reader can start a map from, so the first screen is not a blank field.

    Not the whole graph. A list of every network interface in an estate is a list nobody
    scrolls, so this names the kind it filtered on rather than pretending to be complete.
    """
    repository = TopologyRepository(connection, context)
    rows = repository.roots(scope, node_kind=node_kind, limit=limit)
    found = InventoryRootsOut(
        roots=tuple(
            InventoryRootOut(
                node_id=row.node_id,
                provider_id=str(row.provider_id),
                account_id=str(row.sub_account_id),
                node_kind=str(row.node_kind),
                resource_type=str(row.resource_type),
                region_id=row.region_id,
                name=row.name,
            )
            for row in rows
        )
    )
    meta = build_meta(
        connection,
        scope,
        context,
        # Accounts here, which is the ordinary unit, because a list of roots is a list of
        # resources across accounts rather than a view of slices.
        visible=repository.accounts_seen(scope),
        rows=rows,
    )
    return Envelope(data=found, meta=meta)
