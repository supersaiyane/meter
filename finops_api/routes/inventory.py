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
from finops_api.db.repositories.cost import CostRepository
from finops_api.db.repositories.topology import TopologyRepository, as_node
from finops_api.deps import (
    get_access_context,
    get_connection,
    get_scope,
    get_settings,
)
from finops_api.routes import API_PREFIX, build_meta
from finops_api.routes.waste import recommendation_out
from finops_api.schemas import (
    BlastPartOut,
    BlastRadiusOut,
    CoverageOutList,
    EdgeOut,
    EntityOut,
    Envelope,
    InventoryRootOut,
    InventoryRootsOut,
    NodeOut,
    ResourceFiltersOut,
    ResourceListOut,
    SliceCoverageOut,
    SubgraphOut,
)
from finops_core.config import Settings
from finops_core.domain.tenant import Scope
from finops_core.domain.topology import CoverageState, Edge, GraphCoverage, Node
from finops_query.blast_radius import assess
from finops_query.graph import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_NODES,
    MAX_ALLOWED_DEPTH,
    MAX_ALLOWED_NODES,
    Bounds,
    IncompleteGraphError,
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


@router.get("/inventory/nodes/{node_id}/blast-radius", response_model=Envelope[BlastRadiusOut])
def blast_radius(
    node_id: UUID,
    connection: Connection = Depends(get_connection),
    settings: Settings = Depends(get_settings),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[BlastRadiusOut]:
    """What a change to this resource can reach, or why we will not say.

    FEAT-044, TASK-P3-020, P3 specification section 12. The gate, built before the thing it
    gates: constraint 6 means nothing here applies anything, and a scorer written after an
    applier is a scorer written under pressure to approve.

    **A refusal is a 200 with a reason, not an error.** The graph having a hole in it is a fact
    about the estate rather than a fault in the request, and a status code would make the screen
    render a failure. So both halves travel on one payload and exactly one is populated.

    **Its own route rather than a field on the entity page.** That page walks one hop and this
    walks four, so folding it in would make every visit to a resource pay for a traversal most
    visits do not need, and a refusal here would have to be explained as part of a payload that
    otherwise succeeded.
    """
    repository = TopologyRepository(connection, context)
    node = repository.one(scope, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=NO_SUCH_NODE)

    bounds = Bounds(max_depth=settings.blast_radius_depth)
    graph = repository.subgraph(scope, root_id=node_id, bounds=bounds)
    try:
        found = assess(
            graph,
            target=node,
            wide_at=settings.blast_radius_wide_at,
            max_depth=bounds.max_depth,
        )
    except IncompleteGraphError as refused:
        # Not caught to hide it. Caught so the slices reach the screen as words, which is the
        # difference between a refusal somebody can act on and one they can only be annoyed by.
        answer = BlastRadiusOut(
            band=None,
            parts=(),
            reach=None,
            accounts=None,
            boundary_edges=None,
            depth_bound_reached=False,
            is_lower_bound=True,
            refused_because=tuple(
                f"{entry.account_key.account_id} in {entry.region_id or 'the global slice'} is "
                f"{entry.state.value}"
                + (f" because of {entry.cause.value}" if entry.cause is not None else "")
                for entry in refused.subgraph.incomplete_slices
            )
            or (
                f"the walk was cut short by the {bounds.max_nodes} node cap, so at least "
                f"{refused.subgraph.omitted_nodes} resources were never looked at",
            ),
            max_depth=bounds.max_depth,
        )
    else:
        answer = BlastRadiusOut(
            band=found.band.value,
            parts=tuple(
                BlastPartOut(name=part.name, count=part.count, why=part.why) for part in found.parts
            ),
            reach=found.reach,
            accounts=found.accounts,
            boundary_edges=found.boundary_edges,
            depth_bound_reached=found.depth_bound_reached,
            is_lower_bound=found.is_lower_bound,
            refused_because=(),
            max_depth=bounds.max_depth,
        )

    visible, total = _slice_coverage(graph)
    meta = build_meta(
        connection,
        scope,
        context,
        visible=visible,
        rows=graph.nodes,
        # Slices, like every other P4 surface. The coverage is also the reason a refusal
        # happened, so a screen that reads the strip already knows why before it reads the body.
        coverage=(visible, total),
        coverage_unit="slices",
    )
    return Envelope(data=answer, meta=meta)


@router.get("/inventory/resources", response_model=Envelope[ResourceListOut])
def resources(
    account_id: str | None = Query(default=None, description="Narrow to one account."),
    region_id: str | None = Query(
        default=None, description="Narrow to one region. Omit for every region."
    ),
    node_kind: str | None = Query(default=None, description="Narrow to one kind of resource."),
    resource_type: str | None = Query(
        default=None, description="Narrow to one provider resource type."
    ),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[ResourceListOut]:
    """Every resource this scope can see, filtered and paginated on the server.

    FEAT-056, TASK-P4-012, closing ISS-204. The map answers what is connected to what for one
    root, bounded to four hops. It cannot answer how many gp2 volumes are in one region, which
    is the question a reader actually arrives with.

    Paginated here rather than in the browser. An estate of three hundred accounts is not a
    list a client sorts, and the bound exists for the same reason the traversal's does: an
    unbounded read of a real estate returns the estate.

    The coverage in `meta` counts slices rather than accounts and rows. A list is drawn from
    whatever slices were read, and a slice that refused us contributes nothing while looking
    identical to a region that is genuinely empty, so the denominator a reader needs is the
    number of slices behind the list and not the number of rows in it.
    """
    repository = TopologyRepository(connection, context)
    rows, total = repository.page(
        scope,
        account_id=account_id,
        region_id=region_id,
        node_kind=node_kind,
        resource_type=resource_type,
        limit=limit,
        offset=offset,
    )
    # Read once each. Two calls for the same denominator could disagree, which is the same
    # reason `page` returns its own total rather than leaving the caller to count again.
    slices = repository.slice_count(scope)
    unread = repository.incomplete(scope)
    found = ResourceListOut(
        resources=tuple(_node_out(as_node(row)) for row in rows),
        total=total,
        limit=limit,
        offset=offset,
        filters=ResourceFiltersOut(**repository.vocabularies(scope)),
    )
    meta = build_meta(
        connection,
        scope,
        context,
        # Slices, like the map's, because the honest question about a list of resources is how
        # much of the estate it was drawn from. Counting the rows would report a full page as
        # complete coverage of an estate half of which was never read.
        visible=slices - len(unread),
        rows=rows,
        coverage=(slices - len(unread), slices),
        coverage_unit="slices",
    )
    return Envelope(data=found, meta=meta)


@router.get("/inventory/nodes/{node_id}", response_model=Envelope[EntityOut])
def entity(
    node_id: UUID,
    connection: Connection = Depends(get_connection),
    settings: Settings = Depends(get_settings),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[EntityOut]:
    """One resource: what it is, what it is attached to, what it costs, what is wrong with it.

    FEAT-053. The destination every list in the product needed and did not have, adopted from
    the 2026-09-26 IBM Turbonomic review.

    Two of the fields are admissions rather than facts, and both are there because the
    alternative is a page that reads as reassuring. `coverage` says whether the slice this
    resource came from was read whole, because a neighbour list drawn from a PARTIAL slice may
    be missing the edge that matters. `unmatched_findings` says how many findings in the same
    account could not be joined to any resource, because an empty finding list otherwise reads
    as a clean resource.

    A 404 for a node this scope cannot see, which is the same answer as one that does not
    exist. Distinguishing them would tell a narrowed reader that a resource exists in an
    account they were not granted.
    """
    topology = TopologyRepository(connection, context)
    node = topology.one(scope, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=NO_SUCH_NODE)

    # One hop, through the same bounded traversal the map uses, so the neighbour list and the
    # map cannot disagree about what this resource is attached to.
    around = topology.subgraph(scope, root_id=node_id, bounds=Bounds(max_depth=1))
    neighbours = tuple(one for one in around.nodes if one.node_id != node.node_id)

    findings, unmatched = topology.findings_for(scope, node)

    # FEAT-057. Derived here rather than stored, because UNMANAGED rests on a declaration about
    # our own configuration and a stored judgement outlives the configuration it was made under.
    management, address, reference = topology.management_of(scope, node, settings)

    costs = CostRepository(connection, context)
    period = costs.latest_period(scope)
    monthly = None if period is None else costs.for_resource(scope, node.provider_id, period)

    found = EntityOut(
        node=_node_out(node),
        coverage=None
        if (slice_row := topology.slice_coverage(scope, node)) is None
        else _coverage_out(slice_row),
        neighbours=tuple(_node_out(one) for one in neighbours),
        edges=tuple(
            _edge_out(edge, {one.node_id for one in around.nodes}) for edge in around.edges
        ),
        findings=tuple(recommendation_out(row) for row in findings),
        unmatched_findings=unmatched,
        monthly_cost=monthly,
        cost_period=period,
        management_state=management,
        iac_address=address,
        iac_state_reference=reference,
    )
    meta = build_meta(
        connection,
        scope,
        context,
        # One resource, so the coverage question is about its own slice rather than about the
        # estate. One of one when the slice is complete, nought of one when it is not, which is
        # what makes the trust strip say degraded on a page drawn from an unread region.
        visible=1 if found.coverage is not None and found.coverage.state == "COMPLETE" else 0,
        rows=[node],
        coverage=(
            1 if found.coverage is not None and found.coverage.state == "COMPLETE" else 0,
            1,
        ),
        coverage_unit="slices",
    )
    return Envelope(data=found, meta=meta)
