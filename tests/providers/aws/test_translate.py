"""Every provider failure becomes exactly one cause, and this is the function that decides.

It had no direct test before 2026-09-28, which is worth saying plainly: `translate` is the single
point where an AWS exception becomes one of the seven words the whole product renders, counts and
filters on, and every test of it was incidental to a test of something else.

The cases here are the boundaries rather than the happy path. A mapping that sends a throttle to
AccessDenied is obvious the first time somebody reads a screen. A mapping that sends a
misconfiguration to SchemaDrift is not, because both are loud, both are honest about not knowing
the answer, and only one of them tells an operator where to look. ADR-0026.
"""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from finops_core.errors import (
    AccessDenied,
    CollectionError,
    Misconfigured,
    NotOptedIn,
    SchemaDrift,
    Throttled,
    Unreachable,
)
from finops_providers.aws.client import translate

SCOPE = "aws:111122223333:eu-west-1"
COLLECTOR = "inventory"


def refusal(code: str, message: str = "nope") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": message}}, "DescribeSomething")


def caused_by(code: str) -> CollectionError:
    return translate(refusal(code), scope_key=SCOPE, collector=COLLECTOR)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("AccessDenied", AccessDenied),
        ("AccessDeniedException", AccessDenied),
        ("UnauthorizedOperation", AccessDenied),
        ("Throttling", Throttled),
        ("ThrottlingException", Throttled),
        ("RequestLimitExceeded", Throttled),
        ("OptInRequired", NotOptedIn),
        ("SubscriptionRequiredException", NotOptedIn),
    ],
)
def test_each_known_code_becomes_its_own_cause(code: str, expected: type) -> None:
    assert isinstance(caused_by(code), expected)


@pytest.mark.parametrize(
    "code",
    [
        # The Config aggregator named in settings, and the most likely first call failure in the
        # product: the name is free text and nothing validates it until a read.
        "NoSuchConfigurationAggregatorException",
        # A Terraform state location named in settings. A path with a typo in it and one that was
        # never created are indistinguishable from here, and both are fixed the same way.
        "NoSuchKey",
        "NoSuchBucket",
    ],
)
def test_a_value_the_deployment_set_becomes_misconfigured(code: str) -> None:
    """ADR-0026. Before this they were SchemaDrift, which named the wrong remedy.

    Nothing was hidden by that: SchemaDrift renders as UNRECOGNISED and never as a number. It
    told an operator their schema had drifted and sent them to look for an API change, when the
    fix was one line of their own configuration.
    """
    found = caused_by(code)
    assert isinstance(found, Misconfigured)
    assert "configur" in found.remediation.lower()


@pytest.mark.parametrize(
    "code",
    [
        # We built the request wrongly. That is our bug and not the operator's, and telling them
        # to change a setting would send them to change one that was correct.
        "InvalidExpressionException",
        "InvalidParameterException",
        # A page token that expired part way through a long read. A retry, and neither a
        # misconfiguration nor a quota problem: mapping it to Throttled would inflate a number
        # somebody reads as being over quota. ISS-215 keeps this open.
        "ExpiredNextTokenException",
        "InternalErrorException",
        # A code no set names at all.
        "SomethingNobodyHasSeen",
    ],
)
def test_everything_else_stays_unrecognised(code: str) -> None:
    """The fall through, which is deliberate and is never NoData.

    An unknown failure rendered as a zero is the defect the entire taxonomy exists to prevent, so
    the unknown case has to be the loud one. This is the assertion that keeps `Misconfigured`
    from growing into the generic catch all ISS-015 warns about: a code only joins it by being
    named, never by resembling one.
    """
    assert isinstance(caused_by(code), SchemaDrift)


def test_a_dead_endpoint_is_unreachable_rather_than_denied() -> None:
    """No answer at all is a different fact from an answer that refused."""
    failure = EndpointConnectionError(endpoint_url="https://config.eu-west-1.amazonaws.com/")
    found = translate(failure, scope_key=SCOPE, collector=COLLECTOR)
    assert isinstance(found, Unreachable)


def test_the_cause_carries_the_code_and_the_message() -> None:
    """A cause with no detail is a cause nobody can act on.

    The code matters as much as the message: an operator searching for the exact string AWS
    returned finds the answer, and a paraphrase of it finds nothing.
    """
    found = caused_by("NoSuchConfigurationAggregatorException")
    assert "NoSuchConfigurationAggregatorException" in found.detail
    assert "nope" in found.detail


def test_every_cause_names_its_scope_and_collector() -> None:
    """Without both, a failure on a screen is one nobody can locate."""
    for code in ("AccessDenied", "Throttling", "NoSuchKey", "Unknown"):
        found = caused_by(code)
        assert found.scope_key == SCOPE
        assert found.collector == COLLECTOR
