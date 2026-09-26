"""A bounded subgraph, and the coverage of every slice it crossed.

**Coverage is part of the return type, not a separate call.** That is the whole design of
this module and it is deliberately inconvenient. An optional coverage lookup is one a
caller forgets, and the caller who forgets is FEAT-044, scoring somebody's production
change against a graph that is missing the one cross account edge that mattered. So
`Subgraph` carries it, and a caller that needs completeness calls `require_whole` and gets
an exception rather than a shorter answer.

**Where the traversal actually happens, and why not here.** The recursive walk is a
recursive common table expression in `finops_api/db/repositories/topology.py`, per
ADR-0005. TASK-P4-007 asks for it in this file and it cannot be: `finops_query` holds no
SQLAlchemy at all, and a criterion in the same task says to use the guard's own
`scoped_select`, which lives in `finops_api` and which the import contract forbids this
package from reaching. Scope enforcement outranks file placement, constraint 3, so the
statement is where the guard is. What is here is everything the statement cannot express:
the bounds, the cap, the truncation report, and the fact that coverage travels with the
result.

**Two bounds, and they answer different questions.** Depth stops the walk from crossing
the whole estate through a shared Transit Gateway, which is one hop from everything. The
node cap stops a single hop from returning fifty thousand network interfaces. A graph
without both renders as a hairball, which is a screen nobody reads and a payload nobody
can send.

**Hitting a bound is reported, never silent.** `omitted_nodes` is the count that did not
fit and `depth_reached` is how far the walk actually got. A map that quietly drew nine
hundred of a thousand nodes would be indistinguishable from an estate with nine hundred,
which is the same failure as a refused region drawn as an empty one.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from uuid import UUID

from finops_core.domain.topology import CoverageState, Edge, GraphCoverage, Node

#: How many hops out the walk goes unless a caller says otherwise.
#:
#: Four, because that is the length of the chain the map exists to show: a VPC contains a
#: subnet, which contains an instance, which is attached to a volume, and the security
#: group hanging off the instance is the fourth. Five adds the load balancer's target group
#: and roughly squares the answer on a real estate, which is why this is a parameter and
#: not a constant everyone lives with.
DEFAULT_MAX_DEPTH = 4

#: How many nodes come back before the rest are reported as omitted.
#:
#: Two thousand, which is the figure TASK-P4-009 caps the map at, enforced here as well as
#: at the route. Cytoscape draws two thousand nodes; it does not draw twenty thousand, and
#: a browser asked to try stops responding rather than drawing slowly.
DEFAULT_MAX_NODES = 2000

#: The ceilings a caller cannot raise past. A bound any caller can widen without limit is
#: not a bound, and the route's own parameters are checked against these rather than
#: against nothing.
MAX_ALLOWED_NODES = 10_000
MAX_ALLOWED_DEPTH = 10


@dataclass(frozen=True)
class Bounds:
    """How far out and how wide a traversal may go.

    A parameter with a default rather than a literal in the statement, which is the
    TASK-P4-007 criterion, because the right depth for a map and the right depth for a
    blast radius score are different numbers and neither is the other's.
    """

    max_depth: int = DEFAULT_MAX_DEPTH
    max_nodes: int = DEFAULT_MAX_NODES

    def __post_init__(self) -> None:
        if self.max_depth < 0:
            raise ValueError("A depth bound below nought asks for less than the root itself.")
        if self.max_depth > MAX_ALLOWED_DEPTH:
            raise ValueError(
                f"A depth of {self.max_depth} exceeds the ceiling of {MAX_ALLOWED_DEPTH}. A "
                "bound any caller can widen without limit is not a bound."
            )
        if self.max_nodes < 1:
            raise ValueError(
                "A node cap below one returns nothing at all, which a caller would read as "
                "an estate with nothing in it."
            )
        if self.max_nodes > MAX_ALLOWED_NODES:
            raise ValueError(
                f"A cap of {self.max_nodes} exceeds the ceiling of {MAX_ALLOWED_NODES}."
            )

    @property
    def fetch_limit(self) -> int:
        """One more node than the cap, so the caller can tell truncation from a fit.

        A statement limited to exactly the cap returns the same thing for an estate of two
        thousand and an estate of two million, and the difference is the one a reader
        needs. Asking for one more costs a row and answers it.
        """
        return self.max_nodes + 1


@dataclass(frozen=True)
class Subgraph:
    """What a traversal found, how far it got, and what it could not see.

    The three things beside the nodes and edges are the ones a caller is most likely to
    skip, so none of them is optional and none is behind a second call.
    """

    root_id: UUID
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    #: The coverage of every slice this subgraph touched. Not a convenience: section 6 of
    #: the P4 specification says a traversal returns its coverage as part of the return
    #: type, so a caller cannot forget to look.
    coverage: tuple[GraphCoverage, ...]
    #: How many hops the walk actually reached, which is at most the bound and is less when
    #: the neighbourhood ran out first.
    depth_reached: int
    #: Nodes inside the depth bound that did not fit under the node cap. Zero means the
    #: answer is whole with respect to the cap, and a non zero number is what a screen has
    #: to say out loud.
    omitted_nodes: int

    def __post_init__(self) -> None:
        if self.omitted_nodes < 0:
            raise ValueError("A count of what did not fit is never negative.")
        if self.depth_reached < 0:
            raise ValueError("A depth reached below nought is not a walk.")

    @property
    def is_truncated(self) -> bool:
        """True when the cap cut the answer short."""
        return self.omitted_nodes > 0

    @property
    def incomplete_slices(self) -> tuple[GraphCoverage, ...]:
        """Every slice the walk crossed that is not COMPLETE, in the order given.

        The thing a banner is drawn from. A slice with no coverage row cannot appear here,
        which is why the collector writes one for every enrolled slice: absence of a row
        and absence of resources are indistinguishable to a consumer, and one of them is
        dangerous.
        """
        return tuple(entry for entry in self.coverage if entry.state is not CoverageState.COMPLETE)

    @property
    def is_whole(self) -> bool:
        """True only when every slice crossed is COMPLETE and nothing was omitted.

        Both halves. A subgraph over complete slices that hit the node cap is not whole
        either, and a caller scoring a change against it would be scoring the first two
        thousand neighbours of a resource with more.
        """
        return not self.incomplete_slices and not self.is_truncated

    def require_whole(self) -> Subgraph:
        """Return self, or refuse, for a caller that cannot answer on a partial graph.

        This is what FEAT-044 calls. The P3 specification section 12 says a blast radius
        score refuses against a PARTIAL or UNREAD slice rather than scoring what it can
        see, because a change that looks contained and is not is the one wrong answer
        nobody checks.

        Raises:
            IncompleteGraphError: A slice crossed is not COMPLETE, or the cap cut the answer
                short. The message names the slices, because "the graph is incomplete"
                sends nobody anywhere.
        """
        if self.is_whole:
            return self
        raise IncompleteGraphError(self)


class IncompleteGraphError(RuntimeError):
    """A caller that needs a whole graph was handed one that is not.

    Carries the subgraph rather than only a message, so a caller that wants to render the
    partial answer with a banner can, and a caller that wants to refuse can. What neither
    can do is receive the partial answer without being told.
    """

    def __init__(self, subgraph: Subgraph) -> None:
        self.subgraph = subgraph
        named = ", ".join(
            f"{entry.account_key.account_id} in {entry.region_id or 'the global slice'} is "
            f"{entry.state.value}"
            + (f" because of {entry.cause.value}" if entry.cause is not None else "")
            for entry in subgraph.incomplete_slices
        )
        if subgraph.is_truncated:
            omitted = f"{subgraph.omitted_nodes} nodes did not fit under the cap"
            named = f"{named}; {omitted}" if named else omitted
        super().__init__(
            f"This subgraph cannot answer a question that needs completeness: {named}. An "
            "edge Meter cannot see is not an absent edge."
        )


def assemble(
    *,
    root_id: UUID,
    found: Sequence[tuple[Node, int]],
    edges: Sequence[Edge],
    coverage: Sequence[GraphCoverage],
    bounds: Bounds | None = None,
    inside: Collection[UUID] | None = None,
) -> Subgraph:
    """Turn what the traversal fetched into a bounded, honest subgraph.

    `found` is the nodes with the depth each was reached at, which the recursive statement
    returns and nothing else can supply: depth is a property of the walk rather than of the
    node. It may hold up to `bounds.fetch_limit` entries, one more than the cap, and that
    extra entry is how truncation is detected rather than guessed.

    **The cap keeps the nearest nodes.** Sorted by depth and then by the provider
    identifier, so the answer is the same on every run and a reader comparing two maps of
    one resource sees the same boxes. Keeping an arbitrary subset would make the map change
    shape between refreshes with nothing having changed in the estate.

    **An edge whose target did not survive is dropped, unless the target is a boundary.**
    An edge to a node that is not in the payload draws as a line to nowhere. An edge to a
    node Meter holds no row for is different and is kept: that is a boundary, and the far
    end of a cross account edge is the most interesting thing on the map.

    `inside` is what tells the two apart, and it is the set of node identifiers that exist
    in the graph within the caller's scope. Without it the fetched set stands in, which is
    wrong at the depth bound: a walk of depth nought fetches only the root, so every one of
    its neighbours would look like a boundary and the map would draw four lines to nowhere.
    The repository passes the real set because it is the only layer that can ask.
    """
    limits = bounds or Bounds()
    within_depth = [(node, depth) for node, depth in found if depth <= limits.max_depth]
    ordered = sorted(within_depth, key=lambda pair: (pair[1], pair[0].provider_id))
    kept = ordered[: limits.max_nodes]
    omitted = len(ordered) - len(kept)

    known = {node.node_id for node, _depth in kept}
    # A target Meter holds no row for is a boundary rather than a casualty of a bound, so it
    # is kept. `inside` is the real set of what exists in scope; the fetched set stands in
    # when a caller has none, which is right for a pure test and wrong at the depth bound.
    held = set(inside) if inside is not None else {node.node_id for node, _depth in found}
    surviving = tuple(
        edge
        for edge in edges
        if edge.from_node_id in known and (edge.to_node_id in known or edge.to_node_id not in held)
    )

    return Subgraph(
        root_id=root_id,
        nodes=tuple(node for node, _depth in kept),
        edges=surviving,
        coverage=tuple(coverage),
        depth_reached=max((depth for _node, depth in kept), default=0),
        omitted_nodes=omitted,
    )
