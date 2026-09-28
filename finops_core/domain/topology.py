"""What is connected to what, and how much of the answer Meter actually has.

Two entities and one admission. `Node` and `Edge` are the graph. `GraphCoverage`
is the admission, and it is the reason this module is not simply a pair of
dataclasses.

**An edge Meter cannot see is not an absent edge.** That sentence is section 6
of `docs/specs/2026-09-20-p4-inventory-and-topology-design.md` and it is the
whole design. A cost graph that renders is indistinguishable from a cost graph
that is right: both draw boxes and lines, and the wrong one answers "what talks
to this database" with a shorter list rather than with an error. So every read
of the graph carries the coverage of the slices it crossed, and a caller that
needs completeness has to look at it.

**Coverage is per account and per region, not per run.** A run that read eleven
regions and was refused in the twelfth produced a graph that is right about
eleven twelfths of the estate. One row per run would flatten that into a single
PARTIAL and lose which twelfth, which is the difference between a banner saying
"some data is missing" and a banner naming eu-north-1.

**`CoverageCause` is the taxonomy plus one member.** `finops_core.errors` holds
six causes and ISS-015 explains why there is no seventh and no generic one. An
`UNREAD` slice has no cause among the six, because nothing failed: no read has
been attempted. `NOT_YET_ATTEMPTED` is that state, and it is here rather than in
the taxonomy because it is not a collection failure and `CollectionError` is the
set of collection failures. `tests/core/test_topology.py` asserts every cause in
the taxonomy is a member here, so a seventh cause added there fails the build
until this enum and its check constraint have seen it. See ADR-0023.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID, uuid5

from finops_core.domain.account import AccountKey
from finops_core.domain.fact import Fact


class NodeKind(StrEnum):
    """The kinds of thing the graph can hold, as a closed set.

    Closed for the reason `OrgNodeType` is closed: an open set grows a member
    the first time a provider says something unfamiliar, and the renderer then
    meets a shape it has never drawn. `OTHER` is the deliberate exception and it
    is not a catch all by another name: a resource type the adapter does not
    recognise lands here *and* raises `SchemaDrift`, so the node is still in the
    graph, still connected, and loud.
    """

    VPC = "VPC"
    SUBNET = "SUBNET"
    INSTANCE = "INSTANCE"
    ENI = "ENI"
    SECURITY_GROUP = "SECURITY_GROUP"
    TARGET_GROUP = "TARGET_GROUP"
    LOAD_BALANCER = "LOAD_BALANCER"
    NAT_GATEWAY = "NAT_GATEWAY"
    TGW_ATTACHMENT = "TGW_ATTACHMENT"
    VPC_ENDPOINT = "VPC_ENDPOINT"
    VOLUME = "VOLUME"
    DB_INSTANCE = "DB_INSTANCE"
    FUNCTION = "FUNCTION"
    OTHER = "OTHER"


class EdgeKind(StrEnum):
    """How two nodes are related, in the direction the relationship runs.

    Each of these reads as a sentence from the `from` node to the `to` node: a
    VPC CONTAINS a subnet, an instance is ATTACHED_TO a volume, a subnet
    ROUTES_TO a NAT gateway, a target group TARGETS an instance, a security
    group PERMITS another, a VPC PEERS_WITH another, a role TRUSTS a principal.

    `PEERS_WITH` is the one that looks symmetric and is not. A peering
    connection has a requester and an accepter, and only one of the two sides
    may be readable, so storing it once in the direction it was read keeps the
    asymmetry visible instead of implying both halves were seen.
    """

    CONTAINS = "CONTAINS"
    ATTACHED_TO = "ATTACHED_TO"
    ROUTES_TO = "ROUTES_TO"
    TARGETS = "TARGETS"
    PERMITS = "PERMITS"
    PEERS_WITH = "PEERS_WITH"
    TRUSTS = "TRUSTS"


class CoverageState(StrEnum):
    """How much of one account's one region the graph is built from.

    `UNREAD` is not a synonym for `PARTIAL`. Partial means a read happened and
    fell short, and the cause says how. Unread means no read has been attempted,
    which is the honest state of a region from the moment an account is enrolled
    until the first collector run reaches it. Collapsing the two would make a
    newly enrolled estate look broken, and would make a broken estate look new.
    """

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNREAD = "UNREAD"


class CoverageCause(StrEnum):
    """Why a slice is not COMPLETE. The taxonomy's seven, plus never attempted.

    The values are the `CollectionError` subclass names verbatim, because a
    caught error's `cause` attribute is written straight into this column and a
    translation table between the two would be a second place for the names
    to live. `NOT_YET_ATTEMPTED` is the only member with no counterpart in
    `finops_core.errors`, and the module docstring says why.

    `MISCONFIGURED` arrived with ADR-0026 on 2026-09-28. Two tests refused the
    addition until it was made here, `test_every_taxonomy_cause_is_a_coverage_cause`
    and `test_the_coverage_causes_in_the_schema_match_the_domain_enum`, which is
    what they are for: a cause a collector can raise and a coverage row cannot
    record is a slice that fails with no reason attached to it.
    """

    ACCESS_DENIED = "AccessDenied"
    THROTTLED = "Throttled"
    NOT_OPTED_IN = "NotOptedIn"
    NO_DATA = "NoData"
    UNREACHABLE = "Unreachable"
    SCHEMA_DRIFT = "SchemaDrift"
    MISCONFIGURED = "Misconfigured"
    NOT_YET_ATTEMPTED = "NotYetAttempted"


#: The namespace `node_id_for` derives identifiers in. A fixed UUID rather than a
#: generated one, because the whole point is that two runs, two adapters and the
#: demo seeder all arrive at the same identifier for the same resource.
NODE_NAMESPACE = UUID("6f2b3a1e-9c4d-5f8a-b7e6-1d0c9a8b7f6e")


def node_id_for(*, tenant_id: UUID, provider_id: str) -> UUID:
    """The identity of a node, derived rather than allocated.

    `topology_node.node_id` is Meter's own identifier and `provider_id` is the
    ARN. Deriving the first from the second is what lets an edge be written
    without first reading back the row it points at: the collector holds the ARN
    of both ends of a Config relationship and needs no round trip to turn either
    into a key.

    It lives here for the reason `source_fingerprint` does. Both adapters and the
    demo seeder must produce the same identifier for the same resource, and two
    implementations of an identity is how a duplicate is created. A node written
    under one identifier and its edges written under another is worse than a
    duplicate: the graph is whole, every query returns, and the resource appears
    twice with half its edges each time.

    `uuid5` and not `hash()`. The builtin is salted per process, so an identifier
    from it is stable within one run and different in the next, and the symptom is
    a table that doubles every time the worker restarts.

    Scoped by tenant, so two tenants holding the same ARN, which happens whenever
    a demo tenant is seeded beside a real one, do not collide on one row.
    """
    return uuid5(NODE_NAMESPACE, f"{tenant_id}\x1f{provider_id}")


#: Where an edge came from, as the name of the API call that produced it, never
#: as a free text note. `topology_edge.source` is what a reader uses to decide
#: whether a missing edge means the resource is unconnected or means the one API
#: that would have shown the connection was refused, and "config" does not
#: answer that while "CONFIG_RELATIONSHIP" does. The adapters own the values;
#: this is not an enum because a closed set here would have to grow in
#: `finops_core` every time an adapter learned one more call, which is exactly
#: the coupling constraint 1 forbids.
SOURCE_MAX_LENGTH = 64


@dataclass(frozen=True, kw_only=True)
class Node(Fact):
    """One resource, as a vertex. Identified by the provider's own identifier."""

    #: Meter's identifier for the vertex, from `node_id_for`, so it is stable
    #: across runs for the same resource without a round trip to look it up.
    node_id: UUID
    account_key: AccountKey
    #: The provider's identifier, an ARN on AWS. Unique within a tenant, which is
    #: what makes a second run of the same resource an update rather than a
    #: second vertex with the same edges hanging off it.
    provider_id: str
    node_kind: NodeKind
    #: The provider's own word for the type, kept beside `node_kind` because the
    #: kind is lossy by design: six AWS types map to `OTHER` and a reader looking
    #: at an unfamiliar box needs to know which one it was.
    resource_type: str
    #: None means the resource is global rather than regional: an IAM role belongs
    #: to an account and to no region. Distinct from a region Meter could not read,
    #: which is a PARTIAL slice in `GraphCoverage`. ISS-196 made the same change to
    #: `QuotaUsage` for the same reason, and the workaround both times would have
    #: been a magic region string that shows on a screen as a region nobody has.
    region_id: str | None
    #: None means the resource is regional rather than zonal: a VPC, a security
    #: group, a target group and a load balancer have no single zone, and
    #: `availability_zone` is null for every one of them. It does **not** mean
    #: the zone is unknown. A zone Meter could not read is a PARTIAL slice in
    #: `GraphCoverage`, recorded there and not as a null here, because a null
    #: standing for both would make "which zone is this in" unanswerable for
    #: every resource that legitimately has none.
    availability_zone: str | None
    name: str | None
    tags: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", MappingProxyType(dict(self.tags)))


@dataclass(frozen=True, kw_only=True)
class Edge(Fact):
    """One directed relationship between two nodes.

    Directed, and the direction is part of the identity: `(a, b, CONTAINS)` and
    `(b, a, CONTAINS)` are different edges and both can exist without
    contradiction, because a walk outward from `a` follows the first and a walk
    outward from `b` follows the second. A store that treated them as one would
    answer "what is inside this VPC" with its parent.
    """

    from_node_id: UUID
    to_node_id: UUID
    edge_kind: EdgeKind
    #: Materialised rather than derived by joining both nodes, because the whole
    #: point of the blast radius read is to find the cross account edges, and a
    #: predicate that needs two joins to evaluate is a predicate that gets left
    #: out of the query that most needs it. Set at write time by the collector,
    #: which has both accounts in hand.
    is_cross_account: bool
    #: The API call this edge was read from. See `SOURCE_MAX_LENGTH`.
    source: str

    def __post_init__(self) -> None:
        if self.from_node_id == self.to_node_id and self.edge_kind is not EdgeKind.PERMITS:
            raise ValueError(
                f"A {self.edge_kind.value} edge from a node to itself is not a fact about "
                "the estate, it is a traversal that never terminates. Only PERMITS may be "
                "reflexive, because a security group referring to itself is the ordinary "
                "way an estate lets a tier talk to itself."
            )
        if not self.source:
            raise ValueError(
                "An edge must name the API call it came from. Without it, a missing edge "
                "cannot be told apart from an API that was refused."
            )


#: The order a cause wins in when one slice fell short in several ways at once.
#: `graph_coverage` has one cause column and a reader needs the one that tells them
#: what to do, so an AccessDenied somebody can fix beats a Throttled that resolves
#: itself. `NoData` is last because it is the one cause that is not a fault.
CAUSE_PRECEDENCE: tuple[CoverageCause, ...] = (
    CoverageCause.ACCESS_DENIED,
    CoverageCause.NOT_OPTED_IN,
    CoverageCause.SCHEMA_DRIFT,
    CoverageCause.UNREACHABLE,
    CoverageCause.THROTTLED,
    CoverageCause.NOT_YET_ATTEMPTED,
    CoverageCause.NO_DATA,
)


@dataclass(frozen=True, kw_only=True)
class Shortfall:
    """One API that did not answer, and what that costs the slice.

    Not a `Fact`. It is a record of our own failure rather than something that was
    true at a source, which is the distinction `IngestRun` makes for the same
    reason: giving it an `as_of` would invite the question of what the value means.

    `source` is the API call, not a description, and it matches the `source` an
    `Edge` from that call would have carried. That pairing is the point: a reader
    seeing no PEERS_WITH edges in a region can look at the shortfalls and find
    `ec2:DescribeVpcPeeringConnections` refused, instead of concluding the estate
    has no peering.
    """

    source: str
    cause: CoverageCause
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError(
                "A shortfall must name the API that fell short, or it says only that "
                "something is missing, which is what the graph already said."
            )


@dataclass(frozen=True, kw_only=True)
class SliceRead:
    """Everything one account and region yielded, and everything it did not.

    The return type of a topology read, and the reason it is one type rather than
    two calls. An adapter that returned nodes and edges, with the shortfalls
    available from a second method, is an adapter whose caller writes the graph and
    forgets the second method, and the graph then renders complete.

    A read where every API refused is still a `SliceRead`, with no nodes, no edges
    and a shortfall per API. That is deliberately not an exception: the run has to
    continue to the next account, which is constraint 5, and the caller has to
    write a PARTIAL coverage row rather than nothing at all.
    """

    account_key: AccountKey
    region_id: str | None
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    shortfalls: tuple[Shortfall, ...]
    #: Provider type names this source could not map to a `NodeKind`. The nodes are
    #: present, as `OTHER`, with their `resource_type` intact, so nothing is missing
    #: and this is **not** a shortfall and does not make the slice PARTIAL.
    #:
    #: That distinction was made the other way first and the contract suite caught
    #: it. An estate with a fleet of EKS clusters has no kind for them, so every
    #: slice would have been PARTIAL on every run forever, and a banner that says
    #: data is missing every time is a banner nobody reads by the second week. A
    #: shortfall means a fact Meter could not see. This means a fact it can see and
    #: cannot name, which is ISS-201 and belongs in a run's detail rather than in a
    #: coverage row.
    unmapped: tuple[str, ...] = ()

    @property
    def is_whole(self) -> bool:
        """True only when every API this read depends on answered."""
        return not self.shortfalls

    @property
    def cause(self) -> CoverageCause | None:
        """The one cause the coverage row carries, or None for a whole read."""
        return dominant_cause(self.shortfalls)

    @property
    def state(self) -> CoverageState:
        """COMPLETE or PARTIAL. Never UNREAD: this read was attempted."""
        return CoverageState.COMPLETE if self.is_whole else CoverageState.PARTIAL


def dominant_cause(shortfalls: tuple[Shortfall, ...]) -> CoverageCause | None:
    """The cause a slice's coverage row carries when several APIs fell short.

    None for no shortfalls at all, which is the COMPLETE case.

    Deliberately not the first shortfall in call order. That would make the cause a
    function of which API the adapter happens to call first, so reordering two calls
    for performance would change what a screen tells somebody to fix.
    """
    if not shortfalls:
        return None
    present = {shortfall.cause for shortfall in shortfalls}
    for candidate in CAUSE_PRECEDENCE:
        if candidate in present:
            return candidate
    # Unreachable while `CAUSE_PRECEDENCE` covers the enum, which a test asserts.
    # Raised rather than returning one arbitrarily, because a cause chosen at random
    # is a screen telling somebody to fix something that is not broken.
    raise ValueError(f"No precedence for any of {sorted(cause.value for cause in present)}")


@dataclass(frozen=True, kw_only=True)
class GraphCoverage(Fact):
    """How much of one account's one region the graph was built from.

    The counts are here so a reader can tell an empty region from an unread one
    without a second query. A COMPLETE slice with zero nodes is an account that
    genuinely has nothing in eu-north-1, which is common and is not a fault.
    """

    account_key: AccountKey
    #: None is the account's global slice, which is where a TRUSTS edge between two
    #: IAM roles is recorded. One row per account, like every regional slice.
    region_id: str | None
    state: CoverageState
    #: None only when the state is COMPLETE. The database says the same thing as
    #: a check constraint, because constraint 11 in CLAUDE.md: if this method is
    #: the only thing preventing a PARTIAL row with no cause, the row will
    #: eventually exist, written by something that did not come through here.
    cause: CoverageCause | None
    node_count: int
    edge_count: int

    def __post_init__(self) -> None:
        # Branched on the cause rather than on the state, so the type checker can
        # see that every message below has a cause to name.
        if self.cause is None:
            if self.state is not CoverageState.COMPLETE:
                raise ValueError(
                    f"A {self.state.value} slice must carry a typed cause. A banner that "
                    "says data is missing and cannot say why sends nobody anywhere."
                )
        elif self.state is CoverageState.COMPLETE:
            raise ValueError(
                f"A COMPLETE slice has nothing to explain, and {self.cause.value} on one "
                "would show a reader a failure over a graph that is whole."
            )
        elif (
            self.state is CoverageState.UNREAD and self.cause is not CoverageCause.NOT_YET_ATTEMPTED
        ):
            raise ValueError(
                f"An UNREAD slice has not been read, so {self.cause.value} describes a "
                "failure that did not happen. Use NOT_YET_ATTEMPTED, or say PARTIAL."
            )
        if self.node_count < 0 or self.edge_count < 0:
            raise ValueError("A count of what was read is never negative.")

    @property
    def is_whole(self) -> bool:
        """True only for a slice the graph can be trusted to be complete over."""
        return self.state is CoverageState.COMPLETE
