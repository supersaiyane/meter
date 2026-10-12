"""Every AWS service the hub calls has a way out of its VPC. TASK-P9-001, ADR-0035.

ISS-242: a deployed hub could reach six services while the collectors called about fifteen more,
and nothing said so, because the list of endpoints and the list of calls lived in different
places. This holds the two together. The services the code calls are read from the code, by
the calls that make clients and by the operations `test_response_shapes.py` declares for every
adapter, and each is held to the path the owner chose on 2026-10-05 in P9 spec section 5.1:

- an interface endpoint in the hub's Region, `network.tf`;
- for the services that answer only in us-east-1, the endpoint VPC there, `endpoints.tf`;
- for what the collectors call in each member account, an endpoint in every collection Region;
- for S3, the gateway endpoint;
- for the three with no interface endpoint, Budgets, Support and Invoicing, the relay outside
  the VPC, `relay.tf` and `finops_relay/relay.py`, which also carries spot prices and Savings
  Plans rates, the owner's answer to OPEN-17.

A collector that calls something new fails here rather than on its first call in a deployment.

And one path that is not AWS: OpenAI's and Anthropic's report APIs, through the NAT gateway the
owner chose on 2026-10-12, OPEN-31, which only the worker's security group may use, ADR-0036.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import botocore.session
import pytest

from finops_relay.relay import ALLOWED, PREFIX, RoleKind
from tests.providers.aws.test_response_shapes import READS

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / "infra" / "terraform" / "hub"
MODULE = HUB / "modules" / "endpoint_vpc"
MANAGEMENT = ROOT / "infra" / "terraform" / "management" / "main.tf"
MEMBER = ROOT / "infra" / "terraform" / "member" / "collector_role.yaml"

#: The production packages whose AWS calls the hub makes.
CALLERS = ("finops_providers", "finops_api", "finops_ingest")
#: Names a call makes a client through, whose first argument is the service.
CLIENT_MAKERS = frozenset(
    {"client", "_client", "_factory", "_client_for", "_call", "_pages", "_default_client"}
)

#: Where an SDK service's interface endpoint differs from its name.
ENDPOINT_NAMES = {"cloudwatch": "monitoring", "service-quotas": "servicequotas"}
#: The services that answer only in us-east-1, or only there among the Regions Meter uses.
GLOBAL_ONLY = frozenset({"ce", "organizations", "iam", "cost-optimization-hub", "pricing"})
#: The services with no interface endpoint, measured against the AWS PrivateLink service list on
#: 2026-10-05 for Budgets and Support and on 2026-10-08 for Invoicing.
NO_ENDPOINT = frozenset({"budgets", "support", "invoicing"})
#: The services read through the relay by the owner's choice rather than for want of an endpoint:
#: Savings Plans rates, OPEN-17 as answered on 2026-10-07, TASK-P9-012. Spot prices are an ec2
#: call, which has an endpoint in the hub and is relayed into the other Regions.
RELAYED = frozenset({"savingsplans"})
#: The hosts outside AWS the worker reaches through the NAT gateway, ADR-0036. Nothing else in
#: the production code names a host outside AWS, which `test_no_host_outside_aws_but_these` holds.
INTERNET_HOSTS = frozenset({"api.openai.com", "api.anthropic.com"})
#: What the collectors call in each member account, in every collection Region.
PER_COLLECTION_REGION = frozenset(
    {
        "ec2",
        "cloudwatch",
        "logs",
        "cloudtrail",
        "service-quotas",
        "compute-optimizer",
        # FEAT-077, TASK-P11-003. Applications live in each member account.
        "servicecatalog-appregistry",
    }
)


def text(path: Path) -> str:
    """A file with its comments removed, so a word in a comment is never read as configuration."""
    lines = [line.split("#", 1)[0] for line in path.read_text().splitlines()]
    return "\n".join(lines)


def quoted(block: str) -> set[str]:
    return set(re.findall(r'"([^"]+)"', block))


def hcl_list(path: Path, name: str) -> set[str]:
    match = re.search(rf"{name}\s*=\s*\[(.*?)\]", text(path), re.DOTALL)
    assert match is not None, f"{name} not found in {path.name}"
    return quoted(match.group(1))


def literal_services() -> set[str]:
    """Every literal service a production module makes a client for."""
    available = set(botocore.session.get_session().get_available_services())
    found: set[str] = set()
    for package in CALLERS:
        for path in (ROOT / package).rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and node.args:
                    func = node.func
                    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                    first = node.args[0]
                    if (
                        name in CLIENT_MAKERS
                        and isinstance(first, ast.Constant)
                        and first.value in available
                    ):
                        found.add(str(first.value))
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                    targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
                    named = any(t == "SERVICE" or t.endswith("_SERVICE") for t in targets)
                    if named and node.value.value in available:
                        found.add(str(node.value.value))
    return found


def called() -> set[str]:
    return literal_services() | {service for service, _ in READS}


def hub_endpoints() -> set[str]:
    return hcl_list(HUB / "network.tf", "interface_endpoints")


def global_endpoints() -> set[str]:
    match = re.search(
        r"global_endpoints\s*=\s*\{(.*?)\n  \}\n", text(HUB / "endpoints.tf"), re.DOTALL
    )
    assert match is not None
    return set(re.findall(r"^\s{4}([a-z0-9-]+)\s*=\s*\{", match.group(1), re.MULTILINE))


def second_endpoints() -> set[str]:
    return hcl_list(HUB / "endpoints.tf", "collection_services")


def endpoint_name(service: str) -> str:
    return ENDPOINT_NAMES.get(service, service)


def relay_services() -> set[str]:
    return {service for service, _ in ALLOWED}


# --- what the code calls ------------------------------------------------------


def test_the_scan_finds_what_the_adapters_call() -> None:
    """A scan that found nothing would pass every test below."""
    assert {"ec2", "ce", "organizations", "cloudwatch", "support", "athena"} <= called()
    assert len(called()) >= 18


@pytest.mark.parametrize("service", sorted(called()))
def test_every_service_called_has_a_path(service: str) -> None:
    if service == "s3":
        assert 'service_name      = "com.amazonaws.${var.region}.s3"' in text(HUB / "network.tf")
        assert 'vpc_endpoint_type = "Gateway"' in text(HUB / "network.tf")
    elif service in NO_ENDPOINT:
        assert service in relay_services(), f"{service} has no endpoint and is not relayed"
    elif service in RELAYED:
        assert service in relay_services(), f"{service} is to be relayed and the relay refuses it"
    elif service in GLOBAL_ONLY:
        assert service in global_endpoints(), (
            f"{service} answers in us-east-1 and has no endpoint there"
        )
    else:
        assert endpoint_name(service) in hub_endpoints(), f"{service} has no endpoint in the hub"


@pytest.mark.parametrize("service", sorted(PER_COLLECTION_REGION))
def test_each_collection_region_has_what_the_collectors_call_there(service: str) -> None:
    assert endpoint_name(service) in hub_endpoints()
    assert endpoint_name(service) in second_endpoints()


def test_a_service_with_no_endpoint_is_given_none() -> None:
    names = hub_endpoints() | global_endpoints() | second_endpoints()
    assert not (NO_ENDPOINT & names)


def test_the_relay_is_invoked_through_an_endpoint() -> None:
    assert "lambda" in hub_endpoints()


# --- the relay ----------------------------------------------------------------


def test_spot_prices_and_savings_plans_rates_take_the_relay() -> None:
    """The owner's answer to OPEN-17 on 2026-10-07, in every Region, outside the VPC."""
    assert ("ec2", "DescribeSpotPriceHistory") in ALLOWED
    assert ("savingsplans", "DescribeSavingsPlansOfferingRates") in ALLOWED


def test_the_relay_has_no_vpc_and_writes_where_the_bucket_expires_it() -> None:
    relay = text(HUB / "relay.tf")
    assert 'resource "aws_lambda_function" "relay"' in relay
    assert "vpc_config" not in relay
    assert f'relay_prefix = "{PREFIX}"' in text(HUB / "network.tf")
    assert 'id     = "expire-relay-answers"' in text(HUB / "storage.tf")


@pytest.mark.parametrize(
    ("kind", "where"),
    [
        (RoleKind.OWN, HUB / "relay.tf"),
        (RoleKind.MANAGEMENT, MANAGEMENT),
        (RoleKind.MEMBER, MEMBER),
    ],
)
def test_each_role_grants_what_the_relay_asks_it_for(kind: RoleKind, where: Path) -> None:
    granted = where.read_text()
    for allowed in ALLOWED.values():
        if allowed.role is kind:
            assert allowed.action in granted, f"{allowed.action} is not granted in {where.name}"


def test_the_roles_the_relay_assumes_trust_it_by_name() -> None:
    assert "var.hub_relay_role_name" in text(MANAGEMENT)
    assert "${RelayRoleName}" in MEMBER.read_text()


# --- no way out but these -------------------------------------------------------


def test_the_one_nat_gateway_is_the_workers_in_a_public_subnet() -> None:
    """ADR-0036. One gateway, in a public subnet, and none in an endpoint VPC."""
    every = "\n".join(text(path) for path in HUB.rglob("*.tf"))
    gateways = re.findall(r'resource "aws_nat_gateway" "([a-z_]+)" \{(.*?)\n\}', every, re.DOTALL)
    assert [name for name, _ in gateways] == ["providers"]
    assert "aws_subnet.public[0].id" in gateways[0][1]
    assert "aws_internet_gateway" not in text(MODULE / "main.tf")
    assert "aws_nat_gateway" not in text(MODULE / "main.tf")


def test_the_private_route_table_leads_to_the_endpoint_vpcs_and_the_nat_gateway() -> None:
    network = text(HUB / "network.tf")
    private = re.search(r'resource "aws_route_table" "private" \{(.*?)\n\}', network, re.DOTALL)
    assert private is not None and "route {" not in private.group(1)
    every = "\n".join(text(path) for path in HUB.glob("*.tf"))
    routes = re.findall(r'resource "aws_route" "[a-z_]+" \{(.*?)\n\}', every, re.DOTALL)
    to_private = [route for route in routes if "aws_route_table.private.id" in route]
    assert len(to_private) == 3
    peered = [route for route in to_private if "vpc_peering_connection_id" in route]
    assert len(peered) == 2
    for route in peered:
        assert "0.0.0.0/0" not in route and "gateway_id" not in route
    (out,) = [route for route in to_private if route not in peered]
    assert "aws_nat_gateway.providers.id" in out and '"0.0.0.0/0"' in out


def egress_rules() -> list[str]:
    every = "\n".join(text(path) for path in HUB.glob("*.tf"))
    return re.findall(
        r'resource "aws_vpc_security_group_egress_rule" "[a-z_]+" \{(.*?)\n\}', every, re.DOTALL
    )


def test_only_the_workers_group_may_reach_the_internet_and_only_on_443() -> None:
    """ADR-0036. A route out exists for every task; one group's one rule lets a task use it."""
    every = "\n".join(text(path) for path in HUB.glob("*.tf"))
    outward = [rule for rule in egress_rules() if "0.0.0.0/0" in rule or "::/0" in rule]
    assert len(outward) == 1
    (rule,) = outward
    assert "aws_security_group.worker_internet.id" in rule
    assert re.search(r"from_port\s*=\s*443", rule) and re.search(r"to_port\s*=\s*443", rule)
    assert '"tcp"' in rule
    inline = re.findall(r"egress \{(.*?)\}", every, re.DOTALL)
    assert not [block for block in inline if "0.0.0.0/0" in block or "::/0" in block]


def test_only_the_worker_service_carries_the_internet_group() -> None:
    every = "\n".join(text(path) for path in HUB.glob("*.tf"))
    users = re.findall(r'resource "([a-z_]+)" "([a-z_]+)" \{(.*?)\n\}', every, re.DOTALL)
    carrying = [
        (kind, name)
        for kind, name, body in users
        if "aws_security_group.worker_internet.id" in body and "security_groups" in body
    ]
    assert carrying == [("aws_ecs_service", "worker")]


def test_no_host_outside_aws_but_these() -> None:
    """A production module that names a new host outside AWS fails here, not in a deployment."""
    hosts: set[str] = set()
    for package in CALLERS:
        for path in (ROOT / package).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    hosts.update(re.findall(r"https://([a-z0-9.-]+\.[a-z]{2,})", node.value))
    # docs.aws.amazon.com is named in remediation text for a person to read, never called.
    aws = ("amazonaws.com", "aws.amazon.com")
    outside = {host for host in hosts if not host.endswith(aws)}
    assert outside <= INTERNET_HOSTS


def test_an_endpoint_vpcs_one_route_leads_back_to_the_hub() -> None:
    module = text(MODULE / "main.tf")
    routes = re.findall(r'resource "aws_route" "[a-z_]+" \{(.*?)\n\}', module, re.DOTALL)
    assert len(routes) == 1
    assert "var.hub_cidr" in routes[0] and "vpc_peering_connection_id" in routes[0]


def test_every_provider_tags_what_it_makes_with_the_module() -> None:
    """Constraint 7. Every resource in all three Regions carries finops:module."""
    versions = text(HUB / "versions.tf")
    providers = re.findall(r'provider "aws" \{(.*?)\n\}', versions, re.DOTALL)
    assert len(providers) == 3
    assert all("tags = local.default_tags" in provider for provider in providers)
    assert '"finops:module" = "hub"' in versions


def test_the_deploy_builds_the_relay_before_it_plans_or_applies() -> None:
    pipeline = (ROOT / ".gitlab-ci.yml").read_text()
    assert "build:relay:" in pipeline
    assert pipeline.count('"build:relay"') == 2
