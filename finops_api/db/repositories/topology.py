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

from sqlalchemy import Select, Table, func, text
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


def _fetch(
    repository: ScopedRepository, scope: Scope, statement: Select[tuple[Any, ...]]
) -> Sequence[Row[tuple[Any, ...]]]:
    """Run a projected select through the scoped path.

    One helper rather than a cast at every call site, the same one `waste.py` keeps for the
    same reason: `with_only_columns` narrows the row type and the base class is typed for
    the wide one.
    """
    return repository.fetch(scope, statement)


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

    def slice_count(self, scope: Scope) -> int:
        """How many slices the caller can see at all, which is the banner's denominator.

        Slices, not accounts and not rows. A view over eleven of twelve regions is partial
        in a way counting accounts cannot express, and a row count in that slot has been the
        defect three times.
        """
        rows = models.graph_coverage
        confirmed = require_scope(scope)
        statement = (
            rows.select()
            .with_only_columns(func.count())
            .where(rows.c.tenant_id == confirmed.tenant_id)
            .where(scope_predicate(rows, confirmed))
        )
        found = self._connection.execute(statement).all()
        return int(found[0][0] or 0) if found else 0

    def accounts_seen(self, scope: Scope) -> int:
        """How many accounts this scope holds any graph for, for the ordinary banner."""
        statement = self.scoped_select(scope).with_only_columns(
            func.count(func.distinct(self.table.c.sub_account_id))
        )
        rows = _fetch(self, scope, statement)
        return int(rows[0][0] or 0) if rows else 0

    def roots(
        self, scope: Scope, *, node_kind: str | None = None, limit: int = 200
    ) -> Sequence[Row[Any]]:
        """Nodes a reader can start a map from, containers first.

        Ordered by kind and then by name rather than by identifier, because a reader
        scanning this list is looking for a name they recognise and a UUID order is a random
        one to them.
        """
        statement = self.scoped_select(scope)
        if node_kind is not None:
            statement = statement.where(self.table.c.node_kind == node_kind)
        return self.fetch(
            scope,
            statement.order_by(self.table.c.node_kind, self.table.c.name).limit(limit),
        )

    def page(
        self,
        scope: Scope,
        *,
        account_id: str | None = None,
        region_id: str | None = None,
        node_kind: str | None = None,
        resource_type: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[Row[Any]], int]:
        """One page of resources, and how many match the filter in total.

        FEAT-056, TASK-P4-012. The count comes back with the page rather than from a second
        call, because a reader is told "showing 50 of 4,312" and two statements could disagree
        about the denominator in a way nothing would catch.

        Counted through `scoped_select` like the page, so the total is the total this reader
        may see. A count of every row with a page of the readable ones is the arithmetic that
        tells a narrowed reader how much they are not allowed to look at.

        Ordered by account, then region, then kind, then name. A reader scanning this is
        looking for something they recognise, and the identifier order is a random one to
        them. Deterministic to the identifier at the end, because a page boundary in a
        non deterministic order silently repeats and skips rows.
        """
        statement = self.scoped_select(scope)
        for column, wanted in (
            (self.table.c.sub_account_id, account_id),
            (self.table.c.region_id, region_id),
            (self.table.c.node_kind, node_kind),
            (self.table.c.resource_type, resource_type),
        ):
            if wanted is not None:
                statement = statement.where(column == wanted)

        total = self._connection.execute(
            statement.with_only_columns(func.count()).order_by(None)
        ).scalar_one()
        rows = self.fetch(
            scope,
            statement.order_by(
                self.table.c.sub_account_id,
                self.table.c.region_id,
                self.table.c.node_kind,
                self.table.c.name,
                self.table.c.node_id,
            )
            .limit(limit)
            .offset(offset),
        )
        return rows, int(total)

    def vocabularies(self, scope: Scope) -> dict[str, tuple[str, ...]]:
        """The filter values that actually occur in this scope.

        Read rather than taken from the enumerations, and the difference matters twice. A
        select offering all fourteen node kinds when the estate holds four teaches a reader
        that twelve filters return nothing. And `resource_type` has no enumeration at all: it
        is the provider's own word, ten of which map to OTHER, so the only place the list
        exists is the data.

        A region of null is the account's global slice and is offered as such by the caller,
        never as an empty string, which reads as a bug in a select.
        """
        found: dict[str, tuple[str, ...]] = {}
        for name, column in (
            ("account_id", self.table.c.sub_account_id),
            ("region_id", self.table.c.region_id),
            ("node_kind", self.table.c.node_kind),
            ("resource_type", self.table.c.resource_type),
        ):
            statement = (
                self.scoped_select(scope).with_only_columns(column).distinct().order_by(column)
            )
            found[name] = tuple(
                row[0] for row in self._connection.execute(statement).all() if row[0] is not None
            )
        return found

    def one(self, scope: Scope, node_id: UUID) -> Node | None:
        """One node, or None where the scope cannot see it.

        FEAT-053. None rather than an exception, because a reader following a stale link has
        asked a legitimate question and the answer is that it is not there any more.
        """
        found = self._nodes(scope, (node_id,))
        return found[0] if found else None

    def slice_coverage(self, scope: Scope, node: Node) -> GraphCoverage | None:
        """The coverage of the one slice this node came from.

        None means the collector has never written a row for the slice, which should be
        impossible because `enrol` writes one per enrolled slice on every run. The page says
        so rather than assuming COMPLETE, because assuming it is the exact failure P4 exists
        to prevent and a missing row is evidence that something upstream is wrong.
        """
        found = self._coverage(scope, {(node.account_key.account_id, node.region_id)})
        return found[0] if found else None

    def findings_for(self, scope: Scope, node: Node) -> tuple[Sequence[Row[Any]], int]:
        """Recommendations about this resource, and how many in the account did not match.

        The second number is the honest part. A recommendation joins to a node on the
        provider's own identifier, and the first party sources report identifiers that do not
        always match what Config recorded: the generated estate has three such findings and
        seven that join. So a page showing an empty list would be saying this resource is
        clean when the truth is that nothing could be matched to it.

        Counted per account rather than per tenant, because an unmatched finding in another
        account tells a reader nothing about the resource they are looking at.
        """
        recommendation = models.recommendation
        account = node.account_key.account_id

        mine = (
            recommendation.select()
            .where(recommendation.c.tenant_id == scope.tenant_id)
            .where(scope_predicate(recommendation, scope))
            .where(recommendation.c.sub_account_id == account)
            .where(recommendation.c.resource_id == node.provider_id)
            .order_by(recommendation.c.estimated_monthly_saving.desc())
        )
        matched = self._connection.execute(mine).all()

        # Every node identifier in the account, so an unmatched finding is one whose resource
        # this tenant holds no node for at all rather than one belonging to another resource.
        known = self._connection.execute(
            self.scoped_select(scope)
            .with_only_columns(self.table.c.provider_id)
            .where(self.table.c.sub_account_id == account)
        ).all()
        provider_ids = {str(row.provider_id) for row in known}

        in_account = self._connection.execute(
            recommendation.select()
            .with_only_columns(recommendation.c.resource_id)
            .where(recommendation.c.tenant_id == scope.tenant_id)
            .where(scope_predicate(recommendation, scope))
            .where(recommendation.c.sub_account_id == account)
        ).all()
        unmatched = sum(1 for row in in_account if str(row.resource_id) not in provider_ids)
        return matched, unmatched

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
        return tuple(as_node(row) for row in self._connection.execute(statement).all())

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


def as_node(row: Row[Any]) -> Node:
    """One row as a domain node.

    Public since FEAT-056, because the resource list route maps rows the same way the
    traversal does and a second copy of the field mapping is a second place for a column
    rename to be missed."""
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
