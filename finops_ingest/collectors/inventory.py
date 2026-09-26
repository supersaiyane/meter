"""The graph, written one slice at a time, with what was missed written beside it.

`topology_node`, `topology_edge` and `graph_coverage` were migrated in 0014 and nothing
has ever written to them. This is the writer.

**One collector, not two. ADR-0024.** TASK-P4-006 asks for two, one per source. Two
cannot work: both write `topology_node`, whose identity is `(tenant_id, provider_id)`, so
they cannot each own a row, and the retraction keys on the run id, so whichever ran second
would remove every row the first one wrote and nothing else. The composite source in
`topology.py` reads every source in one run instead, and this collector owns the slice.

**Nothing removes anything unless the slice read COMPLETE.** This is the rule the sub
project turns on, in its most consequential place. A PARTIAL read cannot tell a resource
that is gone from a resource it could not see, so removing on one would delete the estate
a refused credential hid, silently, and the graph would then be smaller and still render.
That is stricter than the plan's criterion, which asks only that a half read removes
nothing, and the extra strictness costs a stale row on a partial slice, which the coverage
banner shows, against data loss that is visible nowhere.

**The removal sits downstream of finishing the read.** The worker runs a unit in one
transaction, so a read that fails part way rolls back everything including any removal,
and that is what does the work in the deployed shape. The ordering is the second
protection and it costs nothing to keep.

**Enrolment and reading are two different lists.** `enrol` covers every slice the source
declares; the loop reads the slices this run was given. A run that reads nineteen of twenty
leaves the twentieth `UNREAD`, which is the state TASK-P4-005 asks for and the one a
dispatcher fanning out per account produces naturally. With one list they could not differ,
and `UNREAD` would be a value in an enumeration that no run could ever leave behind.

**One account failing never fails the run.** Each slice is read inside its own guard, and
a failure lands in `graph_coverage` and in `sync_error` both. The two are not redundant.
Coverage is the state of a slice, which a screen reads to decide whether a number can be
trusted. A sync error is a record of an event with a remediation on it, which a person
reads to decide what to fix. A failure in only the first is one nobody is told to act on;
a failure in only the second leaves every screen confident.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from finops_core.domain.account import AccountKey
from finops_core.domain.topology import CoverageCause, CoverageState, Edge, Node, SliceRead
from finops_core.errors import CollectionError
from finops_ingest import coverage
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "inventory"

#: What a person should do about each cause, taken from the taxonomy rather than written
#: again here. `sync_error.remediation` is NOT NULL and a second copy of these sentences
#: would drift from the first.
REMEDIATION: dict[str, str] = {
    error_type.cause: error_type.remediation_text for error_type in CollectionError.__subclasses__()
}

NODE_COLUMNS = (
    "node_id",
    "tenant_id",
    "ingest_run_id",
    "sub_account_id",
    "provider_id",
    "node_kind",
    "resource_type",
    "region_id",
    "availability_zone",
    "name",
    "as_of",
    "collected_at",
)

#: Everything but the identity. A resource that changed its name, moved zone or was
#: retagged upserts onto its own row, and `ingest_run_id` changing is what tells the
#: retraction this row was seen again.
_NODE_UPDATABLE = tuple(
    column for column in NODE_COLUMNS if column not in ("node_id", "tenant_id", "provider_id")
)

UPSERT_NODE = text(
    "INSERT INTO topology_node ("
    + ", ".join(NODE_COLUMNS)
    + ", tags) VALUES ("
    + ", ".join(f":{column}" for column in NODE_COLUMNS)
    + ", CAST(:tags AS jsonb)) "
    "ON CONFLICT (tenant_id, provider_id) DO UPDATE SET "
    + ", ".join(f"{column} = EXCLUDED.{column}" for column in _NODE_UPDATABLE)
    + ", tags = EXCLUDED.tags"
)

EDGE_COLUMNS = (
    "edge_id",
    "tenant_id",
    "ingest_run_id",
    "from_node_id",
    "to_node_id",
    "edge_kind",
    "is_cross_account",
    "source",
    "sub_account_id",
    "region_id",
    "as_of",
    "collected_at",
)

_EDGE_UPDATABLE = (
    "ingest_run_id",
    "is_cross_account",
    "source",
    "sub_account_id",
    "region_id",
    "as_of",
    "collected_at",
)

UPSERT_EDGE = text(
    "INSERT INTO topology_edge ("
    + ", ".join(EDGE_COLUMNS)
    + ") VALUES ("
    + ", ".join(f":{column}" for column in EDGE_COLUMNS)
    + ") ON CONFLICT (tenant_id, from_node_id, to_node_id, edge_kind) DO UPDATE SET "
    + ", ".join(f"{column} = EXCLUDED.{column}" for column in _EDGE_UPDATABLE)
)

#: `IS NOT DISTINCT FROM` rather than `=`, because a null region is the account's global
#: slice and `region_id = NULL` matches nothing. With `=` the global slice would never be
#: retracted and a role deleted years ago would still be in the graph.
_SLICE = (
    "tenant_id = :tenant AND sub_account_id = :account "
    "AND region_id IS NOT DISTINCT FROM :region AND ingest_run_id <> :run"
)

#: Edges before nodes, because `from_node_id` references `topology_node` and the key
#: deliberately does not cascade. An edge whose origin is in this slice is in this slice,
#: because the edge carries the origin's account and region, so the pair is closed.
RETRACT_EDGES = text(f"DELETE FROM topology_edge WHERE {_SLICE}")
RETRACT_NODES = text(f"DELETE FROM topology_node WHERE {_SLICE}")

SYNC_ERROR = text(
    "INSERT INTO sync_error (error_id, tenant_id, collector, scope_key, error_type, "
    "detail, remediation, first_seen_at, last_seen_at, occurrences) "
    "VALUES (:id, :tenant, :collector, :scope, :error_type, :detail, :remediation, :at, :at, 1) "
    "ON CONFLICT (tenant_id, collector, scope_key, error_type) DO UPDATE SET "
    "detail = EXCLUDED.detail, last_seen_at = EXCLUDED.last_seen_at, "
    "occurrences = sync_error.occurrences + 1"
)

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


def scope_key(account: AccountKey, region: str | None) -> str:
    """The slice, as `docs/07-DATA-MODEL.md` spells a scope key.

    The global slice carries no region rather than the word global, so a reader sorting
    scope keys sees the account's own row above its regions rather than filed under g.
    """
    return str(account) if region is None else f"{account}:{region}"


class InventoryCollector:
    """Reads every enrolled slice, writes what it found, and records what it missed."""

    def __init__(
        self,
        source: Any,
        clock: Clock = _system_clock,
        covers: tuple[tuple[AccountKey, str | None], ...] | None = None,
    ) -> None:
        self._source = source
        self._clock = clock
        # Which slices this run reads, as against which are enrolled. None means all of
        # them, which is what a single worker doing the whole estate passes.
        #
        # They are separate for the reason TASK-P4-005 states: the UNREAD row is created
        # at enrolment and not at first failure, so a slice that is enrolled and that this
        # run did not reach has to keep it. With one list the two could not differ and
        # UNREAD would be a state no run could leave behind, which would make it a value
        # in an enum that never appears.
        self._covers = covers

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        if context.run_id is None:
            # Not a typed collection failure. Nothing about the provider is wrong, the
            # caller assembled the context incorrectly, and a collection error here would
            # be recorded against the scope and send somebody to look at AWS.
            raise ValueError(
                "inventory needs the run id from the ledger's claim. Every node and edge "
                "carries it in a NOT NULL column and the retraction deletes on it, so a "
                "collector inventing one would delete on a fiction."
            )

        at = self._clock()
        tenant: UUID = context.unit.tenant_id
        enrolled = self._source.enrolled_slices
        reading = enrolled if self._covers is None else self._covers

        # Every enrolled slice, before any reading. A slice this run never reaches keeps an
        # UNREAD row, which is what makes it distinguishable from a slice that holds
        # nothing.
        coverage.enrol(
            context.connection, tenant=tenant, run_id=context.run_id, slices=enrolled, at=at
        )

        written = 0
        removed = 0
        for account, region in reading:
            try:
                read = self._source.read_slice(account, region)
            except CollectionError as failure:
                # The one failure a source cannot report as a shortfall: a credential the
                # broker could not assume, which raises before a call was made. One
                # account failing never fails the run, so this records and continues.
                coverage.refused(
                    context.connection,
                    tenant=tenant,
                    run_id=context.run_id,
                    account=account,
                    region=region,
                    cause=CoverageCause(failure.cause),
                    at=at,
                )
                self._record_error(
                    context, account, region, failure.cause, failure.detail or str(failure), at
                )
                continue

            written += self._write(context, read, at)
            if read.state is CoverageState.COMPLETE:
                # Only here. See the module docstring: a PARTIAL read cannot tell a
                # resource that is gone from a resource it could not see.
                removed += self._retract(context, account, region)
            coverage.record(
                context.connection, tenant=tenant, run_id=context.run_id, read=read, at=at
            )
            for shortfall in read.shortfalls:
                self._record_error(
                    context, account, region, shortfall.cause.value, shortfall.detail, at
                )

        return CollectorOutcome(items_written=written, items_removed=removed)

    def _write(self, context: CollectorContext, read: SliceRead, at: datetime) -> int:
        """Nodes, then edges, because an edge references the node it leaves.

        One statement per row rather than batched, because a slice is tens to hundreds of
        rows rather than the tens of thousands `cost_focus` handles, and a batch here
        would buy a round trip and cost the ability to say which row was refused.
        """
        for node in read.nodes:
            context.connection.execute(UPSERT_NODE, self._node_parameters(node, context, at))
        for edge in read.edges:
            context.connection.execute(UPSERT_EDGE, self._edge_parameters(edge, read, context, at))
        return len(read.nodes) + len(read.edges)

    def _retract(self, context: CollectorContext, account: AccountKey, region: str | None) -> int:
        """Remove what the provider no longer reports, in this slice only.

        The signal is the run id, the same one `cost_focus` uses. A row this run saw
        carries this run's id because the upsert set it. A row it did not see kept an
        older one, and in a complete read of a slice the only reason a row goes unseen is
        that the resource is gone.

        Not a timestamp. Two runs inside one second are indistinguishable by a clock, so a
        `collected_at` predicate either removes nothing or removes both runs' work
        depending on which way the comparison leans.

        All four predicates are load bearing. Without the tenant, one tenant's ingest
        removes another's graph. Without the account and the region, reading one slice
        removes every other slice in one statement, which is the worst outcome available
        to this file and the easiest to write.
        """
        parameters = {
            "tenant": context.unit.tenant_id,
            "account": account.account_id,
            "region": region,
            "run": context.run_id,
        }
        edges = context.connection.execute(RETRACT_EDGES, parameters)
        nodes = context.connection.execute(RETRACT_NODES, parameters)
        return int(edges.rowcount or 0) + int(nodes.rowcount or 0)

    def _record_error(
        self,
        context: CollectorContext,
        account: AccountKey,
        region: str | None,
        error_type: str,
        detail: str,
        at: datetime,
    ) -> None:
        """One row per scope and cause, with a rising count rather than one row per run.

        A cause outside the taxonomy is skipped rather than written. `sync_error` has a
        check constraint listing the six, so `NotYetAttempted` would fail the whole unit,
        and it cannot reach here anyway: it is the cause of an unread slice, and an unread
        slice is one nothing tried to read. Skipping it is the safe reading of a state
        that should be impossible.
        """
        if error_type not in REMEDIATION:
            return
        context.connection.execute(
            SYNC_ERROR,
            {
                "id": uuid4(),
                "tenant": context.unit.tenant_id,
                "collector": COLLECTOR,
                "scope": scope_key(account, region),
                "error_type": error_type,
                "detail": detail or error_type,
                "remediation": REMEDIATION[error_type],
                "at": at,
            },
        )

    def _node_parameters(
        self, node: Node, context: CollectorContext, at: datetime
    ) -> dict[str, Any]:
        return {
            "node_id": node.node_id,
            "tenant_id": context.unit.tenant_id,
            "ingest_run_id": context.run_id,
            "sub_account_id": node.account_key.account_id,
            "provider_id": node.provider_id,
            "node_kind": node.node_kind.value,
            "resource_type": node.resource_type,
            "region_id": node.region_id,
            "availability_zone": node.availability_zone,
            "name": node.name,
            # `as_of` stays the source's: it is when the resource was as described.
            # `collected_at` is ours. Constraint 10, and conflating them is what makes a
            # stale configuration item look fresh.
            "as_of": node.as_of,
            "collected_at": at,
            "tags": json.dumps(dict(node.tags)),
        }

    def _edge_parameters(
        self, edge: Edge, read: SliceRead, context: CollectorContext, at: datetime
    ) -> dict[str, Any]:
        return {
            "edge_id": uuid4(),
            "tenant_id": context.unit.tenant_id,
            "ingest_run_id": context.run_id,
            "from_node_id": edge.from_node_id,
            "to_node_id": edge.to_node_id,
            "edge_kind": edge.edge_kind.value,
            "is_cross_account": edge.is_cross_account,
            "source": edge.source,
            # The origin's slice, which is this read's slice, because a source only emits
            # an edge out of a node it read here. Denormalised so the retraction needs no
            # join to a node row this same run may already have removed.
            "sub_account_id": read.account_key.account_id,
            "region_id": read.region_id,
            "as_of": edge.as_of,
            "collected_at": at,
        }
