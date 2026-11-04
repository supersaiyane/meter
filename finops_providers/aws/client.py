"""Client construction and the one place a provider error becomes a typed one.

Two things live here because both are easy to get wrong once and then wrong
everywhere.

The botocore configuration is built from settings rather than left at defaults.
The default retry policy is wrong for cross account fan out: at three hundred
accounts, a throttling event with default retries becomes a thundering herd that
throttles harder. Timeouts matter for the same reason in reverse, since a broken
network path with no connect timeout consumes the whole task budget doing
nothing.

The error translation is the only bridge between botocore and the closed
taxonomy in `finops_core.errors`. An unrecognised code becomes `SchemaDrift`,
never `NoData`. `NoData` renders as a zero, so mapping an unknown failure to it
turns "we do not know" into "it is free", which is the exact defect ISS-015 and
constraint 5 exist to prevent.
"""

from __future__ import annotations

from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from botocore.exceptions import (
    ConnectionError as BotocoreConnectionError,
)

from finops_core.config import Settings
from finops_core.errors import (
    AccessDenied,
    CollectionError,
    NotOptedIn,
    SchemaDrift,
    Throttled,
    Unreachable,
)

#: Codes that mean the credential was refused. The answer is unknown, not zero.
ACCESS_DENIED_CODES = frozenset(
    {
        "AccessDenied",
        "AccessDeniedException",
        "UnauthorizedOperation",
        "AuthFailure",
        "InvalidClientTokenId",
        "SignatureDoesNotMatch",
    }
)

#: Codes that mean slow down. A run retries these rather than reporting failure.
THROTTLE_CODES = frozenset(
    {
        "Throttling",
        "ThrottlingException",
        "ThrottledException",
        "TooManyRequestsException",
        "RequestLimitExceeded",
        "RequestThrottled",
        "SlowDown",
    }
)

#: Codes that mean the service was never enabled for this organization.
NOT_OPTED_IN_CODES = frozenset(
    {
        "AWSOrganizationsNotInUseException",
        "OptInRequired",
        "SubscriptionRequiredException",
        "OrganizationNotFoundException",
        "AccessDeniedForDependencyException",
    }
)

UNREACHABLE_EXCEPTIONS = (
    EndpointConnectionError,
    ConnectTimeoutError,
    ReadTimeoutError,
    BotocoreConnectionError,
)


def botocore_config(settings: Settings) -> Config:
    """Bounded timeouts and a bounded retry policy, both from configuration."""
    return Config(
        connect_timeout=settings.aws_connect_timeout_seconds,
        read_timeout=settings.aws_read_timeout_seconds,
        retries={"max_attempts": settings.aws_max_retries, "mode": "standard"},
    )


def partition_for(region: str) -> str:
    """The partition a region belongs to.

    Derived rather than hardcoded, because a literal partition is an assumption
    that only breaks in the environments where being wrong is most expensive,
    and it breaks as an unhelpful malformed ARN error.
    """
    if region.startswith("cn-"):
        return "aws-cn"
    if region.startswith("us-gov-"):
        return "aws-us-gov"
    if region.startswith("us-iso-"):
        return "aws-iso"
    if region.startswith("us-isob-"):
        return "aws-iso-b"
    return "aws"


def role_arn(account_id: str, role_name: str, region: str) -> str:
    """The collector role in a member account. Built, never stored."""
    return f"arn:{partition_for(region)}:iam::{account_id}:role/{role_name}"


def error_code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))


def translate(error: Exception, scope_key: str, collector: str) -> CollectionError:
    """Turn a provider exception into exactly one of the six causes."""
    if isinstance(error, UNREACHABLE_EXCEPTIONS):
        return Unreachable(scope_key=scope_key, collector=collector, detail=str(error))
    if isinstance(error, ClientError):
        code = error_code(error)
        detail = f"{code}: {error.response.get('Error', {}).get('Message', '')}".strip()
        if code in ACCESS_DENIED_CODES:
            return AccessDenied(scope_key=scope_key, collector=collector, detail=detail)
        if code in THROTTLE_CODES:
            return Throttled(scope_key=scope_key, collector=collector, detail=detail)
        if code in NOT_OPTED_IN_CODES:
            return NotOptedIn(scope_key=scope_key, collector=collector, detail=detail)
        # Deliberately not NoData. An unknown failure rendered as a zero is the
        # defect the whole taxonomy exists to prevent.
        return SchemaDrift(scope_key=scope_key, collector=collector, detail=detail)
    return SchemaDrift(
        scope_key=scope_key,
        collector=collector,
        detail=f"{type(error).__name__}: {error}",
    )
