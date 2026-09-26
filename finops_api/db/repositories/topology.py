"""Reading the graph, bounded, scoped twice, with its coverage attached.

The traversal is a recursive common table expression, per ADR-0005. It is here rather than
in `finops_query/graph.py`, which is where TASK-P4-007 puts it, for a reason the task's own
criteria create: the same task asks for the guard's `scoped_select`, which lives in
`finops_api.guards`, and the import contract forbids `finops_query` from reaching it.
`finops_query` also holds no SQLAlchemy at all. Scope enforcement outranks file placement,
constraint 3, so the statement is where the guard is and `finops_query.graph` holds the
bounds, the cap, the truncation report and the return type that carries coverage.

**The recursion is scoped in its own right, not only at its seed.** The base term is
confined to the scope's accounts and the recursive term repeats that predicate rather than
trusting the rows the base term admitted. That is not belt and braces: a recursive term
without it walks from a permitted node along an edge belonging to an account the caller
cannot read, and the walk does not stop at the boundary of what somebody was granted. The
edges of a graph are exactly where a scope leak hides, because nothing about the answer
looks wrong.

**The cycle is handled by carrying the path.** A security group that references itself is
the ordinary case rather than a pathology, and a naive recursion over it does not terminate.
The statement carries the visited identifiers as an array and refuses a node already on the
path, which is the only form that also handles the two node cycle a pair of groups
referencing each other creates.

**Coverage is read for the slices the answer actually touched**, not for the whole tenant.
A banner naming eleven regions when the map shows two is a banner a reader learns to
dismiss, and the point of the banner is that it is not dismissed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import Table, text
from sqlalchemy.engine import Row

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_api.guards import require_scope, scope_predicate
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.tenant import Scope
from finops_core.domain.topology import (
    CoverageCause,
    CoverageState,
    Edge,
    EdgeKind,
    GraphCoverage,
    Node,
    NodeKind,
)
from finops_query.graph import Bounds, Subgraph, assemble

#: The walk, outward from one root, carrying its path so a cycle terminates.
#:
#: Written as text rather than assembled from the ORM's recursive CTE support for one
#: reason: the array containment predicate that stops the cycle has no faithful expression
#: there, and a recursion whose termination condition is approximated is a recursion that
#: does not terminate on the day the approximation is wrong. The account list the scope
#: admits is still computed by the guard's own rules and bound as a parameter, so the one
#: thing that must not be hand rolled is not.
WALK = """
WITH RECURSIVE reachable AS (
    SELECT
        n.node_id,
        0 AS depth,
        ARRAY[n.node_id] AS path
    FROM topology_node n
    WHERE n.tenant_id = :tenant
      AND n.node_id = :root
      AND n.sub_account_id = ANY(:accounts)
    UNION ALL
    SELECT
        e.to_node_id,
        r.depth + 1,
        r.path || e.to_node_id
    FROM reachable r
    JOIN topology_edge e
      ON e.from_node_id = r.node_id
     AND e.tenant_id = :tenant
     AND e.sub_account_id = ANY(:accounts)
    WHERE r.depth < :max_depth
      AND NOT (e.to_node_id = ANY(r.path))
)
SELECT node_id, min(depth) AS depth
FROM reachable
GROUP BY node_id
ORDER BY depth, node_id
LIMIT :limit
"""

#: The same walk with the arrow reversed, for FEAT-044's question: what reaches this
#: resource. A second literal rather than the direction as a parameter, because a join
#: column chosen by a bound value is not something PostgreSQL will plan, and a test asserts
#: the two differ in exactly the three places they are meant to.
WALK_INWARD = (
    WALK.replace("e.from_node_id = r.node_id", "e.to_node_id = r.node_id")
    .replace(
        "        e.to_node_id,\n        r.depth + 1,\n        r.path || e.to_node_id",
        "        e.from_node_id,\n        r.depth + 1,\n        r.path || e.from_node_id",
    )
    .replace("NOT (e.to_node_id = ANY(r.path))", "NOT (e.from_node_id = ANY(r.path))")
)


class TopologyRepository(ScopedRepository):
    """The graph, read outward or inward from one node, with coverage attached."""

    table: ClassVar[Table] = models.topology_node
    resource: ClassVar[str] = "topology_node"

    def subgraph(
        self,
        scope: Scope,
        *,
        root_id: UUID,
        bounds: Bounds | None = None,
        inward: bool = False,
    ) -> Subgraph:
        """Everything within `bounds` of one node, plus the coverage of its slices.

        `inward` reverses the arrow, which is FEAT-044's question: not what this resource
        reaches but what reaches it. The same bounds apply, because a blast radius that is
        unbounded in one direction is unbounded.

        Returns a `Subgraph` whose coverage is not optional, so a caller cannot answer a
        question that needs completeness without having been handed the reason it might
        not be.
        """
        limits = bounds or Bounds()
        confirmed = require_scope(scope)
        accounts = self._accounts_for(confirmed)

        if not accounts:
            # An empty scope reads nothing, which is the fail closed case. Returned as an
            # empty subgraph rather than raised, because a caller narrowed to no accounts
            # asked a legitimate question with an empty answer.
            return assemble(root_id=root_id, found=(), edges=(), coverage=(), bounds=limits)

        reached = self._connection.execute(
            text(WALK_INWARD if inward else WALK),
            {
                "tenant": confirmed.tenant_id,
                "root": root_id,
                "accounts": accounts,
                "max_depth": limits.max_depth,
                "limit": limits.fetch_limit,
            },
        ).all()
        # One audit row for the whole traversal, naming the scope that was evaluated. A
        # walk is one read, and four rows for it would make the audit log unreadable at
        # exactly the moment somebody is reading it.
        self._audit(confirmed, action="read", outcome="ALLOWED")

        depths = {row.node_id: int(row.depth) for row in reached}
        if not depths:
            return assemble(root_id=root_id, found=(), edges=(), coverage=(), bounds=limits)

        nodes = self._nodes(confirmed, tuple(depths))
        found = tuple((node, depths[node.node_id]) for node in nodes)
        edges = self._edges(confirmed, tuple(depths))
        slices = {(node.account_key.account_id, node.region_id) for node in nodes}
        return assemble(
            root_id=root_id,
            found=found,
            edges=edges,
            coverage=self._coverage(confirmed, slices),
            bounds=limits,
            # Which of the edges' far ends Meter actually holds a row for, in scope. This is
            # what lets `assemble` tell a boundary from a node the depth bound cut: without
            # it a walk of depth nought would draw a line to every neighbour it did not
            # fetch, and a genuine cross account boundary would be indistinguishable from
            # one of them.
            inside=self._existing(confirmed, tuple({edge.to_node_id for edge in edges})),
        )

    def incomplete(self, scope: Scope) -> tuple[GraphCoverage, ...]:
        """Every incomplete slice the caller can see, for the estate wide banner.

        A separate read from the subgraph's, because the two answer different questions.
        The subgraph's coverage is about one map. This is about the estate, and it is what
        the inventory screen shows before anybody has picked a root.
        """
        confirmed = require_scope(scope)
        rows = models.graph_coverage
        statement = (
            rows.select()
            .where(rows.c.tenant_id == confirmed.tenant_id)
            .where(scope_predicate(rows, confirmed))
            .where(rows.c.state != CoverageState.COMPLETE.value)
            .order_by(rows.c.sub_account_id, rows.c.region_id)
        )
        found = self._connection.execute(statement).all()
        self._audit(confirmed, action="read", outcome="ALLOWED")
        return tuple(_as_coverage(row) for row in found)

    # -- the reads underneath -----------------------------------------------

    def _accounts_for(self, scope: Scope) -> list[str]:
        """Which accounts the recursion may walk through.

        A narrowed scope gives its own list. A global scope has none, so this reads the
        tenant's accounts, because the recursive term needs a list and the alternative is a
        `TRUE` that makes it the one place the scope was not applied.
        """
        if not scope.is_global:
            return sorted(key.account_id for key in scope.accounts)
        rows = self._connection.execute(
            models.cloud_account.select()
            .with_only_columns(models.cloud_account.c.account_id)
            .where(models.cloud_account.c.tenant_id == scope.tenant_id)
        ).all()
        return sorted(str(row.account_id) for row in rows)

    def _existing(self, scope: Scope, node_ids: tuple[UUID, ...]) -> set[UUID]:
        """Which of these identifiers Meter holds a node row for, within the scope.

        A projection rather than a full read, because nothing needs the rows: the question
        is membership. Scoped like every other read, so a node in an account the caller
        cannot see counts as a boundary to them, which is the right disclosure and is what
        makes the narrow scope case draw the cross account edge as a boundary rather than
        dropping it.
        """
        if not node_ids:
            return set()
        statement = self.scoped_select(scope).with_only_columns(self.table.c.node_id)
        rows = self._connection.execute(statement.where(self.table.c.node_id.in_(node_ids))).all()
        return {row.node_id for row in rows}

    def _nodes(self, scope: Scope, node_ids: tuple[UUID, ...]) -> tuple[Node, ...]:
        statement = self.scoped_select(scope).where(self.table.c.node_id.in_(node_ids))
        return tuple(_as_node(row) for row in self._connection.execute(statement).all())

    def _edges(self, scope: Scope, node_ids: tuple[UUID, ...]) -> tuple[Edge, ...]:
        """Every edge whose origin is in the answer, including those leaving it.

        Leaving it on purpose. An edge to a node outside the fetched set is a boundary, and
        `finops_query.graph.assemble` keeps it while dropping an edge whose target was
        fetched and then cut by the cap. The difference is the one the map has to draw.
        """
        edges = models.topology_edge
        statement = (
            edges.select()
            .where(edges.c.tenant_id == scope.tenant_id)
            .where(scope_predicate(edges, scope))
            .where(edges.c.from_node_id.in_(node_ids))
        )
        return tuple(_as_edge(row) for row in self._connection.execute(statement).all())

    def _coverage(
        self, scope: Scope, slices: set[tuple[str, str | None]]
    ) -> tuple[GraphCoverage, ...]:
        rows = models.graph_coverage
        accounts = sorted({account for account, _region in slices})
        statement = (
            rows.select()
            .where(rows.c.tenant_id == scope.tenant_id)
            .where(scope_predicate(rows, scope))
            .where(rows.c.sub_account_id.in_(accounts))
        )
        found = self._connection.execute(statement).all()
        return tuple(
            _as_coverage(row) for row in found if (str(row.sub_account_id), row.region_id) in slices
        )


def _as_node(row: Row[Any]) -> Node:
    return Node(
        node_id=row.node_id,
        account_key=AccountKey(provider=Provider.AWS, account_id=str(row.sub_account_id)),
        provider_id=str(row.provider_id),
        node_kind=NodeKind(row.node_kind),
        resource_type=str(row.resource_type),
        region_id=row.region_id,
        availability_zone=row.availability_zone,
        name=row.name,
        tags=dict(row.tags or {}),
        as_of=row.as_of,
        collected_at=row.collected_at,
    )


def _as_edge(row: Row[Any]) -> Edge:
    return Edge(
        from_node_id=row.from_node_id,
        to_node_id=row.to_node_id,
        edge_kind=EdgeKind(row.edge_kind),
        is_cross_account=bool(row.is_cross_account),
        source=str(row.source),
        as_of=row.as_of,
        collected_at=row.collected_at,
    )


def _as_coverage(row: Row[Any]) -> GraphCoverage:
    return GraphCoverage(
        account_key=AccountKey(provider=Provider.AWS, account_id=str(row.sub_account_id)),
        region_id=row.region_id,
        state=CoverageState(row.state),
        cause=None if row.cause is None else CoverageCause(row.cause),
        node_count=int(row.node_count),
        edge_count=int(row.edge_count),
        as_of=row.as_of,
        collected_at=row.collected_at,
    )


def slices_of(nodes: Sequence[Node]) -> tuple[tuple[str, str | None], ...]:
    """The distinct slices a set of nodes came from, sorted for a stable banner.

    Exported because the route needs the same list to name regions in the response, and two
    implementations of "which slices does this map touch" is how a banner comes to name a
    region the map does not show.
    """
    return tuple(
        sorted(
            {(node.account_key.account_id, node.region_id) for node in nodes},
            key=lambda pair: (pair[0], pair[1] or ""),
        )
    )
