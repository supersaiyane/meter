"""What else a change to one resource can reach, and when we refuse to say.

FEAT-044, TASK-P3-020, P3 specification section 12. Adopted in principle from the 2026-09-26
IBM Turbonomic review, whose Auto-Pilot scores blast radius from the dependency graph and auto
applies only the changes it judges safe. We build the gate and not the thing it gates, which is
the order on purpose: constraint 6 means nothing here applies anything, and a scorer written
after an applier is a scorer written under pressure to approve.

**It refuses rather than guesses, and that trade is the feature.** A score that is sometimes
absent is less useful than one always present. An absent score reads as "we do not know". A low
score computed from a graph missing a region reads as "this change is safe", which is a claim
the product would be making on its own initiative about somebody's production estate. So
`assess` calls `Subgraph.require_whole` first and raises rather than scoring what it can see.

**Every answer is a lower bound, and the type says so rather than the screen remembering to.**
An infrastructure graph holds what one resource is attached to. It does not hold that a service
reads another service's queue, that a job parses a file another job writes, or that a dashboard
somebody reports from every Monday is built on this table. Those are application level
dependencies and they are invisible here. `is_lower_bound` is therefore always true, and it is
a field rather than a docstring so no consumer can render a radius without it.

**The reach is a floor twice over.** Once for the paragraph above, and again whenever the walk
reached its depth bound: the resources beyond that bound were never looked at, which is
different from having been looked at and found absent. `require_whole` catches a walk the node
cap cut short and cannot catch this one, because a walk that completed within its depth is not
truncated, it is bounded.

**The band is derived and the threshold is configuration.** A number in code deciding what
counts as wide is a number nobody can argue with, which is ADR-0012's argument about cadence
applied to a judgement. The parts are published beside the band so a reader who disagrees can
point at the count rather than at the word.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from finops_core.domain.topology import Node
from finops_query.graph import Subgraph


class Band(StrEnum):
    """How far a change can reach, as a word.

    Three values, and `CROSS_ACCOUNT` is not simply "wider than WIDE". It is a different kind
    of fact: a change that stays inside one account is somebody's own problem, and a change
    that reaches another account is somebody else's problem and they have not been asked. That
    distinction survives whatever the counts say, so it is a separate band rather than a
    higher threshold.
    """

    CONTAINED = "CONTAINED"
    WIDE = "WIDE"
    CROSS_ACCOUNT = "CROSS_ACCOUNT"


@dataclass(frozen=True)
class Part:
    """One thing counted, and what it means.

    `why` is not decoration. The band is what a reader scans and the parts are what they
    argue with, and a band with no parts behind it is a judgement nobody can check.
    """

    name: str
    count: int
    why: str


@dataclass(frozen=True)
class BlastRadius:
    """What a change to one resource can reach, as far as an infrastructure graph can see."""

    band: Band
    parts: tuple[Part, ...]
    #: Resources reachable from the target within the depth bound, excluding the target.
    reach: int
    #: Accounts touched, including the target's own. Two or more means somebody else's estate.
    accounts: int
    #: Edges whose far end is outside what was read. Each one is a dependency we cannot follow.
    boundary_edges: int
    #: True where the walk reached its depth bound, so `reach` is a floor for that reason as
    #: well as for the reason below.
    depth_bound_reached: bool

    @property
    def is_lower_bound(self) -> bool:
        """Always true, and a property rather than a constant so it reads as a claim.

        An infrastructure graph cannot see that one service reads another's queue or that a
        report somebody runs every Monday is built on this table. Every radius here is
        therefore at least this wide and possibly wider, and there is no configuration and no
        estate in which that stops being the case.
        """
        return True


def assess(
    subgraph: Subgraph,
    *,
    target: Node,
    wide_at: int,
    max_depth: int,
) -> BlastRadius:
    """Score one resource's blast radius, or refuse.

    Args:
        subgraph: An outward walk from the target. Must be whole.
        target: The resource the change is to, excluded from its own reach.
        wide_at: How many reachable resources count as wide. Configuration, because a number
            in code deciding what is wide is a number nobody can argue with.
        max_depth: The bound the walk was given. Passed rather than read off the subgraph,
            which carries how far it got and not what it was allowed: a walk that reached
            three hops is bounded or finished depending on a number it does not hold.

    Raises:
        IncompleteGraphError: A slice crossed is not COMPLETE, or the node cap cut the walk
            short. Raised by `require_whole` and deliberately not caught here: a caller that
            wants to render the partial answer with a banner can, and one that wants to refuse
            can, and what neither can do is receive a score computed from a graph with a hole
            in it.
    """
    whole = subgraph.require_whole()

    reached: set[UUID] = {node.node_id for node in whole.nodes} - {target.node_id}
    accounts = {node.account_key.account_id for node in whole.nodes}
    boundary = tuple(
        edge
        for edge in whole.edges
        if edge.to_node_id not in {node.node_id for node in whole.nodes}
    )
    others = accounts - {target.account_key.account_id}

    parts = (
        Part(
            "Resources reached",
            len(reached),
            "Attached to the target, or attached to something that is, within the depth walked.",
        ),
        Part(
            "Other accounts touched",
            len(others),
            (
                "Accounts other than the target's own. One or more means a change here can "
                "affect an estate whose owner has not been asked."
            ),
        ),
        Part(
            "Dependencies that leave the graph",
            len(boundary),
            (
                "Edges whose far end is outside what was read, usually a resource in an "
                "account Meter does not collect from. Each one is a dependency nobody here "
                "can follow, so it widens the radius by an unknown amount."
            ),
        ),
    )

    if others:
        band = Band.CROSS_ACCOUNT
    elif len(reached) >= wide_at:
        band = Band.WIDE
    else:
        band = Band.CONTAINED

    return BlastRadius(
        band=band,
        parts=parts,
        reach=len(reached),
        accounts=len(accounts),
        boundary_edges=len(boundary),
        # A walk that stopped because it ran out of depth looked at nothing beyond it, which is
        # different from having looked and found nothing. `require_whole` cannot catch this: a
        # walk that completed within its depth is bounded rather than truncated.
        depth_bound_reached=whole.depth_reached >= max_depth,
    )
