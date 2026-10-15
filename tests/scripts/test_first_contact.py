"""make first-contact, over stubbed clients. TASK-P12-008, FEAT-079, ISS-002.

The script's whole purpose is a real AWS account, which no test has, so these hold what can be
held without one: one read answering and one refusing are reported as such, the refusal typed as a
collector's would be; a read whose setting is empty is not tried and says which; the run refuses
without credentials before reading anything; and every collector the deployed composition builds
from AWS has a read here.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path
from typing import Any

import boto3
import pytest
from botocore.exceptions import ClientError

from finops_core.config import Settings
from finops_core.errors import AccessDenied, Misconfigured
from finops_ingest.ai_bindings import AI_PROVIDER_BUILDERS
from finops_ingest.aws_bindings import AWS_BUILDERS
from finops_providers.anthropic.reports import AnthropicReports
from finops_providers.aws.reach import LazyClient
from finops_providers.aws.relay_client import RelayClient
from finops_providers.github.code_host import GitHubCodeHost

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "first_contact.py"

# Loaded by path, as the other scripts' tests load theirs: `scripts/` is not a package.
_spec = importlib.util.spec_from_file_location("first_contact", SCRIPT)
assert _spec is not None and _spec.loader is not None
first_contact = importlib.util.module_from_spec(_spec)
sys.modules["first_contact"] = first_contact
_spec.loader.exec_module(first_contact)

ACCOUNT = "111122223333"
PAYER = "999988887777"


class Answering:
    """A client every call of which answers, recording what it was asked."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def __getattr__(self, operation: str) -> Any:
        def call(**_request: Any) -> dict[str, Any]:
            self.asked.append(operation)
            return {}

        return call


class Refusing:
    """A client every call of which AWS refuses."""

    def __getattr__(self, operation: str) -> Any:
        def call(**_request: Any) -> dict[str, Any]:
            error = {"Error": {"Code": "AccessDenied", "Message": "not for you"}}
            raise ClientError(error, operation)

        return call


@pytest.fixture
def deployed(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "relay_function_name": "meter-dev-relay",
            "s3_bucket": "meter-dev-data",
            "config_aggregator": "meter-organization",
            "org_reader_role_arn": f"arn:aws:iam::{PAYER}:role/meter-org-reader",
            "iac_state_locations": "s3://state-bucket/hub/terraform.tfstate",
        }
    )


def target(settings: Settings) -> Any:
    return first_contact.Target(settings, ACCOUNT, "eu-west-1", date(2026, 10, 12))


def probe(reads: str) -> Any:
    (found,) = [one for one in first_contact.PROBES if one.reads == reads]
    return found


def test_one_read_answering_and_one_refusing_are_reported_as_such(deployed: Settings) -> None:
    probes = (probe("Service Quotas"), probe("AppRegistry"))
    stubs = {"service-quotas": Answering(), "servicecatalog-appregistry": Refusing()}
    answers = first_contact.contact(probes, target(deployed), lambda one, _t: stubs[one.service])
    assert [answer.outcome for answer in answers] == ["answered", "AccessDenied"]
    assert "AccessDenied" in answers[1].detail and ACCOUNT in answers[1].detail


def test_a_read_whose_setting_is_empty_is_not_tried_and_says_which(deployed: Settings) -> None:
    empty = deployed.model_copy(update={"config_aggregator": "", "relay_function_name": ""})
    reads = (probe("the AWS Config aggregator"), probe("Budgets, through the relay"))
    answers = first_contact.contact(reads, target(empty), lambda *_a: pytest.fail("not asked"))
    assert [(answer.outcome, answer.detail) for answer in answers] == [
        ("not tried", "METER_CONFIG_AGGREGATOR is empty"),
        ("not tried", "METER_RELAY_FUNCTION_NAME is empty"),
    ]


@pytest.mark.parametrize(
    "reads",
    [
        "Invoicing, through the relay",
        "AWS Organizations, as the payer",
        "Cost Explorer's commitment reports, as the payer",
    ],
)
def test_a_read_at_the_payer_is_not_tried_when_no_payer_is_named(
    deployed: Settings, reads: str
) -> None:
    nameless = deployed.model_copy(update={"org_reader_role_arn": ""})
    (answer,) = first_contact.contact((probe(reads),), target(nameless), lambda *_a: None)
    assert (answer.outcome, answer.detail) == (
        "not tried",
        "METER_ORG_READER_ROLE_ARN names no payer",
    )


def test_with_no_credentials_it_refuses_before_reading_anything(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = first_contact.main(
        ["--env", "dev", "--account", ACCOUNT, "--region", "eu-west-1"],
        credentials=lambda: False,
        settings_for=lambda _env: pytest.fail("no settings are read without credentials"),
    )
    assert status == first_contact.REFUSED
    assert "first contact refused: no AWS credentials" in capsys.readouterr().err


@pytest.mark.parametrize(("answers", "status"), [(True, 0), (False, 1)])
def test_it_exits_zero_only_when_every_read_answered(
    deployed: Settings, capsys: pytest.CaptureFixture[str], answers: bool, status: int
) -> None:
    def client_for(one: Any, _target: Any) -> Any:
        return Answering() if answers or one.reads != "CloudTrail" else Refusing()

    assert (
        first_contact.main(
            ["--env", "dev", "--account", ACCOUNT, "--region", "eu-west-1"],
            credentials=lambda: True,
            settings_for=lambda _env: deployed,
            client_for=client_for,
        )
        == status
    )
    # No key's secret was named, so neither AI provider nor GitHub was read, and nothing counts
    # against it.
    total = len([one for one in first_contact.PROBES if one.reach not in {"provider", "codehost"}])
    shown = capsys.readouterr().out
    assert f"{total - (0 if answers else 1)} of {total} reads answered." in shown


def test_every_collector_built_from_aws_has_a_read() -> None:
    named = " ".join(one.collectors for one in first_contact.PROBES)
    assert {name for name in AWS_BUILDERS if name not in named} == set()


def test_each_read_goes_the_way_the_deployed_composition_reaches_aws(
    deployed: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("a client was made before it was used")

    monkeypatch.setattr(boto3, "client", refuse)
    client_for = first_contact.clients(target(deployed))
    assert isinstance(client_for(probe("Service Quotas"), target(deployed)), LazyClient)
    assert isinstance(
        client_for(probe("AWS Organizations, as the payer"), target(deployed)), LazyClient
    )
    relayed = client_for(probe("Budgets, through the relay"), target(deployed))
    assert isinstance(relayed, RelayClient)
    assert PAYER in vars(relayed).values()


def test_the_settings_are_the_deployed_parameters_and_an_absent_one_is_empty(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    present = {
        f"METER_{name.upper()}": str(value)
        for name, value in settings.model_dump().items()
        if str(value) and name != "s3_bucket"
    }
    parameters = [
        {"Name": f"/meter/dev/{name}", "Value": value, "Type": "String"}
        for name, value in present.items()
    ] + [
        {"Name": "/meter/dev/METER_SESSION_SIGNING_KEY", "Value": "cipher", "Type": "SecureString"}
    ]
    pages = type("Pages", (), {"paginate": lambda _self, **_r: iter([{"Parameters": parameters}])})
    ssm = type("Ssm", (), {"get_paginator": lambda _self, _name: pages()})
    monkeypatch.setattr(boto3, "client", lambda *_a, **_k: ssm())
    built = first_contact.settings_from_ssm("dev")
    assert built.queue_url == settings.queue_url
    assert built.s3_bucket == "", "a setting with no parameter is the empty one the task is given"
    assert built.session_signing_key == first_contact.UNUSED_SECRET


# --- the AI providers, P13, TASK-P13-009 ----------------------------------------------------------

SECRET = "meter/dev/ai/openai-platform"


class Reports:
    """A provider's reports that answer with nothing, or refuse with a typed cause."""

    def __init__(self, refuse: Exception | None = None) -> None:
        self._refuse = refuse

    def costs(self, *_args: Any) -> Any:
        if self._refuse is not None:
            raise self._refuse
        return iter(())


def test_every_ai_provider_collector_has_a_read() -> None:
    named = " ".join(one.collectors for one in first_contact.PROBES)
    assert {name for name in AI_PROVIDER_BUILDERS if name not in named} == set()


def test_a_provider_is_read_only_when_its_keys_secret_is_named(
    deployed: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    asked: list[str] = []

    def client_for(one: Any, _target: Any) -> Any:
        asked.append(one.service)
        return Reports() if one.reach == "provider" else Answering()

    status = first_contact.main(
        ["--env", "dev", "--account", ACCOUNT, "--region", "eu-west-1", "--openai-secret", SECRET],
        credentials=lambda: True,
        settings_for=lambda _env: deployed,
        client_for=client_for,
    )
    assert status == first_contact.ANSWERED_ALL
    assert "openai" in asked and "anthropic" not in asked
    shown = capsys.readouterr().out
    assert "AI providers not read, no key's secret named: anthropic." in shown
    assert SECRET not in shown, "the report never names a secret"


def test_a_refused_key_is_reported_by_its_typed_cause(deployed: Settings) -> None:
    refused = AccessDenied(scope_key="openai:x", collector="openai_usage", detail="key revoked")
    where = first_contact.Target(
        deployed, ACCOUNT, "eu-west-1", date(2026, 10, 12), ai_secrets={"openai": SECRET}
    )
    (answer,) = first_contact.contact(
        [probe("OpenAI's cost report, with the key named")],
        where,
        lambda _one, _target: Reports(refused),
    )
    assert answer.outcome == "AccessDenied"


def test_a_providers_client_reads_its_key_only_when_the_request_is_made(
    deployed: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("a client was made before it was used")

    monkeypatch.setattr(boto3, "client", refuse)
    where = first_contact.Target(
        deployed, ACCOUNT, "eu-west-1", date(2026, 10, 12), ai_secrets={"anthropic": SECRET}
    )
    built = first_contact.clients(where)(
        probe("Anthropic's cost report, with the key named"), where
    )
    assert isinstance(built, AnthropicReports)


def test_a_relayed_read_of_what_an_account_holds_is_made_as_that_account(
    deployed: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0037: Savings Plans and RDS reservations through the relay, as the member's role."""

    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("a client was made before it was used")

    monkeypatch.setattr(boto3, "client", refuse)
    for reads in (
        "Savings Plans the account holds, through the relay",
        "RDS reservations the account holds, through the relay",
        "ElastiCache reservations the account holds, through the relay",
        "OpenSearch reservations the account holds, through the relay",
        "Redshift reservations the account holds, through the relay",
        "MemoryDB reservations the account holds, through the relay",
    ):
        relayed = first_contact.clients(target(deployed))(probe(reads), target(deployed))
        assert isinstance(relayed, RelayClient), reads
        assert ACCOUNT in vars(relayed).values(), reads


# --- the code host, P15, TASK-P15-002 -------------------------------------------------------------

CODEHOST = "meter/dev/codehost/github-app"
GITHUB = "GitHub, the app's installation, with its key named"
NAMED = ["--codehost-secret", CODEHOST, "--codehost-app-id", "1001"]


class Installation:
    """A code host that lists its repositories, or refuses with a typed cause."""

    def __init__(self, refuse: Exception | None = None) -> None:
        self.refuse = refuse
        self.asked: list[str] = []

    def installation_repositories(self, repository: str) -> tuple[str, ...]:
        self.asked.append(repository)
        if self.refuse is not None:
            raise self.refuse
        return (repository,)


def test_github_is_read_only_when_its_key_app_and_a_repository_are_named(
    deployed: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    host = Installation()

    def client_for(one: Any, _target: Any) -> Any:
        return host if one.reach == "codehost" else Answering()

    common = ["--env", "dev", "--account", ACCOUNT, "--region", "eu-west-1"]
    for argv, read in ((NAMED, False), ([*NAMED, "--codehost-repository", "acme/infra"], True)):
        status = first_contact.main(
            [*common, *argv],
            credentials=lambda: True,
            settings_for=lambda _env: deployed,
            client_for=client_for,
        )
        assert status == first_contact.ANSWERED_ALL
        shown = capsys.readouterr().out
        assert ("GitHub not read" in shown) is not read
        assert CODEHOST not in shown, "the report never names a secret"
    assert host.asked == ["acme/infra"]


def test_an_app_github_refuses_is_reported_by_its_typed_cause(deployed: Settings) -> None:
    refused = Misconfigured(scope_key="github:acme/infra", collector="c", detail="not installed")
    where = first_contact.Target(
        deployed,
        ACCOUNT,
        "eu-west-1",
        date(2026, 10, 15),
        codehost_secret=CODEHOST,
        codehost_app_id="1001",
        codehost_repository="acme/infra",
    )
    (answer,) = first_contact.contact(
        [probe(GITHUB)], where, lambda _one, _target: Installation(refused)
    )
    assert answer.outcome == "Misconfigured"
    (unnamed,) = first_contact.contact([probe(GITHUB)], target(deployed), lambda *_: Installation())
    assert unnamed.outcome == "not tried" and "--codehost-repository" in unnamed.detail


def test_githubs_client_reads_its_key_only_when_the_request_is_made(
    deployed: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("a client was made before it was used")

    monkeypatch.setattr(boto3, "client", refuse)
    where = first_contact.Target(
        deployed,
        ACCOUNT,
        "eu-west-1",
        date(2026, 10, 15),
        codehost_secret=CODEHOST,
        codehost_app_id="1001",
        codehost_repository="acme/infra",
    )
    assert isinstance(first_contact.clients(where)(probe(GITHUB), where), GitHubCodeHost)
