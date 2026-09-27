"""What a change can reach, and the four times we refuse to say.

FEAT-044, TASK-P3-020, P3 specification section 12. Pure.

The refusals carry this file, not the counting. Counting reachable nodes is arithmetic. What
this module exists for is the trade the specification makes: a score that is sometimes absent
is less useful than one always present, and it is the right trade, because an absent score
reads as "we do not know" while a low score computed from a graph missing a region reads as
"this change is safe". That second sentence is a claim the product would be making on its own
initiative about somebody's production estate, and nobody checks the answer that agrees with
them.
"""

from __future__ import annotations

import pytest

from finops_core.domain.topology import CoverageCause, CoverageState
from finops_query.blast_radius import Band, BlastRadius, assess
from finops_query.graph import IncompleteGraphError, Subgraph
from tests.query.test_graph import OTHER, coverage, link, node

DEPTH = 4
WIDE_AT = 5


def graph(
    *,
    nodes: tuple[object, ...],
    edges: tuple[object, ...] = (),
    slices: tuple[object, ...] | None = None,
    depth_reached: int = 2,
    omitted: int = 0,
) -> Subgraph:
    """A walk from the first node. Whole by default, so a case has to ask to be partial."""
    first = nodes[0]
    return Subgraph(
        root_id=first.node_id,  # type: ignore[attr-defined]
        nodes=nodes,  # type: ignore[arg-type]
        edges=edges,  # type: ignore[arg-type]
        coverage=slices if slices is not None else (coverage(),),  # type: ignore[arg-type]
        depth_reached=depth_reached,
        omitted_nodes=omitted,
    )


def radius(subgraph: Subgraph, target: object, *, wide_at: int = WIDE_AT) -> BlastRadius:
    return assess(subgraph, target=target, wide_at=wide_at, max_depth=DEPTH)  # type: ignore[arg-type]


# --- the refusals, which are the feature -------------------------------------


def test_a_partial_slice_refuses_rather_than_scoring_what_it_can_see() -> None:
    """The criterion this task exists for. A region that refused us contributes no edges, so
    every change through it looks more contained than it is, in the one direction that
    matters."""
    root = node("vpc")
    partial = graph(
        nodes=(root,),
        slices=(
            coverage(),
            coverage(account=OTHER, state=CoverageState.PARTIAL, cause=CoverageCause.ACCESS_DENIED),
        ),
    )
    with pytest.raises(IncompleteGraphError) as refused:
        radius(partial, root)
    # The slices by name, because "the graph is incomplete" sends nobody anywhere.
    assert "444455556666" in str(refused.value)
    assert "PARTIAL" in str(refused.value)


def test_an_unread_slice_refuses_as_well() -> None:
    """Unread is not a synonym for partial and both are unsafe to score against. A slice
    nobody attempted and a slice that refused us differ in whose fault it is, not in whether
    the answer can be trusted."""
    root = node("vpc")
    unread = graph(
        nodes=(root,),
        slices=(
            coverage(),
            coverage(
                account=OTHER,
                state=CoverageState.UNREAD,
                cause=CoverageCause.NOT_YET_ATTEMPTED,
            ),
        ),
    )
    with pytest.raises(IncompleteGraphError):
        radius(unread, root)


def test_a_walk_the_node_cap_cut_short_refuses() -> None:
    """A radius computed from four of thirteen nodes is not a small radius. The cap is ours
    rather than the estate's, which makes this refusal about our own bound and not about
    anything the customer did."""
    root = node("vpc")
    with pytest.raises(IncompleteGraphError):
        radius(graph(nodes=(root,), omitted=9), root)


def test_the_refusal_carries_the_graph_so_a_caller_can_still_render_it() -> None:
    """Neither branch is forced. A screen that wants to draw the partial neighbourhood with a
    banner can, and one that wants to show nothing can. What neither can do is receive the
    score without being told the graph had a hole in it."""
    root = node("vpc")
    partial = graph(
        nodes=(root, node("subnet")),
        slices=(coverage(state=CoverageState.PARTIAL, cause=CoverageCause.THROTTLED),),
    )
    with pytest.raises(IncompleteGraphError) as refused:
        radius(partial, root)
    assert len(refused.value.subgraph.nodes) == 2


# --- what it says when it does answer ----------------------------------------


def test_the_target_is_not_in_its_own_reach() -> None:
    """A resource affecting itself is not a radius, and counting it would make every answer
    one larger than it is, including the empty one."""
    root = node("vpc")
    found = radius(graph(nodes=(root,)), root)
    assert found.reach == 0
    assert found.band is Band.CONTAINED


def test_a_small_neighbourhood_is_contained() -> None:
    root = node("vpc")
    near = tuple(node(f"subnet-{i}") for i in range(3))
    found = radius(graph(nodes=(root, *near), edges=tuple(link(root, one) for one in near)), root)
    assert found.reach == 3
    assert found.band is Band.CONTAINED


def test_a_large_neighbourhood_is_wide_at_the_configured_threshold() -> None:
    """The threshold is configuration, so the band moves when the number does rather than when
    somebody edits a constant. Asserted both sides of the boundary, because a threshold tested
    on one side is a threshold whose comparison direction is a guess."""
    root = node("vpc")
    near = tuple(node(f"subnet-{i}") for i in range(WIDE_AT))
    whole = graph(nodes=(root, *near))
    assert radius(whole, root, wide_at=WIDE_AT).band is Band.WIDE
    assert radius(whole, root, wide_at=WIDE_AT + 1).band is Band.CONTAINED


def test_touching_another_account_outranks_the_count() -> None:
    """Not simply wider than wide. A change inside one account is somebody's own problem, and a
    change reaching another account is somebody else's problem and they have not been asked.
    That survives whatever the count says, so it is a separate band and not a higher threshold.
    """
    root = node("vpc")
    far = node("their-vpc", account=OTHER)
    found = radius(graph(nodes=(root, far), edges=(link(root, far, cross=True),)), root)
    # One reachable resource, which would be CONTAINED on the count alone.
    assert found.reach == 1
    assert found.band is Band.CROSS_ACCOUNT
    assert found.accounts == 2


def test_every_part_is_published_with_its_count_and_its_meaning() -> None:
    """The band is what a reader scans and the parts are what they argue with. A band with no
    parts behind it is a judgement nobody can check, which is the same argument ADR-0016 makes
    about a severity and score.py makes about a posture."""
    root = node("vpc")
    found = radius(graph(nodes=(root, node("subnet"))), root)
    assert {one.name for one in found.parts} == {
        "Resources reached",
        "Other accounts touched",
        "Dependencies that leave the graph",
    }
    for part in found.parts:
        assert len(part.why) > 40, part.name


def test_an_edge_leaving_the_graph_is_counted_as_an_unknown() -> None:
    """The far end is in an account Meter does not collect from, so the radius is wider than
    this by an amount nobody here can measure. Counted rather than ignored, because an edge to
    nowhere is the most interesting thing on the map."""
    root = node("vpc")
    unseen = node("elsewhere", account=OTHER)
    # The far node is not in the payload, so the edge leaves the graph.
    found = radius(graph(nodes=(root,), edges=(link(root, unseen, cross=True),)), root)
    assert found.boundary_edges == 1
    assert [one.count for one in found.parts if "leave" in one.name] == [1]


# --- the lower bound, which is not optional ----------------------------------


def test_every_radius_is_a_lower_bound() -> None:
    """There is no configuration and no estate in which this stops being true. An infrastructure
    graph cannot see that one service reads another's queue, or that a report somebody runs
    every Monday is built on this table. A field rather than a docstring, so no consumer can
    render a radius without it."""
    root = node("vpc")
    assert radius(graph(nodes=(root,)), root).is_lower_bound


def test_a_walk_that_reached_its_depth_bound_says_so() -> None:
    """The floor `require_whole` cannot catch. A walk that completed within its depth is bounded
    rather than truncated, so nothing about it is incomplete, and the resources beyond the bound
    were never looked at, which is different from having been looked at and found absent."""
    root = node("vpc")
    assert radius(graph(nodes=(root,), depth_reached=DEPTH), root).depth_bound_reached
    assert not radius(graph(nodes=(root,), depth_reached=DEPTH - 1), root).depth_bound_reached
