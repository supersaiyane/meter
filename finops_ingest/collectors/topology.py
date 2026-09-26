"""Several sources of the same slice, read together and merged into one answer.

Config supplies most relationships and stops at the account boundary. The four APIs in
`finops_providers/aws/topology.py` supply the edges that cross it. Both describe the
same slice, so a consumer has to see one graph rather than two, and this is where the
two become one.

**Read together, in one run, on purpose. ADR-0024.** The first draft of TASK-P4-006 had
two collectors on two cadences, one per source, and it cannot work. Both write
`topology_node`, whose identity is `(tenant_id, provider_id)`, so they cannot each own a
row. And the retraction that removes a departed resource keys on the run id, so whichever
collector ran second would delete every row the first one wrote and nothing else. The
version with a source column on the node, so each collector retracts only its own, works
and is intricate, and intricacy on the one path where a bug deletes data is not worth a
second cadence. One run owns a slice's graph.

**First source wins a duplicate.** Every node the supplement emits is a resource Config
also records, because the supplement emits them only so it can stand alone when Config
was refused. Config's version is the richer one: it has the name, the tags and a real
capture time. So the caller orders the sources richest first, and the merge keeps the
first it saw rather than the last.

**A shortfall from any source makes the slice PARTIAL.** That is the point of merging
them as a set rather than picking a winner: if Config answered and the peering call
refused, the graph is missing its peering edges and the coverage row has to say so even
though most of the slice is there.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from finops_core.domain.account import AccountKey
from finops_core.domain.topology import Edge, EdgeKind, Node, Shortfall, SliceRead

# Deliberately no `COLLECTOR` constant. This module is a source, not a collector: it
# reads and merges, and `inventory.py` is what the dispatcher runs. The constant would
# put "topology" in `tests/ingest/test_registry.py::test_every_collector_has_a_cadence`,
# which would then demand a schedule row for something nothing can run, and a scheduled
# collector nobody can run installs a row whose `finished_at` stays null forever and
# reports as permanently stale.


def merge(reads: Sequence[SliceRead]) -> SliceRead:
    """One `SliceRead` from several of the same slice, the earliest source winning.

    Raises:
        ValueError: There are no reads, or they are not all of one slice. Merging two
            accounts' graphs would write one account's coverage over another's and no
            screen could detect it, so this refuses rather than picking one.
    """
    if not reads:
        raise ValueError(
            "Nothing to merge. A slice with no sources is a caller that built an empty "
            "source list, not an estate with no resources."
        )
    first = reads[0]
    for other in reads[1:]:
        if (other.account_key, other.region_id) != (first.account_key, first.region_id):
            raise ValueError(
                f"These reads describe different slices, {first.account_key} in "
                f"{first.region_id} and {other.account_key} in {other.region_id}. Merging "
                "them would write one account's coverage over another's."
            )

    nodes: dict[str, Node] = {}
    edges: dict[tuple[str, str, EdgeKind], Edge] = {}
    shortfalls: list[Shortfall] = []
    unmapped: list[str] = []
    for read in reads:
        for node in read.nodes:
            nodes.setdefault(node.provider_id, node)
        for edge in read.edges:
            edges.setdefault((str(edge.from_node_id), str(edge.to_node_id), edge.edge_kind), edge)
        shortfalls.extend(read.shortfalls)
        unmapped.extend(name for name in read.unmapped if name not in unmapped)

    return SliceRead(
        account_key=first.account_key,
        region_id=first.region_id,
        nodes=tuple(nodes.values()),
        edges=tuple(edges.values()),
        shortfalls=tuple(shortfalls),
        unmapped=tuple(unmapped),
    )


class CompositeTopologySource:
    """Every source of one slice, behind the one port a collector talks to.

    Satisfies `TopologySource` itself, so the collector does not know how many sources
    there are and a third one is a change here rather than in the collector.
    """

    def __init__(self, *sources: Any) -> None:
        if not sources:
            raise ValueError(
                "A composite with no sources reads an empty graph and reports it as "
                "complete, which is the one answer this sub project exists to prevent."
            )
        # Ordered richest first. The module docstring says which duplicate wins.
        self._sources = sources

    @property
    def enrolled_slices(self) -> tuple[tuple[AccountKey, str | None], ...]:
        """The union, in the order the first source gave them.

        A union rather than the first source's list alone, because a source that reads a
        slice nobody else does still has to have a coverage row: a slice missing from
        the denominator is a slice no screen can report as unread.
        """
        found: list[tuple[AccountKey, str | None]] = []
        for source in self._sources:
            for entry in source.enrolled_slices:
                if entry not in found:
                    found.append(entry)
        return tuple(found)

    def read_slice(self, account: AccountKey, region: str | None) -> SliceRead:
        """Every source's answer for one slice, merged.

        A source raising is deliberately not caught here. A `TopologySource` reports a
        refusal as a shortfall, so an exception means something outside the estate went
        wrong: a malformed argument, or a credential the broker could not assume. The
        collector catches that and writes a PARTIAL row, which is where it belongs,
        because that is the layer that knows which run to record it against.
        """
        return merge([source.read_slice(account, region) for source in self._sources])
