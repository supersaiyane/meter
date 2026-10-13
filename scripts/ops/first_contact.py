"""Make each AWS read Meter depends on once, against one account and Region, and report each.

TASK-P12-008, FEAT-079, P12 spec section 5.6, ISS-002. `make first-contact ENV=dev ACCOUNT=<id>
REGION=<region>`. No AWS adapter in this product has made a real call, so the first contact with
an account is where every assumption about permissions, endpoints and settings meets AWS. This
makes the cheapest read each collector depends on, one each, through the same path the deployed
composition uses: the hub's own credentials, the collector role the credential broker assumes in
the account, or the relay. Each is reported as answered, as the typed cause it failed with, or as
not tried, naming the empty setting it needed.

It reads the deployed settings from SSM Parameter Store, `/meter/<env>/`, so what is tried is what
the tasks are given. It writes nothing anywhere. Run it with credentials for the hub account, with
`AWS_REGION` set to the hub's Region; it refuses to run without credentials, rather than report
every read as failed for a reason that is not the account's.

Cost Explorer charges for each request, USD 0.01 at AWS's published price (modelled), and the relay
reads each start one Lambda invocation. Everything else here is free to call.

An AI provider is read too, P13, when its key's secret is named: `--openai-secret` and
`--anthropic-secret`, each under `meter/<env>/ai/`. The key is read through the worker's own reader
and asked for one day of costs, the read `scripts/ops/connect_ai_provider.py` proves before it
connects an organization. A provider whose secret is not named is not read, and the report says
so, so an estate with no AI provider can still answer every read. The key is never printed.
`docs/runbooks/ai-providers.md` has the owner's steps.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final
from urllib.parse import urlsplit
from uuid import uuid4

import boto3

from finops_core.config import Settings
from finops_core.constants import ENV_PREFIX
from finops_core.domain.ai import ProviderAccount
from finops_core.errors import CollectionError
from finops_core.ports.ai import AiProviderReports
from finops_providers.anthropic.reports import COLLECTOR as ANTHROPIC_COLLECTOR
from finops_providers.anthropic.reports import AnthropicReports
from finops_providers.aws.client import translate
from finops_providers.aws.gpu_metrics import METRIC as GPU_METRIC
from finops_providers.aws.reach import (
    GLOBAL_REGION,
    hub_client,
    member_clients,
    payer_client,
    payer_of,
    relay,
)
from finops_providers.aws.secrets import AiKeyReader
from finops_providers.openai.reports import COLLECTOR as OPENAI_COLLECTOR
from finops_providers.openai.reports import OpenAiReports

#: Exit statuses: every read answered, at least one did not, or the run was refused.
ANSWERED_ALL: Final = 0
NOT_ALL_ANSWERED: Final = 1
REFUSED: Final = 2

#: What a probe's outcome is when it answered, and when it could not be tried.
ANSWERED: Final = "answered"
NOT_TRIED: Final = "not tried"

#: The signing key is a secret the probes never use, and it may still be Terraform's placeholder.
UNUSED_SECRET: Final = "unused by first contact"


@dataclass(frozen=True)
class Target:
    """What a probe is pointed at: the settings, the account and Region named, today."""

    settings: Settings
    account: str
    region: str
    today: date
    #: Each AI provider's key secret, by provider, P13. A provider not named here is not tried.
    ai_secrets: dict[str, str] = field(default_factory=dict)

    @property
    def payer(self) -> str | None:
        return payer_of(self.settings)


@dataclass(frozen=True)
class Probe:
    """One read: what it reads, who depends on it, how it is reached and how it is made."""

    reads: str
    collectors: str
    reach: str
    service: str
    read: Callable[[Any, Target], Any]
    #: Settings that must be set, besides the account and Region, for the read to be tried.
    needs: tuple[str, ...] = ()
    #: A Region of its own, for a service that answers in one Region only.
    region: str | None = None


@dataclass(frozen=True)
class Answer:
    probe: Probe
    outcome: str
    detail: str = ""


def _yesterday(target: Target) -> dict[str, str]:
    return {
        "Start": (target.today - timedelta(days=1)).isoformat(),
        "End": target.today.isoformat(),
    }


def _first_state(target: Target) -> dict[str, str]:
    """The first configured Terraform state location, `s3://bucket/key`, as a head request."""
    location = urlsplit(target.settings.iac_locations[0])
    return {"Bucket": location.netloc, "Key": location.path.lstrip("/")}


RELAYED: Final = ("relay_function_name", "s3_bucket")

#: How each AI provider's reports are made from its key, and the collector a failure is named for.
ReportsFor = Callable[[Callable[[], str]], AiProviderReports]
PROVIDER_REPORTS: Final[dict[str, tuple[ReportsFor, str]]] = {
    "anthropic": (lambda key: AnthropicReports(uuid4(), uuid4(), key), ANTHROPIC_COLLECTOR),
    "openai": (lambda key: OpenAiReports(uuid4(), uuid4(), key), OPENAI_COLLECTOR),
}


def _a_day_of_costs(provider: str) -> Callable[[AiProviderReports, Target], Any]:
    """One day of a provider's costs, the read connecting an organization proves."""

    def read(reports: AiProviderReports, target: Target) -> Any:
        account = ProviderAccount(
            provider=provider,
            organization_id="first-contact",
            name="first contact",
            key_secret_name=target.ai_secrets[provider],
        )
        end = datetime(target.today.year, target.today.month, target.today.day, tzinfo=UTC)
        return tuple(reports.costs(account, end - timedelta(days=1), end))

    return read


PROBES: Final[tuple[Probe, ...]] = (
    Probe(
        "the hub's own credentials",
        "every collector",
        "hub",
        "sts",
        lambda c, _t: c.get_caller_identity(),
    ),
    Probe(
        "the collector role in the account",
        "account_health and every per account read",
        "member",
        "sts",
        lambda c, _t: c.get_caller_identity(),
    ),
    Probe(
        "AWS Organizations, as the payer",
        "org_tree",
        "payer",
        "organizations",
        lambda c, _t: c.describe_organization(),
        region=GLOBAL_REGION,
    ),
    Probe(
        "Cost Explorer's commitment reports, as the payer",
        "commitment",
        "payer",
        "ce",
        lambda c, t: c.get_savings_plans_utilization(TimePeriod=_yesterday(t)),
        region=GLOBAL_REGION,
    ),
    Probe(
        "Service Quotas",
        "quotas",
        "member",
        "service-quotas",
        lambda c, _t: c.list_services(MaxResults=1),
    ),
    Probe(
        "CloudWatch metrics",
        "container_usage",
        "member",
        "cloudwatch",
        lambda c, _t: c.list_metrics(Namespace="AWS/EC2", RecentlyActive="PT3H"),
    ),
    Probe(
        "the GPU agent's metrics",
        "gpu_utilization",
        "member",
        "cloudwatch",
        lambda c, t: c.list_metrics(
            Namespace=t.settings.gpu_metrics_namespace, MetricName=GPU_METRIC, RecentlyActive="PT3H"
        ),
    ),
    Probe(
        "EC2 reservations the account holds",
        "commitment_inventory",
        "member",
        "ec2",
        lambda c, _t: c.describe_reserved_instances(),
    ),
    Probe(
        "Savings Plans the account holds, through the relay",
        "commitment_inventory",
        "relay-member",
        "savingsplans",
        lambda c, _t: c.describe_savings_plans(maxResults=1),
        needs=RELAYED,
        region=GLOBAL_REGION,
    ),
    Probe(
        "RDS reservations the account holds, through the relay",
        "commitment_inventory",
        "relay-member",
        "rds",
        lambda c, _t: c.describe_reserved_db_instances(MaxRecords=20),
        needs=RELAYED,
    ),
    Probe(
        "ElastiCache reservations the account holds, through the relay",
        "commitment_inventory",
        "relay-member",
        "elasticache",
        lambda c, _t: c.describe_reserved_cache_nodes(MaxRecords=20),
        needs=RELAYED,
    ),
    Probe(
        "OpenSearch reservations the account holds, through the relay",
        "commitment_inventory",
        "relay-member",
        "opensearch",
        lambda c, _t: c.describe_reserved_instances(MaxResults=1),
        needs=RELAYED,
    ),
    Probe(
        "Redshift reservations the account holds, through the relay",
        "commitment_inventory",
        "relay-member",
        "redshift",
        lambda c, _t: c.describe_reserved_nodes(MaxRecords=20),
        needs=RELAYED,
    ),
    Probe(
        "MemoryDB reservations the account holds, through the relay",
        "commitment_inventory",
        "relay-member",
        "memorydb",
        lambda c, _t: c.describe_reserved_nodes(MaxResults=1),
        needs=RELAYED,
    ),
    Probe(
        "Bedrock's invocation logging configuration",
        "bedrock_invocations",
        "member",
        "bedrock",
        lambda c, _t: c.get_model_invocation_logging_configuration(),
    ),
    Probe(
        "AppRegistry",
        "ownership",
        "member",
        "servicecatalog-appregistry",
        lambda c, _t: c.list_applications(maxResults=1),
    ),
    Probe(
        "CloudTrail",
        "ownership",
        "member",
        "cloudtrail",
        lambda c, _t: c.lookup_events(MaxResults=1),
    ),
    Probe(
        "the AWS Config aggregator",
        "inventory",
        "hub",
        "config",
        lambda c, t: c.describe_configuration_aggregators(
            ConfigurationAggregatorNames=[t.settings.config_aggregator]
        ),
        needs=("config_aggregator",),
    ),
    Probe(
        "the CUR export bucket",
        "cost_focus",
        "hub",
        "s3",
        lambda c, t: c.list_objects_v2(
            Bucket=t.settings.cur_export_bucket, Prefix=t.settings.cur_export_prefix, MaxKeys=1
        ),
    ),
    Probe(
        "the first Terraform state location",
        "iac_state",
        "hub",
        "s3",
        lambda c, t: c.head_object(**_first_state(t)),
        needs=("iac_state_locations",),
    ),
    Probe(
        "the Athena workgroup",
        "cost_focus",
        "hub",
        "athena",
        lambda c, t: c.get_work_group(WorkGroup=t.settings.cur_athena_workgroup),
    ),
    Probe(
        "Cost Explorer",
        "commitment and platform_cost",
        "hub",
        "ce",
        lambda c, t: c.get_cost_and_usage(
            TimePeriod=_yesterday(t), Granularity="DAILY", Metrics=["UnblendedCost"]
        ),
        region=GLOBAL_REGION,
    ),
    Probe(
        "Compute Optimizer",
        "recommendations",
        "hub",
        "compute-optimizer",
        lambda c, _t: c.get_enrollment_status(),
        region=GLOBAL_REGION,
    ),
    Probe(
        "the Price List",
        "price_catalog",
        "hub",
        "pricing",
        lambda c, _t: c.describe_services(MaxResults=1),
        region=GLOBAL_REGION,
    ),
    Probe(
        "EC2 instance types",
        "instance_catalog",
        "hub",
        "ec2",
        lambda c, _t: c.describe_instance_types(MaxResults=5),
    ),
    Probe(
        "Budgets, through the relay",
        "budgets",
        "relay",
        "budgets",
        lambda c, t: c.describe_budgets(AccountId=t.payer, MaxResults=1),
        needs=RELAYED,
        region=GLOBAL_REGION,
    ),
    Probe(
        "Invoicing, through the relay",
        "invoices",
        "relay",
        "invoicing",
        lambda c, t: c.list_invoice_summaries(
            Selector={"ResourceType": "ACCOUNT_ID", "Value": t.payer}, MaxResults=1
        ),
        needs=RELAYED,
        region=GLOBAL_REGION,
    ),
    Probe(
        "spot prices, through the relay",
        "spot_prices",
        "relay",
        "ec2",
        lambda c, _t: c.describe_spot_price_history(MaxResults=1),
        needs=RELAYED,
    ),
    Probe(
        "Savings Plans rates, through the relay",
        "savings_plan_rates",
        "relay",
        "savingsplans",
        lambda c, _t: c.describe_savings_plans_offering_rates(maxResults=1),
        needs=RELAYED,
        region=GLOBAL_REGION,
    ),
    Probe(
        "OpenAI's cost report, with the key named",
        "openai_usage",
        "provider",
        "openai",
        _a_day_of_costs("openai"),
    ),
    Probe(
        "Anthropic's cost report, with the key named",
        "anthropic_usage",
        "provider",
        "anthropic",
        _a_day_of_costs("anthropic"),
    ),
)

ClientFor = Callable[[Probe, Target], Any]


def clients(target: Target) -> ClientFor:
    """The deployed composition's paths to AWS, for each probe."""
    member = member_clients(target.settings)

    def client_for(probe: Probe, where: Target) -> Any:
        region = probe.region or where.region
        if probe.reach == "provider":
            # The worker's path: the key read from the AI path when the request is made.
            make, collector = PROVIDER_REPORTS[probe.service]
            keys = AiKeyReader(where.settings.env, hub_client(where.settings, "secretsmanager"))
            secret = where.ai_secrets[probe.service]
            return make(
                keys.reader(secret, scope_key=f"{probe.service}:{secret}", collector=collector)
            )
        if probe.reach == "payer":
            # The organization reader role in the management account, ISS-294 and ISS-296.
            return payer_client(where.settings, probe.service, region)
        if probe.reach == "member":
            return member(probe.service, where.account, region)
        if probe.reach == "relay":
            account = where.payer if probe.service in {"budgets", "invoicing"} else None
            return relay(where.settings, service=probe.service, region=region, account_id=account)
        if probe.reach == "relay-member":
            # Through the relay as the account's own collector role, ADR-0037.
            return relay(
                where.settings, service=probe.service, region=region, account_id=where.account
            )
        return hub_client(where.settings, probe.service, probe.region)

    return client_for


def _missing(probe: Probe, target: Target) -> str | None:
    if probe.reach == "provider" and probe.service not in target.ai_secrets:
        return f"--{probe.service}-secret was not given"
    for name in probe.needs:
        if not getattr(target.settings, name):
            return f"{ENV_PREFIX}{name.upper()} is empty"
    if (
        probe.reach == "payer" or probe.service in {"budgets", "invoicing"}
    ) and target.payer is None:
        return f"{ENV_PREFIX}ORG_READER_ROLE_ARN names no payer"
    return None


def contact(probes: Iterable[Probe], target: Target, client_for: ClientFor) -> list[Answer]:
    """Make each read once. A failure is typed exactly as a collector's would be."""
    answers = []
    for probe in probes:
        missing = _missing(probe, target)
        if missing is not None:
            answers.append(Answer(probe, NOT_TRIED, missing))
            continue
        try:
            probe.read(client_for(probe, target), target)
        except CollectionError as failure:
            answers.append(Answer(probe, failure.cause, str(failure)))
        # Every other failure is typed the way a collector's is, and none stops the reads after it.
        except Exception as failure:
            typed = translate(
                failure, scope_key=f"{target.account}:{target.region}", collector="first_contact"
            )
            answers.append(Answer(probe, typed.cause, str(typed)))
        else:
            answers.append(Answer(probe, ANSWERED))
    return answers


def settings_from_ssm(environment: str) -> Settings:
    """The settings the tasks of `environment` are given, read from its parameters.

    A setting with no parameter is one the tasks are given as empty, settings.tf.
    """
    pages = boto3.client("ssm").get_paginator("get_parameters_by_path")
    found = {
        parameter["Name"].rsplit("/", 1)[-1]: parameter["Value"]
        for page in pages.paginate(Path=f"/meter/{environment}/", WithDecryption=False)
        for parameter in page["Parameters"]
        if parameter["Type"] == "String"
    }
    values = {name: found.get(f"{ENV_PREFIX}{name.upper()}", "") for name in Settings.model_fields}
    values["session_signing_key"] = UNUSED_SECRET
    return Settings.model_validate(values)


def has_credentials() -> bool:
    return boto3.Session().get_credentials() is not None


def report(answers: Sequence[Answer]) -> str:
    width = max(len(answer.probe.reads) for answer in answers)
    lines = [
        f"{answer.outcome:<14} {answer.probe.reads:<{width}}  {answer.probe.collectors}"
        + (f"\n{'':<15}{answer.detail}" if answer.detail else "")
        for answer in answers
    ]
    answered = sum(1 for answer in answers if answer.outcome == ANSWERED)
    return "\n".join([*lines, f"\n{answered} of {len(answers)} reads answered."])


def main(
    argv: Sequence[str] | None = None,
    *,
    credentials: Callable[[], bool] = has_credentials,
    settings_for: Callable[[str], Settings] = settings_from_ssm,
    client_for: ClientFor | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Make each AWS read Meter depends on once.")
    parser.add_argument("--env", required=True, help="whose settings: dev, staging or prod")
    parser.add_argument("--account", required=True, help="the 12 digit account to read")
    parser.add_argument("--region", required=True, help="the Region to read it in")
    for provider in sorted(PROVIDER_REPORTS):
        parser.add_argument(
            f"--{provider}-secret",
            default="",
            help=f"the secret holding a {provider} organization's admin key, under meter/<env>/ai/",
        )
    arguments = parser.parse_args(argv)
    if not credentials():
        print(
            "first contact refused: no AWS credentials. Sign in to the hub account first; without "
            "them every read would fail for a reason that is not the account's.",
            file=sys.stderr,
        )
        return REFUSED
    target = Target(
        settings=settings_for(arguments.env),
        account=arguments.account,
        region=arguments.region,
        today=datetime.now(UTC).date(),
        ai_secrets={
            provider: secret
            for provider in PROVIDER_REPORTS
            if (secret := getattr(arguments, f"{provider}_secret"))
        },
    )
    asked = [one for one in PROBES if one.reach != "provider" or one.service in target.ai_secrets]
    answers = contact(asked, target, client_for or clients(target))
    print(report(answers))
    unread = sorted(set(PROVIDER_REPORTS) - set(target.ai_secrets))
    if unread:
        print(f"AI providers not read, no key's secret named: {', '.join(unread)}.")
    return ANSWERED_ALL if all(one.outcome == ANSWERED for one in answers) else NOT_ALL_ANSWERED


if __name__ == "__main__":  # pragma: no cover - run by make first-contact
    raise SystemExit(main())
