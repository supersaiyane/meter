"""The graph, and the table that says how much of it is real.

Revision ID: 0014_topology
Revises: 0013_finops_score
Create Date: 2026-09-26

FEAT-030 and FEAT-031, TASK-P4-002. The plan numbered this 0011 when it was
written; the head had moved to 0013 by the time it was built.

Three tables, and the third is the one the sub project exists for. Section 6 of
the P4 specification: an edge Meter cannot see is not an absent edge. A cost
collector that fails leaves a number missing and the screen says so. A topology
collector that fails leaves a graph that still renders, still traverses, and
answers every question wrongly in the one direction that matters, because
everything looks less connected than it is. `graph_coverage` is the row that
makes that visible, and it is written on every run including a failed one.

**Three decisions here go beyond what the specification's column tables name,
and each one is here because the specification's own rule required it.**

**No foreign key from an edge to its `to_node_id`.** The most interesting edge in
this table is a cross account one, and the far end of a `TRUSTS` edge is
routinely a principal in an account Meter does not collect from at all. A foreign
key would refuse exactly those rows, which is the rule in section 6 inverted: an
edge Meter cannot fully see would become an absent edge, silently, at the
database. `from_node_id` does carry one, because every edge is written outward
from a resource this run actually read, and that invariant is true.

**And that key does not cascade.** `principal_scope` is the only table in this
schema that cascades and `tests/db/test_models.py` holds it to that, which caught
a first draft of this revision where it did. The reason it is the right refusal
here and not only a rule being obeyed: a cascade would remove edges that nothing
counted, so the run ledger's `items_removed` would undercount every departed
resource by the size of its neighbourhood. Without it, removing a node whose edges
are still present fails at the database, which forces the collector to remove edges
first and makes forgetting loud rather than silent.

**An edge carries the origin's `sub_account_id` and `region_id`.** Denormalised
for the same reason `is_cross_account` is: the retraction that removes what the
provider withdrew has to be scoped to the slice the run read, and without these
two columns that predicate needs a join back to `topology_node`. A join whose
other side this run may already have removed, which means the edge survives
forever and the graph keeps an edge to a resource that no longer exists. They are
the origin's slice and not the edge's, and a cross account edge's other end is in
another slice: that is what `is_cross_account` is for.

**`cause` admits seven values, not the four the specification lists.** ADR-0023.
The cause arrives from a caught `CollectionError` and there are six of those, so
narrowing here would mean mapping an unexpected cause onto something else, which
is the guessing the taxonomy exists to prevent. The seventh is
`NotYetAttempted`, which is what an `UNREAD` slice carries, because nothing
failed: no read has been attempted. `tests/db/test_p4_constraints.py` asserts
this list and `finops_core.domain.topology.CoverageCause` agree.

Backward compatible, per constraint 12: three new tables and nothing else. No
column is renamed, none is removed, and every table that existed before this
revision is untouched, so the task definitions running during a rolling deploy
neither see nor need any of it.
"""

from __future__ import annotations

from alembic import op

revision = "0014_topology"
down_revision = "0013_finops_score"
branch_labels = None
depends_on = None

#: The seven values `graph_coverage.cause` admits, as SQL literals. Derived from
#: `finops_core.domain.topology.CoverageCause` by hand because a migration does
#: not import application code: a migration has to keep running after the code
#: has moved on. The test asserts the two agree, which is the half that matters.
CAUSES = (
    "AccessDenied",
    "Throttled",
    "NotOptedIn",
    "NoData",
    "Unreachable",
    "SchemaDrift",
    "NotYetAttempted",
)

NODE_KINDS = (
    "VPC",
    "SUBNET",
    "INSTANCE",
    "ENI",
    "SECURITY_GROUP",
    "TARGET_GROUP",
    "LOAD_BALANCER",
    "NAT_GATEWAY",
    "TGW_ATTACHMENT",
    "VPC_ENDPOINT",
    "VOLUME",
    "DB_INSTANCE",
    "FUNCTION",
    "OTHER",
)

EDGE_KINDS = (
    "CONTAINS",
    "ATTACHED_TO",
    "ROUTES_TO",
    "TARGETS",
    "PERMITS",
    "PEERS_WITH",
    "TRUSTS",
)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE topology_node (
        node_id           UUID PRIMARY KEY,
        tenant_id         UUID        NOT NULL REFERENCES tenant (tenant_id),
        ingest_run_id     UUID        NOT NULL REFERENCES ingest_run (run_id),
        sub_account_id    TEXT        NOT NULL,
        provider_id       TEXT        NOT NULL,
        node_kind         TEXT        NOT NULL,
        resource_type     TEXT        NOT NULL,
        region_id         TEXT        NOT NULL,
        availability_zone TEXT,
        name              TEXT,
        tags              JSONB       NOT NULL DEFAULT '{}',
        as_of             TIMESTAMPTZ NOT NULL,
        collected_at      TIMESTAMPTZ NOT NULL
    )
    """,
    # The provider's identifier is the resource's identity, so a second run of the
    # same resource upserts onto the row it describes rather than landing beside it
    # with the same edges hanging off both. `node_id` is derived from this pair by
    # `finops_core.domain.topology.node_id_for`, which is why an edge can be written
    # without first reading back the node row it points at.
    """
    CREATE UNIQUE INDEX uq_topology_node__provider_id
        ON topology_node (tenant_id, provider_id)
    """,
    f"""
    ALTER TABLE topology_node
        ADD CONSTRAINT ck_topology_node__kind_known
        CHECK (node_kind IN ({_quoted(NODE_KINDS)}))
    """,
    # A zone that is not in its own region is a row that would put a resource in two
    # places at once on the map, and the likeliest way to write one is a collector
    # that read the zone from one call and the region from another.
    """
    ALTER TABLE topology_node
        ADD CONSTRAINT ck_topology_node__zone_within_region
        CHECK (availability_zone IS NULL OR availability_zone LIKE region_id || '%')
    """,
    """
    ALTER TABLE topology_node
        ADD CONSTRAINT ck_topology_node__collected_after_as_of
        CHECK (collected_at >= as_of)
    """,
    # The slice read: every collector predicate, every coverage join and the map's
    # own query start from an account and a region.
    """
    CREATE INDEX ix_topology_node__slice
        ON topology_node (tenant_id, sub_account_id, region_id)
    """,
    # The retraction predicate. A row this run saw carries this run's id.
    """
    CREATE INDEX ix_topology_node__run
        ON topology_node (tenant_id, ingest_run_id)
    """,
    """
    CREATE TABLE topology_edge (
        edge_id          UUID PRIMARY KEY,
        tenant_id        UUID        NOT NULL REFERENCES tenant (tenant_id),
        ingest_run_id    UUID        NOT NULL REFERENCES ingest_run (run_id),
        from_node_id     UUID        NOT NULL REFERENCES topology_node (node_id),
        to_node_id       UUID        NOT NULL,
        edge_kind        TEXT        NOT NULL,
        is_cross_account BOOLEAN     NOT NULL,
        source           TEXT        NOT NULL,
        sub_account_id   TEXT        NOT NULL,
        region_id        TEXT        NOT NULL,
        as_of            TIMESTAMPTZ NOT NULL,
        collected_at     TIMESTAMPTZ NOT NULL
    )
    """,
    # Direction is part of the identity. A security group permitting an instance is
    # not the instance permitting the group, and a store that merged the two would
    # answer "what is inside this VPC" with the VPC's parent.
    """
    CREATE UNIQUE INDEX uq_topology_edge__directed
        ON topology_edge (tenant_id, from_node_id, to_node_id, edge_kind)
    """,
    f"""
    ALTER TABLE topology_edge
        ADD CONSTRAINT ck_topology_edge__kind_known
        CHECK (edge_kind IN ({_quoted(EDGE_KINDS)}))
    """,
    # An edge that cannot say which API call produced it is an edge whose absence
    # cannot be told apart from an API that was refused, which is the distinction
    # this whole sub project is about.
    """
    ALTER TABLE topology_edge
        ADD CONSTRAINT ck_topology_edge__has_source
        CHECK (length(source) > 0)
    """,
    # Only a security group may refer to itself, which is the ordinary way an estate
    # lets a tier talk to itself. Any other reflexive edge is a traversal that does
    # not terminate, written by a collector that read a relationship backwards.
    """
    ALTER TABLE topology_edge
        ADD CONSTRAINT ck_topology_edge__self_edge_only_permits
        CHECK (from_node_id <> to_node_id OR edge_kind = 'PERMITS')
    """,
    """
    ALTER TABLE topology_edge
        ADD CONSTRAINT ck_topology_edge__collected_after_as_of
        CHECK (collected_at >= as_of)
    """,
    # Outward traversal, which is the recursive term of every walk in
    # `finops_query.graph`.
    """
    CREATE INDEX ix_topology_edge__outward
        ON topology_edge (tenant_id, from_node_id)
    """,
    # Inward traversal. FEAT-044's blast radius asks what reaches a resource, which
    # is the same walk with the arrow reversed, and without this index it is a scan.
    """
    CREATE INDEX ix_topology_edge__inward
        ON topology_edge (tenant_id, to_node_id)
    """,
    """
    CREATE INDEX ix_topology_edge__slice
        ON topology_edge (tenant_id, sub_account_id, region_id)
    """,
    # The cross account edges, which are few and are the ones anybody asks for by
    # name. Partial, so the index is the size of the answer rather than the table.
    """
    CREATE INDEX ix_topology_edge__cross_account
        ON topology_edge (tenant_id, from_node_id)
        WHERE is_cross_account
    """,
    """
    CREATE TABLE graph_coverage (
        coverage_id    UUID PRIMARY KEY,
        tenant_id      UUID        NOT NULL REFERENCES tenant (tenant_id),
        ingest_run_id  UUID        NOT NULL REFERENCES ingest_run (run_id),
        sub_account_id TEXT        NOT NULL,
        region_id      TEXT        NOT NULL,
        state          TEXT        NOT NULL,
        cause          TEXT,
        node_count     INTEGER     NOT NULL,
        edge_count     INTEGER     NOT NULL,
        as_of          TIMESTAMPTZ NOT NULL,
        collected_at   TIMESTAMPTZ NOT NULL
    )
    """,
    # One row per slice, not a history. A second row for the same account and region
    # would let a consumer read either one and get a different answer about whether
    # the graph can be trusted, and nothing would say which was current.
    """
    CREATE UNIQUE INDEX uq_graph_coverage__slice
        ON graph_coverage (tenant_id, sub_account_id, region_id)
    """,
    """
    ALTER TABLE graph_coverage
        ADD CONSTRAINT ck_graph_coverage__state_known
        CHECK (state IN ('COMPLETE', 'PARTIAL', 'UNREAD'))
    """,
    f"""
    ALTER TABLE graph_coverage
        ADD CONSTRAINT ck_graph_coverage__cause_known
        CHECK (cause IS NULL OR cause IN ({_quoted(CAUSES)}))
    """,
    # The constraint this table exists for. A slice that is not complete and cannot
    # say why produces a banner saying data is missing that sends nobody anywhere,
    # and a complete slice carrying a cause shows a reader a failure over a graph
    # that is whole. Written as a biconditional so both halves are one rule.
    """
    ALTER TABLE graph_coverage
        ADD CONSTRAINT ck_graph_coverage__cause_iff_not_complete
        CHECK ((state = 'COMPLETE') = (cause IS NULL))
    """,
    # An UNREAD slice has not been read, so any cause naming a failure describes
    # something that did not happen. This is the database half of the same rule
    # `GraphCoverage.__post_init__` states, per constraint 11.
    """
    ALTER TABLE graph_coverage
        ADD CONSTRAINT ck_graph_coverage__unread_is_not_yet_attempted
        CHECK (state <> 'UNREAD' OR cause = 'NotYetAttempted')
    """,
    # A slice nobody has read has nothing in it. A non zero count on an UNREAD row
    # would be a number read from somewhere the row says was never read.
    """
    ALTER TABLE graph_coverage
        ADD CONSTRAINT ck_graph_coverage__unread_is_empty
        CHECK (state <> 'UNREAD' OR (node_count = 0 AND edge_count = 0))
    """,
    """
    ALTER TABLE graph_coverage
        ADD CONSTRAINT ck_graph_coverage__counts_not_negative
        CHECK (node_count >= 0 AND edge_count >= 0)
    """,
    """
    ALTER TABLE graph_coverage
        ADD CONSTRAINT ck_graph_coverage__collected_after_as_of
        CHECK (collected_at >= as_of)
    """,
    # The banner's read: every incomplete slice for a tenant, which is a short list
    # on a healthy estate and the first thing a reader needs on an unhealthy one.
    """
    CREATE INDEX ix_graph_coverage__incomplete
        ON graph_coverage (tenant_id, sub_account_id, region_id)
        WHERE state <> 'COMPLETE'
    """,
)

#: Removed in the reverse of the order they were created, because the edge table
#: references the node table. A revision whose downgrade does not run is a
#: revision nobody can back out of, which is the state constraint 12 is about.
_DOWN: tuple[str, ...] = (
    "graph_coverage",
    "topology_edge",
    "topology_node",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table in _DOWN:
        op.execute(f"DROP TABLE IF EXISTS {table}")
