"""One contract, parameterised over providers, rather than one file per provider.

Two files drift apart within a month, and the month they drift is the month the
AWS adapter starts raising something the fake never does. The whole value is
that both implementations are held to the same sentence.

A provider declares which ports it satisfies. That is not politeness: an adapter
arrives one port at a time, and the alternative to declaring it is either a file
of skips that nobody prunes, or a suite that pretends a missing implementation
passed. A port nobody has implemented yet reports as skipped, by name.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import pytest

from finops_core.config import Settings, load_settings
from finops_core.domain.account import AccountKey, Provider
from finops_providers.fake import fixtures
from finops_providers.fake.provider import FakeProvider

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_EXAMPLE = ROOT / ".env.example"
VARIABLE = re.compile(r"^(METER_[A-Z0-9_]+)=(.*)$", re.MULTILINE)

ACCOUNT_DISCOVERY = "AccountDiscovery"
CREDENTIAL_BROKER = "CredentialBroker"


class ProviderPorts(Protocol):
    """The subset of ports the contract suite exercises."""

    def session_for(self, account: AccountKey, region: str) -> object: ...


@dataclass(frozen=True)
class ProviderUnderTest:
    """A provider plus the handful of identifiers the contract needs to name."""

    name: str
    provider: Any
    region: str
    #: An account the provider can read.
    known_account: AccountKey
    #: An account that exists but refuses us. Every provider must have one.
    denied_account: AccountKey
    #: An account the provider has never heard of.
    unknown_account: AccountKey
    #: Which ports this provider satisfies today.
    supports: frozenset[str] = field(default_factory=frozenset)


def settings_from_example(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for key, value in VARIABLE.findall(ENV_EXAMPLE.read_text(encoding="utf-8")):
        monkeypatch.setenv(key, value)
    return load_settings()


def build_fake(_monkeypatch: pytest.MonkeyPatch) -> Iterator[ProviderUnderTest]:
    yield ProviderUnderTest(
        name="fake",
        provider=FakeProvider(),
        region=fixtures.REGION,
        known_account=fixtures.ACCOUNT_KEYS[0],
        denied_account=fixtures.DENIED_ACCOUNT_KEY,
        unknown_account=AccountKey(provider=Provider.AWS, account_id="fake-not-enrolled"),
        supports=frozenset({ACCOUNT_DISCOVERY, CREDENTIAL_BROKER}),
    )


AWS_REGION = "eu-west-1"
AWS_KNOWN = AccountKey(provider=Provider.AWS, account_id="111122223333")
AWS_DENIED = AccountKey(provider=Provider.AWS, account_id="444455556666")
AWS_UNKNOWN = AccountKey(provider=Provider.AWS, account_id="777788889999")


AWS_ROOT = "r-contract"
AWS_UNIT = "ou-contract"


class ContractOrganizations:
    """A fixed organization for the contract, containing the denied account.

    moto generates its own account identifiers, so the organization the contract
    needs, one that definitely contains the account we then get refused on,
    cannot be built there. What the contract is asking of an adapter is whether
    it turns provider responses into domain objects with the right shape and
    parentage, and that is exactly what this exercises.
    """

    def get_paginator(self, operation: str) -> Any:
        return _ContractPaginator(operation)


class _ContractPaginator:
    def __init__(self, operation: str) -> None:
        self._operation = operation

    def paginate(self, **kwargs: Any) -> Any:
        parent = kwargs.get("ParentId")
        if self._operation == "list_roots":
            return iter([{"Roots": [{"Id": AWS_ROOT, "Name": "root"}]}])
        if self._operation == "list_organizational_units_for_parent":
            units = [{"Id": AWS_UNIT, "Name": "unit"}] if parent == AWS_ROOT else []
            return iter([{"OrganizationalUnits": units}])
        accounts = (
            [
                {"Id": AWS_KNOWN.account_id, "Name": "known", "Status": "ACTIVE"},
                {"Id": AWS_DENIED.account_id, "Name": "denied", "Status": "ACTIVE"},
            ]
            if parent == AWS_UNIT
            else []
        )
        return iter([{"Accounts": accounts}])


class AwsUnderContract:
    """The two AWS adapters presented as the one object the contract talks to."""

    def __init__(self, broker: Any, discovery: Any) -> None:
        self._broker = broker
        self._discovery = discovery

    def session_for(self, account: AccountKey, region: str) -> Any:
        return self._broker.session_for(account, region)

    def list_accounts(self) -> Any:
        return self._discovery.list_accounts()

    def describe_organization(self) -> Any:
        return self._discovery.describe_organization()


def build_aws(monkeypatch: pytest.MonkeyPatch) -> Iterator[ProviderUnderTest]:
    """The AWS adapter under moto.

    moto never refuses an assume call, so the denied and unknown accounts are
    made to fail with the provider's own ClientError shape. That is the right
    simulation for this contract: the question is whether the adapter turns a
    refusal into the typed domain error, not whether moto can produce one.
    """
    import boto3
    from botocore.exceptions import ClientError
    from moto import mock_aws

    from finops_providers.aws.accounts import AwsAccountDiscovery
    from finops_providers.aws.credentials import AwsCredentialBroker

    settings = settings_from_example(monkeypatch)
    refused = {AWS_DENIED.account_id, AWS_UNKNOWN.account_id}

    mock = mock_aws()
    mock.start()
    try:
        boto3.client("secretsmanager", region_name=AWS_REGION).create_secret(
            Name=settings.external_id_secret, SecretString="contract-external-id"
        )
        real_client = boto3.client

        class RefusingSts:
            def __init__(self, inner: Any) -> None:
                self._inner = inner

            def assume_role(self, **kwargs: Any) -> Any:
                if any(account in kwargs["RoleArn"] for account in refused):
                    raise ClientError(
                        {"Error": {"Code": "AccessDenied", "Message": "refused"}},
                        "AssumeRole",
                    )
                return self._inner.assume_role(**kwargs)

        def factory(service: str, region: str) -> Any:
            client = real_client(service, region_name=region)
            return RefusingSts(client) if service == "sts" else client

        yield ProviderUnderTest(
            name="aws",
            provider=AwsUnderContract(
                broker=AwsCredentialBroker(settings, client_factory=factory),
                discovery=AwsAccountDiscovery(
                    settings, client_factory=lambda: ContractOrganizations()
                ),
            ),
            region=AWS_REGION,
            known_account=AWS_KNOWN,
            denied_account=AWS_DENIED,
            unknown_account=AWS_UNKNOWN,
            supports=frozenset({ACCOUNT_DISCOVERY, CREDENTIAL_BROKER}),
        )
    finally:
        mock.stop()


BUILDERS = {"fake": build_fake, "aws": build_aws}


@pytest.fixture(params=sorted(BUILDERS))
def subject(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[ProviderUnderTest]:
    yield from BUILDERS[request.param](monkeypatch)


@pytest.fixture
def requires_port(subject: ProviderUnderTest) -> object:
    """Skip by name when a provider has not implemented the port under test."""

    def check(port: str) -> None:
        if port not in subject.supports:
            pytest.skip(f"{subject.name} does not implement {port} yet")

    return check
