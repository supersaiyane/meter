"""The record of what was not read, written on every run including a failed one.

This is the table the sub project exists for, and section 6 of the P4 specification
is the whole argument. When a cost collector fails a number is missing and the screen
says so. When a topology collector fails the graph is still a graph: it renders, it
traverses, and every query against it returns an answer that is wrong in the one
direction that matters, because everything looks less connected than it is.

**The objection this answers, from the plan: could coverage not be derived?** A slice
with no nodes was presumably not read. It could not, and the difference is the sub
project. An account with genuinely no resources in a region and an account whose
region refused us look identical by row count, and only one of them is safe to score
against. So the state is stored, per slice, with a typed cause and the counts that
were actually read.

**Three states, and `UNREAD` is not a synonym for `PARTIAL`.** Partial means a read
happened and fell short. Unread means no read has been attempted, which is the honest
state of a slice from the moment its account is enrolled until the first run reaches
it. `enrol` writes those rows before any reading, so a slice the run never reaches
still has a row, because absence of a row and absence of resources are
indistinguishable to a consumer and one of them is dangerous.

**Two writers rather than one, and the asymmetry is deliberate.** `enrol` writes only
where there is no row yet, so it can run at the head of every collection without
undoing what a successful read recorded last night. `record` overwrites, because a
slice's coverage is its current state and not a history: a second row for the same
account and region would let a consumer read either one and get a different answer
about whether the graph can be trusted, with nothing saying which was current.

**A slice moves back to COMPLETE on its own.** Nothing clears a PARTIAL row, because
nothing needs to: the next successful read of that slice upserts over it with a null
cause. `tests/ingest/test_coverage.py` asserts the transition in both directions,
which is the criterion TASK-P4-005 states, and it is worth asserting both ways because
a writer that only ever widened the failure would look correct on the way down.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from finops_core.domain.account import AccountKey
from finops_core.domain.topology import CoverageCause, CoverageState, SliceRead

#: Upserted on the slice, not inserted. The conflict target is the expression the
#: unique index is built on, coalesced because a unique index treats nulls as distinct
#: and a null region is the account's global slice.
UPSERT = text(
    "INSERT INTO graph_coverage (coverage_id, tenant_id, ingest_run_id, sub_account_id, "
    "region_id, state, cause, node_count, edge_count, as_of, collected_at) "
    "VALUES (:coverage_id, :tenant, :run, :account, :region, :state, :cause, :nodes, "
    ":edges, :as_of, :collected_at) "
    "ON CONFLICT (tenant_id, sub_account_id, COALESCE(region_id, '')) DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, state = EXCLUDED.state, "
    "cause = EXCLUDED.cause, node_count = EXCLUDED.node_count, "
    "edge_count = EXCLUDED.edge_count, as_of = EXCLUDED.as_of, "
    "collected_at = EXCLUDED.collected_at"
)

#: The same statement without the overwrite. `enrol` uses it so a run starting after a
#: successful one does not reset last night's COMPLETE rows to UNREAD for the minutes
#: before it reaches them, which would make a healthy estate look unread on every
#: screen for as long as a collection takes.
CLAIM = text(
    "INSERT INTO graph_coverage (coverage_id, tenant_id, ingest_run_id, sub_account_id, "
    "region_id, state, cause, node_count, edge_count, as_of, collected_at) "
    "VALUES (:coverage_id, :tenant, :run, :account, :region, 'UNREAD', 'NotYetAttempted', "
    "0, 0, :as_of, :collected_at) "
    "ON CONFLICT (tenant_id, sub_account_id, COALESCE(region_id, '')) DO NOTHING"
)

Clock = Callable[[], datetime]

Slice = tuple[AccountKey, str | None]


def enrol(
    connection: Any,
    *,
    tenant: UUID,
    run_id: UUID,
    slices: Iterable[Slice],
    at: datetime,
) -> int:
    """Give every enrolled slice an UNREAD row, and leave existing rows alone.

    Called at the head of a collection over the source's `enrolled_slices`, which is
    the denominator. A slice this run never reaches keeps its UNREAD row, and that is
    the point: the criterion says the row is created when the account is enrolled
    rather than when a collection first fails, and a row written only on failure cannot
    distinguish a slice nobody tried from a slice that does not exist.

    One run of latency, honestly. A slice enrolled between two runs gets its row at the
    head of the next one rather than at the instant the account row appeared. The
    alternative is a trigger or a second writer inside account discovery, and neither
    is worth a second place for this rule to live.

    Returns how many rows were new, which is worth counting because the number is zero
    on every run after the first and a non zero one means the estate grew.
    """
    written = 0
    for account, region in slices:
        result = connection.execute(
            CLAIM,
            {
                "coverage_id": uuid4(),
                "tenant": tenant,
                "run": run_id,
                "account": account.account_id,
                "region": region,
                "as_of": at,
                "collected_at": at,
            },
        )
        written += int(result.rowcount or 0)
    return written


def record(
    connection: Any,
    *,
    tenant: UUID,
    run_id: UUID,
    read: SliceRead,
    at: datetime,
) -> None:
    """Write what one read of one slice found, overwriting whatever was there.

    The state and the cause come from the read rather than from the caller, so a
    collector cannot write COMPLETE over a read that carried four shortfalls. The
    counts are what was read, not what was expected: a COMPLETE slice with zero nodes
    is an account that genuinely has nothing there, and telling that apart from an
    unread one without a second query is why the counts are stored at all.
    """
    write(
        connection,
        tenant=tenant,
        run_id=run_id,
        account=read.account_key,
        region=read.region_id,
        state=read.state,
        cause=read.cause,
        node_count=len(read.nodes),
        edge_count=len(read.edges),
        at=at,
    )


def refused(
    connection: Any,
    *,
    tenant: UUID,
    run_id: UUID,
    account: AccountKey,
    region: str | None,
    cause: CoverageCause,
    at: datetime,
) -> None:
    """Write a PARTIAL row for a slice no read ever got to.

    `record` covers every failure inside the source, which returns a `SliceRead`
    carrying shortfalls. This covers the one outside it: a credential broker refusing
    before a call was made, which raises rather than returning, and would otherwise
    leave the slice showing whatever its row said last night. A slice whose credential
    was revoked this morning and which still reads COMPLETE from last night's run is
    the exact failure this table prevents, arriving through the one door the source
    cannot see.
    """
    write(
        connection,
        tenant=tenant,
        run_id=run_id,
        account=account,
        region=region,
        state=CoverageState.PARTIAL,
        cause=cause,
        node_count=0,
        edge_count=0,
        at=at,
    )


def write(
    connection: Any,
    *,
    tenant: UUID,
    run_id: UUID,
    account: AccountKey,
    region: str | None,
    state: CoverageState,
    cause: CoverageCause | None,
    node_count: int,
    edge_count: int,
    at: datetime,
) -> None:
    """The one statement, with the pairing rule checked before the database checks it.

    The check constraint says the same thing and is the one that actually holds, per
    constraint 11. This raises first so the message names the collector's mistake rather
    than arriving as an integrity error from a statement a reader then has to match back
    to a caller.
    """
    if (state is CoverageState.COMPLETE) != (cause is None):
        raise ValueError(
            f"A {state.value} slice and a cause of {cause} do not pair. A complete slice "
            "has nothing to explain, and an incomplete one that cannot say why shows a "
            "banner that sends nobody anywhere."
        )
    connection.execute(
        UPSERT,
        {
            "coverage_id": uuid4(),
            "tenant": tenant,
            "run": run_id,
            "account": account.account_id,
            "region": region,
            "state": state.value,
            # The typed cause, as its own value, never a message. Free text here would
            # be a column nobody can group by, and the detail that explains one failure
            # belongs on `sync_error` beside the run that hit it.
            "cause": None if cause is None else cause.value,
            "nodes": node_count,
            "edges": edge_count,
            "as_of": at,
            "collected_at": at,
        },
    )
