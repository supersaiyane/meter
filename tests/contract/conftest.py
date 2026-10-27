"""One contract, parameterised over providers, rather than one file per provider.

Two files drift apart within a month, and the month they drift is the month the
AWS adapter starts raising something the fake never does. The whole value of a
contract suite is that both implementations are held to the same sentence.

The AWS entry is registered here as a skip rather than left out. A provider
that is silently absent looks like a provider that passes, and the run should
say out loud that only one implementation is currently under contract.
TASK-P0-017 replaces the skip with a real builder.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pytest

from finops_core.domain.account import AccountKey, Provider
from finops_providers.fake import fixtures
from finops_providers.fake.provider import FakeProvider


class ProviderPorts(Protocol):
    """The subset of ports the contract suite exercises."""

    def session_for(self, account: AccountKey, region: str) -> object: ...
    def list_accounts(self) -> object: ...
    def describe_organization(self) -> object: ...


@dataclass(frozen=True)
class ProviderUnderTest:
    """A provider plus the handful of identifiers the contract needs to name."""

    name: str
    provider: ProviderPorts
    region: str
    #: An account the provider can read.
    known_account: AccountKey
    #: An account that exists but refuses us. Every provider must have one.
    denied_account: AccountKey
    #: An account the provider has never heard of.
    unknown_account: AccountKey


def build_fake() -> ProviderUnderTest:
    return ProviderUnderTest(
        name="fake",
        provider=FakeProvider(),
        region=fixtures.REGION,
        known_account=fixtures.ACCOUNT_KEYS[0],
        denied_account=fixtures.DENIED_ACCOUNT_KEY,
        unknown_account=AccountKey(provider=Provider.AWS, account_id="fake-not-enrolled"),
    )


PROVIDER_PARAMS = [
    pytest.param("fake", id="fake"),
    pytest.param(
        "aws",
        id="aws",
        marks=pytest.mark.skip(
            reason="The AWS adapter arrives in TASK-P0-017. Listed rather than omitted, "
            "because a provider that is silently absent reads as a provider that passes."
        ),
    ),
]

BUILDERS = {"fake": build_fake}


@pytest.fixture(params=PROVIDER_PARAMS)
def subject(request: pytest.FixtureRequest) -> ProviderUnderTest:
    return BUILDERS[request.param]()
