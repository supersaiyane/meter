"""What is connected to what, and the parts of the estate nobody could read.

The P4 plan's second rule is that the fake estate is incomplete by default, and
this is that estate. Of fifteen account and region slices:

- every slice in `fake-region-c` is `PARTIAL`, because the region refuses
- both readable slices of the denied account are `PARTIAL`, with `AccessDenied`
- one slice, `fake-product-b` in `fake-region-b`, is `UNREAD`: enrolled, and never
  attempted, which TASK-P4-005 says is created at enrolment and not at failure
- the rest are `COMPLETE`

**An edge Meter cannot see is not an absent edge.** The denied account's VPC
still appears, as a node known only from the other end of a Transit Gateway
attachment the platform account owns. Its interior is unknown. A blast radius
walk that reaches it has reached the edge of what is known, and its own
coverage says so.

**The cycle TASK-P4-007 tests for is here**: a security group that references
itself, beside a pair that reference each other.

**Every edge names the API that supplied it**, TASK-P4-004, and cross account is
set on the row rather than computed on read.

The node and edge kinds were proposals when this was written and are now the real
enumerations from `finops_core.domain.topology`, which TASK-P4-001 settled. Two
things the estate had to give up in the move, both recorded in ISS-201: a container
cluster, a cache and a stream have no kind of their own and draw as `OTHER`, and
replication has no edge kind, so a read replica is joined with `ROUTES_TO`, which is
the closest of the seven and not the right word.

The `UNREAD` cause this estate invented, `NotYetAttempted`, became the decision in
ADR-0023: it is a member of `CoverageCause` and not of the error taxonomy, because
nothing failed and a collector cannot raise "I have not tried".

**The denied account's VPC is no longer a node.** It was a node with
`interior_known=False`, and the schema has no such column, because it does not need
one: an edge may point at a node with no row, and that absence is the boundary. The
Transit Gateway attachment still names it, `finops_query.graph` stops there, and the
account's own coverage row says `AccessDenied`.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.topology import (
    CoverageCause,
    CoverageState,
    EdgeKind,
    NodeKind,
    Shortfall,
    SliceRead,
    node_id_for,
)
from finops_core.domain.topology import Edge as DomainEdge
from finops_core.domain.topology import Node as DomainNode
from finops_fakes import estate_shape as shape
from finops_fakes import fixtures, utilization

COLLECTOR = "topology"

CONFIG = "CONFIG_RELATIONSHIP"
TGW_API = "ec2:DescribeTransitGatewayAttachments"
PEERING_API = "ec2:DescribeVpcPeeringConnections"
ENDPOINT_API = "ec2:DescribeVpcEndpointConnections"
#: The four API names are imported from the adapter rather than repeated, because
#: a consumer grouping edges by source would otherwise see two different estates
#: behind one port. `iam:GetRole` was written here first and the adapter calls
#: `iam:ListRoles`, so a screen filtering on the source would have shown no trust
#: edges for exactly one of the two providers.
TRUST_API = "iam:ListRoles"

#: Node kinds by provider resource type, from the real fourteen. Ten of the
#: twenty four types here land on `OTHER`, which is the estate showing the gap
#: ISS-201 records rather than the fake papering over it: a container cluster, a
#: cache, a stream, a transit gateway, a peering connection, an endpoint service,
#: a snapshot, an elastic IP, a log group and an alarm have no kind of their own.
#: `resource_type` travels beside the kind so a screen can still name them.
KIND_OF: Mapping[str, NodeKind] = {
    "AWS::EC2::VPC": NodeKind.VPC,
    "AWS::EC2::Subnet": NodeKind.SUBNET,
    "AWS::EC2::SecurityGroup": NodeKind.SECURITY_GROUP,
    "AWS::EC2::TransitGateway": NodeKind.OTHER,
    "AWS::EC2::TransitGatewayAttachment": NodeKind.TGW_ATTACHMENT,
    "AWS::EC2::VPCPeeringConnection": NodeKind.OTHER,
    "AWS::EC2::VPCEndpoint": NodeKind.VPC_ENDPOINT,
    "AWS::EC2::VPCEndpointService": NodeKind.OTHER,
    "AWS::EC2::NatGateway": NodeKind.NAT_GATEWAY,
    "AWS::EC2::EIP": NodeKind.OTHER,
    "AWS::EC2::Instance": NodeKind.INSTANCE,
    "AWS::AutoScaling::AutoScalingGroup": NodeKind.OTHER,
    "AWS::EKS::Cluster": NodeKind.OTHER,
    "AWS::ECS::Cluster": NodeKind.OTHER,
    "AWS::RDS::DBInstance": NodeKind.DB_INSTANCE,
    "AWS::MSK::Cluster": NodeKind.OTHER,
    "AWS::ElastiCache::CacheCluster": NodeKind.OTHER,
    "AWS::EC2::Volume": NodeKind.VOLUME,
    "AWS::EC2::Snapshot": NodeKind.OTHER,
    "AWS::ElasticLoadBalancingV2::LoadBalancer": NodeKind.LOAD_BALANCER,
    "AWS::IAM::Role": NodeKind.OTHER,
    "AWS::Logs::LogGroup": NodeKind.OTHER,
    "AWS::CloudWatch::Alarm": NodeKind.OTHER,
    "Custom::CloudWatch::Metric": NodeKind.OTHER,
}

#: The types that belong to the account's global slice rather than to a region.
#: The same partition `finops_providers/aws/config_inventory.py` makes, for the
#: same reason: an IAM role belongs to an account and to no region.
GLOBAL_TYPES = frozenset({"AWS::IAM::Role"})


@dataclass(frozen=True)
class Node:
    """One resource. `node_id` here is the provider identifier, not Meter's.

    The stored `node_id` is derived from it by `node_id_for`, which is what lets the
    edges below name both ends by path without looking anything up.
    """

    node_id: str
    account_id: str
    region_id: str | None
    availability_zone: str | None
    resource_type: str
    name: str


@dataclass(frozen=True)
class Edge:
    from_node_id: str
    to_node_id: str
    edge_kind: EdgeKind
    source: str


def _net(account: str, region: str) -> dict[str, str]:
    base = f"amazonvpc/{account}/{region}"
    return {
        "vpc": f"{base}/vpc",
        "subnet_a": f"{base}/subnet-a",
        "subnet_b": f"{base}/subnet-b",
        "subnet_c": f"{base}/subnet-c",
        "sg_app": f"{base}/sg-app",
        "sg_db": f"{base}/sg-db",
        "sg_self": f"{base}/sg-cluster",
    }


#: Which networks exist. Platform accounts carry a recovery copy in region b.
_NETWORKS: tuple[tuple[str, str], ...] = (
    ("fake-platform-a", shape.REGION_A),
    ("fake-platform-a", shape.REGION_B),
    ("fake-platform-b", shape.REGION_A),
    ("fake-platform-b", shape.REGION_B),
    ("fake-product-a", shape.REGION_A),
    ("fake-product-b", shape.REGION_A),
)

TGW = f"amazonvpc/fake-platform-a/{shape.REGION_A}/tgw"
DENIED_VPC = f"amazonvpc/{shape.DENIED_ACCOUNT}/{shape.REGION_A}/vpc"
PEERING = f"amazonvpc/fake-platform-a/{shape.REGION_A}/pcx-dr"
ENDPOINT_SERVICE = f"amazonvpc/fake-platform-a/{shape.REGION_A}/vpce-svc-payments"
ENDPOINT = f"amazonvpc/fake-product-a/{shape.REGION_A}/vpce-payments"
TRUSTING_ROLE = "iam/fake-platform-b/role/batch-deployer"
TRUSTED_ROLE = "iam/fake-platform-a/role/platform-ci"
EKS_PLATFORM = "amazoneks/fake-platform-a/platform-eks"
EKS_BATCH = "amazoneks/fake-platform-b/batch-eks"
ECS_PRODUCT = "amazonecs/fake-product-a/product-ecs"


def nodes() -> tuple[Node, ...]:
    out: list[Node] = []
    for account, region in _NETWORKS:
        n = _net(account, region)
        out.append(Node(n["vpc"], account, region, None, "AWS::EC2::VPC", f"{account}-{region}"))
        for letter in ("a", "b", "c"):
            out.append(
                Node(
                    n[f"subnet_{letter}"],
                    account,
                    region,
                    shape.zone(region, letter),
                    "AWS::EC2::Subnet",
                    f"private-{letter}",
                )
            )
        for key, name in (("sg_app", "app"), ("sg_db", "database"), ("sg_self", "cluster")):
            out.append(Node(n[key], account, region, None, "AWS::EC2::SecurityGroup", name))
    out += [
        Node(TGW, "fake-platform-a", shape.REGION_A, None, "AWS::EC2::TransitGateway", "core-tgw"),
        Node(
            PEERING,
            "fake-platform-a",
            shape.REGION_A,
            None,
            "AWS::EC2::VPCPeeringConnection",
            "dr-peering",
        ),
        Node(
            ENDPOINT_SERVICE,
            "fake-platform-a",
            shape.REGION_A,
            None,
            "AWS::EC2::VPCEndpointService",
            "payments-privatelink",
        ),
        Node(
            ENDPOINT,
            "fake-product-a",
            shape.REGION_A,
            None,
            "AWS::EC2::VPCEndpoint",
            "payments-endpoint",
        ),
        Node(TRUSTED_ROLE, "fake-platform-a", None, None, "AWS::IAM::Role", "platform-ci"),
        Node(TRUSTING_ROLE, "fake-platform-b", None, None, "AWS::IAM::Role", "batch-deployer"),
        Node(
            EKS_PLATFORM,
            "fake-platform-a",
            shape.REGION_A,
            None,
            "AWS::EKS::Cluster",
            "platform-eks",
        ),
        Node(EKS_BATCH, "fake-platform-b", shape.REGION_A, None, "AWS::EKS::Cluster", "batch-eks"),
        Node(
            ECS_PRODUCT, "fake-product-a", shape.REGION_A, None, "AWS::ECS::Cluster", "product-ecs"
        ),
    ]
    # `DENIED_VPC` is deliberately not in this list. It is known only from the far
    # end of the attachment the platform account owns, and the schema expresses that
    # as an edge whose target has no node row rather than as a flag on a node. A walk
    # that reaches it has reached the edge of what is known, and the account's own
    # coverage row says AccessDenied.
    for account, region in _NETWORKS:
        out.append(
            Node(
                f"{TGW}/attach/{account}/{region}",
                "fake-platform-a",
                shape.REGION_A,
                None,
                "AWS::EC2::TransitGatewayAttachment",
                f"attach-{account}-{region}",
            )
        )
    out.append(
        Node(
            f"{TGW}/attach/{shape.DENIED_ACCOUNT}/{shape.REGION_A}",
            "fake-platform-a",
            shape.REGION_A,
            None,
            "AWS::EC2::TransitGatewayAttachment",
            f"attach-{shape.DENIED_ACCOUNT}",
        )
    )
    for s in utilization.SPECS:
        out.append(Node(s.resource_id, s.account_id, s.region_id, s.zone, s.resource_type, s.name))
    return tuple(out)


def _placement(s: utilization.Spec) -> str:
    n = _net(s.account_id, s.region_id)
    letter = (s.zone or "x-a")[-1]
    return n.get(f"subnet_{letter}", n["subnet_a"])


def edges() -> tuple[Edge, ...]:
    out: list[Edge] = []
    for account, region in _NETWORKS:
        n = _net(account, region)
        for letter in ("a", "b", "c"):
            out.append(Edge(n["vpc"], n[f"subnet_{letter}"], EdgeKind.CONTAINS, CONFIG))
        for key in ("sg_app", "sg_db", "sg_self"):
            out.append(Edge(n["vpc"], n[key], EdgeKind.CONTAINS, CONFIG))
        # The database group admits the app group, and the app group admits the
        # database group back for health checks: a two node cycle.
        out.append(Edge(n["sg_db"], n["sg_app"], EdgeKind.PERMITS, CONFIG))
        out.append(Edge(n["sg_app"], n["sg_db"], EdgeKind.PERMITS, CONFIG))
        # A group admitting its own members: the one node cycle TASK-P4-007 names.
        out.append(Edge(n["sg_self"], n["sg_self"], EdgeKind.PERMITS, CONFIG))
        attach = f"{TGW}/attach/{account}/{region}"
        out.append(Edge(TGW, attach, EdgeKind.CONTAINS, TGW_API))
        out.append(Edge(attach, n["vpc"], EdgeKind.ATTACHED_TO, TGW_API))
    denied_attach = f"{TGW}/attach/{shape.DENIED_ACCOUNT}/{shape.REGION_A}"
    out.append(Edge(TGW, denied_attach, EdgeKind.CONTAINS, TGW_API))
    out.append(Edge(denied_attach, DENIED_VPC, EdgeKind.ATTACHED_TO, TGW_API))

    pa, pb = _net("fake-platform-a", shape.REGION_A), _net("fake-platform-a", shape.REGION_B)
    out.append(Edge(pa["vpc"], PEERING, EdgeKind.ATTACHED_TO, PEERING_API))
    out.append(Edge(PEERING, pb["vpc"], EdgeKind.PEERS_WITH, PEERING_API))
    out.append(Edge(pa["vpc"], ENDPOINT_SERVICE, EdgeKind.CONTAINS, CONFIG))
    out.append(Edge(ENDPOINT, ENDPOINT_SERVICE, EdgeKind.ROUTES_TO, ENDPOINT_API))
    out.append(
        Edge(_net("fake-product-a", shape.REGION_A)["vpc"], ENDPOINT, EdgeKind.CONTAINS, CONFIG)
    )
    out.append(Edge(TRUSTING_ROLE, TRUSTED_ROLE, EdgeKind.TRUSTS, TRUST_API))

    out.append(Edge(EKS_PLATFORM, "amazonec2/fake-platform-a/0001", EdgeKind.CONTAINS, CONFIG))
    out.append(Edge(EKS_PLATFORM, "amazonec2/fake-platform-a/0002", EdgeKind.CONTAINS, CONFIG))
    out.append(Edge(EKS_BATCH, "amazonec2/fake-platform-b/0001", EdgeKind.CONTAINS, CONFIG))

    for s in utilization.SPECS:
        n = _net(s.account_id, s.region_id)
        if s.kind in ("instance", "asg", "asg_eks", "rds", "cache", "msk", "nat", "alb"):
            out.append(Edge(_placement(s), s.resource_id, EdgeKind.CONTAINS, CONFIG))
        if s.kind in ("instance", "asg", "asg_eks", "alb"):
            out.append(Edge(s.resource_id, n["sg_app"], EdgeKind.ATTACHED_TO, CONFIG))
        if s.kind in ("asg_eks",):
            out.append(Edge(s.resource_id, n["sg_self"], EdgeKind.ATTACHED_TO, CONFIG))
        if s.kind in ("rds", "cache", "msk"):
            out.append(Edge(s.resource_id, n["sg_db"], EdgeKind.ATTACHED_TO, CONFIG))
        target = s.config.get("attached_to") or s.config.get("targets")
        if target:
            # A volume is attached to its instance; a load balancer targets what it
            # sends traffic to, which is the kind the domain has for exactly this.
            out.append(
                Edge(
                    s.resource_id,
                    str(target),
                    EdgeKind.ATTACHED_TO if s.kind == "volume" else EdgeKind.TARGETS,
                    CONFIG,
                )
            )
        replica_of = s.config.get("replica_of")
        if replica_of:
            # Replication has no kind among the seven. ROUTES_TO is where a read
            # goes, which is the closest and is not the right word. ISS-201.
            out.append(Edge(str(replica_of), s.resource_id, EdgeKind.ROUTES_TO, CONFIG))
    return tuple(out)


def _accounts() -> Mapping[str, str]:
    """Which account owns each end of an edge, boundary nodes included.

    `DENIED_VPC` has no node row and still has an owner, which is what makes the
    attachment edge cross account. Deriving it from the node list alone would have
    made the one edge this estate exists to test look like a local one.
    """
    owners = {n.node_id: n.account_id for n in nodes()}
    owners[DENIED_VPC] = shape.DENIED_ACCOUNT
    return owners


def _slices() -> Mapping[str, tuple[str, str | None]]:
    """The account and region each node was read in, for an edge's own slice."""
    return {n.node_id: (n.account_id, n.region_id) for n in nodes()}


def coverage_state(
    account_id: str, region_id: str | None
) -> tuple[CoverageState, CoverageCause | None]:
    """The state and typed cause of one slice. Every slice has exactly one.

    A region of None is the account's global slice, which holds the IAM roles and
    the TRUSTS edges between them. It is COMPLETE everywhere except in the denied
    account, because a refused credential refuses the whole account and not one
    region of it.
    """
    if region_id == shape.REFUSING_REGION:
        return CoverageState.PARTIAL, CoverageCause.NOT_OPTED_IN
    if account_id == shape.DENIED_ACCOUNT:
        return CoverageState.PARTIAL, CoverageCause.ACCESS_DENIED
    if (account_id, region_id) == ("fake-product-b", shape.REGION_B):
        return CoverageState.UNREAD, CoverageCause.NOT_YET_ATTEMPTED
    return CoverageState.COMPLETE, None


def stored_node_id(provider_id: str) -> str:
    """Meter's identifier for a node, derived the one way production derives it.

    Through `node_id_for` rather than reinvented here, because a seeded graph whose
    identifiers do not match the ones a collector would compute is a graph that looks
    right and doubles the first time a collector runs against the same estate.
    """
    return str(node_id_for(tenant_id=fixtures.TENANT_ID, provider_id=provider_id))


def slices() -> tuple[tuple[str, str | None], ...]:
    """Every account and region this estate is expected to be able to read.

    The regions, plus one global slice per account. The denominator TASK-P4-005 needs
    to write an UNREAD row at enrolment instead of at first failure.
    """
    return tuple(
        (account, region) for account in fixtures.ACCOUNT_IDS for region in (*shape.REGIONS, None)
    )


def node_rows() -> Iterator[Mapping[str, object]]:
    for n in nodes():
        yield {
            "tenant_id": str(fixtures.TENANT_ID),
            "node_id": stored_node_id(n.node_id),
            "provider_id": n.node_id,
            "sub_account_id": n.account_id,
            "region_id": None if n.resource_type in GLOBAL_TYPES else n.region_id,
            "availability_zone": n.availability_zone,
            "node_kind": KIND_OF[n.resource_type].value,
            "resource_type": n.resource_type,
            "name": n.name,
            "as_of": fixtures.AS_OF.isoformat(),
            "collected_at": fixtures.COLLECTED_AT.isoformat(),
        }


def edge_rows() -> Iterator[Mapping[str, object]]:
    """Every edge, carrying the slice of its origin rather than of the pair.

    A cross account edge's other end is in another slice, which is what
    `is_cross_account` is for. The columns here are the origin's, so the retraction
    that removes a withdrawn edge can be scoped without joining back to a node row
    the same run may already have removed.
    """
    owner = _accounts()
    where = _slices()
    for e in edges():
        account, region = where[e.from_node_id]
        yield {
            "tenant_id": str(fixtures.TENANT_ID),
            "from_node_id": stored_node_id(e.from_node_id),
            "to_node_id": stored_node_id(e.to_node_id),
            "edge_kind": e.edge_kind.value,
            "source": e.source,
            "is_cross_account": owner[e.from_node_id] != owner[e.to_node_id],
            "sub_account_id": account,
            "region_id": region,
            "as_of": fixtures.AS_OF.isoformat(),
            "collected_at": fixtures.COLLECTED_AT.isoformat(),
        }


def _per_slice(rows: Iterator[Mapping[str, object]]) -> dict[tuple[str, str | None], int]:
    """How many rows fell in each account and region, for the coverage counts."""
    counted: dict[tuple[str, str | None], int] = {}
    for row in rows:
        region = row["region_id"]
        key = (str(row["sub_account_id"]), None if region is None else str(region))
        counted[key] = counted.get(key, 0) + 1
    return counted


def coverage_rows() -> Iterator[Mapping[str, object]]:
    """One row per slice, twenty of them, including the refused and the unread.

    The counts are what they are rather than what the state implies: a COMPLETE
    slice with nothing in it is an account that genuinely has nothing there, and
    telling that apart from an unread one without a second query is the reason the
    counts are stored at all.
    """
    node_count = _per_slice(node_rows())
    edge_count = _per_slice(edge_rows())

    for account, region in slices():
        state, cause = coverage_state(account, region)
        unread = state is CoverageState.UNREAD
        yield {
            "tenant_id": str(fixtures.TENANT_ID),
            "sub_account_id": account,
            "region_id": region,
            "state": state.value,
            "cause": None if cause is None else cause.value,
            # An unread slice has nothing in it, which the check constraint also says.
            "node_count": 0 if unread else node_count.get((account, region), 0),
            "edge_count": 0 if unread else edge_count.get((account, region), 0),
            "as_of": fixtures.AS_OF.isoformat(),
            "collected_at": fixtures.COLLECTED_AT.isoformat(),
        }


# --- the same estate, behind the TopologySource port -------------------------
#
# The rows above are for the seeder. This is for a collector, and it is here rather
# than in a module of its own so the two views of one estate cannot drift: a seeded
# graph and a collected graph that disagree would look like a bug in the collector.
#
# **The shortfalls are why this is not a trivial adapter.** The estate is
# deliberately incomplete, and a fake that returned nodes with no shortfalls would
# let a consumer pass the contract while treating a refused region as an empty one,
# which is the single failure section 6 of the P4 specification exists to prevent.

#: The API name a shortfall from the aggregator carries, matching the one the AWS
#: adapter uses. The contract asserts both, because a consumer grouping shortfalls by
#: source would otherwise see two different estates behind one port.
AGGREGATOR = "config:SelectAggregateResourceConfig"


def accounts_by_node_id() -> Mapping[str, str]:
    """Which account owns each end of an edge, boundary nodes included."""
    return _accounts()


def region_of(node: Node) -> str | None:
    """Which slice a node belongs to, with a global type in the global one."""
    return None if node.resource_type in GLOBAL_TYPES else node.region_id


def shortfalls_for(account_id: str, region: str | None) -> tuple[Shortfall, ...]:
    """What one slice could not read, from the estate's own coverage decision.

    Derived from `coverage_state` rather than written out again, so the seeded rows
    and a live read of the fake cannot disagree about which slices are whole.

    An `UNREAD` slice yields no shortfall, because a read happened: the slice is no
    longer unattempted and its emptiness is the complete answer. `UNREAD` is written
    at enrolment and is a statement about the absence of a read, which a read cannot
    make about itself.
    """
    state, cause = coverage_state(account_id, region)
    if state is CoverageState.COMPLETE or cause is None:
        return ()
    if cause is CoverageCause.NOT_YET_ATTEMPTED:
        return ()
    return (
        Shortfall(
            source=AGGREGATOR,
            cause=cause,
            detail=f"the fake estate refuses {account_id} in {region or 'the global slice'}",
        ),
    )


def _domain_node(node: Node, account: AccountKey) -> DomainNode:
    return DomainNode(
        node_id=node_id_for(tenant_id=fixtures.TENANT_ID, provider_id=node.node_id),
        account_key=account,
        provider_id=node.node_id,
        node_kind=KIND_OF[node.resource_type],
        resource_type=node.resource_type,
        region_id=region_of(node),
        availability_zone=node.availability_zone,
        name=node.name,
        tags={"finops:module": "fixture"},
        as_of=fixtures.AS_OF,
        collected_at=fixtures.COLLECTED_AT,
    )


def _domain_edge(edge: Edge, owner: Mapping[str, str]) -> DomainEdge:
    return DomainEdge(
        from_node_id=node_id_for(tenant_id=fixtures.TENANT_ID, provider_id=edge.from_node_id),
        to_node_id=node_id_for(tenant_id=fixtures.TENANT_ID, provider_id=edge.to_node_id),
        edge_kind=edge.edge_kind,
        is_cross_account=owner[edge.from_node_id] != owner[edge.to_node_id],
        source=edge.source,
        as_of=fixtures.AS_OF,
        collected_at=fixtures.COLLECTED_AT,
    )


class FakeTopologySource:
    """The generated estate behind the `TopologySource` port.

    Holds no state. Every call recomputes from the functions above, which is what
    keeps a test that reads twice from seeing two different estates.
    """

    @property
    def enrolled_slices(self) -> tuple[tuple[AccountKey, str | None], ...]:
        """Every slice the estate is expected to read, the refusing ones included.

        The denominator, and it includes the slices that refuse. A source reporting
        only the slices it could read would make the set of accounts inferable from
        the set of successes, which is the circular definition that makes an unread
        region indistinguishable from one that does not exist.
        """
        return tuple(
            (AccountKey(provider=Provider.AWS, account_id=account), region)
            for account, region in slices()
        )

    def read_slice(self, account: AccountKey, region: str | None) -> SliceRead:
        """One account and one region, with what could not be read named."""
        shortfalls = shortfalls_for(account.account_id, region)
        if shortfalls:
            # A refusing slice yields nothing, which is honest and is not the same as
            # yielding nothing because there is nothing there. The shortfall is what
            # tells the two apart, and it is the whole point of the port's shape.
            return SliceRead(
                account_key=account,
                region_id=region,
                nodes=(),
                edges=(),
                shortfalls=shortfalls,
            )

        mine = {
            node.node_id
            for node in nodes()
            if node.account_id == account.account_id and region_of(node) == region
        }
        owner = accounts_by_node_id()
        return SliceRead(
            account_key=account,
            region_id=region,
            nodes=tuple(_domain_node(node, account) for node in nodes() if node.node_id in mine),
            # Only edges whose origin is in this slice, the same rule the AWS adapter
            # follows: an edge out of a node this slice never read is a fact this
            # slice cannot vouch for, and it belongs to the origin's own slice.
            edges=tuple(_domain_edge(edge, owner) for edge in edges() if edge.from_node_id in mine),
            shortfalls=(),
        )
