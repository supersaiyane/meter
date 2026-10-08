"""The relay outside the VPC: one allow listed, read only AWS call, answered through S3.

TASK-P9-001, ADR-0035, P9 spec section 5.1. The hub has no route out, and three services it
calls have no interface endpoint: Budgets, Support and Invoicing. Spot prices and Savings Plans
rates in every Region come this way too, the owner's answer to OPEN-17. This module runs as a
Lambda function with no VPC. The hub invokes it through the Lambda interface endpoint, it makes
exactly one call, or one paginated call, and writes the answer to the data bucket, which the
hub reads through its S3 gateway endpoint. Cadence stays in `collector_schedule`, constraint 9,
because the hub decides when to ask.

**Allow listed, and the role is not the caller's to choose.** Each call the relay will make is
named in `ALLOWED` with the IAM action it needs and the role it is made as: the payer's
organization reader, a member account's collector role, or the function's own. Anything else is
refused before a client exists. A role it assumes is narrowed by a session policy to the one
action, so even a relay that was edited to call something else could not, constraint 6.

**One paginated call is every page, even where botocore has no paginator.** Savings Plans'
`DescribeSavingsPlansOfferingRates` pages by `nextToken` and botocore 1.43.108 models no paginator
for it, so the relay follows the token itself, up to `MAX_PAGES`, TASK-P9-012. A call that would
go further is refused with `PAGE_LIMIT` rather than answered with the pages it reached, because a
partial answer read as a whole one is a catalog quietly missing prices.

**Errors travel as AWS said them.** A refused or throttled call returns AWS's own code and
message, and the hub raises them as the `ClientError` they were, so `translate` names the same
cause it would have named for a direct call. Nothing is collapsed into an empty answer.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Final
from uuid import uuid4

from botocore import xform_name
from botocore.exceptions import BotoCoreError, ClientError, OperationNotPageableError


class RoleKind(StrEnum):
    """Who the relay is when it makes a call."""

    #: The payer's organization reader, for the payer wide reads.
    MANAGEMENT = "management"
    #: A member account's collector role, for a read about that account.
    MEMBER = "member"
    #: The function's own role, for public price data that belongs to no account.
    OWN = "own"


@dataclass(frozen=True)
class Allowed:
    """One call the relay may make, the IAM action it needs, and who makes it."""

    action: str
    role: RoleKind


#: Every call the relay makes. `tests/contract/test_network_paths.py` holds this to the services
#: the hub cannot reach through an endpoint, and to the relay's IAM policy in the hub stack.
ALLOWED: Final[Mapping[tuple[str, str], Allowed]] = {
    ("budgets", "DescribeBudgets"): Allowed("budgets:ViewBudget", RoleKind.MANAGEMENT),
    ("invoicing", "ListInvoiceSummaries"): Allowed(
        "invoicing:ListInvoiceSummaries", RoleKind.MANAGEMENT
    ),
    ("support", "DescribeTrustedAdvisorChecks"): Allowed(
        "support:DescribeTrustedAdvisorChecks", RoleKind.MEMBER
    ),
    ("support", "DescribeTrustedAdvisorCheckResult"): Allowed(
        "support:DescribeTrustedAdvisorCheckResult", RoleKind.MEMBER
    ),
    ("ec2", "DescribeSpotPriceHistory"): Allowed("ec2:DescribeSpotPriceHistory", RoleKind.OWN),
    ("savingsplans", "DescribeSavingsPlansOfferingRates"): Allowed(
        "savingsplans:DescribeSavingsPlansOfferingRates", RoleKind.OWN
    ),
}


def role_arn(account_id: str, role_name: str, region: str) -> str:
    """A collector role's ARN, as `finops_providers.aws.client.role_arn` builds it.

    A copy rather than an import, because importing the adapter would bring its settings and
    their dependencies into a function whose runtime has only boto3. `tests/providers/aws/
    test_relay.py` holds the two equal for every partition.
    """
    partition = "aws"
    for prefix, name in (
        ("cn-", "aws-cn"),
        ("us-gov-", "aws-us-gov"),
        ("us-isob-", "aws-iso-b"),
        ("us-iso-", "aws-iso"),
    ):
        if region.startswith(prefix):
            partition = name
            break
    return f"arn:{partition}:iam::{account_id}:role/{role_name}"


#: Where an answer is written in the data bucket, under a prefix a lifecycle rule expires.
PREFIX: Final = "relay"
#: The code a refusal by the relay itself carries, never one AWS uses.
REFUSED: Final = "RelayRefused"
#: The code for a call that never reached AWS, which the hub reads as Unreachable.
UNREACHED: Final = "RelayUnreachable"
#: The code for a call with more pages than one invocation follows. SchemaDrift at the hub.
PAGE_LIMIT: Final = "RelayPageLimit"
#: The most pages one invocation follows by hand. A Region's Savings Plans rates for one plan
#: type and payment option are about 13 pages of 1,000 (modelled), so this is far above any call
#: the allow list makes, and far below the function's 300 second timeout.
MAX_PAGES: Final = 200
#: The continuation token's name, as the services the relay calls spell it.
_TOKENS: Final = ("NextToken", "nextToken")
SESSION_NAME: Final = "meter-relay"

_DATETIME: Final = "$datetime"


class RefusedError(ValueError):
    """A request the relay will not make, with the reason in words."""


class PageLimitError(RuntimeError):
    """A call with more pages than the relay follows in one invocation."""


@dataclass(frozen=True)
class Request:
    """One call, as the hub asked for it."""

    service: str
    operation: str
    params: Mapping[str, Any]
    region: str
    #: The account the call is about, for a call made as a role in it; None for the relay's own.
    account_id: str | None
    paginate: bool

    @property
    def allowed(self) -> Allowed:
        return ALLOWED[(self.service, self.operation)]


def parse(event: Mapping[str, Any]) -> Request:
    """The request an event holds, or `RefusedError` saying why it is not one the relay makes."""
    service, operation = str(event.get("service") or ""), str(event.get("operation") or "")
    allowed = ALLOWED.get((service, operation))
    if allowed is None:
        raise RefusedError(f"{service}.{operation} is not a call the relay makes")
    params = event.get("params") or {}
    region = str(event.get("region") or "")
    if not isinstance(params, Mapping) or not region:
        raise RefusedError("a request names its parameters as an object and its Region")
    account_id = event.get("account_id")
    if allowed.role is not RoleKind.OWN and not account_id:
        raise RefusedError(f"{service}.{operation} is made in an account, and none was named")
    return Request(
        service=service,
        operation=operation,
        params=dict(params),
        region=region,
        account_id=None if allowed.role is RoleKind.OWN else str(account_id),
        paginate=bool(event.get("paginate")),
    )


def encode(pages: list[Any]) -> bytes:
    """The answer as JSON, with each timestamp tagged so it comes back a timestamp."""

    def tagged(value: Any) -> Any:
        if isinstance(value, datetime | date):
            return {_DATETIME: value.isoformat()}
        raise TypeError(f"{type(value).__name__} is not part of an AWS answer the relay carries")

    return json.dumps(pages, default=tagged).encode()


def decode(body: bytes) -> list[Any]:
    """An answer the relay wrote, timestamps restored, so an adapter reads what boto3 gave."""

    def restored(found: dict[str, Any]) -> Any:
        if set(found) == {_DATETIME}:
            return datetime.fromisoformat(str(found[_DATETIME]))
        return found

    pages: list[Any] = json.loads(body, object_hook=restored)
    return pages


def call(client: Any, request: Request) -> list[Any]:
    """Make the one call, every page of it where asked, and return the pages."""
    method = xform_name(request.operation)
    if not request.paginate:
        return [getattr(client, method)(**request.params)]
    try:
        paginator = client.get_paginator(method)
    except OperationNotPageableError:
        return follow(getattr(client, method), request.params)
    return list(paginator.paginate(**request.params))


def follow(operation: Callable[..., Any], params: Mapping[str, Any]) -> list[Any]:
    """Every page of a call botocore cannot paginate, following its token by hand."""
    pages: list[Any] = []
    token: dict[str, Any] = {}
    while len(pages) < MAX_PAGES:
        page = operation(**params, **token)
        pages.append(page)
        name = next((key for key in _TOKENS if page.get(key)), None)
        if name is None:
            return pages
        token = {name: page[name]}
    raise PageLimitError(f"more than {MAX_PAGES} pages; none is returned rather than some")


def session_policy(request: Request) -> str:
    """A session policy granting the one action, so an assumed role can do nothing else."""
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Action": request.allowed.action, "Resource": "*"}],
        }
    )


SessionFor = Callable[[Request], Any]
Put = Callable[[str, bytes], None]


class Relay:
    """The function's body, with its AWS session and its writer given to it."""

    def __init__(
        self,
        *,
        session_for: SessionFor,
        put: Put,
        new_key: Callable[[Request], str] | None = None,
    ) -> None:
        self._session_for = session_for
        self._put = put
        self._new_key = new_key or _new_key

    def __call__(self, event: Mapping[str, Any]) -> dict[str, Any]:
        try:
            request = parse(event)
        except RefusedError as refused:
            return {"error": {"Code": REFUSED, "Message": str(refused)}}
        try:
            session = self._session_for(request)
            client = session.client(request.service, region_name=request.region)
            pages = call(client, request)
        except ClientError as failure:
            error = failure.response.get("Error", {})
            return {"error": {"Code": error.get("Code", ""), "Message": error.get("Message", "")}}
        except BotoCoreError as failure:
            return {"error": {"Code": UNREACHED, "Message": str(failure)}}
        except PageLimitError as failure:
            return {"error": {"Code": PAGE_LIMIT, "Message": str(failure)}}
        key = self._new_key(request)
        self._put(key, encode(pages))
        return {"key": key, "pages": len(pages)}


def _new_key(request: Request) -> str:
    return f"{PREFIX}/{request.service}/{request.operation}/{uuid4()}.json"


class AssumingSessions:
    """The relay's sessions in production: its own, or a role assumed for the one action.

    Reads the same three settings the hub's credential broker reads, from the function's
    environment, because the relay is not the hub and does not load the hub's settings.
    """

    def __init__(self, environ: Mapping[str, str], boto3_module: Any) -> None:
        self._environ = environ
        self._boto3 = boto3_module
        self._external_id: str | None = None

    def __call__(self, request: Request) -> Any:
        role = request.allowed.role
        if role is RoleKind.OWN:
            return self._boto3.Session()
        if role is RoleKind.MANAGEMENT:
            arn = self._environ["METER_ORG_READER_ROLE_ARN"]
        else:
            arn = role_arn(
                str(request.account_id), self._environ["METER_COLLECTOR_ROLE_NAME"], request.region
            )
        answer = self._boto3.client("sts", region_name=request.region).assume_role(
            RoleArn=arn,
            RoleSessionName=SESSION_NAME,
            ExternalId=self._external(request.region),
            Policy=session_policy(request),
        )
        credentials = answer["Credentials"]
        return self._boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
        )

    def _external(self, region: str) -> str:
        """Read the ExternalId once per container. Never logged, never in an answer."""
        if self._external_id is None:
            secret = self._boto3.client("secretsmanager", region_name=region).get_secret_value(
                SecretId=self._environ["METER_EXTERNAL_ID_SECRET"]
            )
            self._external_id = str(secret["SecretString"])
        return self._external_id


def handler(event: Mapping[str, Any], _context: Any) -> dict[str, Any]:
    """The Lambda entry point. Built on first use, so a test importing this module needs no AWS."""
    global _RELAY
    if _RELAY is None:
        import boto3

        bucket = os.environ["METER_S3_BUCKET"]
        s3 = boto3.client("s3")
        _RELAY = Relay(
            session_for=AssumingSessions(os.environ, boto3),
            put=lambda key, body: s3.put_object(Bucket=bucket, Key=key, Body=body),
        )
    return _RELAY(event)


_RELAY: Relay | None = None
