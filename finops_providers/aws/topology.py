"""The edges AWS Config does not give you, from the four APIs that do.

**Nothing in this file has ever made a call.** ISS-202. Every response shape is
read from documentation and the tests answer from a literal.

**Why this file exists at all, since Config supplies most relationships.** The long
tail is where the cross account edges are. A Transit Gateway attachment in the
payer's account points at a VPC the payer does not own, a peering connection names
an account on the other side, a PrivateLink endpoint and its service are routinely
in different accounts, and a role's trust policy names a principal somewhere else
entirely. Config's relationship records stop at the account boundary. A blast radius
score built on Config alone is therefore confidently wrong in exactly the direction
that matters: it says a change is contained when it is not.

**Four reads, four shortfalls, one result.** Each API is guarded on its own, so a
refused `DescribeVpcPeeringConnections` costs the peering edges and nothing else.
The three that answered are in the result, and the coverage row for the slice says
PARTIAL with one cause, which is more than a caller would get from an exception and
is the reason `read_slice` does not raise. A run that discarded three good reads
because the fourth refused would be constraint 5 broken inside one collector.

**`as_of` is the clock here, and in `config_inventory.py` it is not.** A Describe
call reports the present, so the fact was true at the moment it was asked, and the
two timestamps are legitimately equal. Config returns a capture time that can be
months old, and using our own clock there would make a stale configuration item read
as fresh. The difference is not an inconsistency between the two adapters, it is the
two APIs answering different questions, and constraint 10 is what makes the
difference visible rather than invisible.

**The nodes this file emits are the ones its own APIs name.** It does not rely on
Config having run, because a slice where Config was refused and these four answered
is a real slice: `topology_edge` keys its origin onto `topology_node`, so an edge out
of a node nothing wrote would fail the whole unit at the database. The far ends are
deliberately not emitted as nodes. A VPC in another account, an endpoint owned by
somebody else and an external principal are boundaries, and an edge pointing at a
node with no row is how the schema says so.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.config import Settings
from finops_core.domain.account import AccountKey
from finops_core.domain.topology import (
    CoverageCause,
    Edge,
    EdgeKind,
    Node,
    NodeKind,
    Shortfall,
    SliceRead,
    node_id_for,
)
from finops_core.errors import CollectionError, Throttled
from finops_providers.aws.client import partition_for, translate

COLLECTOR = "topology"

#: Every edge and node from this file names the API that produced it. A reader seeing
#: no peering edges in a region has to be able to tell an estate with no peering from
#: a slice where this one call was refused, and the pair of a `source` on the edge and
#: a `Shortfall` on the slice is what answers that.
TGW_API = "ec2:DescribeTransitGatewayAttachments"
PEERING_API = "ec2:DescribeVpcPeeringConnections"
ENDPOINT_API = "ec2:DescribeVpcEndpointConnections"
TRUST_API = "iam:ListRoles"

#: Seconds before the first retry of a throttled page, doubled per attempt. The same
#: shape the other adapters use.
THROTTLE_BACKOFF_BASE_SECONDS = 1.0

#: The resource type the attachment API reports for a VPC. Anything else is an
#: attachment to something this file does not model, which is a node kept with no far
#: end rather than an attachment dropped.
VPC_RESOURCE_TYPE = "vpc"

Clock = Callable[[], datetime]
Sleeper = Callable[[float], None]


def _system_clock() -> datetime:
    return datetime.now(UTC)


class _Found:
    """What one reader produced. Three tuples, and deliberately not a domain type.

    A `SliceRead` per reader would have to name the account and region four times and
    would invite a caller to treat one API's answer as the whole slice's.
    """

    __slots__ = ("edges", "nodes", "shortfalls")

    def __init__(
        self,
        nodes: tuple[Node, ...],
        edges: tuple[Edge, ...],
        shortfalls: tuple[Shortfall, ...] = (),
    ) -> None:
        self.nodes = nodes
        self.edges = edges
        self.shortfalls = shortfalls


def _arn(account_id: str, region: str, resource: str) -> str:
    """An EC2 ARN, built because these APIs return bare identifiers.

    `topology_node.provider_id` is an ARN everywhere else, and a node identified one
    way here and another way from Config would appear twice with half its edges each
    time. That is the failure `node_id_for` exists to prevent, arriving through the
    identifier rather than through the hash.
    """
    return f"arn:{partition_for(region)}:ec2:{region}:{account_id}:{resource}"


def _account_of(arn: str) -> str:
    """The account in an ARN, or an empty string where there is not one.

    Five fields in, which is the one piece of ARN structure this file reads. Read here
    rather than in the domain for the reason `ResourceRef` gives: pulling structure out
    of a provider identifier is how an adapter's format becomes a domain assumption.
    """
    parts = arn.split(":")
    return parts[4] if len(parts) > 4 else ""


def _trusted_principals(document: Any) -> tuple[str, ...]:
    """Every account principal a role's assume role policy admits, as ARNs.

    The document arrives URL encoded and as a string rather than as an object, which is
    why this parses rather than reads. A document that does not parse yields nothing and
    the caller records a `SchemaDrift` shortfall: a trust relationship guessed at is
    worse than one reported missing, because the guess lands in the blast radius of
    somebody's production change.

    `Service` and `Federated` principals are deliberately skipped. They are not
    accounts, so there is no node at the far end to point an edge at, and an edge to
    `ec2.amazonaws.com` would put every instance role in every other one's blast
    radius.
    """
    if isinstance(document, str):
        try:
            parsed: Any = json.loads(unquote(document))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return ()
    elif isinstance(document, dict):
        parsed = document
    else:
        return ()
    if not isinstance(parsed, dict):
        return ()
    statements = parsed.get("Statement")
    if isinstance(statements, dict):
        statements = [statements]
    if not isinstance(statements, list):
        return ()
    found: list[str] = []
    for statement in statements:
        if not isinstance(statement, dict) or statement.get("Effect") != "Allow":
            continue
        principal = statement.get("Principal")
        if not isinstance(principal, dict):
            continue
        entries = principal.get("AWS")
        if isinstance(entries, str):
            entries = [entries]
        if not isinstance(entries, list):
            continue
        found.extend(str(entry) for entry in entries if str(entry).startswith("arn:"))
    # Ordered and deduplicated, so two statements naming one principal produce one edge
    # rather than a second the unique index would refuse.
    return tuple(dict.fromkeys(found))


class AwsEdgeSupplement:
    """The four APIs Config does not cover, each guarded on its own.

    Unproved, ISS-202. The client factory takes a service, an account and a region, so
    a caller can hand back one client per assumed role. IAM is global and is still
    asked for with the slice's region, because a session is scoped to a region even
    when its service is not.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        client_factory: Callable[[str, str, str], Any],
        tenant_id: Any,
        enrolled: tuple[tuple[AccountKey, str | None], ...],
        clock: Clock = _system_clock,
        sleeper: Sleeper | None = None,
    ) -> None:
        self._settings = settings
        self._factory = client_factory
        self._tenant_id = tenant_id
        self._enrolled = enrolled
        self._clock = clock
        if sleeper is None:
            import time

            sleeper = time.sleep
        self._sleeper = sleeper

    @property
    def enrolled_slices(self) -> tuple[tuple[AccountKey, str | None], ...]:
        return self._enrolled

    def read_slice(self, account: AccountKey, region: str | None) -> SliceRead:
        """Four reads, and a result that says which of them fell short.

        The global slice reads only the trust policies, because the other three APIs
        are regional. A global slice that tried them would ask EC2 for a region it was
        not given, which is a fault in our own call rather than in the estate.
        """
        at = self._clock()
        nodes: dict[str, Node] = {}
        edges: dict[tuple[str, str, EdgeKind], Edge] = {}
        shortfalls: list[Shortfall] = []

        if region is not None:
            for api, reader in (
                (TGW_API, self._attachments),
                (PEERING_API, self._peerings),
                (ENDPOINT_API, self._endpoints),
            ):
                self._absorb(api, reader, account, region, at, nodes, edges, shortfalls)
        self._absorb(TRUST_API, self._trusts, account, region, at, nodes, edges, shortfalls)

        return SliceRead(
            account_key=account,
            region_id=region,
            nodes=tuple(nodes.values()),
            edges=tuple(edges.values()),
            shortfalls=tuple(shortfalls),
        )

    def _absorb(
        self,
        api: str,
        reader: Callable[[AccountKey, Any, datetime], _Found],
        account: AccountKey,
        region: Any,
        at: datetime,
        nodes: dict[str, Node],
        edges: dict[tuple[str, str, EdgeKind], Edge],
        shortfalls: list[Shortfall],
    ) -> None:
        """Run one reader, and keep what it produced or why it did not.

        This is where the task's third criterion lives: a partial read of one edge kind
        does not discard the others. Each reader runs inside its own guard, and a
        failure contributes one shortfall naming its own API rather than aborting the
        slice.
        """
        try:
            found = reader(account, region, at)
        except CollectionError as failure:
            shortfalls.append(
                Shortfall(source=api, cause=CoverageCause(failure.cause), detail=failure.detail)
            )
            return
        for node in found.nodes:
            nodes.setdefault(node.provider_id, node)
        for edge in found.edges:
            edges.setdefault((str(edge.from_node_id), str(edge.to_node_id), edge.edge_kind), edge)
        shortfalls.extend(found.shortfalls)

    # -- Transit Gateway ---------------------------------------------------

    def _attachments(self, account: AccountKey, region: str, at: datetime) -> _Found:
        """Attachments the account owns, and the VPCs on the other side of them.

        The cross account case is the whole point. `ResourceOwnerId` is the account
        that owns the attached VPC and `TransitGatewayOwnerId` is the account that owns
        the gateway, and they differ whenever a shared gateway is doing its job.
        """
        nodes: list[Node] = []
        edges: list[Edge] = []
        shortfalls: list[Shortfall] = []
        for raw in self._pages(
            "ec2",
            account,
            region,
            "describe_transit_gateway_attachments",
            "TransitGatewayAttachments",
            TGW_API,
        ):
            attachment_id = str(raw.get("TransitGatewayAttachmentId") or "")
            gateway_id = str(raw.get("TransitGatewayId") or "")
            if not attachment_id or not gateway_id:
                continue
            gateway_owner = str(raw.get("TransitGatewayOwnerId") or account.account_id)
            attachment = _arn(
                account.account_id, region, f"transit-gateway-attachment/{attachment_id}"
            )
            gateway = _arn(gateway_owner, region, f"transit-gateway/{gateway_id}")
            nodes.append(
                self._node(
                    attachment,
                    account,
                    NodeKind.TGW_ATTACHMENT,
                    "AWS::EC2::TransitGatewayAttachment",
                    region,
                    str(raw.get("State") or "") or None,
                    at,
                )
            )
            if gateway_owner == account.account_id:
                # Only when this account owns it. A gateway in another account is a
                # boundary, and a node row for it would claim a resource this slice
                # never read and put it in another account's node count.
                nodes.append(
                    self._node(
                        gateway,
                        account,
                        NodeKind.OTHER,
                        "AWS::EC2::TransitGateway",
                        region,
                        gateway_id,
                        at,
                    )
                )
                edges.append(
                    self._edge(gateway, attachment, EdgeKind.CONTAINS, TGW_API, at, gateway_owner)
                )
            resource_type = str(raw.get("ResourceType") or "")
            resource_id = str(raw.get("ResourceId") or "")
            if resource_type != VPC_RESOURCE_TYPE or not resource_id:
                # An attachment to a VPN, a Direct Connect gateway or a peer. The
                # attachment node stays, because the attachment is real and costs
                # money. Only its far end is unmodelled, and saying so is honest.
                shortfalls.append(
                    Shortfall(
                        source=TGW_API,
                        cause=CoverageCause.SCHEMA_DRIFT,
                        detail=(
                            f"attachment {attachment_id} is to a "
                            f"{resource_type or 'unnamed'} resource, which this adapter "
                            "does not model, so its far end is missing"
                        ),
                    )
                )
                continue
            owner = str(raw.get("ResourceOwnerId") or account.account_id)
            edges.append(
                self._edge(
                    attachment,
                    _arn(owner, region, f"vpc/{resource_id}"),
                    EdgeKind.ATTACHED_TO,
                    TGW_API,
                    at,
                    owner,
                )
            )
        return _Found(tuple(nodes), tuple(edges), tuple(shortfalls))

    # -- VPC peering -------------------------------------------------------

    def _peerings(self, account: AccountKey, region: str, at: datetime) -> _Found:
        """Peering connections, as two edges rather than collapsed into one.

        One edge, `pcx PEERS_WITH accepter`, and the direction is the asymmetry. A
        peering has a requester and an accepter and only one of the two sides may be
        readable, so a single symmetric edge between the two VPCs would imply both ends
        were seen, which is the claim this sub project refuses to make on evidence it
        does not have. The near side comes from Config, for the reason in the body.
        """
        nodes: list[Node] = []
        edges: list[Edge] = []
        for raw in self._pages(
            "ec2",
            account,
            region,
            "describe_vpc_peering_connections",
            "VpcPeeringConnections",
            PEERING_API,
        ):
            peering_id = str(raw.get("VpcPeeringConnectionId") or "")
            requester = raw.get("RequesterVpcInfo")
            accepter = raw.get("AccepterVpcInfo")
            if not peering_id or not isinstance(requester, dict) or not isinstance(accepter, dict):
                continue
            peering = _arn(account.account_id, region, f"vpc-peering-connection/{peering_id}")
            nodes.append(
                self._node(
                    peering,
                    account,
                    NodeKind.OTHER,
                    "AWS::EC2::VPCPeeringConnection",
                    region,
                    peering_id,
                    at,
                )
            )
            # The near side, `requester_vpc ATTACHED_TO pcx`, is deliberately not
            # emitted here. Its origin is a VPC this file does not read, and
            # `topology_edge` keys the origin onto `topology_node`, so writing it would
            # fail the whole unit in any slice where Config had been refused. Config
            # does supply that edge, because both resources are in one account and its
            # relationship records reach that far. This file is for the edges Config
            # cannot give, which here is the far side only. If Config was refused, the
            # peering connection sits in the graph with no edge into it and the slice's
            # coverage row says PARTIAL, which is the honest outcome.
            far_owner = str(accepter.get("OwnerId") or account.account_id)
            far_vpc = str(accepter.get("VpcId") or "")
            if far_vpc:
                far_region = str(accepter.get("Region") or region)
                edges.append(
                    self._edge(
                        peering,
                        _arn(far_owner, far_region, f"vpc/{far_vpc}"),
                        EdgeKind.PEERS_WITH,
                        PEERING_API,
                        at,
                        far_owner,
                    )
                )
        return _Found(tuple(nodes), tuple(edges))

    # -- PrivateLink -------------------------------------------------------

    def _endpoints(self, account: AccountKey, region: str, at: datetime) -> _Found:
        """Endpoint connections to services this account publishes.

        The endpoint is usually in somebody else's account, which is what makes this
        one of the four edges worth a whole file. The service is ours, the endpoint is
        theirs, and Config's relationship records see neither side of the pair.
        """
        nodes: list[Node] = []
        edges: list[Edge] = []
        for raw in self._pages(
            "ec2",
            account,
            region,
            "describe_vpc_endpoint_connections",
            "VpcEndpointConnections",
            ENDPOINT_API,
        ):
            service_id = str(raw.get("ServiceId") or "")
            endpoint_id = str(raw.get("VpcEndpointId") or "")
            if not service_id or not endpoint_id:
                continue
            service = _arn(account.account_id, region, f"vpc-endpoint-service/{service_id}")
            nodes.append(
                self._node(
                    service,
                    account,
                    NodeKind.OTHER,
                    "AWS::EC2::VPCEndpointService",
                    region,
                    service_id,
                    at,
                )
            )
            owner = str(raw.get("VpcEndpointOwner") or account.account_id)
            # From the service outward, because the service is the resource this slice
            # read. The endpoint is the boundary.
            edges.append(
                self._edge(
                    service,
                    _arn(owner, region, f"vpc-endpoint/{endpoint_id}"),
                    EdgeKind.ROUTES_TO,
                    ENDPOINT_API,
                    at,
                    owner,
                )
            )
        return _Found(tuple(nodes), tuple(edges))

    # -- cross account trust -----------------------------------------------

    def _trusts(self, account: AccountKey, region: str | None, at: datetime) -> _Found:
        """Roles this account holds, and the principals they admit.

        IAM is global, so these belong to the account's global slice and the nodes
        carry no region. A role recorded against a region would be the same role
        eleven times over, once per region enrolled.
        """
        nodes: list[Node] = []
        edges: list[Edge] = []
        shortfalls: list[Shortfall] = []
        for raw in self._pages("iam", account, region or "", "list_roles", "Roles", TRUST_API):
            arn = str(raw.get("Arn") or "")
            if not arn:
                continue
            nodes.append(
                self._node(
                    arn,
                    account,
                    NodeKind.OTHER,
                    "AWS::IAM::Role",
                    None,
                    str(raw.get("RoleName") or "") or None,
                    at,
                )
            )
            document = raw.get("AssumeRolePolicyDocument")
            principals = _trusted_principals(document)
            if document is not None and not principals:
                shortfalls.append(
                    Shortfall(
                        source=TRUST_API,
                        cause=CoverageCause.SCHEMA_DRIFT,
                        detail=(
                            f"the trust policy on {arn} named no account principal this "
                            "adapter could read, so any cross account trust it grants is "
                            "missing from the graph"
                        ),
                    )
                )
            for principal in principals:
                edges.append(
                    self._edge(
                        arn, principal, EdgeKind.TRUSTS, TRUST_API, at, _account_of(principal)
                    )
                )
        return _Found(tuple(nodes), tuple(edges), tuple(shortfalls))

    # -- building the domain objects ----------------------------------------

    def _node(
        self,
        provider_id: str,
        account: AccountKey,
        kind: NodeKind,
        resource_type: str,
        region: str | None,
        name: str | None,
        at: datetime,
    ) -> Node:
        return Node(
            node_id=node_id_for(tenant_id=self._tenant_id, provider_id=provider_id),
            account_key=account,
            provider_id=provider_id,
            node_kind=kind,
            resource_type=resource_type,
            region_id=region,
            # None throughout. Every resource this file reads is regional or global,
            # never zonal, and a zone guessed from a subnet would be a fact nothing
            # here observed.
            availability_zone=None,
            name=name,
            tags={},
            # Both the clock. A Describe call reports the present, so the fact was true
            # at the moment it was asked. The module docstring says why this differs
            # from the Config adapter.
            as_of=at,
            collected_at=at,
        )

    def _edge(
        self,
        origin: str,
        target: str,
        kind: EdgeKind,
        api: str,
        at: datetime,
        target_account: str,
    ) -> Edge:
        near = _account_of(origin)
        return Edge(
            from_node_id=node_id_for(tenant_id=self._tenant_id, provider_id=origin),
            to_node_id=node_id_for(tenant_id=self._tenant_id, provider_id=target),
            edge_kind=kind,
            # Compared account to account at write time, which is the task's second
            # criterion. Computing it on read needs both node rows, and the row for the
            # far end of a cross account edge is the one that does not exist.
            is_cross_account=bool(near and target_account and near != target_account),
            source=api,
            as_of=at,
            collected_at=at,
        )

    # -- calling the provider ----------------------------------------------

    def _pages(
        self,
        service: str,
        account: AccountKey,
        region: str,
        operation: str,
        key: str,
        api: str,
    ) -> Iterator[Mapping[str, Any]]:
        """Every page of one operation, with a bounded retry on throttling.

        Written against the token in the response rather than a paginator, because a
        paginator a test client has to implement is a test client that has stopped
        being a literal. `Marker` as well as `NextToken`, because IAM pages one way and
        EC2 the other.
        """
        client = self._factory(service, account.account_id, region)
        scope_key = f"acct:{account.account_id}"
        if region:
            scope_key = f"{scope_key}:{region}"
        token: str | None = None
        attempt = 0
        while True:
            request: dict[str, Any] = {}
            if token is not None:
                request["Marker" if service == "iam" else "NextToken"] = token
            try:
                page = getattr(client, operation)(**request)
            except (ClientError, BotoCoreError) as failure:
                typed = translate(failure, scope_key=scope_key, collector=f"{COLLECTOR}:{api}")
                if not isinstance(typed, Throttled) or attempt >= self._settings.aws_max_retries:
                    raise typed from failure
                self._sleeper(THROTTLE_BACKOFF_BASE_SECONDS * (2**attempt))
                attempt += 1
                continue
            # Reset per page rather than per call, so a long run throttled on every
            # tenth page is not failed on the tenth throttle.
            attempt = 0
            for raw in page.get(key, []):
                if isinstance(raw, dict):
                    yield raw
            token = page.get("NextToken") or page.get("Marker")
            if not token:
                return
