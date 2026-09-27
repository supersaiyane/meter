"""Every consumer of the graph, held to the one rule the graph has.

Section 6 of the P4 specification: an edge Meter cannot see is not an absent edge. A
consumer that answers over a PARTIAL slice as though it were COMPLETE is the failure the
whole sub project exists to prevent, and it is silent: the graph renders, the traversal
returns, and the answer is wrong in the one direction that matters.

**This looks like a test for a consumer that does not exist yet.** FEAT-044 is a P3 feature
and comes after this. Writing it here is the point: the rule belongs to the graph, and the
first consumer to arrive should find the test already waiting rather than be trusted to
remember.

**Adding a consumer without handling PARTIAL fails this file.** The population is scanned
rather than listed: any module in the six production packages that imports
`finops_query.graph` is a consumer. The declared set below must equal the scanned set, so a
new module fails `test_every_consumer_module_is_declared` until somebody adds it, and
declaring it means saying whether it refuses or surfaces and supplying the proof.

A consumer discharges the rule in one of two ways, and nothing else counts:

- **Refuses.** Handed a partial subgraph it raises `IncompleteGraphError`. This is what
  FEAT-044 does, per the P3 specification section 12: a blast radius score refuses rather
  than scoring what it can see, because a change that looks contained and is not is the one
  wrong answer nobody checks.
- **Surfaces.** It answers, and the incomplete slice appears in what it produces, naming the
  account and the typed cause. A map is allowed to draw a partial graph; it is not allowed
  to draw one quietly.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from finops_api.routes import inventory
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
from finops_query import blast_radius
from finops_query.graph import Bounds, IncompleteGraphError, Subgraph, assemble

ROOT = Path(__file__).resolve().parents[2]

#: The six packages the layer contract names. A consumer outside them is not production
#: code, and the fakes and the tests are deliberately not held to this.
PRODUCTION_PACKAGES = (
    "finops_core",
    "finops_providers",
    "finops_query",
    "finops_ingest",
    "finops_api",
    "finops_mcp",
)

#: What counts as consuming the graph. Either import form, because a module that reaches it
#: through the package rather than the symbol is still a consumer.
IMPORTS_GRAPH = re.compile(r"from finops_query\.graph import|from finops_query import graph")

TENANT = UUID("11111111-1111-1111-1111-111111111111")
READABLE = AccountKey(provider=Provider.AWS, account_id="111122223333")
REFUSED = AccountKey(provider=Provider.AWS, account_id="444455556666")
REGION = "eu-west-1"
NOW = datetime(2026, 9, 26, 6, 0, tzinfo=UTC)
FETCHED = datetime(2026, 9, 26, 6, 5, tzinfo=UTC)


@dataclass(frozen=True)
class Consumer:
    """One module that reads the graph, and how it discharges the rule.

    `answer` is preferred: a callable the contract can run against a partial subgraph.
    `proved_by` is for a consumer whose entry point needs a database, and it names a test
    that must exist. The contract checks the file for it, so a name that rots fails here
    rather than quietly excusing the module.
    """

    module: str
    #: True where the consumer must raise rather than answer.
    refuses: bool
    #: What to call with a partial subgraph. Typed as a callable rather than `Any` so a
    #: declaration that forgot to make it one fails the type check rather than the run.
    answer: Callable[[Subgraph], Any] | None = None
    proved_by: str | None = None

    def __post_init__(self) -> None:
        if self.answer is None and self.proved_by is None:
            raise ValueError(
                f"{self.module} declares neither a callable nor a test, so nothing here "
                "checks it. A consumer with no proof is a consumer that will answer over a "
                "partial slice on the day it matters."
            )


def _rendered_route(graph: Subgraph) -> str:
    """What the route puts on the wire for a partial subgraph."""
    return inventory._subgraph_out(graph, Bounds()).model_dump_json()


CONSUMERS: tuple[Consumer, ...] = (
    Consumer(
        module="finops_query.graph",
        refuses=True,
        answer=lambda graph: graph.require_whole(),
    ),
    Consumer(
        module="finops_api.routes.inventory",
        refuses=False,
        answer=_rendered_route,
    ),
    Consumer(
        module="finops_query.blast_radius",
        # Refuses, and it is the reason the whole contract exists. A low radius over a graph
        # missing a region reads as "this change is safe", which is a claim the product would be
        # making on its own initiative about somebody's production estate, and nobody checks the
        # answer that agrees with them.
        refuses=True,
        answer=lambda graph: blast_radius.assess(
            graph,
            target=graph.nodes[0],
            wide_at=10,
            max_depth=4,
        ),
    ),
    Consumer(
        module="finops_api.db.repositories.topology",
        refuses=False,
        # Its entry point needs a database, so the proof is the integration test that walks
        # a real graph across a refused account and asserts the coverage came back with it.
        proved_by=(
            "tests/api/test_topology_repository.py::"
            "test_a_global_walk_carries_the_partial_slice_it_crossed"
        ),
    ),
)


def node(name: str, account: AccountKey) -> Node:
    provider_id = f"arn:aws:ec2:{REGION}:{account.account_id}:vpc/{name}"
    return Node(
        node_id=node_id_for(tenant_id=TENANT, provider_id=provider_id),
        account_key=account,
        provider_id=provider_id,
        node_kind=NodeKind.VPC,
        resource_type="AWS::EC2::VPC",
        region_id=REGION,
        availability_zone=None,
        name=name,
        tags={},
        as_of=NOW,
        collected_at=FETCHED,
    )


def coverage(
    account: AccountKey, state: CoverageState, cause: CoverageCause | None
) -> GraphCoverage:
    return GraphCoverage(
        account_key=account,
        region_id=REGION,
        state=state,
        cause=cause,
        node_count=1,
        edge_count=1,
        as_of=NOW,
        collected_at=FETCHED,
    )


def a_partial_graph() -> Subgraph:
    """The situation the test exists for, built the way the plan describes it.

    One region's edges removed and its slice marked PARTIAL. The root is readable, so a
    consumer that only looked at the nodes would see a perfectly ordinary graph, which is
    exactly why the coverage has to be checked rather than inferred.
    """
    root = node("vpc", READABLE)
    return assemble(
        root_id=root.node_id,
        found=((root, 0),),
        # The edge into the refused account survives as a boundary, because an edge Meter
        # cannot follow is not an absent edge.
        edges=(
            Edge(
                from_node_id=root.node_id,
                to_node_id=node("far", REFUSED).node_id,
                edge_kind=EdgeKind.PEERS_WITH,
                is_cross_account=True,
                source="ec2:DescribeVpcPeeringConnections",
                as_of=NOW,
                collected_at=FETCHED,
            ),
        ),
        coverage=(
            coverage(READABLE, CoverageState.COMPLETE, None),
            coverage(REFUSED, CoverageState.PARTIAL, CoverageCause.ACCESS_DENIED),
        ),
    )


def a_whole_graph() -> Subgraph:
    root = node("vpc", READABLE)
    return assemble(
        root_id=root.node_id,
        found=((root, 0),),
        edges=(),
        coverage=(coverage(READABLE, CoverageState.COMPLETE, None),),
    )


# --- the population is scanned, not listed ----------------------------------


def scanned_consumers() -> frozenset[str]:
    """Every production module that imports the graph."""
    found: set[str] = set()
    for package in PRODUCTION_PACKAGES:
        for path in (ROOT / package).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if IMPORTS_GRAPH.search(path.read_text(encoding="utf-8")):
                found.add(".".join(path.relative_to(ROOT).with_suffix("").parts))
    return frozenset(found)


def test_the_scan_finds_the_consumers_that_exist() -> None:
    """The gate's own input, checked before the gate is trusted.

    A regex that matched nothing would make the test below pass for every possible state of
    the codebase, which is the failure mode of every source scanning check. The floor is the
    count at the time of writing, so adding a consumer does not have to come back here.
    """
    found = scanned_consumers()
    assert len(found) >= 2, f"the scan found only {sorted(found)}"
    assert "finops_api.db.repositories.topology" in found


def test_every_consumer_module_is_declared() -> None:
    """The criterion: adding a consumer without handling PARTIAL fails this file.

    `finops_query.graph` is declared and is not scanned, because it defines the rule rather
    than importing it. Everything else has to be in both.
    """
    declared = {consumer.module for consumer in CONSUMERS}
    missing = scanned_consumers() - declared
    assert not missing, (
        "these modules read the graph and no case here holds them to what a PARTIAL slice "
        f"means: {sorted(missing)}. Declare each one as refusing or surfacing."
    )


def test_no_declared_consumer_has_disappeared() -> None:
    """The other direction. A declaration for a module nobody imports is a case that passes
    over nothing, which looks exactly like a case that works."""
    for consumer in CONSUMERS:
        importlib.import_module(consumer.module)


# --- the rule itself, parameterised over consumers --------------------------


@pytest.mark.parametrize("consumer", CONSUMERS, ids=lambda one: one.module)
def test_a_consumer_refuses_or_surfaces_a_partial_slice(consumer: Consumer) -> None:
    """Handed a graph over a refused account, every consumer either refuses or says so.

    Both branches are asserted from the same partial graph, so a consumer cannot pass by
    being handed an easier one.
    """
    graph = a_partial_graph()
    assert not graph.is_whole, "the fixture is not partial, so this case proves nothing"

    if consumer.proved_by is not None:
        path, _, node_id = consumer.proved_by.partition("::")
        source = (ROOT / path).read_text(encoding="utf-8")
        assert f"def {node_id}(" in source, (
            f"{consumer.module} names {consumer.proved_by} as its proof and that test does "
            "not exist, so nothing holds the module to the rule."
        )
        return

    answer = consumer.answer
    assert answer is not None, "a consumer with neither a callable nor a proof cannot exist"

    if consumer.refuses:
        with pytest.raises(IncompleteGraphError) as raised:
            answer(graph)
        # Naming the slice, because "the graph is incomplete" sends nobody anywhere.
        assert REFUSED.account_id in str(raised.value)
        assert CoverageCause.ACCESS_DENIED.value in str(raised.value)
        return

    rendered = answer(graph)
    assert REFUSED.account_id in rendered, (
        f"{consumer.module} answered over a partial slice without naming the account it "
        "could not read. A map may draw a partial graph; it may not draw one quietly."
    )
    assert CoverageCause.ACCESS_DENIED.value in rendered, (
        f"{consumer.module} named the slice and not the cause, so a reader is told data is "
        "missing and not what to do about it."
    )


@pytest.mark.parametrize("consumer", CONSUMERS, ids=lambda one: one.module)
def test_a_consumer_that_refuses_still_answers_a_whole_graph(consumer: Consumer) -> None:
    """The refusal has to be about the coverage rather than about the consumer.

    A consumer that refused everything would pass the case above and be useless, which is
    the failure mode of every test that only checks the unhappy path.
    """
    answer = consumer.answer
    if answer is None:
        pytest.skip(f"{consumer.module} is proved by {consumer.proved_by}")
    graph = a_whole_graph()
    assert graph.is_whole
    answer(graph)


def test_an_unread_slice_is_refused_exactly_like_a_partial_one() -> None:
    """Unread is not a lesser problem than partial. A slice nobody has read is one nobody can
    score against, and the P3 specification section 12 names both."""
    root = node("vpc", READABLE)
    graph = assemble(
        root_id=root.node_id,
        found=((root, 0),),
        edges=(),
        coverage=(coverage(READABLE, CoverageState.UNREAD, CoverageCause.NOT_YET_ATTEMPTED),),
    )
    with pytest.raises(IncompleteGraphError, match="UNREAD"):
        graph.require_whole()


def test_a_truncated_graph_over_complete_slices_is_refused_too() -> None:
    """The other half of `is_whole`. A caller scoring a change against the first two thousand
    neighbours of a resource with more is scoring a subset it did not choose."""
    nodes = tuple((node(f"n{index}", READABLE), 1) for index in range(5))
    graph = assemble(
        root_id=nodes[0][0].node_id,
        found=nodes,
        edges=(),
        coverage=(coverage(READABLE, CoverageState.COMPLETE, None),),
        bounds=Bounds(max_nodes=2),
    )
    assert graph.incomplete_slices == ()
    with pytest.raises(IncompleteGraphError, match="did not fit under the cap"):
        graph.require_whole()
