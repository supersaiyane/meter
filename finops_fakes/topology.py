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

The node and edge kinds, and the cause on an `UNREAD` slice, are proposals.
TASK-P4-001 has not been written, and the plan names neither enumeration. See
`DATA_DICTIONARY.md` for the one decision this estate forces early: the six
error types have no member for a slice nobody attempted.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from finops_fakes import estate_shape as shape
from finops_fakes import fixtures, utilization

COLLECTOR = "topology"

CONFIG = "CONFIG_RELATIONSHIP"
TGW_API = "ec2:DescribeTransitGatewayAttachments"
PEERING_API = "ec2:DescribeVpcPeeringConnections"
ENDPOINT_API = "ec2:DescribeVpcEndpointConnections"
TRUST_API = "iam:GetRole"

#: Node kinds by provider resource type. Proposed, pending TASK-P4-001.
KIND_OF: Mapping[str, str] = {
    "AWS::EC2::VPC": "NETWORK",
    "AWS::EC2::Subnet": "NETWORK",
    "AWS::EC2::SecurityGroup": "NETWORK",
    "AWS::EC2::TransitGateway": "NETWORK",
    "AWS::EC2::TransitGatewayAttachment": "NETWORK",
    "AWS::EC2::VPCPeeringConnection": "NETWORK",
    "AWS::EC2::VPCEndpoint": "NETWORK",
    "AWS::EC2::VPCEndpointService": "NETWORK",
    "AWS::EC2::NatGateway": "NETWORK",
    "AWS::EC2::EIP": "NETWORK",
    "AWS::EC2::Instance": "COMPUTE",
    "AWS::AutoScaling::AutoScalingGroup": "COMPUTE",
    "AWS::EKS::Cluster": "CONTAINER",
    "AWS::ECS::Cluster": "CONTAINER",
    "AWS::RDS::DBInstance": "DATABASE",
    "AWS::MSK::Cluster": "DATABASE",
    "AWS::ElastiCache::CacheCluster": "CACHE",
    "AWS::EC2::Volume": "STORAGE",
    "AWS::EC2::Snapshot": "STORAGE",
    "AWS::ElasticLoadBalancingV2::LoadBalancer": "LOAD_BALANCER",
    "AWS::IAM::Role": "IDENTITY",
    "AWS::Logs::LogGroup": "OBSERVABILITY",
    "AWS::CloudWatch::Alarm": "OBSERVABILITY",
    "Custom::CloudWatch::Metric": "OBSERVABILITY",
}


@dataclass(frozen=True)
class Node:
    node_id: str
    account_id: str
    region_id: str | None
    availability_zone: str | None
    resource_type: str
    name: str
    #: False for a node known only from the far end of an edge.
    interior_known: bool = True


@dataclass(frozen=True)
class Edge:
    from_node_id: str
    to_node_id: str
    edge_kind: str
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
        # Known only from the attachment the platform account owns. Its subnets,
        # its security groups and whatever runs inside it are unknown.
        Node(
            DENIED_VPC,
            shape.DENIED_ACCOUNT,
            shape.REGION_A,
            None,
            "AWS::EC2::VPC",
            f"{shape.DENIED_ACCOUNT}-{shape.REGION_A}",
            interior_known=False,
        ),
    ]
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
            out.append(Edge(n["vpc"], n[f"subnet_{letter}"], "CONTAINS", CONFIG))
        for key in ("sg_app", "sg_db", "sg_self"):
            out.append(Edge(n["vpc"], n[key], "CONTAINS", CONFIG))
        # The database group admits the app group, and the app group admits the
        # database group back for health checks: a two node cycle.
        out.append(Edge(n["sg_db"], n["sg_app"], "REFERENCES", CONFIG))
        out.append(Edge(n["sg_app"], n["sg_db"], "REFERENCES", CONFIG))
        # A group admitting its own members: the one node cycle TASK-P4-007 names.
        out.append(Edge(n["sg_self"], n["sg_self"], "REFERENCES", CONFIG))
        attach = f"{TGW}/attach/{account}/{region}"
        out.append(Edge(TGW, attach, "CONTAINS", TGW_API))
        out.append(Edge(attach, n["vpc"], "ATTACHED_TO", TGW_API))
    denied_attach = f"{TGW}/attach/{shape.DENIED_ACCOUNT}/{shape.REGION_A}"
    out.append(Edge(TGW, denied_attach, "CONTAINS", TGW_API))
    out.append(Edge(denied_attach, DENIED_VPC, "ATTACHED_TO", TGW_API))

    pa, pb = _net("fake-platform-a", shape.REGION_A), _net("fake-platform-a", shape.REGION_B)
    out.append(Edge(pa["vpc"], PEERING, "CONNECTS_VIA", PEERING_API))
    out.append(Edge(PEERING, pb["vpc"], "PEERS_WITH", PEERING_API))
    out.append(Edge(pa["vpc"], ENDPOINT_SERVICE, "CONTAINS", CONFIG))
    out.append(Edge(ENDPOINT, ENDPOINT_SERVICE, "CONNECTS_VIA", ENDPOINT_API))
    out.append(Edge(_net("fake-product-a", shape.REGION_A)["vpc"], ENDPOINT, "CONTAINS", CONFIG))
    out.append(Edge(TRUSTING_ROLE, TRUSTED_ROLE, "TRUSTS", TRUST_API))

    out.append(Edge(EKS_PLATFORM, "amazonec2/fake-platform-a/0001", "CONTAINS", CONFIG))
    out.append(Edge(EKS_PLATFORM, "amazonec2/fake-platform-a/0002", "CONTAINS", CONFIG))
    out.append(Edge(EKS_BATCH, "amazonec2/fake-platform-b/0001", "CONTAINS", CONFIG))

    for s in utilization.SPECS:
        n = _net(s.account_id, s.region_id)
        if s.kind in ("instance", "asg", "asg_eks", "rds", "cache", "msk", "nat", "alb"):
            out.append(Edge(_placement(s), s.resource_id, "CONTAINS", CONFIG))
        if s.kind in ("instance", "asg", "asg_eks", "alb"):
            out.append(Edge(s.resource_id, n["sg_app"], "ATTACHED_TO", CONFIG))
        if s.kind in ("asg_eks",):
            out.append(Edge(s.resource_id, n["sg_self"], "ATTACHED_TO", CONFIG))
        if s.kind in ("rds", "cache", "msk"):
            out.append(Edge(s.resource_id, n["sg_db"], "ATTACHED_TO", CONFIG))
        target = s.config.get("attached_to") or s.config.get("targets")
        if target:
            out.append(
                Edge(
                    s.resource_id,
                    str(target),
                    "ATTACHED_TO" if s.kind == "volume" else "ROUTES_TO",
                    CONFIG,
                )
            )
        replica_of = s.config.get("replica_of")
        if replica_of:
            out.append(Edge(str(replica_of), s.resource_id, "REPLICATES_TO", CONFIG))
    return tuple(out)


def _accounts() -> Mapping[str, str]:
    return {n.node_id: n.account_id for n in nodes()}


def coverage_state(account_id: str, region_id: str) -> tuple[str, str | None]:
    """The state and typed cause of one slice. Every slice has exactly one."""
    if region_id == shape.REFUSING_REGION:
        return "PARTIAL", "NotOptedIn"
    if account_id == shape.DENIED_ACCOUNT:
        return "PARTIAL", "AccessDenied"
    if (account_id, region_id) == ("fake-product-b", shape.REGION_B):
        return "UNREAD", "NotYetAttempted"
    return "COMPLETE", None


def node_rows() -> Iterator[Mapping[str, object]]:
    for n in nodes():
        yield {
            "tenant_id": str(fixtures.TENANT_ID),
            "node_id": n.node_id,
            "sub_account_id": n.account_id,
            "region_id": n.region_id,
            "availability_zone": n.availability_zone,
            "node_kind": KIND_OF[n.resource_type],
            "resource_type": n.resource_type,
            "name": n.name,
            "interior_known": n.interior_known,
            "as_of": fixtures.AS_OF.isoformat(),
            "collected_at": fixtures.COLLECTED_AT.isoformat(),
        }


def edge_rows() -> Iterator[Mapping[str, object]]:
    owner = _accounts()
    for e in edges():
        yield {
            "tenant_id": str(fixtures.TENANT_ID),
            "from_node_id": e.from_node_id,
            "to_node_id": e.to_node_id,
            "edge_kind": e.edge_kind,
            "source": e.source,
            "is_cross_account": owner[e.from_node_id] != owner[e.to_node_id],
            "as_of": fixtures.AS_OF.isoformat(),
            "collected_at": fixtures.COLLECTED_AT.isoformat(),
        }


def coverage_rows() -> Iterator[Mapping[str, object]]:
    """Fifteen rows, one per account and region, including the refused ones."""
    for account in fixtures.ACCOUNT_IDS:
        for region in shape.REGIONS:
            state, cause = coverage_state(account, region)
            yield {
                "tenant_id": str(fixtures.TENANT_ID),
                "sub_account_id": account,
                "region_id": region,
                "state": state,
                "cause": cause,
                "as_of": fixtures.AS_OF.isoformat(),
                "collected_at": fixtures.COLLECTED_AT.isoformat(),
            }
