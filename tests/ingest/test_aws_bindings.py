"""Every collector a deployment runs is built from its AWS adapters. TASK-P12-002, FEAT-079.

P12 spec section 5.1 and the plan's criteria: in AWS mode each collector is built from the AWS
adapters on the unit's session, a collector that cannot be built fails each run typed, and a
build over a stubbed session holds no fake. Building is also held to touching no network, because
it happens outside every adapter's error handling.
"""

from __future__ import annotations

import types
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import boto3
import pytest

from finops_core.config import Settings
from finops_core.domain.account import AccountKey, AccountStatus, Provider
from finops_core.errors import Misconfigured, SchemaDrift
from finops_fakes.composition import builders as fake_builders
from finops_ingest import accounts, aws_bindings
from finops_ingest.ai_bindings import AI_PROVIDER_BUILDERS
from finops_ingest.aws_bindings import AWS_BUILDERS, UNBUILT, enrolled
from finops_ingest.codehost_bindings import CODEHOST_BUILDERS
from finops_ingest.collectors.fix_pull_requests import Connected, FixPullRequestsCollector
from finops_ingest.composition import (
    _FROM_METER,
    PER_ACCOUNT,
    RETENTION,
    production_registry,
    worker_collectors,
)
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext

AT = datetime(2026, 10, 12, 6, 0, tzinfo=UTC)
ACCOUNTS = ("111111111111", "222222222222")
TENANT = uuid4()


class Accounts:
    """The worker's connection in shape: answers the enrolled accounts query and records it."""

    def __init__(self, found: tuple[str, ...] = ACCOUNTS) -> None:
        self.found = found
        self.asked: list[tuple[str, dict[str, Any]]] = []

    def execute(self, statement: Any, params: dict[str, Any]) -> Any:
        self.asked.append((str(statement), params))
        return SimpleNamespace(scalars=lambda: iter(self.found))


class Session:
    """An assumed boto3 session in shape. Asking it for a client during a build is a failure."""

    def client(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("a build made a client on the unit's session")


@pytest.fixture
def deployed(settings: Settings) -> Settings:
    """Settings as a deployment that has configured every read has them."""
    return settings.model_copy(
        update={
            "relay_function_name": "meter-dev-relay",
            "s3_bucket": "meter-dev-data",
            "config_aggregator": "meter-organization",
            "org_reader_role_arn": "arn:aws:iam::999988887777:role/meter-org-reader",
        }
    )


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """A build that makes a boto3 client, or a session, fails rather than reaching AWS."""

    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("a build made a boto3 client")

    monkeypatch.setattr(boto3, "client", refuse)
    monkeypatch.setattr(boto3, "Session", refuse)


def context(name: str, settings: Settings, *, session: Any = "assumed") -> CollectorContext:
    per_account = name in PER_ACCOUNT
    unit = WorkUnit(
        tenant_id=TENANT,
        collector=name,
        window_start=AT,
        window_end=AT,
        account=AccountKey(provider=Provider.AWS, account_id=ACCOUNTS[0]) if per_account else None,
        region="eu-west-1" if per_account else None,
    )
    assumed = SimpleNamespace(session=Session()) if session == "assumed" and per_account else None
    return CollectorContext(
        unit=unit, connection=Accounts(), session=assumed, settings=settings, run_id=uuid4()
    )


def reachable(root: Any) -> Iterator[Any]:
    """Everything a built collector holds: attributes, closures, containers and bound methods."""
    seen: set[int] = set()
    stack = [root]
    while stack:
        found = stack.pop()
        if id(found) in seen or isinstance(found, (str, bytes, int, float, Decimal, type)):
            continue
        seen.add(id(found))
        yield found
        if isinstance(found, types.ModuleType):
            continue
        if isinstance(found, dict):
            stack.extend(found.values())
        elif isinstance(found, (list, tuple, set, frozenset)):
            stack.extend(found)
        elif isinstance(found, types.MethodType):
            stack.extend((found.__self__, found.__func__))
        elif isinstance(found, types.FunctionType):
            stack.extend(cell.cell_contents for cell in found.__closure__ or ())
        elif hasattr(found, "__dict__") and not type(found).__module__.startswith("boto"):
            stack.extend(vars(found).values())


def fakes_in(root: Any) -> list[str]:
    return [
        f"{type(one).__module__}.{type(one).__name__}"
        for one in reachable(root)
        if type(one).__module__.startswith("finops_fakes")
        or str(getattr(one, "__module__", "")).startswith("finops_fakes")
    ]


def test_every_collector_the_worker_runs_is_built_from_aws_meter_or_said_why_not() -> None:
    aws, unbuilt, meter = set(AWS_BUILDERS), set(UNBUILT), set(_FROM_METER)
    # P13, TASK-P13-004. The AI providers' collectors, built from their own adapters.
    providers = set(AI_PROVIDER_BUILDERS)
    # P15, TASK-P15-004. The code host's collector, built from the GitHub adapter.
    codehost = set(CODEHOST_BUILDERS)
    assert not (aws & unbuilt or aws & meter or unbuilt & meter or providers & (aws | meter))
    assert not codehost & (aws | unbuilt | meter | providers)
    assert aws | unbuilt | meter | providers | codehost == worker_collectors() - RETENTION


def test_the_code_host_collector_is_built_on_the_github_adapter_with_no_call_made(
    deployed: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TASK-P15-004. Nothing reaches AWS or GitHub until a fix is opened."""
    from finops_providers.github.code_host import GitHubCodeHost

    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("a client was made before it was used")

    monkeypatch.setattr(boto3, "client", refuse)
    work = context("fix_pull_requests", deployed)
    built = CODEHOST_BUILDERS["fix_pull_requests"](work)
    assert isinstance(built, FixPullRequestsCollector)
    assert fakes_in(built) == []
    # The code host is made for a run's connection; the key is read only when a request is made.
    connected = Connected("1001", f"meter/{deployed.env}/codehost/github-app")
    assert isinstance(built._code_host_for(work, connected), GitHubCodeHost)


def test_the_comment_collector_is_built_on_the_github_adapter_with_no_call_made(
    deployed: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TASK-P16-006. Nothing reaches AWS or GitHub until an estimate waits for its comment."""
    from finops_ingest.collectors.plan_comments import PlanCommentsCollector
    from finops_providers.github.code_host import GitHubCodeHost

    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("a client was made before it was used")

    monkeypatch.setattr(boto3, "client", refuse)
    work = context("plan_comments", deployed)
    built = CODEHOST_BUILDERS["plan_comments"](work)
    assert isinstance(built, PlanCommentsCollector)
    assert fakes_in(built) == []
    connected = Connected("1001", f"meter/{deployed.env}/codehost/github-app")
    assert isinstance(built._code_host_for(work, connected), GitHubCodeHost)


@pytest.mark.parametrize("name", sorted(AWS_BUILDERS))
def test_a_collector_is_built_from_its_aws_adapters_and_holds_no_fake(
    name: str, deployed: Settings
) -> None:
    built = AWS_BUILDERS[name](context(name, deployed))
    held = list(reachable(built))
    assert callable(built)
    assert any(type(one).__module__.startswith("finops_providers.aws") for one in held), name
    assert fakes_in(built) == []


def test_the_search_for_a_fake_finds_one_where_there_is_one(settings: Settings) -> None:
    built = fake_builders(lambda: AT)["quotas"](context("quotas", settings))
    assert fakes_in(built)


@pytest.mark.parametrize("name", sorted(UNBUILT))
def test_a_collector_that_cannot_be_built_for_aws_fails_each_run_typed(
    name: str, deployed: Settings
) -> None:
    issue = UNBUILT[name].rsplit(", ", 1)[-1]
    with pytest.raises(Misconfigured, match=issue) as raised:
        production_registry().get(name).run(context(name, deployed))
    assert raised.value.collector == name


@pytest.mark.parametrize("name", ["budgets", "invoices", "savings_plan_rates", "spot_prices"])
def test_a_relayed_read_with_no_relay_named_fails_typed_naming_the_setting(
    name: str, deployed: Settings
) -> None:
    unnamed = deployed.model_copy(update={"relay_function_name": ""})
    with pytest.raises(Misconfigured, match="METER_RELAY_FUNCTION_NAME") as raised:
        AWS_BUILDERS[name](context(name, unnamed))
    assert raised.value.collector == name


def test_a_relayed_read_with_no_bucket_for_its_answers_fails_typed(deployed: Settings) -> None:
    with pytest.raises(Misconfigured, match="METER_S3_BUCKET"):
        AWS_BUILDERS["budgets"](context("budgets", deployed.model_copy(update={"s3_bucket": ""})))


def test_the_inventory_with_no_aggregator_named_fails_typed(deployed: Settings) -> None:
    unnamed = deployed.model_copy(update={"config_aggregator": ""})
    with pytest.raises(Misconfigured, match="METER_CONFIG_AGGREGATOR"):
        AWS_BUILDERS["inventory"](context("inventory", unnamed))


@pytest.mark.parametrize("name", ["budgets", "invoices"])
def test_a_read_at_the_payer_with_no_role_arn_to_find_it_in_fails_typed(
    name: str, deployed: Settings
) -> None:
    broken = deployed.model_copy(update={"org_reader_role_arn": "meter-org-reader"})
    with pytest.raises(Misconfigured, match="METER_ORG_READER_ROLE_ARN"):
        AWS_BUILDERS[name](context(name, broken))


@pytest.mark.parametrize("name", ["container_usage", "quotas"])
def test_an_account_scoped_unit_with_no_assumed_session_is_drift(
    name: str, deployed: Settings
) -> None:
    with pytest.raises(SchemaDrift, match="no assumed session"):
        AWS_BUILDERS[name](context(name, deployed, session=None))


def test_the_budgets_and_invoices_are_read_at_the_payer_through_the_relay(
    deployed: Settings,
) -> None:
    for name in ("budgets", "invoices"):
        held = list(reachable(AWS_BUILDERS[name](context(name, deployed))))
        relayed = [one for one in held if type(one).__name__ == "RelayClient"]
        assert relayed, name
        assert all("999988887777" in vars(one).values() for one in relayed), name


def test_the_inventory_reads_every_active_account_in_every_region_and_globally(
    deployed: Settings,
) -> None:
    unit = context("inventory", deployed)
    regions = (*deployed.region_list, None)
    assert enrolled(unit) == tuple(
        (AccountKey(provider=Provider.AWS, account_id=account), region)
        for account in ACCOUNTS
        for region in regions
    )
    ((statement, params),) = unit.connection.asked
    assert statement == accounts.ACTIVE
    assert params == {
        "tenant": TENANT,
        "provider": Provider.AWS.value,
        "status": AccountStatus.ACTIVE.value,
    }


@pytest.mark.parametrize(
    ("name", "adapter", "service"),
    [
        ("commitment", "CostExplorerCommitmentReport", "ce"),
        ("org_tree", "AwsAccountDiscovery", "organizations"),
    ],
)
def test_what_only_the_payer_answers_is_read_as_the_payer(
    name: str, adapter: str, service: str, deployed: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ISS-294 and ISS-296: Cost Explorer's commitments and Organizations, as the org reader."""
    asked: list[str] = []

    def payer(_settings: Settings, wanted: str, _region: str) -> Any:
        asked.append(wanted)
        return SimpleNamespace()

    monkeypatch.setattr(aws_bindings, "payer_client", payer)
    built = AWS_BUILDERS[name](context(name, deployed))
    (found,) = [one for one in reachable(built) if type(one).__name__ == adapter]
    found._factory()
    assert asked == [service]
