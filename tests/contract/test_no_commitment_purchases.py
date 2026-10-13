"""Meter never buys a commitment, and this keeps that true. Constraint 6, P14 rule 1.

P14 reads every commitment the organization holds and drafts purchase plans, and a person buys.
The read only property is worth more than any convenience a purchase call would bring, so this
file asserts an absence in the three places it could be undone: no role is granted an action that
buys, exchanges, sells or queues a commitment; the relay, whose roles reach every member account
and the payer, allow lists no such call; and no production module calls one.

It also holds the payer's grant to exactly the Cost Explorer reads P14 needs, ISS-294, so the role
that gained them is not quietly widened later.
"""

from __future__ import annotations

import pathlib
import re

from finops_relay.relay import ALLOWED

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

#: Every file that grants an AWS permission to a role Meter assumes.
GRANTS = (
    *sorted((ROOT / "infra" / "terraform" / "hub").glob("*.tf")),
    *sorted((ROOT / "infra" / "terraform" / "management").glob("*.tf")),
    ROOT / "infra" / "terraform" / "member" / "collector_role.yaml",
)

PRODUCTION_PACKAGES = (
    "finops_core",
    "finops_providers",
    "finops_ingest",
    "finops_query",
    "finops_api",
    "finops_mcp",
    "finops_relay",
)

#: The services a commitment is bought from.
COMMITMENT_SERVICES = (
    "savingsplans",
    "ec2",
    "rds",
    "elasticache",
    "es",
    "redshift",
    "memorydb",
    "dynamodb",
)

#: An action that changes a commitment: a write verb on anything reserved, or a Savings Plan's.
BUYING_ACTION = re.compile(
    r"\b(?:" + "|".join(COMMITMENT_SERVICES) + r"):(?:"
    r"(?:Purchase|Modify|Accept|Create|Cancel|Delete|Return)\w*Reserv\w*"
    r"|CreateSavingsPlan|ReturnSavingsPlan|DeleteQueuedSavingsPlan|\*)"
)

#: The same calls as boto3 spells its methods, which is how a module would make one.
BUYING_CALL = re.compile(
    r"\b(?:purchase|modify|accept|create|cancel|delete|return)_\w*reserv\w*"
    r"|\bcreate_savings_plan\b|\breturn_savings_plan\b|\bdelete_queued_savings_plan\b"
)

#: The payer's Cost Explorer reads, exactly, TASK-P14-001.
PAYER_COMMITMENT_READS = {
    "ce:GetSavingsPlansUtilization",
    "ce:GetSavingsPlansUtilizationDetails",
    "ce:GetSavingsPlansCoverage",
    "ce:GetReservationUtilization",
    "ce:GetReservationCoverage",
    "ce:GetSavingsPlansPurchaseRecommendation",
    "ce:GetReservationPurchaseRecommendation",
}


def test_the_files_that_grant_permissions_are_found() -> None:
    # A glob that stopped matching would make every assertion below vacuous.
    assert len(GRANTS) > 3
    assert all(path.exists() for path in GRANTS)


def test_no_role_is_granted_an_action_that_buys_a_commitment() -> None:
    found = {
        f"{path.relative_to(ROOT)}: {match.group(0)}"
        for path in GRANTS
        for match in BUYING_ACTION.finditer(path.read_text(encoding="utf-8"))
    }
    assert found == set()


def test_the_relay_allow_lists_no_call_that_buys_a_commitment() -> None:
    writes = re.compile(r"^(?:Purchase|Modify|Accept|Create|Cancel|Delete|Return|Put|Update)")
    assert {operation for _service, operation in ALLOWED if writes.match(operation)} == set()


def test_no_production_module_calls_a_purchase() -> None:
    found = {
        f"{path.relative_to(ROOT)}: {match.group(0)}"
        for package in PRODUCTION_PACKAGES
        for path in sorted((ROOT / package).rglob("*.py"))
        for match in BUYING_CALL.finditer(path.read_text(encoding="utf-8"))
    }
    assert found == set()


def test_the_payer_is_granted_exactly_the_commitment_reads() -> None:
    management = (ROOT / "infra" / "terraform" / "management" / "main.tf").read_text(
        encoding="utf-8"
    )
    granted = set(re.findall(r'"(ce:\w+)"', management))
    assert granted == PAYER_COMMITMENT_READS


def test_the_pattern_would_catch_a_purchase() -> None:
    """The check is only as good as its pattern, so the pattern is checked against the calls."""
    for action in (
        "savingsplans:CreateSavingsPlan",
        "ec2:PurchaseReservedInstancesOffering",
        "ec2:AcceptReservedInstancesExchangeQuote",
        "rds:PurchaseReservedDBInstancesOffering",
        "redshift:AcceptReservedNodeExchange",
        "ec2:*",
    ):
        assert BUYING_ACTION.search(f'"{action}"'), action
    assert not BUYING_ACTION.search('"ec2:DescribeReservedInstances"')
    assert BUYING_CALL.search("client.purchase_reserved_instances_offering(")
    assert not BUYING_CALL.search("client.describe_reserved_instances(")
