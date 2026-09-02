"""What every CredentialBroker must do, and above all how it must fail.

The parity assertion here is the reason the suite exists. If the fake raises
AccessDenied for an account that refuses us and the AWS adapter raises a
botocore ClientError, then every caller written against the fake has an
`except Exception` in it by the time the adapter lands, and the taxonomy
TASK-P0-005 built is gone.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from finops_core import errors

from .conftest import CREDENTIAL_BROKER, ProviderUnderTest

pytestmark = pytest.mark.contract


@pytest.fixture(autouse=True)
def _skip_when_unimplemented(requires_port: Callable[[str], None]) -> None:
    requires_port(CREDENTIAL_BROKER)


SIX_CAUSES = tuple(errors.CollectionError.__subclasses__())


def test_a_known_account_yields_a_session(subject: ProviderUnderTest) -> None:
    session = subject.provider.session_for(subject.known_account, subject.region)
    assert session is not None


def test_a_session_says_when_it_expires(subject: ProviderUnderTest) -> None:
    """A long run has to renew before the handle dies, so the expiry is part of it."""
    session = subject.provider.session_for(subject.known_account, subject.region)
    assert session.expires_at.tzinfo is not None


def test_a_denied_account_raises_access_denied_from_every_provider(
    subject: ProviderUnderTest,
) -> None:
    """Error type parity. This is the assertion the whole suite exists for."""
    with pytest.raises(errors.AccessDenied) as caught:
        subject.provider.session_for(subject.denied_account, subject.region)
    assert type(caught.value) is errors.AccessDenied


def test_the_failure_is_one_of_the_six_and_never_something_generic(
    subject: ProviderUnderTest,
) -> None:
    try:
        subject.provider.session_for(subject.unknown_account, subject.region)
    except errors.CollectionError as raised:
        assert type(raised) in SIX_CAUSES
    else:  # pragma: no cover - a provider that accepts an unknown account is a defect
        pytest.fail("an unknown account was accepted rather than refused")


def test_the_failure_carries_the_scope_the_collector_and_a_remediation(
    subject: ProviderUnderTest,
) -> None:
    """A failure a reader cannot act on is only marginally better than a zero."""
    with pytest.raises(errors.AccessDenied) as caught:
        subject.provider.session_for(subject.denied_account, subject.region)
    failure = caught.value
    # The account has to be identifiable from the scope key. The exact shape is
    # provider:account:region, documented in docs/07-DATA-MODEL.md, but a
    # contract that pins the whole string tests formatting rather than meaning.
    assert str(subject.denied_account) in failure.scope_key
    assert failure.collector
    assert failure.remediation.strip()


def test_a_denied_account_never_returns_a_session_instead_of_raising(
    subject: ProviderUnderTest,
) -> None:
    """Returning something empty is how a failure becomes a zero further up."""
    with pytest.raises(errors.CollectionError):
        subject.provider.session_for(subject.denied_account, subject.region)
