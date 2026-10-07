"""The relay outside the VPC and the hub's client for it. TASK-P9-001, ADR-0035.

The relay is held to three promises: it makes only the calls `ALLOWED` names, as the role the
list names and narrowed to the one action; an answer comes back as boto3 gave it, timestamps
included; and a refusal comes back as AWS's own code. The strongest test here runs the existing
adapters unchanged through the client and an in process relay, because the point of the design
is that no adapter needs a second implementation for the path its calls take.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from finops_core.errors import AccessDenied, Throttled
from finops_providers.aws.budgets import AwsBudgets
from finops_providers.aws.invoices import AwsInvoices
from finops_providers.aws.relay_client import RelayClient, lambda_invoke, s3_fetch
from finops_relay.relay import (
    ALLOWED,
    PREFIX,
    REFUSED,
    UNREACHED,
    AssumingSessions,
    RefusedError,
    Relay,
    RoleKind,
    decode,
    encode,
    parse,
    session_policy,
)

PAYER = "111122223333"
ISSUED = datetime(2026, 9, 3, 6, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 7, 6, 0, tzinfo=UTC)

BUDGET = {
    "BudgetName": "All accounts",
    "BudgetLimit": {"Amount": "1000", "Unit": "USD"},
    "TimeUnit": "MONTHLY",
    "BudgetType": "COST",
    "TimePeriod": {"Start": datetime(2026, 9, 1, tzinfo=UTC), "End": datetime(2087, 6, 15)},
}
INVOICE = {
    "AccountId": PAYER,
    "InvoiceId": "inv-2026-08",
    "IssuedDate": ISSUED,
    "Entity": {"InvoicingEntity": "Amazon Web Services, Inc."},
    "BillingPeriod": {"Month": 8, "Year": 2026},
    "InvoiceType": "INVOICE",
    "BaseCurrencyAmount": {
        "TotalAmountBeforeTax": "100.00",
        "TotalAmount": "110.00",
        "CurrencyCode": "USD",
        "AmountBreakdown": {"Taxes": {"TotalAmount": "10.00"}},
    },
}


class _Paginator:
    def __init__(self, pages: list[Any]) -> None:
        self._pages = pages

    def paginate(self, **_: Any) -> Any:
        return iter(self._pages)


class _AwsClient:
    def __init__(self, pages: dict[str, list[Any]], failure: Exception | None = None) -> None:
        self._pages = pages
        self._failure = failure

    def get_paginator(self, name: str) -> _Paginator:
        if self._failure is not None:
            raise self._failure
        return _Paginator(self._pages[name])

    def describe_trusted_advisor_checks(self, **_: Any) -> Any:
        if self._failure is not None:
            raise self._failure
        return {"checks": [{"id": "check-1", "name": "Service Limits"}]}


#: Every client the stubbed sessions made, as (service, Region).
MADE: list[tuple[str, str]] = []


class _Session:
    def __init__(self, client: _AwsClient) -> None:
        self._client = client

    def client(self, service: str, region_name: str) -> _AwsClient:
        MADE.append((service, region_name))
        return self._client


def relayed(aws: _AwsClient) -> tuple[Relay, dict[str, bytes], list[Any]]:
    """A relay over a stubbed AWS, its bucket, and the requests it was asked to make."""
    bucket: dict[str, bytes] = {}
    asked: list[Any] = []

    def session_for(request: Any) -> _Session:
        asked.append(request)
        return _Session(aws)

    relay = Relay(session_for=session_for, put=bucket.__setitem__)
    return relay, bucket, asked


def client_for(relay: Relay, bucket: dict[str, bytes], service: str) -> RelayClient:
    return RelayClient(
        service=service,
        region="us-east-1",
        account_id=PAYER,
        invoke=relay,
        fetch=bucket.__getitem__,
    )


# --- the allow list -----------------------------------------------------------


def test_every_call_allowed_is_read_only_and_names_its_role() -> None:
    for (service, operation), allowed in ALLOWED.items():
        assert operation.startswith(("Describe", "List", "Get")), (service, operation)
        assert allowed.action.split(":")[0] == service, (service, allowed.action)
        assert isinstance(allowed.role, RoleKind)


@pytest.mark.parametrize(
    ("event", "says"),
    [
        (
            {"service": "ec2", "operation": "TerminateInstances", "region": "eu-west-1"},
            "not a call",
        ),
        ({"service": "budgets", "operation": "DescribeBudgets", "region": "us-east-1"}, "account"),
        ({"service": "budgets", "operation": "DescribeBudgets", "account_id": PAYER}, "Region"),
    ],
)
def test_a_request_outside_the_list_is_refused_before_any_client(
    event: dict[str, Any], says: str
) -> None:
    with pytest.raises(RefusedError, match=says):
        parse(event)
    relay, bucket, asked = relayed(_AwsClient({}))
    answer = relay(event)
    assert answer["error"]["Code"] == REFUSED
    assert asked == [] and bucket == {}


def test_the_relays_own_calls_name_no_account() -> None:
    request = parse(
        {
            "service": "ec2",
            "operation": "DescribeSpotPriceHistory",
            "region": "eu-west-2",
            "account_id": "someone-else",
        }
    )
    assert request.account_id is None


def test_an_assumed_role_is_narrowed_to_the_one_action() -> None:
    request = parse(
        {
            "service": "invoicing",
            "operation": "ListInvoiceSummaries",
            "region": "us-east-1",
            "account_id": PAYER,
        }
    )
    policy = json.loads(session_policy(request))
    assert policy["Statement"] == [
        {"Effect": "Allow", "Action": "invoicing:ListInvoiceSummaries", "Resource": "*"}
    ]


# --- the codec ----------------------------------------------------------------


def test_timestamps_come_back_as_timestamps() -> None:
    pages = [{"IssuedDate": ISSUED, "Day": date(2026, 8, 1), "Amount": "1.00", "Nested": [{}]}]
    restored = decode(encode(pages))
    assert restored[0]["IssuedDate"] == ISSUED
    assert restored[0]["Day"] == datetime(2026, 8, 1)
    assert restored[0]["Amount"] == "1.00"


def test_a_value_aws_never_sends_is_refused_rather_than_stringified() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        encode([{"x": Decimal("1")}])


# --- the existing adapters, unchanged, through the relay --------------------


def test_the_budgets_adapter_reads_through_the_relay_unchanged() -> None:
    relay, bucket, asked = relayed(_AwsClient({"describe_budgets": [{"Budgets": [BUDGET]}]}))
    found = AwsBudgets(
        client=client_for(relay, bucket, "budgets"), account_id=PAYER, clock=lambda: NOW
    ).budgets()
    (budget,) = tuple(found)
    assert budget.limit == Decimal("1000")
    assert MADE[-1] == ("budgets", "us-east-1")
    assert asked[0].allowed.role is RoleKind.MANAGEMENT
    assert all(key.startswith(f"{PREFIX}/budgets/DescribeBudgets/") for key in bucket)


def test_the_invoice_adapter_reads_through_the_relay_with_its_timestamps() -> None:
    relay, bucket, _ = relayed(
        _AwsClient({"list_invoice_summaries": [{"InvoiceSummaries": [INVOICE]}]})
    )
    found = AwsInvoices(
        client=client_for(relay, bucket, "invoicing"), account_id=PAYER, clock=lambda: NOW
    ).invoices(date(2026, 8, 1), date(2026, 9, 1))
    (invoice,) = tuple(found)
    assert invoice.issued_at == ISSUED
    assert invoice.billed_cost == Decimal("110.00")


@pytest.mark.parametrize(
    ("code", "cause"),
    [("AccessDeniedException", AccessDenied), ("ThrottlingException", Throttled)],
)
def test_a_refusal_reaches_the_adapter_as_the_cause_it_was(
    code: str, cause: type[Exception]
) -> None:
    failure = ClientError({"Error": {"Code": code, "Message": "no"}}, "ListInvoiceSummaries")
    relay, bucket, _ = relayed(_AwsClient({}, failure))
    with pytest.raises(cause):
        tuple(
            AwsInvoices(
                client=client_for(relay, bucket, "invoicing"), account_id=PAYER, clock=lambda: NOW
            ).invoices(date(2026, 8, 1), date(2026, 9, 1))
        )
    assert bucket == {}


def test_a_call_that_never_reached_aws_says_so() -> None:
    relay, _, _ = relayed(_AwsClient({}, EndpointConnectionError(endpoint_url="https://x")))
    answer = relay(
        {
            "service": "support",
            "operation": "DescribeTrustedAdvisorChecks",
            "params": {"language": "en"},
            "region": "us-east-1",
            "account_id": PAYER,
        }
    )
    assert answer["error"]["Code"] == UNREACHED


def test_a_single_call_is_answered_as_one_page() -> None:
    relay, bucket, _ = relayed(_AwsClient({}))
    support = client_for(relay, bucket, "support")
    assert support.describe_trusted_advisor_checks(language="en")["checks"][0]["id"] == "check-1"


def test_a_method_the_service_does_not_have_is_an_attribute_error() -> None:
    support = RelayClient(
        service="support",
        region="us-east-1",
        account_id=PAYER,
        invoke=lambda _event: {},
        fetch=lambda _key: b"[]",
    )
    with pytest.raises(AttributeError):
        support.launch_rockets()


# --- production wiring, with AWS stubbed ------------------------------------


class _Boto3:
    """The slice of the boto3 module `AssumingSessions` uses."""

    def __init__(self) -> None:
        self.assumed: list[dict[str, Any]] = []
        self.secrets_read = 0
        self.sessions: list[dict[str, Any]] = []
        self.regions: list[str] = []

    def Session(self, **credentials: Any) -> dict[str, Any]:  # noqa: N802, boto3's own name
        self.sessions.append(credentials)
        return credentials

    def client(self, service: str, region_name: str) -> Any:
        boto3 = self
        self.regions.append(region_name)

        class _Client:
            def assume_role(self, **request: Any) -> Any:
                boto3.assumed.append(request)
                keys = {"AccessKeyId": "a", "SecretAccessKey": "b", "SessionToken": "c"}
                return {"Credentials": keys}

            def get_secret_value(self, **_: Any) -> Any:
                boto3.secrets_read += 1
                return {"SecretString": "the-external-id"}

        assert service in {"sts", "secretsmanager"}, service
        return _Client()


ENVIRON = {
    "METER_ORG_READER_ROLE_ARN": "arn:aws:iam::999988887777:role/FinOpsOrgReader",
    "METER_COLLECTOR_ROLE_NAME": "FinOpsCollectorRole",
    "METER_EXTERNAL_ID_SECRET": "meter/external-id",
}


def request_for(service: str, operation: str) -> Any:
    return parse(
        {"service": service, "operation": operation, "region": "us-east-1", "account_id": PAYER}
    )


def test_a_payer_read_assumes_the_organization_reader_narrowed_to_one_action() -> None:
    boto3 = _Boto3()
    AssumingSessions(ENVIRON, boto3)(request_for("budgets", "DescribeBudgets"))
    (assumed,) = boto3.assumed
    assert assumed["RoleArn"] == ENVIRON["METER_ORG_READER_ROLE_ARN"]
    assert assumed["ExternalId"] == "the-external-id"
    assert set(boto3.regions) == {"us-east-1"}
    assert json.loads(assumed["Policy"])["Statement"][0]["Action"] == "budgets:ViewBudget"


def test_a_member_read_assumes_that_accounts_collector_role() -> None:
    boto3 = _Boto3()
    sessions = AssumingSessions(ENVIRON, boto3)
    sessions(request_for("support", "DescribeTrustedAdvisorChecks"))
    sessions(request_for("support", "DescribeTrustedAdvisorCheckResult"))
    assert boto3.assumed[0]["RoleArn"] == f"arn:aws:iam::{PAYER}:role/FinOpsCollectorRole"
    # The ExternalId is read once per container, not once per call.
    assert boto3.secrets_read == 1


def test_the_relays_own_read_assumes_nothing() -> None:
    boto3 = _Boto3()
    request = parse(
        {"service": "ec2", "operation": "DescribeSpotPriceHistory", "region": "eu-west-2"}
    )
    AssumingSessions(ENVIRON, boto3)(request)
    assert boto3.assumed == []
    assert boto3.sessions == [{}]


def test_the_lambda_invoke_and_s3_fetch_carry_the_answer_and_a_failure() -> None:
    class _Payload:
        def __init__(self, body: Any) -> None:
            self._body = json.dumps(body).encode()

        def read(self) -> bytes:
            return self._body

    class _Lambda:
        def __init__(self, failing: bool) -> None:
            self._failing = failing

        def invoke(self, **_: Any) -> Any:
            if self._failing:
                return {"FunctionError": "Unhandled", "Payload": _Payload({"errorMessage": "x"})}
            return {"Payload": _Payload({"key": "relay/k", "pages": 1})}

    assert lambda_invoke(_Lambda(False), "fn")({})["key"] == "relay/k"
    assert lambda_invoke(_Lambda(True), "fn")({})["error"]["Code"] == "RelayFailed"

    class _S3:
        def get_object(self, **asked: Any) -> Any:
            return {"Body": _Payload([asked["Key"]])}

    assert json.loads(s3_fetch(_S3(), "bucket")("relay/k")) == ["relay/k"]


@pytest.mark.parametrize(
    "region",
    ["eu-west-2", "us-east-1", "cn-north-1", "us-gov-west-1", "us-iso-east-1", "us-isob-east-1"],
)
def test_the_relays_copy_of_the_role_arn_matches_the_adapters(region: str) -> None:
    """A copy, so the relay needs nothing beyond boto3, held equal to the one it copies."""
    from finops_providers.aws.client import role_arn as adapters
    from finops_relay.relay import role_arn as relays

    assert relays(PAYER, "FinOpsCollectorRole", region) == adapters(
        PAYER, "FinOpsCollectorRole", region
    )
