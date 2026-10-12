"""How the hub reaches AWS for a collector. TASK-P12-002, FEAT-079.

Each test holds one promise `finops_providers.aws.reach` makes: a client is made on first use and
once, on the credentials and in the Region the read needs, a member account is reached through
the broker, the relay is invoked by the configured name, and the payer is the account the org
reader role lives in.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import boto3
import pytest

from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_providers.aws import reach
from finops_providers.aws.reach import (
    LazyClient,
    PerAccountCatalogue,
    hub_client,
    member_clients,
    payer_of,
    relay,
    session_clients,
)

MEMBER = "222233334444"


class Session:
    """A boto3 session in shape, recording each client asked of it."""

    def __init__(self) -> None:
        self.made: list[tuple[str, str, Any]] = []

    def client(self, service: str, region_name: str, config: Any) -> Any:
        self.made.append((service, region_name, config))
        return SimpleNamespace(service=service, region=region_name)


class Broker:
    """The credential broker in shape, recording each account it is asked to assume."""

    def __init__(self) -> None:
        self.asked: list[tuple[AccountKey, str]] = []
        self.session = Session()

    def session_for(self, account: AccountKey, region: str) -> Any:
        self.asked.append((account, region))
        return SimpleNamespace(session=self.session)


@pytest.fixture
def made(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str | None, Any]]:
    """Every boto3 client made on the hub's own credentials."""
    found: list[tuple[str, str | None, Any]] = []

    def client(service: str, region_name: str | None = None, config: Any = None) -> Any:
        found.append((service, region_name, config))
        return SimpleNamespace(answer=lambda: service, invoke=lambda **_kwargs: None)

    monkeypatch.setattr(boto3, "client", client)
    return found


def test_a_lazy_client_makes_nothing_until_asked_and_then_once() -> None:
    calls: list[int] = []

    def make() -> Any:
        calls.append(1)
        return SimpleNamespace(read=lambda: "read")

    client = LazyClient(make)
    assert calls == []
    assert client.read() == "read"
    assert client.read() == "read"
    assert calls == [1]


def test_a_hub_client_is_made_on_first_use_in_its_region_with_the_bounded_config(
    settings: Settings, made: list[tuple[str, str | None, Any]]
) -> None:
    client = hub_client(settings, "pricing", "us-east-1")
    assert made == []
    assert client.answer() == "pricing"
    ((service, region, config),) = made
    assert (service, region) == ("pricing", "us-east-1")
    assert config.connect_timeout == settings.aws_connect_timeout_seconds
    assert config.read_timeout == settings.aws_read_timeout_seconds


def test_an_account_scoped_read_uses_the_session_the_worker_assumed(settings: Settings) -> None:
    session = Session()
    session_clients(settings, session)("service-quotas", "eu-west-1")
    ((service, region, config),) = session.made
    assert (service, region) == ("service-quotas", "eu-west-1")
    assert config.read_timeout == settings.aws_read_timeout_seconds


def test_a_member_account_is_assumed_through_the_broker_only_when_first_read(
    settings: Settings,
) -> None:
    broker = Broker()
    client = member_clients(settings, broker)("cloudtrail", MEMBER, "eu-west-1")
    assert broker.asked == []
    assert client.service == "cloudtrail"
    assert broker.asked == [(AccountKey(provider=Provider.AWS, account_id=MEMBER), "eu-west-1")]
    assert broker.session.made[0][:2] == ("cloudtrail", "eu-west-1")


def test_the_relay_is_invoked_by_its_configured_name_and_answers_from_the_data_bucket(
    settings: Settings, made: list[tuple[str, str | None, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = settings.model_copy(
        update={"relay_function_name": "meter-dev-relay", "s3_bucket": "meter-dev-data"}
    )
    wired: dict[str, Any] = {}

    def invoke(client: Any, name: str) -> Any:
        wired["invoke"] = (client, name)
        return dict

    def fetch(client: Any, bucket: str) -> Any:
        wired["fetch"] = (client, bucket)
        return bytes

    monkeypatch.setattr(reach, "lambda_invoke", invoke)
    monkeypatch.setattr(reach, "s3_fetch", fetch)
    relay(configured, service="budgets", region="us-east-1", account_id=MEMBER)
    assert wired["invoke"][1] == "meter-dev-relay"
    assert wired["fetch"][1] == "meter-dev-data"
    assert made == [], "the relay's Lambda and S3 clients are made on first use"
    wired["invoke"][0].invoke()
    assert [service for service, _region, _config in made] == ["lambda"]


@pytest.mark.parametrize(
    ("arn", "payer"),
    [
        ("arn:aws:iam::111122223333:role/meter-org-reader", "111122223333"),
        ("arn:aws:iam::111122223333:role/path/meter-org-reader", "111122223333"),
        ("arn:aws:iam::111122223333:user/somebody", None),
        ("arn:aws:iam::12345:role/meter-org-reader", None),
        ("arn:aws:sts::111122223333:assumed-role/meter/x", None),
        ("", None),
    ],
)
def test_the_payer_is_the_account_the_org_reader_role_lives_in(
    settings: Settings, arn: str, payer: str | None
) -> None:
    assert payer_of(settings.model_copy(update={"org_reader_role_arn": arn})) == payer


def test_the_catalogue_reads_each_account_on_that_accounts_own_role() -> None:
    asked: list[tuple[str, str, str]] = []
    pages = SimpleNamespace(paginate=lambda **_request: iter([{"applications": []}]))

    def member(service: str, account_id: str, region: str) -> Any:
        asked.append((service, account_id, region))
        return SimpleNamespace(get_paginator=lambda _operation: pages)

    catalogue = PerAccountCatalogue(member=member, owner_key="owner")
    account = AccountKey(provider=Provider.AWS, account_id=MEMBER)
    assert tuple(catalogue.applications(account, "eu-west-1")) == ()
    assert asked == [("servicecatalog-appregistry", MEMBER, "eu-west-1")]
