"""The graph collector, against a real database, because the rules are about deletes.

Three of the four criteria of TASK-P4-006 are about what is removed and when, and none of
them can be reasoned about from the source: a retraction whose predicate is one clause
short removes every other slice in one statement, and the symptom is a graph that still
renders. So every case here runs the real statements against a real schema.

The fourth is that one account failing never fails the run, and that assertion has two
halves on purpose. Coverage is the state of a slice, which a screen reads to decide whether
a number can be trusted. A sync error is an event with a remediation on it, which a person
reads to decide what to fix. A failure in only the first is one nobody is told to act on; a
failure in only the second leaves every screen confident.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.topology import (
    CoverageCause,
    CoverageState,
    Edge,
    EdgeKind,
    Node,
    NodeKind,
    Shortfall,
    SliceRead,
    node_id_for,
)
from finops_core.errors import AccessDenied, Throttled
from finops_core.ports.inventory import TopologySource
from finops_ingest.collectors import topology
from finops_ingest.collectors.inventory import COLLECTOR, InventoryCollector
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext

pytestmark = pytest.mark.integration

AT = datetime(2026, 9, 26, 6, 5, tzinfo=UTC)
LATER = datetime(2026, 9, 26, 12, 5, tzinfo=UTC)
CAPTURED = datetime(2026, 9, 26, 6, 0, tzinfo=UTC)

ACCOUNT = AccountKey(provider=Provider.AWS, account_id="111122223333")
OTHER = AccountKey(provider=Provider.AWS, account_id="444455556666")
REGION = "eu-west-1"
SECOND_REGION = "eu-north-1"

VPC = "arn:aws:ec2:eu-west-1:111122223333:vpc/vpc-01"
SUBNET = "arn:aws:ec2:eu-west-1:111122223333:subnet/subnet-0a"
FAR = "arn:aws:ec2:eu-west-1:444455556666:vpc/vpc-far"


def arn(account: AccountKey, region: str | None, resource: str) -> str:
    """A slice specific ARN, because a node's identity is `(tenant_id, provider_id)`.

    Written as a function after a first draft reused one ARN across three slices and got
    two rows instead of six, which is the schema being right: an ARN names one resource in
    one account in one region, so the same string in two slices is one row and the second
    slice overwrites the first's account and region.
    """
    where = region or "global"
    return f"arn:aws:ec2:{where}:{account.account_id}:{resource}"


def unit_for(tenant: UUID) -> WorkUnit:
    return WorkUnit(tenant_id=tenant, collector=COLLECTOR, window_start=AT, window_end=AT)


def a_run(connection: Any, tenant: UUID) -> UUID:
    run = uuid4()
    connection.execute(
        text(
            "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, "
            "idempotency_key, status, as_of_window_start, as_of_window_end) "
            "VALUES (:run, :t, :c, 'scope', :key, 'SUCCEEDED', :at, :at)"
        ),
        {"run": run, "t": tenant, "c": COLLECTOR, "key": str(run), "at": AT},
    )
    return run


def node(
    provider_id: str,
    tenant: UUID,
    *,
    account: AccountKey = ACCOUNT,
    region: str | None = REGION,
    kind: NodeKind = NodeKind.VPC,
    name: str | None = "production",
) -> Node:
    return Node(
        node_id=node_id_for(tenant_id=tenant, provider_id=provider_id),
        account_key=account,
        provider_id=provider_id,
        node_kind=kind,
        resource_type="AWS::EC2::VPC",
        region_id=region,
        availability_zone=None,
        name=name,
        tags={"finops:module": "network"},
        as_of=CAPTURED,
        collected_at=AT,
    )


def edge(origin: str, target: str, tenant: UUID, *, cross: bool = False) -> Edge:
    return Edge(
        from_node_id=node_id_for(tenant_id=tenant, provider_id=origin),
        to_node_id=node_id_for(tenant_id=tenant, provider_id=target),
        edge_kind=EdgeKind.CONTAINS,
        is_cross_account=cross,
        source="CONFIG_RELATIONSHIP",
        as_of=CAPTURED,
        collected_at=AT,
    )


def whole(tenant: UUID, *, region: str | None = REGION, account: AccountKey = ACCOUNT) -> SliceRead:
    """A complete read of one slice: two nodes and the edge between them."""
    vpc = arn(account, region, "vpc/vpc-01")
    subnet = arn(account, region, "subnet/subnet-0a")
    return SliceRead(
        account_key=account,
        region_id=region,
        nodes=(
            node(vpc, tenant, account=account, region=region),
            node(subnet, tenant, account=account, region=region, kind=NodeKind.SUBNET),
        ),
        edges=(edge(vpc, subnet, tenant),),
        shortfalls=(),
    )


def partial(tenant: UUID, *, region: str | None = REGION) -> SliceRead:
    """A read that saw one node and lost an API."""
    return SliceRead(
        account_key=ACCOUNT,
        region_id=region,
        nodes=(node(VPC, tenant, region=region),),
        edges=(),
        shortfalls=(
            Shortfall(
                source="ec2:DescribeVpcPeeringConnections",
                cause=CoverageCause.ACCESS_DENIED,
                detail="the peering call was refused",
            ),
        ),
    )


def empty(account: AccountKey = ACCOUNT, region: str | None = REGION) -> SliceRead:
    return SliceRead(account_key=account, region_id=region, nodes=(), edges=(), shortfalls=())


class Source:
    """A topology source answering from a dictionary, or raising for a slice.

    Raising is the one failure a real source cannot report as a shortfall: a credential the
    broker could not assume, before any call was made.
    """

    def __init__(
        self,
        reads: dict[tuple[str, str | None], SliceRead] | None = None,
        *,
        slices: tuple[tuple[AccountKey, str | None], ...] = ((ACCOUNT, REGION),),
        raises: dict[tuple[str, str | None], Exception] | None = None,
    ) -> None:
        self._reads = reads or {}
        self._slices = slices
        self._raises = raises or {}
        self.asked: list[tuple[str, str | None]] = []

    @property
    def enrolled_slices(self) -> tuple[tuple[AccountKey, str | None], ...]:
        return self._slices

    def read_slice(self, account: AccountKey, region: str | None) -> SliceRead:
        key = (account.account_id, region)
        self.asked.append(key)
        if key in self._raises:
            raise self._raises[key]
        found = self._reads.get(key)
        return found if found is not None else empty(account, region)


def run_collector(engine: Engine, tenant: UUID, source: Source, *, at: datetime = AT) -> Any:
    with engine.begin() as connection:
        run = a_run(connection, tenant)
        context = CollectorContext(unit=unit_for(tenant), connection=connection, run_id=run)
        return InventoryCollector(source, clock=lambda: at)(context)


def count(engine: Engine, table_name: str, tenant: UUID) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text(f"SELECT count(*) FROM {table_name} WHERE tenant_id = :t"), {"t": tenant}
            ).scalar_one()
        )


def rows(engine: Engine, statement: str, tenant: UUID) -> list[Any]:
    with engine.connect() as connection:
        return list(connection.execute(text(statement), {"t": tenant}))


# --- the ordinary run --------------------------------------------------------


def test_a_complete_read_writes_its_nodes_and_edges(engine: Engine, tenant_id: UUID) -> None:
    source = Source({(ACCOUNT.account_id, REGION): whole(tenant_id)})
    outcome = run_collector(engine, tenant_id, source)
    assert outcome.items_written == 3
    assert count(engine, "topology_node", tenant_id) == 2
    assert count(engine, "topology_edge", tenant_id) == 1
    assert count(engine, "graph_coverage", tenant_id) == 1


def test_the_two_timestamps_come_from_two_places(engine: Engine, tenant_id: UUID) -> None:
    """Constraint 10. `as_of` stays the source's, because it is when the resource was as
    described. `collected_at` is ours."""
    run_collector(engine, tenant_id, Source({(ACCOUNT.account_id, REGION): whole(tenant_id)}))
    found = rows(
        engine, "SELECT as_of, collected_at FROM topology_node WHERE tenant_id = :t", tenant_id
    )
    for row in found:
        assert row.as_of == CAPTURED
        assert row.collected_at == AT


def test_an_edge_carries_the_slice_of_its_origin(engine: Engine, tenant_id: UUID) -> None:
    run_collector(engine, tenant_id, Source({(ACCOUNT.account_id, REGION): whole(tenant_id)}))
    (row,) = rows(
        engine,
        "SELECT sub_account_id, region_id, source FROM topology_edge WHERE tenant_id = :t",
        tenant_id,
    )
    assert (row.sub_account_id, row.region_id) == (ACCOUNT.account_id, REGION)
    assert row.source == "CONFIG_RELATIONSHIP"


def test_running_twice_writes_the_same_graph_rather_than_a_second_copy(
    engine: Engine, tenant_id: UUID
) -> None:
    source = Source({(ACCOUNT.account_id, REGION): whole(tenant_id)})
    run_collector(engine, tenant_id, source)
    run_collector(engine, tenant_id, source, at=LATER)
    assert count(engine, "topology_node", tenant_id) == 2
    assert count(engine, "topology_edge", tenant_id) == 1


def test_a_renamed_resource_upserts_onto_its_own_row(engine: Engine, tenant_id: UUID) -> None:
    run_collector(engine, tenant_id, Source({(ACCOUNT.account_id, REGION): whole(tenant_id)}))
    renamed = SliceRead(
        account_key=ACCOUNT,
        region_id=REGION,
        nodes=(node(VPC, tenant_id, name="staging"),),
        edges=(),
        shortfalls=(),
    )
    run_collector(engine, tenant_id, Source({(ACCOUNT.account_id, REGION): renamed}), at=LATER)
    names = {
        row.name
        for row in rows(engine, "SELECT name FROM topology_node WHERE tenant_id = :t", tenant_id)
    }
    assert names == {"staging"}


# --- a departed resource, and only when the slice was complete ---------------


def test_a_departed_resource_is_removed_with_its_edges(engine: Engine, tenant_id: UUID) -> None:
    """The first criterion, scoped to one tenant and one run, the pattern `cost_focus` uses.
    The edges go first because `from_node_id` references the node and the key deliberately
    does not cascade."""
    run_collector(engine, tenant_id, Source({(ACCOUNT.account_id, REGION): whole(tenant_id)}))
    shrunk = SliceRead(
        account_key=ACCOUNT,
        region_id=REGION,
        nodes=(node(VPC, tenant_id),),
        edges=(),
        shortfalls=(),
    )
    outcome = run_collector(
        engine, tenant_id, Source({(ACCOUNT.account_id, REGION): shrunk}), at=LATER
    )
    assert outcome.items_removed == 2
    assert count(engine, "topology_node", tenant_id) == 1
    assert count(engine, "topology_edge", tenant_id) == 0


def test_a_partial_read_removes_nothing(engine: Engine, tenant_id: UUID) -> None:
    """Stricter than the criterion, and the rule the sub project turns on. A partial read
    cannot tell a resource that is gone from a resource it could not see, so removing on one
    would delete the estate a refused credential hid, silently, and the graph would then be
    smaller and still render."""
    run_collector(engine, tenant_id, Source({(ACCOUNT.account_id, REGION): whole(tenant_id)}))
    outcome = run_collector(
        engine, tenant_id, Source({(ACCOUNT.account_id, REGION): partial(tenant_id)}), at=LATER
    )
    assert outcome.items_removed == 0
    assert count(engine, "topology_node", tenant_id) == 2
    assert count(engine, "topology_edge", tenant_id) == 1


def test_a_read_that_fails_part_way_removes_nothing(engine: Engine, tenant_id: UUID) -> None:
    """The second criterion. The removal sits downstream of finishing the read, so a source
    that raises never reaches it."""
    run_collector(engine, tenant_id, Source({(ACCOUNT.account_id, REGION): whole(tenant_id)}))
    refusing = Source(
        raises={
            (ACCOUNT.account_id, REGION): AccessDenied(
                scope_key=f"acct:{ACCOUNT.account_id}", collector=COLLECTOR, detail="revoked"
            )
        }
    )
    outcome = run_collector(engine, tenant_id, refusing, at=LATER)
    assert outcome.items_removed == 0
    assert count(engine, "topology_node", tenant_id) == 2


def test_reading_one_slice_never_removes_another(engine: Engine, tenant_id: UUID) -> None:
    """The worst outcome available to the retraction and the easiest to write. Without the
    account and region predicates, reading one slice removes every other in one statement."""
    filled = Source(
        {
            (ACCOUNT.account_id, REGION): whole(tenant_id),
            (ACCOUNT.account_id, SECOND_REGION): whole(tenant_id, region=SECOND_REGION),
            (OTHER.account_id, REGION): whole(tenant_id, account=OTHER),
        },
        slices=((ACCOUNT, REGION), (ACCOUNT, SECOND_REGION), (OTHER, REGION)),
    )
    run_collector(engine, tenant_id, filled)
    assert count(engine, "topology_node", tenant_id) == 6

    one = Source(
        {(ACCOUNT.account_id, REGION): empty()},
        slices=((ACCOUNT, REGION),),
    )
    run_collector(engine, tenant_id, one, at=LATER)
    left = rows(
        engine,
        "SELECT sub_account_id, region_id FROM topology_node WHERE tenant_id = :t "
        "ORDER BY sub_account_id, region_id",
        tenant_id,
    )
    assert [(row.sub_account_id, row.region_id) for row in left] == [
        (ACCOUNT.account_id, SECOND_REGION),
        (ACCOUNT.account_id, SECOND_REGION),
        (OTHER.account_id, REGION),
        (OTHER.account_id, REGION),
    ]


def test_the_global_slice_is_retracted_like_any_other(engine: Engine, tenant_id: UUID) -> None:
    """`region_id = NULL` matches nothing, so with `=` rather than `IS NOT DISTINCT FROM` the
    global slice would never be retracted and a role deleted years ago would still be in the
    graph."""
    role = "arn:aws:iam::111122223333:role/platform-ci"
    present = SliceRead(
        account_key=ACCOUNT,
        region_id=None,
        nodes=(node(role, tenant_id, region=None, kind=NodeKind.OTHER),),
        edges=(),
        shortfalls=(),
    )
    run_collector(
        engine, tenant_id, Source({(ACCOUNT.account_id, None): present}, slices=((ACCOUNT, None),))
    )
    assert count(engine, "topology_node", tenant_id) == 1
    outcome = run_collector(
        engine,
        tenant_id,
        Source({(ACCOUNT.account_id, None): empty(ACCOUNT, None)}, slices=((ACCOUNT, None),)),
        at=LATER,
    )
    assert outcome.items_removed == 1
    assert count(engine, "topology_node", tenant_id) == 0


# --- one account failing never fails the run --------------------------------


def test_a_refused_slice_reaches_coverage_and_sync_error_both(
    engine: Engine, tenant_id: UUID
) -> None:
    """The third criterion, and both halves are asserted because either alone hides the
    failure from somebody."""
    refusing = Source(
        {(ACCOUNT.account_id, REGION): whole(tenant_id)},
        slices=((ACCOUNT, REGION), (OTHER, REGION)),
        raises={
            (OTHER.account_id, REGION): AccessDenied(
                scope_key=f"acct:{OTHER.account_id}", collector=COLLECTOR, detail="no role here"
            )
        },
    )
    outcome = run_collector(engine, tenant_id, refusing)
    assert outcome.items_written == 3
    states = {
        row.sub_account_id: (row.state, row.cause)
        for row in rows(
            engine,
            "SELECT sub_account_id, state, cause FROM graph_coverage WHERE tenant_id = :t",
            tenant_id,
        )
    }
    assert states[ACCOUNT.account_id] == ("COMPLETE", None)
    assert states[OTHER.account_id] == ("PARTIAL", "AccessDenied")
    errors = rows(
        engine,
        "SELECT scope_key, error_type, detail, remediation FROM sync_error WHERE tenant_id = :t",
        tenant_id,
    )
    assert len(errors) == 1
    assert errors[0].scope_key == f"{OTHER}:{REGION}"
    assert errors[0].error_type == "AccessDenied"
    assert "no role here" in errors[0].detail
    # The remediation comes from the taxonomy rather than being written again here.
    assert "trust policy" in errors[0].remediation


def test_a_shortfall_inside_a_read_also_reaches_sync_error(engine: Engine, tenant_id: UUID) -> None:
    """A partial read is not an exception, so this is the path a refused single API takes.
    Without it, a peering call that has refused for a month is a banner nobody is told how to
    clear."""
    run_collector(engine, tenant_id, Source({(ACCOUNT.account_id, REGION): partial(tenant_id)}))
    (error,) = rows(
        engine,
        "SELECT scope_key, error_type, detail FROM sync_error WHERE tenant_id = :t",
        tenant_id,
    )
    assert error.error_type == "AccessDenied"
    assert "peering" in error.detail


def test_a_repeated_failure_raises_a_count_rather_than_adding_a_row(
    engine: Engine, tenant_id: UUID
) -> None:
    source = Source({(ACCOUNT.account_id, REGION): partial(tenant_id)})
    run_collector(engine, tenant_id, source)
    run_collector(engine, tenant_id, source, at=LATER)
    (error,) = rows(
        engine,
        "SELECT occurrences, first_seen_at, last_seen_at FROM sync_error WHERE tenant_id = :t",
        tenant_id,
    )
    assert error.occurrences == 2
    assert error.first_seen_at == AT
    assert error.last_seen_at == LATER


def test_two_causes_in_one_slice_are_two_rows(engine: Engine, tenant_id: UUID) -> None:
    """A slice can fall short in two ways and a person has to be told about both, while the
    coverage row holds the one cause that says what to fix."""
    two = SliceRead(
        account_key=ACCOUNT,
        region_id=REGION,
        nodes=(),
        edges=(),
        shortfalls=(
            Shortfall(source="a", cause=CoverageCause.ACCESS_DENIED, detail="one"),
            Shortfall(source="b", cause=CoverageCause.THROTTLED, detail="two"),
        ),
    )
    run_collector(engine, tenant_id, Source({(ACCOUNT.account_id, REGION): two}))
    causes = {
        row.error_type
        for row in rows(engine, "SELECT error_type FROM sync_error WHERE tenant_id = :t", tenant_id)
    }
    assert causes == {"AccessDenied", "Throttled"}
    (row,) = rows(engine, "SELECT cause FROM graph_coverage WHERE tenant_id = :t", tenant_id)
    assert row.cause == "AccessDenied"


def test_a_throttled_slice_is_partial_rather_than_absent(engine: Engine, tenant_id: UUID) -> None:
    refusing = Source(
        raises={
            (ACCOUNT.account_id, REGION): Throttled(
                scope_key=f"acct:{ACCOUNT.account_id}", collector=COLLECTOR, detail="slow down"
            )
        }
    )
    run_collector(engine, tenant_id, refusing)
    (row,) = rows(engine, "SELECT state, cause FROM graph_coverage WHERE tenant_id = :t", tenant_id)
    assert (row.state, row.cause) == ("PARTIAL", "Throttled")


# --- enrolment and the run id -----------------------------------------------


def test_every_enrolled_slice_gets_a_row(engine: Engine, tenant_id: UUID) -> None:
    source = Source(
        {(ACCOUNT.account_id, REGION): whole(tenant_id)},
        slices=((ACCOUNT, REGION), (ACCOUNT, SECOND_REGION), (ACCOUNT, None)),
    )
    run_collector(engine, tenant_id, source)
    states = {
        row.region_id: row.state
        for row in rows(
            engine, "SELECT region_id, state FROM graph_coverage WHERE tenant_id = :t", tenant_id
        )
    }
    # Read and found empty, which is COMPLETE, and deliberately not the same as unread.
    assert states == {REGION: "COMPLETE", SECOND_REGION: "COMPLETE", None: "COMPLETE"}


def test_a_collector_without_a_run_id_refuses_to_run(engine: Engine, tenant_id: UUID) -> None:
    """A collector inventing a run id would write a number naming no run and then delete on a
    fiction."""
    with engine.begin() as connection:
        context = CollectorContext(unit=unit_for(tenant_id), connection=connection)
        with pytest.raises(ValueError, match="run id"):
            InventoryCollector(Source(), clock=lambda: AT)(context)


def test_every_row_names_the_run_that_wrote_it(engine: Engine, tenant_id: UUID) -> None:
    source = Source({(ACCOUNT.account_id, REGION): whole(tenant_id)})
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        context = CollectorContext(unit=unit_for(tenant_id), connection=connection, run_id=run)
        InventoryCollector(source, clock=lambda: AT)(context)
    for table_name in ("topology_node", "topology_edge", "graph_coverage"):
        found = rows(
            engine,
            f"SELECT DISTINCT ingest_run_id FROM {table_name} WHERE tenant_id = :t",
            tenant_id,
        )
        assert [row.ingest_run_id for row in found] == [run], table_name


def test_a_cross_account_edge_survives_with_no_node_at_its_far_end(
    engine: Engine, tenant_id: UUID
) -> None:
    """The far end of a cross account edge is a boundary, and an edge pointing at a node with
    no row is how the schema says so."""
    crossing = SliceRead(
        account_key=ACCOUNT,
        region_id=REGION,
        nodes=(node(VPC, tenant_id),),
        edges=(edge(VPC, FAR, tenant_id, cross=True),),
        shortfalls=(),
    )
    run_collector(engine, tenant_id, Source({(ACCOUNT.account_id, REGION): crossing}))
    (row,) = rows(
        engine, "SELECT is_cross_account FROM topology_edge WHERE tenant_id = :t", tenant_id
    )
    assert row.is_cross_account is True
    assert count(engine, "topology_node", tenant_id) == 1


# --- the composite source, which is why there is one collector ---------------


def test_the_composite_merges_two_sources_of_one_slice(tenant_id: UUID) -> None:
    """Config supplies most relationships and stops at the account boundary; the four
    APIs supply the edges that cross it. A consumer has to see one graph."""
    rich = SliceRead(
        account_key=ACCOUNT,
        region_id=REGION,
        nodes=(node(VPC, tenant_id, name="from config"),),
        edges=(edge(VPC, SUBNET, tenant_id),),
        shortfalls=(),
    )
    supplement = SliceRead(
        account_key=ACCOUNT,
        region_id=REGION,
        nodes=(node(VPC, tenant_id, name="thin"), node(FAR, tenant_id, account=OTHER)),
        edges=(edge(VPC, FAR, tenant_id, cross=True),),
        shortfalls=(),
    )
    merged = topology.merge([rich, supplement])
    assert len(merged.nodes) == 2
    assert len(merged.edges) == 2
    # First source wins the duplicate, because the caller orders them richest first and
    # Config's node carries the name, the tags and a real capture time.
    assert {one.provider_id: one.name for one in merged.nodes}[VPC] == "from config"


def test_a_shortfall_from_any_source_makes_the_whole_slice_partial(tenant_id: UUID) -> None:
    """The point of merging as a set rather than picking a winner. If Config answered and
    the peering call refused, the graph is missing its peering edges and the coverage row
    has to say so even though most of the slice is there."""
    merged = topology.merge([whole(tenant_id), partial(tenant_id)])
    assert merged.state is CoverageState.PARTIAL
    assert merged.cause is CoverageCause.ACCESS_DENIED
    assert merged.nodes


def test_merging_two_different_slices_is_refused(tenant_id: UUID) -> None:
    """Merging two accounts' graphs would write one account's coverage over another's, and
    no screen could detect it."""
    with pytest.raises(ValueError, match="different slices"):
        topology.merge([whole(tenant_id), whole(tenant_id, account=OTHER)])


def test_merging_nothing_is_refused() -> None:
    with pytest.raises(ValueError, match="Nothing to merge"):
        topology.merge([])


def test_a_composite_with_no_sources_is_refused() -> None:
    """It would read an empty graph and report it as complete, which is the one answer this
    sub project exists to prevent."""
    with pytest.raises(ValueError, match="no sources"):
        topology.CompositeTopologySource()


def test_the_composite_satisfies_the_port_and_unions_the_denominator(tenant_id: UUID) -> None:
    """A source that reads a slice nobody else does still has to have a coverage row: a
    slice missing from the denominator is a slice no screen can report as unread."""
    first = Source({(ACCOUNT.account_id, REGION): whole(tenant_id)})
    second = Source(
        {(OTHER.account_id, REGION): whole(tenant_id, account=OTHER)},
        slices=((ACCOUNT, REGION), (OTHER, REGION)),
    )
    composite = topology.CompositeTopologySource(first, second)
    assert isinstance(composite, TopologySource)
    assert composite.enrolled_slices == ((ACCOUNT, REGION), (OTHER, REGION))
    read = composite.read_slice(ACCOUNT, REGION)
    assert read.state is CoverageState.COMPLETE
    assert len(read.nodes) == 2


def test_the_collector_runs_against_a_composite_end_to_end(engine: Engine, tenant_id: UUID) -> None:
    """The shape the deployed collector is built in, so the wiring is exercised rather than
    only the parts."""
    config = Source({(ACCOUNT.account_id, REGION): whole(tenant_id)})
    supplement = Source(
        {
            (ACCOUNT.account_id, REGION): SliceRead(
                account_key=ACCOUNT,
                region_id=REGION,
                nodes=(node(VPC, tenant_id),),
                edges=(edge(VPC, FAR, tenant_id, cross=True),),
                shortfalls=(),
            )
        }
    )
    composite = topology.CompositeTopologySource(config, supplement)
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        context = CollectorContext(unit=unit_for(tenant_id), connection=connection, run_id=run)
        outcome = InventoryCollector(composite, clock=lambda: AT)(context)
    assert outcome.items_written == 4
    assert count(engine, "topology_edge", tenant_id) == 2
    (row,) = rows(engine, "SELECT state FROM graph_coverage WHERE tenant_id = :t", tenant_id)
    assert row.state == "COMPLETE"


def test_a_run_that_reads_fewer_slices_than_are_enrolled_leaves_the_rest_unread(
    engine: Engine, tenant_id: UUID
) -> None:
    """The state TASK-P4-005 asks for, produced rather than staged. A dispatcher fanning
    out per account makes this shape naturally, and with one list of slices the collector
    could not express it: UNREAD would be a value no run could leave behind."""
    source = Source(
        {(ACCOUNT.account_id, REGION): whole(tenant_id)},
        slices=((ACCOUNT, REGION), (ACCOUNT, SECOND_REGION)),
    )
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        context = CollectorContext(unit=unit_for(tenant_id), connection=connection, run_id=run)
        InventoryCollector(source, clock=lambda: AT, covers=((ACCOUNT, REGION),))(context)
    states = {
        row.region_id: (row.state, row.cause)
        for row in rows(
            engine,
            "SELECT region_id, state, cause FROM graph_coverage WHERE tenant_id = :t",
            tenant_id,
        )
    }
    assert states[REGION] == ("COMPLETE", None)
    assert states[SECOND_REGION] == ("UNREAD", "NotYetAttempted")
    assert source.asked == [(ACCOUNT.account_id, REGION)]
