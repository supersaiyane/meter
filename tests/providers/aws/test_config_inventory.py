"""The Config aggregator adapter, against a client that answers from a literal.

Nothing in the adapter has ever made a real call, ISS-200, so every case here
asserts a mapping rather than a behaviour of AWS. That is worth saying because it
bounds what passing means: the adapter turns the documented response into the
documented domain objects, and nothing here shows the response looks like this.

The cases that carry weight are the ones about what happens when the answer is
incomplete. A refused aggregator produces a `SliceRead` rather than an exception, a
result that does not parse loses one row rather than a hundred, and an unfamiliar
resource type is in the graph and named in a shortfall rather than absent.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.topology import CoverageCause, CoverageState, EdgeKind, NodeKind
from finops_core.ports.inventory import TopologySource
from finops_providers.aws.config_inventory import (
    CONFIG_RELATIONSHIP,
    PAGE_SIZE,
    ConfigAggregatorInventory,
)

TENANT = UUID("11111111-1111-1111-1111-111111111111")
ACCOUNT = AccountKey(provider=Provider.AWS, account_id="111122223333")
OTHER_ACCOUNT = AccountKey(provider=Provider.AWS, account_id="444455556666")
REGION = "eu-west-1"
NOW = datetime(2026, 9, 26, 6, 5, tzinfo=UTC)
CAPTURED = "2026-09-26T06:00:00.000Z"

VPC_ARN = f"arn:aws:ec2:{REGION}:{ACCOUNT.account_id}:vpc/vpc-01"
SUBNET_ARN = f"arn:aws:ec2:{REGION}:{ACCOUNT.account_id}:subnet/subnet-0a"
GROUP_ARN = f"arn:aws:ec2:{REGION}:{ACCOUNT.account_id}:security-group/sg-app"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT.account_id}:role/platform-ci"


def item(**overrides: Any) -> dict[str, Any]:
    """One configuration item, valid, with any field overridden."""
    values: dict[str, Any] = {
        "accountId": ACCOUNT.account_id,
        "awsRegion": REGION,
        "resourceType": "AWS::EC2::VPC",
        "resourceId": VPC_ARN,
        "resourceName": "production",
        "arn": VPC_ARN,
        "availabilityZone": None,
        "tags": [{"key": "finops:module", "value": "network"}],
        "configurationItemCaptureTime": CAPTURED,
        "relationships": [],
    }
    values.update(overrides)
    return values


def related(arn: str, name: str, resource_type: str = "AWS::EC2::Subnet") -> dict[str, Any]:
    return {"resourceType": resource_type, "resourceId": arn, "relationshipName": name}


class Client:
    """Answers `select_aggregate_resource_config` from pages handed to it."""

    def __init__(self, *pages: Any, raises: Exception | None = None) -> None:
        self._pages = list(pages)
        self._raises = raises
        self.requests: list[dict[str, Any]] = []
        self.raised = 0

    def select_aggregate_resource_config(self, **request: Any) -> Any:
        self.requests.append(request)
        if self._raises is not None:
            self.raised += 1
            raise self._raises
        if not self._pages:
            return {"Results": []}
        return self._pages.pop(0)


def page(*items: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    """A response, with the items encoded the way the API encodes them."""
    body: dict[str, Any] = {"Results": [json.dumps(one) for one in items]}
    if token is not None:
        body["NextToken"] = token
    return body


def source(settings: Settings, client: Client) -> ConfigAggregatorInventory:
    return ConfigAggregatorInventory(
        settings,
        client=client,
        aggregator_name="meter-org",
        tenant_id=TENANT,
        enrolled=((ACCOUNT, REGION),),
        clock=lambda: NOW,
        sleeper=lambda _seconds: None,
    )


def denied() -> ClientError:
    return ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "Select")


def throttled() -> ClientError:
    return ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow"}}, "Select")


# --- the ordinary read -------------------------------------------------------


def test_a_configuration_item_becomes_a_node(settings: Settings) -> None:
    read = source(settings, Client(page(item()))).read_slice(ACCOUNT, REGION)
    assert read.is_whole
    assert read.state is CoverageState.COMPLETE
    assert read.cause is None
    (node,) = read.nodes
    assert node.provider_id == VPC_ARN
    assert node.node_kind is NodeKind.VPC
    assert node.resource_type == "AWS::EC2::VPC"
    assert node.region_id == REGION
    assert node.availability_zone is None
    assert node.name == "production"
    assert dict(node.tags) == {"finops:module": "network"}


def test_the_two_timestamps_come_from_two_places(settings: Settings) -> None:
    """Constraint 10. `as_of` is Config's capture time and `collected_at` is ours,
    and an adapter using its own clock for both would make a configuration item from
    months ago read as one from this morning."""
    (node,) = source(settings, Client(page(item()))).read_slice(ACCOUNT, REGION).nodes
    assert node.as_of == datetime(2026, 9, 26, 6, 0, tzinfo=UTC)
    assert node.collected_at == NOW


def test_a_zonal_resource_keeps_its_zone(settings: Settings) -> None:
    read = source(
        settings,
        Client(
            page(
                item(
                    resourceType="AWS::EC2::Subnet",
                    resourceId=SUBNET_ARN,
                    arn=SUBNET_ARN,
                    availabilityZone=f"{REGION}a",
                )
            )
        ),
    ).read_slice(ACCOUNT, REGION)
    (node,) = read.nodes
    assert node.node_kind is NodeKind.SUBNET
    assert node.availability_zone == f"{REGION}a"


def test_a_global_resource_has_no_region_and_no_zone(settings: Settings) -> None:
    """An IAM role belongs to an account and to no region, and a zone alongside a
    null region is a pair the schema refuses and that cannot be true."""
    read = source(
        settings,
        Client(
            page(
                item(
                    resourceType="AWS::IAM::Role",
                    resourceId=ROLE_ARN,
                    arn=ROLE_ARN,
                    awsRegion=None,
                    availabilityZone=f"{REGION}a",
                )
            )
        ),
    ).read_slice(ACCOUNT, None)
    (node,) = read.nodes
    assert node.region_id is None
    assert node.availability_zone is None


# --- relationships become edges ---------------------------------------------


def test_an_outward_relationship_becomes_an_edge(settings: Settings) -> None:
    read = source(
        settings,
        Client(
            page(
                item(relationships=[related(SUBNET_ARN, "Contains Subnet")]),
                item(resourceType="AWS::EC2::Subnet", resourceId=SUBNET_ARN, arn=SUBNET_ARN),
            )
        ),
    ).read_slice(ACCOUNT, REGION)
    (edge,) = read.edges
    assert edge.edge_kind is EdgeKind.CONTAINS
    assert edge.source == CONFIG_RELATIONSHIP
    assert edge.is_cross_account is False
    by_arn = {node.provider_id: node.node_id for node in read.nodes}
    assert (edge.from_node_id, edge.to_node_id) == (by_arn[VPC_ARN], by_arn[SUBNET_ARN])


def test_an_inward_relationship_runs_from_the_far_end(settings: Settings) -> None:
    """`Is contained in Vpc` on a subnet is the VPC containing the subnet, so the
    edge is the same fact the VPC's own item reports in the other direction."""
    read = source(
        settings,
        Client(
            page(
                item(),
                item(
                    resourceType="AWS::EC2::Subnet",
                    resourceId=SUBNET_ARN,
                    arn=SUBNET_ARN,
                    relationships=[
                        related(VPC_ARN, "Is contained in Vpc", "AWS::EC2::VPC"),
                    ],
                ),
            )
        ),
    ).read_slice(ACCOUNT, REGION)
    (edge,) = read.edges
    by_arn = {node.provider_id: node.node_id for node in read.nodes}
    assert (edge.from_node_id, edge.to_node_id) == (by_arn[VPC_ARN], by_arn[SUBNET_ARN])


def test_an_inward_relationship_from_outside_the_slice_is_not_emitted(
    settings: Settings,
) -> None:
    """Not a dropped edge. Config reports a relationship from both ends, so it
    belongs to the origin's own slice, whose coverage row answers for it. Emitting it
    here would mean an edge out of a node this slice never read."""
    outside = f"arn:aws:ec2:{REGION}:{OTHER_ACCOUNT.account_id}:vpc/vpc-far"
    read = source(
        settings,
        Client(
            page(
                item(
                    resourceType="AWS::EC2::Subnet",
                    resourceId=SUBNET_ARN,
                    arn=SUBNET_ARN,
                    relationships=[related(outside, "Is contained in Vpc", "AWS::EC2::VPC")],
                )
            )
        ),
    ).read_slice(ACCOUNT, REGION)
    assert read.edges == ()
    assert len(read.nodes) == 1


def test_an_edge_to_a_node_outside_the_slice_is_cross_account(settings: Settings) -> None:
    """Set at write time, not computed on read, because the cross account edges are
    the ones anybody asks for by name and a predicate needing two joins is the one
    left out of the query that most needs it."""
    far = f"arn:aws:ec2:{REGION}:{OTHER_ACCOUNT.account_id}:subnet/subnet-far"
    read = source(
        settings,
        Client(page(item(relationships=[related(far, "Contains Subnet")]))),
    ).read_slice(ACCOUNT, REGION)
    (edge,) = read.edges
    assert edge.is_cross_account is True


def test_a_relationship_to_itself_is_skipped(settings: Settings) -> None:
    """Config reports one for a security group under a name that maps to
    ATTACHED_TO, which the check constraint refuses, so it is skipped here rather
    than left to fail the whole unit at the database."""
    read = source(
        settings,
        Client(
            page(
                item(
                    resourceType="AWS::EC2::SecurityGroup",
                    resourceId=GROUP_ARN,
                    arn=GROUP_ARN,
                    relationships=[
                        related(GROUP_ARN, "Is associated with SecurityGroup", "AWS::EC2::Group")
                    ],
                )
            )
        ),
    ).read_slice(ACCOUNT, REGION)
    assert read.edges == ()
    assert read.is_whole


def test_the_same_pair_twice_yields_one_edge(settings: Settings) -> None:
    """Two relationship names mapping to one kind would otherwise be refused by the
    unique index, so the collector never sees the second."""
    read = source(
        settings,
        Client(
            page(
                item(
                    relationships=[
                        related(SUBNET_ARN, "Contains Subnet"),
                        related(SUBNET_ARN, "Contains Subnet again"),
                    ]
                ),
                item(resourceType="AWS::EC2::Subnet", resourceId=SUBNET_ARN, arn=SUBNET_ARN),
            )
        ),
    ).read_slice(ACCOUNT, REGION)
    assert len(read.edges) == 1


def test_an_unmapped_relationship_name_is_named_rather_than_guessed(
    settings: Settings,
) -> None:
    read = source(
        settings,
        Client(page(item(relationships=[related(SUBNET_ARN, "Fraternises with Subnet")]))),
    ).read_slice(ACCOUNT, REGION)
    assert read.edges == ()
    assert not read.is_whole
    (shortfall,) = read.shortfalls
    assert shortfall.source == CONFIG_RELATIONSHIP
    assert shortfall.cause is CoverageCause.SCHEMA_DRIFT
    assert "Fraternises with Subnet" in shortfall.detail


# --- what happens when the answer is incomplete -----------------------------


def test_a_refused_aggregator_returns_a_slice_read_rather_than_raising(
    settings: Settings,
) -> None:
    """The one that matters. An exception here would discard every account after
    this one, which is constraint 5 broken at the first refusal."""
    read = source(settings, Client(raises=denied())).read_slice(ACCOUNT, REGION)
    assert read.nodes == ()
    assert read.edges == ()
    assert read.state is CoverageState.PARTIAL
    assert read.cause is CoverageCause.ACCESS_DENIED
    (shortfall,) = read.shortfalls
    assert shortfall.source == "config:SelectAggregateResourceConfig"
    assert "AccessDenied" in shortfall.detail


def test_an_unreachable_endpoint_is_its_own_cause(settings: Settings) -> None:
    failure = EndpointConnectionError(endpoint_url="https://config.eu-west-1.amazonaws.com")
    read = source(settings, Client(raises=failure)).read_slice(ACCOUNT, REGION)
    assert read.cause is CoverageCause.UNREACHABLE


def test_an_unfamiliar_resource_type_is_in_the_graph_and_named(settings: Settings) -> None:
    """OTHER, listed, and the slice stays COMPLETE. Absent would mean the map quietly
    stops drawing four of the most expensive things in an estate, and PARTIAL would
    mean an estate with a fleet of EKS clusters shows a data is missing banner on
    every run forever. ISS-201."""
    cluster = f"arn:aws:eks:{REGION}:{ACCOUNT.account_id}:cluster/platform"
    read = source(
        settings,
        Client(page(item(resourceType="AWS::EKS::Cluster", resourceId=cluster, arn=cluster))),
    ).read_slice(ACCOUNT, REGION)
    (node,) = read.nodes
    assert node.node_kind is NodeKind.OTHER
    assert node.resource_type == "AWS::EKS::Cluster"
    assert read.unmapped == ("AWS::EKS::Cluster",)
    assert read.shortfalls == ()
    assert read.state is CoverageState.COMPLETE


def test_a_resource_with_no_capture_time_is_omitted_and_named(settings: Settings) -> None:
    """Its `as_of` would have to be invented, and an invented `as_of` is a stale
    number wearing a fresh timestamp."""
    read = source(settings, Client(page(item(configurationItemCaptureTime=None)))).read_slice(
        ACCOUNT, REGION
    )
    assert read.nodes == ()
    (shortfall,) = read.shortfalls
    assert shortfall.cause is CoverageCause.SCHEMA_DRIFT
    assert "no capture time" in shortfall.detail


def test_a_result_that_does_not_parse_loses_one_row_not_the_page(
    settings: Settings,
) -> None:
    client = Client({"Results": ["{not json", json.dumps(item())]})
    read = source(settings, client).read_slice(ACCOUNT, REGION)
    assert len(read.nodes) == 1


# --- pagination and retry ---------------------------------------------------


def test_every_page_is_read(settings: Settings) -> None:
    """An unpaginated call does not fail, it returns the first hundred resources and
    a graph that is quietly a hundredth of the estate."""
    second = f"arn:aws:ec2:{REGION}:{ACCOUNT.account_id}:vpc/vpc-02"
    client = Client(page(item(), token="more"), page(item(resourceId=second, arn=second)))
    read = source(settings, client).read_slice(ACCOUNT, REGION)
    assert len(read.nodes) == 2
    assert [request.get("NextToken") for request in client.requests] == [None, "more"]
    assert {request["Limit"] for request in client.requests} == {PAGE_SIZE}


def test_the_query_names_the_account_and_the_region(settings: Settings) -> None:
    client = Client(page(item()))
    source(settings, client).read_slice(ACCOUNT, REGION)
    expression = client.requests[0]["Expression"]
    assert f"accountId = '{ACCOUNT.account_id}'" in expression
    assert f"awsRegion = '{REGION}'" in expression
    assert client.requests[0]["ConfigurationAggregatorName"] == "meter-org"


def test_the_two_slice_queries_partition_the_account(settings: Settings) -> None:
    """The global slice asks for the global types and the regional slice asks for
    everything else in one region. Without the second half the same IAM role would
    arrive once per region, as eleven nodes with eleven regions and one identifier."""
    global_client = Client(page(item()))
    source(settings, global_client).read_slice(ACCOUNT, None)
    global_where = global_client.requests[0]["Expression"].split("WHERE", 1)[1]
    assert "resourceType IN (" in global_where
    assert "'AWS::IAM::Role'" in global_where
    assert "awsRegion =" not in global_where

    regional_client = Client(page(item()))
    source(settings, regional_client).read_slice(ACCOUNT, REGION)
    regional_where = regional_client.requests[0]["Expression"].split("WHERE", 1)[1]
    assert f"awsRegion = '{REGION}'" in regional_where
    assert "resourceType NOT IN (" in regional_where


def test_a_global_type_has_no_region_whatever_config_recorded_it_under(
    settings: Settings,
) -> None:
    """The recording region is a fact about our own Config setup, and storing it
    would put an IAM role on the map in eu-west-1."""
    read = source(
        settings,
        Client(
            page(
                item(
                    resourceType="AWS::IAM::Role",
                    resourceId=ROLE_ARN,
                    arn=ROLE_ARN,
                    awsRegion=REGION,
                )
            )
        ),
    ).read_slice(ACCOUNT, None)
    (node,) = read.nodes
    assert node.region_id is None


def test_a_throttled_page_is_retried_to_the_configured_bound(settings: Settings) -> None:
    client = Client(raises=throttled())
    read = source(settings, client).read_slice(ACCOUNT, REGION)
    assert read.cause is CoverageCause.THROTTLED
    # One first attempt plus the configured retries, and not one more. An unbounded
    # retry against a throttled payer is a run that never ends.
    assert client.raised == settings.aws_max_retries + 1


def test_a_refusal_that_is_not_throttling_is_not_retried(settings: Settings) -> None:
    client = Client(raises=denied())
    source(settings, client).read_slice(ACCOUNT, REGION)
    assert client.raised == 1


def test_the_enrolled_slices_are_the_denominator(settings: Settings) -> None:
    """Handed in, not discovered. The set of slices that should be readable cannot be
    derived from the set that was."""
    assert source(settings, Client()).enrolled_slices == ((ACCOUNT, REGION),)


def test_it_satisfies_the_port(settings: Settings) -> None:
    assert isinstance(source(settings, Client()), TopologySource)


@pytest.mark.parametrize("region", [REGION, None])
def test_an_empty_slice_reads_as_complete_and_empty(settings: Settings, region: str | None) -> None:
    """A slice that genuinely holds nothing is COMPLETE with no nodes, which is the
    distinction the whole sub project exists to keep: not the same as unread."""
    read = source(settings, Client(page())).read_slice(ACCOUNT, region)
    assert read.nodes == ()
    assert read.state is CoverageState.COMPLETE
