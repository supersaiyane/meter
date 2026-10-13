"""What each account holds, read from Savings Plans, EC2 and RDS. TASK-P14-002, FEAT-086.

Every answer here goes through botocore's Stubber, which refuses a response that does not match
the service's own model, so the shapes this adapter reads are AWS's and not invented. The failures
that matter: a refusal is AccessDenied and never an account holding nothing, a field the model
promises and an answer lacks is SchemaDrift, and every page of a paged answer is read.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import boto3
import pytest
from botocore.stub import Stubber

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.commitments import EC2, RDS, RESERVATION, SAVINGS_PLAN
from finops_core.errors import AccessDenied, SchemaDrift
from finops_providers.aws.commitment_inventory import AwsCommitmentHoldings

TENANT = uuid4()
ACCOUNT = AccountKey(provider=Provider.AWS, account_id="111122223333")
REGION = "eu-west-1"
AT = datetime(2026, 10, 13, 6, tzinfo=UTC)
YEAR = 31536000
START = datetime(2026, 1, 1, tzinfo=UTC)


def client(service: str, region: str = REGION) -> Any:
    return boto3.client(
        service, region_name=region, aws_access_key_id="x", aws_secret_access_key="y"
    )


def holdings(
    *, savings_plans: Any = None, ec2: Any = None, rds: Any = None
) -> AwsCommitmentHoldings:
    reservations: dict[str, Any] = {}
    if ec2 is not None:
        reservations[EC2] = lambda _account, _region: ec2
    if rds is not None:
        reservations[RDS] = lambda _account, _region: rds
    return AwsCommitmentHoldings(
        TENANT,
        savings_plans_for=lambda _account: savings_plans,
        reservations_for=reservations,
        clock=lambda: AT,
    )


def plan(plan_id: str, **overrides: Any) -> dict[str, Any]:
    found = {
        "savingsPlanId": plan_id,
        "savingsPlanType": "Compute",
        "paymentOption": "No Upfront",
        "termDurationInSeconds": YEAR,
        "commitment": "3.2",
        "upfrontPaymentAmount": "0",
        "recurringPaymentAmount": "3.2",
        "currency": "USD",
        "start": "2026-01-01T00:00:00.000Z",
        "end": "2027-01-01T00:00:00.000Z",
        "state": "active",
        "region": "",
    }
    found.update(overrides)
    return found


def test_savings_plans_are_read_to_the_last_page_with_their_real_term() -> None:
    sp = client("savingsplans", "us-east-1")
    with Stubber(sp) as stub:
        stub.add_response(
            "describe_savings_plans", {"savingsPlans": [plan("sp-1")], "nextToken": "more"}
        )
        stub.add_response(
            "describe_savings_plans",
            {
                "savingsPlans": [
                    plan(
                        "sp-2",
                        savingsPlanType="EC2Instance",
                        region="eu-west-1",
                        ec2InstanceFamily="m5",
                        termDurationInSeconds=3 * YEAR,
                        paymentOption="Partial Upfront",
                        upfrontPaymentAmount="14454",
                    )
                ]
            },
            {"nextToken": "more"},
        )
        found = list(holdings(savings_plans=sp).savings_plans(ACCOUNT))
    by_id = {one.commitment_id: one for one in found}
    assert set(by_id) == {"sp-1", "sp-2"}
    compute = by_id["sp-1"]
    assert (compute.kind, compute.program, compute.region_id, compute.term_months) == (
        SAVINGS_PLAN,
        "Compute",
        None,
        12,
    )
    assert compute.hourly_commitment == Decimal("3.2") and compute.quantity is None
    assert compute.ends_at - compute.starts_at == timedelta(days=365)
    ec2_plan = by_id["sp-2"]
    assert (ec2_plan.region_id, ec2_plan.applies_to, ec2_plan.term_months) == (
        "eu-west-1",
        "m5",
        36,
    )
    assert ec2_plan.upfront_amount == Decimal("14454")


def test_ec2_and_rds_reservations_are_read_with_their_counts_and_ends() -> None:
    ec2, rds = client("ec2"), client("rds")
    with Stubber(ec2) as ec2_stub, Stubber(rds) as rds_stub:
        ec2_stub.add_response(
            "describe_reserved_instances",
            {
                "ReservedInstances": [
                    {
                        "ReservedInstancesId": "ri-ec2-1",
                        "InstanceType": "m5.large",
                        "InstanceCount": 4,
                        "Start": START,
                        "End": START + timedelta(days=365),
                        "Duration": YEAR,
                        "OfferingType": "No Upfront",
                        "FixedPrice": 0.0,
                        "UsagePrice": 0.0,
                        "RecurringCharges": [{"Amount": 0.244, "Frequency": "Hourly"}],
                        "CurrencyCode": "USD",
                        "State": "active",
                    }
                ]
            },
        )
        rds_stub.add_response(
            "describe_reserved_db_instances",
            {
                "ReservedDBInstances": [
                    {
                        "ReservedDBInstanceId": "ri-rds-1",
                        "DBInstanceClass": "db.r6g.large",
                        "DBInstanceCount": 2,
                        "StartTime": START,
                        "Duration": YEAR,
                        "OfferingType": "All Upfront",
                        "FixedPrice": 3504.0,
                        "UsagePrice": 0.0,
                        "RecurringCharges": [],
                        "CurrencyCode": "USD",
                        "State": "active",
                    }
                ]
            },
        )
        found = list(holdings(ec2=ec2, rds=rds).reservations(ACCOUNT, REGION))
    by_id = {one.commitment_id: one for one in found}
    ec2_ri, rds_ri = by_id["ri-ec2-1"], by_id["ri-rds-1"]
    assert (ec2_ri.kind, ec2_ri.program, ec2_ri.quantity, ec2_ri.region_id) == (
        RESERVATION,
        EC2,
        4,
        REGION,
    )
    assert ec2_ri.recurring_hourly == Decimal("0.244") and ec2_ri.hourly_commitment is None
    # RDS states a start and a length, never an end; the end is the start plus the length.
    assert (rds_ri.program, rds_ri.quantity, rds_ri.ends_at) == (
        RDS,
        2,
        START + timedelta(seconds=YEAR),
    )
    assert rds_ri.upfront_amount == Decimal("3504.0")


def test_an_account_that_refuses_is_access_denied_never_one_holding_nothing() -> None:
    ec2 = client("ec2")
    with Stubber(ec2) as stub:
        stub.add_client_error(
            "describe_reserved_instances", service_error_code="UnauthorizedOperation"
        )
        with pytest.raises(AccessDenied):
            list(holdings(ec2=ec2).reservations(ACCOUNT, REGION))


def test_a_field_the_model_promises_and_the_answer_lacks_is_schema_drift() -> None:
    sp = client("savingsplans", "us-east-1")
    broken = plan("sp-1")
    del broken["commitment"]
    with Stubber(sp) as stub:
        stub.add_response("describe_savings_plans", {"savingsPlans": [broken]})
        with pytest.raises(SchemaDrift, match="cannot read"):
            list(holdings(savings_plans=sp).savings_plans(ACCOUNT))


class Relayed:
    """The relay client in shape: every page from its paginator, as the relay follows tokens."""

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages

    def get_paginator(self, _method: str) -> Any:
        pages = self.pages
        return type("Paginator", (), {"paginate": lambda _self: iter(pages)})()


def test_a_relayed_answer_is_read_from_its_pages_with_times_as_strings() -> None:
    relayed = Relayed([{"savingsPlans": [plan("sp-1")]}, {"savingsPlans": [plan("sp-2")]}])
    found = list(holdings(savings_plans=relayed).savings_plans(ACCOUNT))
    assert [one.commitment_id for one in found] == ["sp-1", "sp-2"]
    assert found[0].starts_at == START


def test_a_service_with_no_reader_is_refused_when_built() -> None:
    with pytest.raises(ValueError, match="no reader"):
        AwsCommitmentHoldings(
            TENANT,
            savings_plans_for=lambda _a: None,
            reservations_for={"DynamoDB": lambda *_: None},
        )
