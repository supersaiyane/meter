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
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final
from urllib.parse import urlsplit

import boto3

from finops_core.config import Settings
from finops_core.constants import ENV_PREFIX
from finops_core.errors import CollectionError
from finops_providers.aws.client import translate
from finops_providers.aws.reach import (
    GLOBAL_REGION,
    hub_client,
    member_clients,
    payer_of,
    relay,
)

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
        "AWS Organizations",
        "org_tree",
        "hub",
        "organizations",
        lambda c, _t: c.describe_organization(),
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
        "container_usage and gpu_utilization",
        "member",
        "cloudwatch",
        lambda c, _t: c.list_metrics(Namespace="AWS/EC2", RecentlyActive="PT3H"),
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
)

ClientFor = Callable[[Probe, Target], Any]


def clients(target: Target) -> ClientFor:
    """The deployed composition's paths to AWS, for each probe."""
    member = member_clients(target.settings)

    def client_for(probe: Probe, where: Target) -> Any:
        region = probe.region or where.region
        if probe.reach == "member":
            return member(probe.service, where.account, region)
        if probe.reach == "relay":
            account = where.payer if probe.service in {"budgets", "invoicing"} else None
            return relay(where.settings, service=probe.service, region=region, account_id=account)
        return hub_client(where.settings, probe.service, probe.region)

    return client_for


def _missing(probe: Probe, target: Target) -> str | None:
    for field in probe.needs:
        if not getattr(target.settings, field):
            return f"{ENV_PREFIX}{field.upper()} is empty"
    if probe.service in {"budgets", "invoicing"} and target.payer is None:
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
    )
    answers = contact(PROBES, target, client_for or clients(target))
    print(report(answers))
    return ANSWERED_ALL if all(one.outcome == ANSWERED for one in answers) else NOT_ALL_ANSWERED


if __name__ == "__main__":  # pragma: no cover - run by make first-contact
    raise SystemExit(main())
