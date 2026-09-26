"""The four APIs Config does not cover, against clients that answer from literals.

Unproved against AWS, ISS-202, so every case asserts a mapping. The ones that carry
weight are about independence: a refused peering call must cost the peering edges and
nothing else, because a run that discarded three good reads because the fourth
refused would be constraint 5 broken inside one collector.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from uuid import UUID

import pytest
from botocore.exceptions import ClientError

from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.topology import CoverageCause, CoverageState, EdgeKind, NodeKind
from finops_core.ports.inventory import TopologySource
from finops_providers.aws.topology import (
    ENDPOINT_API,
    PEERING_API,
    TGW_API,
    TRUST_API,
    AwsEdgeSupplement,
)

TENANT = UUID("11111111-1111-1111-1111-111111111111")
ACCOUNT = AccountKey(provider=Provider.AWS, account_id="111122223333")
FAR = AccountKey(provider=Provider.AWS, account_id="444455556666")
REGION = "eu-west-1"
NOW = datetime(2026, 9, 26, 6, 5, tzinfo=UTC)

ATTACHMENT = {
    "TransitGatewayAttachmentId": "tgw-attach-01",
    "TransitGatewayId": "tgw-01",
    "TransitGatewayOwnerId": ACCOUNT.account_id,
    "ResourceOwnerId": FAR.account_id,
    "ResourceType": "vpc",
    "ResourceId": "vpc-far",
    "State": "available",
}

PEERING = {
    "VpcPeeringConnectionId": "pcx-01",
    "RequesterVpcInfo": {"VpcId": "vpc-01", "OwnerId": ACCOUNT.account_id, "Region": REGION},
    "AccepterVpcInfo": {"VpcId": "vpc-dr", "OwnerId": ACCOUNT.account_id, "Region": "eu-west-2"},
}

ENDPOINT = {
    "ServiceId": "vpce-svc-01",
    "VpcEndpointId": "vpce-01",
    "VpcEndpointOwner": FAR.account_id,
    "VpcEndpointState": "available",
}


def trust_policy(*principals: str) -> str:
    """One assume role policy document, URL encoded as the API returns it."""
    return quote(
        json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": list(principals)},
                        "Action": "sts:AssumeRole",
                    }
                ],
            }
        )
    )


ROLE = {
    "RoleName": "platform-ci",
    "Arn": f"arn:aws:iam::{ACCOUNT.account_id}:role/platform-ci",
    "AssumeRolePolicyDocument": trust_policy(f"arn:aws:iam::{FAR.account_id}:root"),
}


class Ec2:
    """Answers the three EC2 reads, and can be made to refuse any one of them."""

    def __init__(
        self,
        *,
        attachments: list[Any] | None = None,
        peerings: list[Any] | None = None,
        endpoints: list[Any] | None = None,
        refuse: frozenset[str] = frozenset(),
        error: Exception | None = None,
    ) -> None:
        self._attachments = attachments if attachments is not None else [ATTACHMENT]
        self._peerings = peerings if peerings is not None else [PEERING]
        self._endpoints = endpoints if endpoints is not None else [ENDPOINT]
        self._refuse = refuse
        self._error = error or ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "refused"}}, "Describe"
        )
        self.calls: list[str] = []

    def _answer(self, name: str, key: str, rows: list[Any]) -> Any:
        self.calls.append(name)
        if name in self._refuse:
            raise self._error
        return {key: rows}

    def describe_transit_gateway_attachments(self, **_: Any) -> Any:
        return self._answer("attachments", "TransitGatewayAttachments", self._attachments)

    def describe_vpc_peering_connections(self, **_: Any) -> Any:
        return self._answer("peerings", "VpcPeeringConnections", self._peerings)

    def describe_vpc_endpoint_connections(self, **_: Any) -> Any:
        return self._answer("endpoints", "VpcEndpointConnections", self._endpoints)


class Iam:
    """Answers `list_roles`, pageable by `Marker` the way IAM pages."""

    def __init__(
        self, *pages: list[Any], refuse: bool = False, error: Exception | None = None
    ) -> None:
        self._pages = list(pages) or [[ROLE]]
        self._refuse = refuse
        self._error = error or ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "refused"}}, "ListRoles"
        )
        self.markers: list[str | None] = []

    def list_roles(self, **request: Any) -> Any:
        self.markers.append(request.get("Marker"))
        if self._refuse:
            raise self._error
        if not self._pages:
            return {"Roles": []}
        rows = self._pages.pop(0)
        body: dict[str, Any] = {"Roles": rows}
        if self._pages:
            body["Marker"] = f"page-{len(self._pages)}"
        return body


def supplement(
    settings: Settings, *, ec2: Ec2 | None = None, iam: Iam | None = None
) -> AwsEdgeSupplement:
    resolved_ec2 = ec2 or Ec2()
    resolved_iam = iam or Iam()
    return AwsEdgeSupplement(
        settings,
        client_factory=lambda service, _account, _region: (
            resolved_iam if service == "iam" else resolved_ec2
        ),
        tenant_id=TENANT,
        enrolled=((ACCOUNT, REGION), (ACCOUNT, None)),
        clock=lambda: NOW,
        sleeper=lambda _seconds: None,
    )


def sources(read: Any) -> set[str]:
    return {edge.source for edge in read.edges}


# --- every edge names its API ------------------------------------------------


def test_every_edge_names_the_api_that_supplied_it(settings: Settings) -> None:
    """The first criterion. Without it a future reader cannot tell which edges in the
    table depend on this file, and a missing peering edge cannot be told apart from a
    refused peering call."""
    read = supplement(settings).read_slice(ACCOUNT, REGION)
    assert read.edges
    assert sources(read) == {TGW_API, PEERING_API, ENDPOINT_API, TRUST_API}


def test_a_readable_slice_is_whole(settings: Settings) -> None:
    read = supplement(settings).read_slice(ACCOUNT, REGION)
    assert read.is_whole
    assert read.state is CoverageState.COMPLETE


def test_both_timestamps_are_the_clock_because_a_describe_reports_the_present(
    settings: Settings,
) -> None:
    """Deliberately unlike the Config adapter, which has a capture time that can be
    months old. The two APIs answer different questions, and constraint 10 is what
    makes the difference visible."""
    read = supplement(settings).read_slice(ACCOUNT, REGION)
    for node in read.nodes:
        assert node.as_of == NOW
        assert node.collected_at == NOW


# --- cross account, set at write time ---------------------------------------


def test_an_attachment_to_another_account_is_cross_account(settings: Settings) -> None:
    """The second criterion, and the reason the file exists. Computing it on read needs
    both node rows, and the row for the far end is the one that does not exist."""
    read = supplement(settings).read_slice(ACCOUNT, REGION)
    across = [
        edge
        for edge in read.edges
        if edge.source == TGW_API and edge.edge_kind is EdgeKind.ATTACHED_TO
    ]
    assert [edge.is_cross_account for edge in across] == [True]


def test_a_gateway_this_account_owns_is_not_cross_account(settings: Settings) -> None:
    read = supplement(settings).read_slice(ACCOUNT, REGION)
    contains = [
        edge
        for edge in read.edges
        if edge.source == TGW_API and edge.edge_kind is EdgeKind.CONTAINS
    ]
    assert [edge.is_cross_account for edge in contains] == [False]


def test_a_gateway_in_another_account_gets_no_node(settings: Settings) -> None:
    """A node row for it would claim a resource this slice never read and put it in
    another account's node count."""
    shared = dict(ATTACHMENT, TransitGatewayOwnerId=FAR.account_id)
    read = supplement(settings, ec2=Ec2(attachments=[shared])).read_slice(ACCOUNT, REGION)
    types = {node.resource_type for node in read.nodes}
    assert "AWS::EC2::TransitGateway" not in types
    assert "AWS::EC2::TransitGatewayAttachment" in types


def test_a_trust_to_another_account_is_cross_account(settings: Settings) -> None:
    read = supplement(settings).read_slice(ACCOUNT, REGION)
    (trust,) = [edge for edge in read.edges if edge.edge_kind is EdgeKind.TRUSTS]
    assert trust.is_cross_account is True


def test_a_trust_to_this_account_is_not_cross_account(settings: Settings) -> None:
    own = dict(
        ROLE, AssumeRolePolicyDocument=trust_policy(f"arn:aws:iam::{ACCOUNT.account_id}:root")
    )
    read = supplement(settings, iam=Iam([own])).read_slice(ACCOUNT, REGION)
    (trust,) = [edge for edge in read.edges if edge.edge_kind is EdgeKind.TRUSTS]
    assert trust.is_cross_account is False


def test_a_service_principal_yields_no_edge(settings: Settings) -> None:
    """An edge to `ec2.amazonaws.com` would put every instance role in every other
    one's blast radius, and there is no node at the far end to point it at."""
    service = dict(
        ROLE,
        AssumeRolePolicyDocument=quote(
            json.dumps(
                {
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "ec2.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ]
                }
            )
        ),
    )
    read = supplement(settings, iam=Iam([service])).read_slice(ACCOUNT, None)
    assert [edge for edge in read.edges if edge.edge_kind is EdgeKind.TRUSTS] == []


def test_one_principal_named_twice_yields_one_edge(settings: Settings) -> None:
    principal = f"arn:aws:iam::{FAR.account_id}:root"
    twice = dict(ROLE, AssumeRolePolicyDocument=trust_policy(principal, principal))
    read = supplement(settings, iam=Iam([twice])).read_slice(ACCOUNT, None)
    assert len([edge for edge in read.edges if edge.edge_kind is EdgeKind.TRUSTS]) == 1


def test_a_trust_policy_that_does_not_parse_is_named_rather_than_guessed(
    settings: Settings,
) -> None:
    """A trust relationship guessed at is worse than one reported missing, because the
    guess lands in the blast radius of somebody's production change."""
    broken = dict(ROLE, AssumeRolePolicyDocument="%7Bnot json")
    read = supplement(settings, iam=Iam([broken])).read_slice(ACCOUNT, None)
    assert [edge for edge in read.edges if edge.edge_kind is EdgeKind.TRUSTS] == []
    (shortfall,) = read.shortfalls
    assert shortfall.source == TRUST_API
    assert shortfall.cause is CoverageCause.SCHEMA_DRIFT


# --- peering keeps its asymmetry ---------------------------------------------


def test_a_peering_is_one_directed_edge_from_the_connection_outward(
    settings: Settings,
) -> None:
    """Directed, because only one of the two sides may be readable and a symmetric edge
    would imply both ends were seen.

    Only the far side. The near side, `requester_vpc ATTACHED_TO pcx`, would leave a
    VPC this file does not read, and `topology_edge` keys its origin onto
    `topology_node`, so it would fail the whole unit in any slice where Config had been
    refused. Config supplies that edge, because both resources are in one account.
    """
    read = supplement(settings).read_slice(ACCOUNT, REGION)
    (peering,) = [edge for edge in read.edges if edge.source == PEERING_API]
    assert peering.edge_kind is EdgeKind.PEERS_WITH
    known = {node.node_id for node in read.nodes}
    assert peering.from_node_id in known
    assert peering.to_node_id not in known


def test_the_endpoint_edge_runs_from_the_service_this_slice_read(settings: Settings) -> None:
    read = supplement(settings).read_slice(ACCOUNT, REGION)
    (edge,) = [one for one in read.edges if one.source == ENDPOINT_API]
    known = {node.node_id for node in read.nodes}
    assert edge.from_node_id in known
    assert edge.to_node_id not in known
    assert edge.is_cross_account is True


# --- independence, which is the third criterion ------------------------------


@pytest.mark.parametrize(
    ("refused", "lost", "kept"),
    [
        ("attachments", TGW_API, (PEERING_API, ENDPOINT_API, TRUST_API)),
        ("peerings", PEERING_API, (TGW_API, ENDPOINT_API, TRUST_API)),
        ("endpoints", ENDPOINT_API, (TGW_API, PEERING_API, TRUST_API)),
    ],
)
def test_one_refused_api_costs_its_own_edges_and_no_others(
    settings: Settings, refused: str, lost: str, kept: tuple[str, ...]
) -> None:
    """The criterion as a parameterised case, so adding a fifth API without guarding it
    separately fails here."""
    read = supplement(settings, ec2=Ec2(refuse=frozenset({refused}))).read_slice(ACCOUNT, REGION)
    assert sources(read) == set(kept)
    (shortfall,) = read.shortfalls
    assert shortfall.source == lost
    assert shortfall.cause is CoverageCause.ACCESS_DENIED
    assert read.state is CoverageState.PARTIAL


def test_a_refused_trust_read_leaves_the_three_ec2_reads_intact(settings: Settings) -> None:
    read = supplement(settings, iam=Iam(refuse=True)).read_slice(ACCOUNT, REGION)
    assert sources(read) == {TGW_API, PEERING_API, ENDPOINT_API}
    (shortfall,) = read.shortfalls
    assert shortfall.source == TRUST_API


def test_every_api_refusing_still_returns_a_slice_read(settings: Settings) -> None:
    """Four shortfalls, no edges, and not an exception. The caller writes a PARTIAL
    coverage row and moves to the next account."""
    read = supplement(
        settings,
        ec2=Ec2(refuse=frozenset({"attachments", "peerings", "endpoints"})),
        iam=Iam(refuse=True),
    ).read_slice(ACCOUNT, REGION)
    assert read.edges == ()
    assert read.nodes == ()
    assert {shortfall.source for shortfall in read.shortfalls} == {
        TGW_API,
        PEERING_API,
        ENDPOINT_API,
        TRUST_API,
    }
    assert read.cause is CoverageCause.ACCESS_DENIED


def test_an_attachment_to_something_unmodelled_keeps_the_attachment_and_says_so(
    settings: Settings,
) -> None:
    """The attachment is real and costs money. Only its far end is unmodelled."""
    vpn = dict(ATTACHMENT, ResourceType="vpn", ResourceId="vpn-01")
    read = supplement(settings, ec2=Ec2(attachments=[vpn])).read_slice(ACCOUNT, REGION)
    assert any(node.node_kind is NodeKind.TGW_ATTACHMENT for node in read.nodes)
    assert not [
        edge
        for edge in read.edges
        if edge.source == TGW_API and edge.edge_kind is EdgeKind.ATTACHED_TO
    ]
    drift = [one for one in read.shortfalls if one.source == TGW_API]
    assert drift and "vpn" in drift[0].detail


# --- the global slice and pagination ----------------------------------------


def test_the_global_slice_reads_only_the_trust_policies(settings: Settings) -> None:
    """The other three APIs are regional, and asking EC2 for a region it was not given
    is a fault in our own call rather than in the estate."""
    ec2 = Ec2()
    read = supplement(settings, ec2=ec2).read_slice(ACCOUNT, None)
    assert ec2.calls == []
    assert sources(read) == {TRUST_API}
    for node in read.nodes:
        assert node.region_id is None


def test_every_page_of_roles_is_read(settings: Settings) -> None:
    second = dict(ROLE, RoleName="batch", Arn=f"arn:aws:iam::{ACCOUNT.account_id}:role/batch")
    iam = Iam([ROLE], [second])
    read = supplement(settings, iam=iam).read_slice(ACCOUNT, None)
    assert len([node for node in read.nodes if node.resource_type == "AWS::IAM::Role"]) == 2
    assert iam.markers == [None, "page-1"]


def test_a_throttled_call_is_retried_to_the_configured_bound(settings: Settings) -> None:
    throttled = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "slow"}}, "ListRoles"
    )
    iam = Iam(refuse=True, error=throttled)
    read = supplement(settings, iam=iam).read_slice(ACCOUNT, None)
    assert read.cause is CoverageCause.THROTTLED
    assert len(iam.markers) == settings.aws_max_retries + 1


def test_it_satisfies_the_port(settings: Settings) -> None:
    assert isinstance(supplement(settings), TopologySource)


def test_every_edge_leaves_a_node_this_slice_wrote(settings: Settings) -> None:
    """`topology_edge` keys its origin onto `topology_node`, so an edge out of a node
    nothing wrote would fail the whole unit at the database. This file does not rely on
    Config having run first."""
    read = supplement(settings).read_slice(ACCOUNT, REGION)
    known = {node.node_id for node in read.nodes}
    for edge in read.edges:
        assert edge.from_node_id in known, edge.source
