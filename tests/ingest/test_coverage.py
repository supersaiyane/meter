"""The coverage writer, against a real database, because the rule is a constraint.

The cases worth having are the four criteria of TASK-P4-005, and one of them is worth
asserting in both directions rather than one: a slice that failed and then succeeded
has to move back to COMPLETE. A writer that only ever widened the failure would look
correct on the way down, and the screen would show an estate that never recovers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, text

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
from finops_ingest import coverage

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 26, 6, 5, tzinfo=UTC)
LATER = datetime(2026, 9, 26, 12, 5, tzinfo=UTC)
ACCOUNT = AccountKey(provider=Provider.AWS, account_id="111122223333")
OTHER = AccountKey(provider=Provider.AWS, account_id="444455556666")
REGION = "eu-west-1"
SECOND_REGION = "eu-north-1"

INSERT_RUN = text(
    "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, idempotency_key, "
    "status, as_of_window_start, as_of_window_end) "
    "VALUES (:run, :t, 'inventory', 'scope', :key, 'SUCCEEDED', :at, :at)"
)

READ_SLICES = text(
    "SELECT sub_account_id, region_id, state, cause, node_count, edge_count, as_of "
    "FROM graph_coverage WHERE tenant_id = :t "
    "ORDER BY sub_account_id, COALESCE(region_id, '')"
)


def a_run(connection: Connection, tenant: UUID) -> UUID:
    run = uuid4()
    connection.execute(INSERT_RUN, {"run": run, "t": tenant, "key": str(run), "at": NOW})
    return run


def slice_read(
    *,
    account: AccountKey = ACCOUNT,
    region: str | None = REGION,
    nodes: int = 0,
    edges: int = 0,
    shortfalls: tuple[Shortfall, ...] = (),
) -> SliceRead:
    """A read with the requested number of nodes and edges, and nothing else in it.

    The identity of the nodes does not matter to this writer, only how many there were,
    so they are generated rather than written out. What matters is that the counts on
    the row come from the read rather than from the caller.
    """
    made = tuple(
        Node(
            node_id=node_id_for(tenant_id=uuid4(), provider_id=f"arn:fixture:{index}"),
            account_key=account,
            provider_id=f"arn:fixture:{index}",
            node_kind=NodeKind.VPC,
            resource_type="AWS::EC2::VPC",
            region_id=region,
            availability_zone=None,
            name=None,
            tags={},
            as_of=NOW,
            collected_at=NOW,
        )
        for index in range(nodes)
    )
    joined = tuple(
        Edge(
            from_node_id=node_id_for(tenant_id=uuid4(), provider_id=f"from:{index}"),
            to_node_id=node_id_for(tenant_id=uuid4(), provider_id=f"to:{index}"),
            edge_kind=EdgeKind.CONTAINS,
            is_cross_account=False,
            source="CONFIG_RELATIONSHIP",
            as_of=NOW,
            collected_at=NOW,
        )
        for index in range(edges)
    )
    return SliceRead(
        account_key=account,
        region_id=region,
        nodes=made,
        edges=joined,
        shortfalls=shortfalls,
    )


def denied() -> tuple[Shortfall, ...]:
    return (
        Shortfall(
            source="config:SelectAggregateResourceConfig",
            cause=CoverageCause.ACCESS_DENIED,
            detail="refused",
        ),
    )


# --- a row for every slice, on every run -------------------------------------


def test_enrolment_writes_an_unread_row_for_every_slice(engine: Engine, tenant_id: UUID) -> None:
    """The second criterion. Created when the account is enrolled rather than when a
    collection first fails, because a row written only on failure cannot distinguish a
    slice nobody tried from a slice that does not exist."""
    slices = ((ACCOUNT, REGION), (ACCOUNT, SECOND_REGION), (ACCOUNT, None), (OTHER, REGION))
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        written = coverage.enrol(connection, tenant=tenant_id, run_id=run, slices=slices, at=NOW)
        rows = connection.execute(READ_SLICES, {"t": tenant_id}).all()
    assert written == 4
    assert len(rows) == 4
    for row in rows:
        assert row.state == "UNREAD"
        assert row.cause == "NotYetAttempted"
        assert (row.node_count, row.edge_count) == (0, 0)


def test_enrolment_is_idempotent_and_does_not_undo_a_successful_read(
    engine: Engine, tenant_id: UUID
) -> None:
    """The reason `enrol` does not overwrite. A second run that reset last night's
    COMPLETE rows to UNREAD would make a healthy estate look unread on every screen for
    as long as a collection takes."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        coverage.enrol(
            connection, tenant=tenant_id, run_id=run, slices=((ACCOUNT, REGION),), at=NOW
        )
        coverage.record(connection, tenant=tenant_id, run_id=run, read=slice_read(nodes=7), at=NOW)
        again = coverage.enrol(
            connection, tenant=tenant_id, run_id=run, slices=((ACCOUNT, REGION),), at=LATER
        )
        (row,) = connection.execute(READ_SLICES, {"t": tenant_id}).all()
    assert again == 0
    assert row.state == "COMPLETE"
    assert row.node_count == 7


def test_a_slice_the_run_never_reaches_keeps_its_unread_row(
    engine: Engine, tenant_id: UUID
) -> None:
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        coverage.enrol(
            connection,
            tenant=tenant_id,
            run_id=run,
            slices=((ACCOUNT, REGION), (ACCOUNT, SECOND_REGION)),
            at=NOW,
        )
        coverage.record(connection, tenant=tenant_id, run_id=run, read=slice_read(nodes=3), at=NOW)
        rows = {row.region_id: row for row in connection.execute(READ_SLICES, {"t": tenant_id})}
    assert rows[REGION].state == "COMPLETE"
    assert rows[SECOND_REGION].state == "UNREAD"


# --- the state and the cause come from the read ------------------------------


def test_a_whole_read_is_complete_with_no_cause(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        coverage.record(
            connection, tenant=tenant_id, run_id=run, read=slice_read(nodes=12, edges=19), at=NOW
        )
        (row,) = connection.execute(READ_SLICES, {"t": tenant_id}).all()
    assert (row.state, row.cause) == ("COMPLETE", None)
    assert (row.node_count, row.edge_count) == (12, 19)


def test_a_read_with_shortfalls_is_partial_and_carries_the_typed_cause(
    engine: Engine, tenant_id: UUID
) -> None:
    """The fourth criterion. The cause is the value, never a message: free text here
    would be a column nobody can group by."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        coverage.record(
            connection, tenant=tenant_id, run_id=run, read=slice_read(shortfalls=denied()), at=NOW
        )
        (row,) = connection.execute(READ_SLICES, {"t": tenant_id}).all()
    assert (row.state, row.cause) == ("PARTIAL", "AccessDenied")


def test_a_complete_slice_with_nothing_in_it_is_not_the_same_as_an_unread_one(
    engine: Engine, tenant_id: UUID
) -> None:
    """The objection the plan raises and this answers. An account with genuinely no
    resources in a region and an account whose region refused us look identical by row
    count, and only one of them is safe to score against."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        coverage.enrol(
            connection,
            tenant=tenant_id,
            run_id=run,
            slices=((ACCOUNT, REGION), (ACCOUNT, SECOND_REGION)),
            at=NOW,
        )
        coverage.record(connection, tenant=tenant_id, run_id=run, read=slice_read(), at=NOW)
        rows = {row.region_id: row for row in connection.execute(READ_SLICES, {"t": tenant_id})}
    assert (rows[REGION].state, rows[REGION].node_count) == ("COMPLETE", 0)
    assert (rows[SECOND_REGION].state, rows[SECOND_REGION].node_count) == ("UNREAD", 0)


def test_a_cause_that_does_not_pair_with_its_state_is_refused_before_the_database(
    engine: Engine, tenant_id: UUID
) -> None:
    """The check constraint says the same thing and is what actually holds. This raises
    first so the message names the collector's mistake."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        with pytest.raises(ValueError, match="do not pair"):
            coverage.write(
                connection,
                tenant=tenant_id,
                run_id=run,
                account=ACCOUNT,
                region=REGION,
                state=CoverageState.COMPLETE,
                cause=CoverageCause.ACCESS_DENIED,
                node_count=0,
                edge_count=0,
                at=NOW,
            )


# --- both directions of the transition ---------------------------------------


def test_a_slice_that_failed_and_then_succeeded_moves_back_to_complete(
    engine: Engine, tenant_id: UUID
) -> None:
    """The third criterion, on the way up. Nothing clears a PARTIAL row because nothing
    needs to: the next successful read upserts over it with a null cause."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        coverage.record(
            connection, tenant=tenant_id, run_id=run, read=slice_read(shortfalls=denied()), at=NOW
        )
        (failed,) = connection.execute(READ_SLICES, {"t": tenant_id}).all()
        assert (failed.state, failed.cause) == ("PARTIAL", "AccessDenied")

        later = a_run(connection, tenant_id)
        coverage.record(
            connection, tenant=tenant_id, run_id=later, read=slice_read(nodes=5, edges=8), at=LATER
        )
        (recovered,) = connection.execute(READ_SLICES, {"t": tenant_id}).all()
    assert (recovered.state, recovered.cause) == ("COMPLETE", None)
    assert (recovered.node_count, recovered.edge_count) == (5, 8)
    assert recovered.as_of == LATER


def test_a_slice_that_succeeded_and_then_failed_moves_to_partial(
    engine: Engine, tenant_id: UUID
) -> None:
    """The same criterion on the way down, which is the direction a writer that only
    widened the failure would still pass. Both are asserted because either alone is
    consistent with a broken implementation."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        coverage.record(
            connection, tenant=tenant_id, run_id=run, read=slice_read(nodes=5, edges=8), at=NOW
        )
        later = a_run(connection, tenant_id)
        coverage.record(
            connection,
            tenant=tenant_id,
            run_id=later,
            read=slice_read(shortfalls=denied()),
            at=LATER,
        )
        (row,) = connection.execute(READ_SLICES, {"t": tenant_id}).all()
    assert (row.state, row.cause) == ("PARTIAL", "AccessDenied")
    # The counts go with it. Leaving five nodes on a refused slice would be the graph
    # claiming to hold what it could not read this morning.
    assert (row.node_count, row.edge_count) == (0, 0)


def test_the_row_names_the_run_that_last_wrote_it(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        first = a_run(connection, tenant_id)
        coverage.record(connection, tenant=tenant_id, run_id=first, read=slice_read(), at=NOW)
        second = a_run(connection, tenant_id)
        coverage.record(connection, tenant=tenant_id, run_id=second, read=slice_read(), at=LATER)
        found = connection.execute(
            text("SELECT ingest_run_id FROM graph_coverage WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).scalar_one()
    assert found == second


# --- the failure the source cannot report ------------------------------------


def test_a_refusal_outside_the_source_still_reaches_the_table(
    engine: Engine, tenant_id: UUID
) -> None:
    """A slice whose credential was revoked this morning and which still reads COMPLETE
    from last night's run is the exact failure this table prevents, arriving through the
    one door the source cannot see."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        coverage.record(connection, tenant=tenant_id, run_id=run, read=slice_read(nodes=9), at=NOW)
        later = a_run(connection, tenant_id)
        coverage.refused(
            connection,
            tenant=tenant_id,
            run_id=later,
            account=ACCOUNT,
            region=REGION,
            cause=CoverageCause.ACCESS_DENIED,
            at=LATER,
        )
        (row,) = connection.execute(READ_SLICES, {"t": tenant_id}).all()
    assert (row.state, row.cause, row.node_count) == ("PARTIAL", "AccessDenied", 0)


# --- the global slice and the coalesced key ----------------------------------


def test_the_global_slice_is_its_own_row_and_upserts_onto_itself(
    engine: Engine, tenant_id: UUID
) -> None:
    """The unique index coalesces the region, so the null slice has exactly one row and
    a second write to it updates rather than inserting."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        coverage.record(
            connection, tenant=tenant_id, run_id=run, read=slice_read(region=None, nodes=2), at=NOW
        )
        coverage.record(
            connection,
            tenant=tenant_id,
            run_id=run,
            read=slice_read(region=None, shortfalls=denied()),
            at=LATER,
        )
        rows = connection.execute(READ_SLICES, {"t": tenant_id}).all()
    assert len(rows) == 1
    assert rows[0].region_id is None
    assert rows[0].state == "PARTIAL"


def test_two_accounts_do_not_share_a_slice(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        coverage.record(connection, tenant=tenant_id, run_id=run, read=slice_read(nodes=1), at=NOW)
        coverage.record(
            connection,
            tenant=tenant_id,
            run_id=run,
            read=slice_read(account=OTHER, shortfalls=denied()),
            at=NOW,
        )
        rows = connection.execute(READ_SLICES, {"t": tenant_id}).all()
    assert [(row.sub_account_id, row.state) for row in rows] == [
        (ACCOUNT.account_id, "COMPLETE"),
        (OTHER.account_id, "PARTIAL"),
    ]
