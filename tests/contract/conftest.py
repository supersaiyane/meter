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

import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

import pytest
from botocore.exceptions import ClientError

from finops_core.config import Settings, load_settings
from finops_core.domain.account import AccountKey, Provider
from finops_fakes import fixtures
from finops_fakes.provider import FakeProvider

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_EXAMPLE = ROOT / ".env.example"
VARIABLE = re.compile(r"^(METER_[A-Z0-9_]+)=(.*)$", re.MULTILINE)

ACCOUNT_DISCOVERY = "AccountDiscovery"
CREDENTIAL_BROKER = "CredentialBroker"
COST_EXPORT = "CostExport"
COMMITMENT_REPORT = "CommitmentReport"
TOPOLOGY_SOURCE = "TopologySource"
QUOTA_SOURCE = "QuotaSource"
CONTAINER_SOURCE = "ContainerSource"


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
        supports=frozenset(
            {
                ACCOUNT_DISCOVERY,
                CREDENTIAL_BROKER,
                COST_EXPORT,
                COMMITMENT_REPORT,
                TOPOLOGY_SOURCE,
                QUOTA_SOURCE,
                CONTAINER_SOURCE,
            }
        ),
    )


AWS_REGION = "eu-west-1"
AWS_KNOWN = AccountKey(provider=Provider.AWS, account_id="111122223333")
AWS_DENIED = AccountKey(provider=Provider.AWS, account_id="444455556666")
AWS_UNKNOWN = AccountKey(provider=Provider.AWS, account_id="777788889999")


AWS_ROOT = "r-contract"
AWS_UNIT = "ou-contract"


class ContractContainerInsights:
    """Container Insights as two clusters: one that publishes requests, one that does not.

    `contract-enhanced` has enhanced observability so `pod_cpu_request` exists for
    it. `contract-plain` does not, which is the case the whole port exists to keep
    honest: usage and no request, never a request of zero.
    """

    ENHANCED = "contract-enhanced"
    PLAIN = "contract-plain"

    def get_paginator(self, operation: str) -> Any:
        if operation == "list_metrics":
            return _ContractMetricList()
        if operation == "get_metric_data":
            return _ContractMetricData()
        raise AssertionError(f"the contract stub was asked for {operation}")


class _ContractMetricList:
    def paginate(self, **kwargs: Any) -> list[dict[str, Any]]:
        metric = kwargs.get("MetricName")
        wanted = {d["Name"] for d in kwargs.get("Dimensions") or ()}
        if metric == "pod_cpu_request":
            # Only the enhanced cluster, which is how the adapter learns which
            # clusters can report a request at all.
            return [
                {
                    "Metrics": [
                        {
                            "Dimensions": [
                                {"Name": "ClusterName", "Value": ContractContainerInsights.ENHANCED}
                            ]
                        }
                    ]
                }
            ]
        if wanted == {"ClusterName"}:
            return [
                {
                    "Metrics": [
                        {"Dimensions": [{"Name": "ClusterName", "Value": name}]}
                        for name in (
                            ContractContainerInsights.ENHANCED,
                            ContractContainerInsights.PLAIN,
                        )
                    ]
                }
            ]
        return [
            {
                "Metrics": [
                    {
                        "Dimensions": [
                            {"Name": "ClusterName", "Value": name},
                            {"Name": "Namespace", "Value": "payments"},
                            {"Name": "Service", "Value": "api"},
                        ]
                    }
                    for name in (
                        ContractContainerInsights.ENHANCED,
                        ContractContainerInsights.PLAIN,
                    )
                ]
            }
        ]


class _ContractMetricData:
    def paginate(self, **kwargs: Any) -> list[dict[str, Any]]:
        results = []
        for query in kwargs.get("MetricDataQueries") or ():
            metric = query["MetricStat"]["Metric"]["MetricName"]
            # Every query the adapter asks for gets a value, including the request
            # queries, which it only asks for on the enhanced cluster. The plain
            # cluster therefore comes back with usage and no request, without this
            # stub having to special case anything.
            value = {
                "pod_cpu_usage_total": 240.0,
                "pod_memory_working_set": 512.0,
                "pod_cpu_request": 1000.0,
                "pod_memory_request": 2048.0,
            }.get(metric)
            if value is None:
                continue
            results.append({"Id": query["Id"], "Values": [value]})
        return [{"MetricDataResults": results}]


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


#: One recorded Athena page, enough for the contract's questions and no more.
#: The adapter's own suite exercises the shapes; this asks whether both
#: implementations answer the same sentences.
CONTRACT_PERIOD = date(2026, 8, 1)
CONTRACT_ROW = {
    "billingaccountid": AWS_KNOWN.account_id,
    "subaccountid": AWS_DENIED.account_id,
    "billingperiodstart": "2026-08-01",
    "billingperiodend": "2026-09-01",
    "chargeperiodstart": "2026-08-01T00:00:00",
    "chargeperiodend": "2026-08-02T00:00:00",
    "providername": "AWS",
    "servicename": "AmazonEC2",
    "chargecategory": "Usage",
    "billedcost": "12.3400",
    "effectivecost": "11.0000",
}


class _ContractPages:
    def __init__(self, pages: list[Any]) -> None:
        self._pages = pages

    def paginate(self, **_: Any) -> Any:
        return iter(self._pages)


class ContractAthena:
    """Answers with one row for the contract period and nothing for any other."""

    def __init__(self) -> None:
        self._wanted = ""

    def start_query_execution(self, **kwargs: Any) -> Any:
        self._wanted = kwargs["QueryString"]
        return {"QueryExecutionId": "q-contract"}

    def get_query_execution(self, **_: Any) -> Any:
        return {"QueryExecution": {"Status": {"State": "SUCCEEDED", "StateChangeReason": ""}}}

    def get_paginator(self, _: str) -> _ContractPages:
        columns = sorted(CONTRACT_ROW)
        rows: list[Any] = [{"Data": [{"VarCharValue": name} for name in columns]}]
        if "2026-08" in self._wanted:
            rows.append({"Data": [{"VarCharValue": CONTRACT_ROW[name]} for name in columns]})
        return _ContractPages(
            [
                {
                    "ResultSet": {
                        "ResultSetMetadata": {"ColumnInfo": [{"Name": n} for n in columns]},
                        "Rows": rows,
                    }
                }
            ]
        )


class ContractCostExplorer:
    """Recorded Cost Explorer responses, shaped as the documentation describes them.

    Recorded rather than moto, because moto does not implement the Savings Plans or
    reservation reports at all. That is a real limit on what this contract proves:
    it holds the adapter to the documented response shape, and only a real account
    can settle whether the shape is right. ISS-122.

    The four commitments mirror the fake's on purpose, so a contract assertion that
    passes for one provider and fails for the other is telling us about the adapter
    and not about the data. The reservation figures are in hours, which is what the
    API actually returns and what makes the adapter derive money from them.
    """

    def get_savings_plans_utilization_details(self, **_: Any) -> dict[str, Any]:
        return {
            "SavingsPlansUtilizationDetails": [
                {
                    # Fully consumed. Utilization is one and the waste is nothing.
                    "SavingsPlanArn": "arn:aws:savingsplans::111122223333:savingsplan/live",
                    "Attributes": {
                        "startDateTime": "2026-01-01T00:00:00Z",
                        "endDateTime": "2027-01-01T00:00:00Z",
                    },
                    "Utilization": {
                        "TotalCommitment": "761.07",
                        "UsedCommitment": "761.07",
                        "UnusedCommitment": "0",
                        "UtilizationPercentage": "100",
                    },
                },
                {
                    # Ended inside the window. Reported as expired, never dropped.
                    "SavingsPlanArn": "arn:aws:savingsplans::111122223333:savingsplan/gone",
                    "Attributes": {
                        "startDateTime": "2025-08-01T00:00:00Z",
                        "endDateTime": "2026-08-15T00:00:00Z",
                    },
                    "Utilization": {
                        "TotalCommitment": "202.95",
                        "UsedCommitment": "202.95",
                        "UnusedCommitment": "0",
                        "UtilizationPercentage": "100",
                    },
                },
                {
                    # Purchased and not yet started, so it obliged nothing.
                    "SavingsPlanArn": "arn:aws:savingsplans::111122223333:savingsplan/queued",
                    "Attributes": {
                        "startDateTime": "2026-09-01T00:00:00Z",
                        "endDateTime": "2027-09-01T00:00:00Z",
                    },
                    "Utilization": {
                        "TotalCommitment": "0",
                        "UsedCommitment": "0",
                        "UnusedCommitment": "0",
                        "UtilizationPercentage": "0",
                    },
                },
            ]
        }

    def get_savings_plans_coverage(self, **_: Any) -> dict[str, Any]:
        return {
            "SavingsPlansCoverages": [
                {
                    "Attributes": {"SERVICE": "AmazonEC2"},
                    "Coverage": {
                        "SpendCoveredBySavingsPlans": "964.02",
                        "OnDemandCost": "1423.66",
                        "TotalCost": "2387.68",
                        "CoveragePercentage": "40.37",
                    },
                },
                {
                    # Eligible and entirely uncovered, which is a zero and not a None.
                    "Attributes": {"SERVICE": "AWSLambda"},
                    "Coverage": {
                        "SpendCoveredBySavingsPlans": "0",
                        "OnDemandCost": "149.23",
                        "TotalCost": "149.23",
                        "CoveragePercentage": "0",
                    },
                },
            ]
        }

    def get_reservation_utilization(self, **_: Any) -> dict[str, Any]:
        return {
            "UtilizationsByTime": [
                {
                    "Groups": [
                        {
                            "Key": "ri-rds-contract",
                            # Hours, not money. The adapter derives the money and
                            # says so, which is the point of recording it this way.
                            "Utilization": {
                                "PurchasedHours": "744",
                                "TotalActualHours": "461.28",
                                "UnusedHours": "282.72",
                                "UtilizationPercentage": "62",
                                "TotalAmortizedFee": "967.01",
                            },
                        }
                    ]
                }
            ]
        }

    def get_reservation_coverage(self, **_: Any) -> dict[str, Any]:
        return {
            "CoveragesByTime": [
                {
                    "Groups": [
                        {
                            "Attributes": {"SERVICE": "AmazonRDS"},
                            "Coverage": {
                                "CoverageCost": {
                                    "OnDemandCost": "474.90",
                                    "ReservedCost": "599.55",
                                }
                            },
                        }
                    ]
                }
            ]
        }


class ContractS3:
    def get_paginator(self, _: str) -> _ContractPages:
        return _ContractPages(
            [{"CommonPrefixes": [{"Prefix": "exports/focus/BILLING_PERIOD=2026-08/"}]}]
        )


#: One recorded Config aggregator page, holding exactly the shapes the contract
#: asks about: a regional resource with a relationship, the resource that
#: relationship names, a global resource, and a type the adapter cannot name.
#:
#: Recorded rather than moto, because moto does not implement
#: `select_aggregate_resource_config` at all. That is a real limit on what this
#: proves, and it is the same limit ISS-200 already records: the contract holds the
#: adapter to the documented response shape, and only a real account can settle
#: whether the shape is right.
CONTRACT_CAPTURED = "2026-08-24T06:00:00.000Z"
CONTRACT_VPC = f"arn:aws:ec2:{AWS_REGION}:{AWS_KNOWN.account_id}:vpc/vpc-contract"
CONTRACT_SUBNET = f"arn:aws:ec2:{AWS_REGION}:{AWS_KNOWN.account_id}:subnet/subnet-contract"
CONTRACT_ROLE = f"arn:aws:iam::{AWS_KNOWN.account_id}:role/contract-ci"
CONTRACT_CLUSTER = f"arn:aws:eks:{AWS_REGION}:{AWS_KNOWN.account_id}:cluster/contract"


def _config_item(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "accountId": AWS_KNOWN.account_id,
        "awsRegion": AWS_REGION,
        "resourceType": "AWS::EC2::VPC",
        "resourceId": CONTRACT_VPC,
        "resourceName": "contract",
        "arn": CONTRACT_VPC,
        "availabilityZone": None,
        "tags": [{"key": "finops:module", "value": "fixture"}],
        "configurationItemCaptureTime": CONTRACT_CAPTURED,
        "relationships": [],
    }
    values.update(overrides)
    return values


class ContractConfig:
    """Answers the aggregator query, and refuses for the denied account.

    The refusal is the half that matters. moto never refuses, and what the contract
    is asking is whether a refused slice comes back as a `SliceRead` carrying a typed
    cause rather than as an exception that discards every account after this one.
    """

    def select_aggregate_resource_config(self, **request: Any) -> Any:
        expression = str(request.get("Expression", ""))
        if AWS_DENIED.account_id in expression or AWS_UNKNOWN.account_id in expression:
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "refused"}},
                "SelectAggregateResourceConfig",
            )
        if "resourceType IN (" in expression:
            return {
                "Results": [
                    json.dumps(
                        _config_item(
                            resourceType="AWS::IAM::Role",
                            resourceId=CONTRACT_ROLE,
                            arn=CONTRACT_ROLE,
                            awsRegion=AWS_REGION,
                            resourceName="contract-ci",
                        )
                    )
                ]
            }
        return {
            "Results": [
                json.dumps(
                    _config_item(
                        relationships=[
                            {
                                "resourceType": "AWS::EC2::Subnet",
                                "resourceId": CONTRACT_SUBNET,
                                "relationshipName": "Contains Subnet",
                            }
                        ]
                    )
                ),
                json.dumps(
                    _config_item(
                        resourceType="AWS::EC2::Subnet",
                        resourceId=CONTRACT_SUBNET,
                        arn=CONTRACT_SUBNET,
                        resourceName="private-a",
                        availabilityZone=f"{AWS_REGION}a",
                    )
                ),
                json.dumps(
                    _config_item(
                        resourceType="AWS::EKS::Cluster",
                        resourceId=CONTRACT_CLUSTER,
                        arn=CONTRACT_CLUSTER,
                        resourceName="contract-eks",
                    )
                ),
            ]
        }


#: The quota the contract measures, the one nothing measures, and the one Trusted Advisor
#: reports. Three, because with a single measured quota an adapter that omitted the
#: unmeasurable ones entirely would pass every sentence in the contract.
CONTRACT_MEASURED_QUOTA = "L-1216C47A"
CONTRACT_UNMEASURED_QUOTA = "L-0EA8095F"
CONTRACT_ADVISOR_QUOTA = "L-53DA6B97"


class _Pages:
    """A paginator over a fixed list of pages, which is all these stubs need."""

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages

    def paginate(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return self._pages


class ContractServiceQuotas:
    """Service Quotas for one account, holding the three quotas above.

    The shapes are the ones `tests/providers/aws/test_response_shapes.py` checks against
    the botocore model, so a key here that AWS would never send fails there.
    """

    def __init__(self, *, refuse: bool = False) -> None:
        self._refuse = refuse

    def get_paginator(self, name: str) -> Any:
        if self._refuse:
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "refused"}}, name)
        if name == "list_services":
            return _Pages([{"Services": [{"ServiceCode": "ec2", "ServiceName": "Amazon EC2"}]}])
        if name == "list_service_quotas":
            return _Pages([{"Quotas": _CONTRACT_QUOTAS}])
        if name == "list_requested_service_quota_change_history":
            return _Pages([{"RequestedQuotas": _CONTRACT_REQUESTS}])
        raise AssertionError(f"the contract does not stub {name}")


_CONTRACT_QUOTAS: list[dict[str, Any]] = [
    {
        "ServiceCode": "ec2",
        "ServiceName": "Amazon EC2",
        "QuotaCode": CONTRACT_MEASURED_QUOTA,
        "QuotaName": "Running On-Demand Standard instances",
        "Value": 320.0,
        "Adjustable": True,
        "GlobalQuota": False,
        "UsageMetric": {
            "MetricNamespace": "AWS/Usage",
            "MetricName": "ResourceCount",
            "MetricDimensions": {
                "Service": "EC2",
                "Resource": "vCPU",
                "Type": "Resource",
                "Class": "Standard/OnDemand",
            },
            "MetricStatisticRecommendation": "Maximum",
        },
    },
    {
        # No usage metric and not adjustable, which is the common shape in a real estate.
        "ServiceCode": "ec2",
        "ServiceName": "Amazon EC2",
        "QuotaCode": CONTRACT_UNMEASURED_QUOTA,
        "QuotaName": "AMI sharing quota",
        "Value": 500.0,
        "Adjustable": False,
        "GlobalQuota": True,
    },
    {
        "ServiceCode": "ec2",
        "ServiceName": "Amazon EC2",
        "QuotaCode": CONTRACT_ADVISOR_QUOTA,
        "QuotaName": "Application Load Balancers",
        "Value": 50.0,
        "Adjustable": True,
        "GlobalQuota": False,
    },
]

_CONTRACT_REQUESTS: list[dict[str, Any]] = [
    {
        "Id": "contract-request-0001",
        "ServiceCode": "ec2",
        "QuotaCode": CONTRACT_MEASURED_QUOTA,
        "QuotaName": "Running On-Demand Standard instances",
        "DesiredValue": 640.0,
        "Status": "PENDING",
        "Created": datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
        "LastUpdated": datetime(2026, 9, 22, 9, 0, tzinfo=UTC),
        "GlobalQuota": False,
    },
    {
        # A request for a quota nothing can measure, and a refusal. Tracking and measuring
        # are independent, and DENIED is the status a product is tempted to hide.
        "Id": "contract-request-0002",
        "ServiceCode": "ec2",
        "QuotaCode": CONTRACT_UNMEASURED_QUOTA,
        "QuotaName": "AMI sharing quota",
        "DesiredValue": 1000.0,
        "Status": "DENIED",
        "Created": datetime(2026, 8, 1, 9, 0, tzinfo=UTC),
        "LastUpdated": datetime(2026, 8, 9, 9, 0, tzinfo=UTC),
        "GlobalQuota": True,
    },
]


class ContractCloudWatch:
    """One measured series, and nothing for the other two quotas.

    The queries that come back with no result are the point: a quota whose metric
    published nothing is unmeasured, and it must not arrive as a zero.
    """

    def get_paginator(self, name: str) -> Any:
        assert name == "get_metric_data"
        return _Pages(
            [
                {
                    "MetricDataResults": [
                        {"Id": "q0", "Values": [180.0, 212.0, 196.0], "StatusCode": "Complete"}
                    ]
                }
            ]
        )


class ContractSupport:
    """Trusted Advisor with the service limits check, or without the support tier."""

    def __init__(self, *, subscribed: bool = True) -> None:
        self._subscribed = subscribed

    def describe_trusted_advisor_checks(self, **_kwargs: Any) -> Any:
        if not self._subscribed:
            raise ClientError(
                {"Error": {"Code": "SubscriptionRequiredException", "Message": "no plan"}},
                "DescribeTrustedAdvisorChecks",
            )
        return {"checks": [{"id": "contract-check", "name": "Service Limits"}]}

    def describe_trusted_advisor_check_result(self, **_kwargs: Any) -> Any:
        return {
            "result": {
                "checkId": "contract-check",
                "flaggedResources": [
                    {
                        "status": "warning",
                        "region": AWS_REGION,
                        # region, service, limit name, limit, usage, status. A bare
                        # positional list, which is why the adapter names its indices.
                        "metadata": [
                            AWS_REGION,
                            "Amazon EC2",
                            "Application Load Balancers",
                            "50",
                            "43",
                            "Yellow",
                        ],
                    }
                ],
            }
        }


#: One instance per service, so a test can reason about how many calls were made.
_CONTRACT_QUOTA_CLIENTS: dict[str, Any] = {
    "service-quotas": ContractServiceQuotas(),
    "cloudwatch": ContractCloudWatch(),
    "support": ContractSupport(),
}


class AwsUnderContract:
    """The AWS adapters presented as the one object the contract talks to."""

    def __init__(
        self,
        broker: Any,
        discovery: Any,
        cost: Any,
        commitment: Any,
        topology: Any,
        quotas: Any,
        containers: Any,
    ) -> None:
        self._broker = broker
        self._discovery = discovery
        self._cost = cost
        self._commitment = commitment
        self._topology = topology
        self._quotas = quotas
        self._containers = containers

    def list_clusters(self, account: AccountKey, region: str) -> Any:
        return self._containers.list_clusters(account, region)

    def reservations(self, account: AccountKey, region: str) -> Any:
        return self._containers.reservations(account, region)

    def list_quotas(self, account: AccountKey, region: str) -> Any:
        return self._quotas.list_quotas(account, region)

    def requests(self, account: AccountKey, region: str) -> Any:
        return self._quotas.requests(account, region)

    @property
    def enrolled_slices(self) -> Any:
        return self._topology.enrolled_slices

    def read_slice(self, account: AccountKey, region: str | None) -> Any:
        return self._topology.read_slice(account, region)

    def utilization(self, window_start: Any, window_end: Any) -> Any:
        return self._commitment.utilization(window_start, window_end)

    def coverage(self, window_start: Any, window_end: Any) -> Any:
        return self._commitment.coverage(window_start, window_end)

    def latest_available_period(self) -> Any:
        return self._cost.latest_available_period()

    def read_period(self, period_start: Any, period_end: Any) -> Any:
        return self._cost.read_period(period_start, period_end)

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
    from finops_providers.aws.commitment import CostExplorerCommitmentReport
    from finops_providers.aws.config_inventory import ConfigAggregatorInventory
    from finops_providers.aws.container_insights import ContainerInsightsSource
    from finops_providers.aws.credentials import AwsCredentialBroker
    from finops_providers.aws.cur import AthenaCostExport
    from finops_providers.aws.quotas import AwsQuotas

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
                cost=AthenaCostExport(
                    settings,
                    tenant_id=fixtures.TENANT_ID,
                    ingest_run_id=fixtures.INGEST_RUN_ID,
                    client_factory=lambda service: (
                        ContractAthena() if service == "athena" else ContractS3()
                    ),
                    sleeper=lambda _: None,
                ),
                commitment=CostExplorerCommitmentReport(
                    settings,
                    tenant_id=fixtures.TENANT_ID,
                    client_factory=lambda: ContractCostExplorer(),
                ),
                topology=ConfigAggregatorInventory(
                    settings,
                    client=ContractConfig(),
                    aggregator_name="contract-aggregator",
                    tenant_id=fixtures.TENANT_ID,
                    enrolled=(
                        (AWS_KNOWN, AWS_REGION),
                        (AWS_KNOWN, None),
                        (AWS_DENIED, AWS_REGION),
                    ),
                    sleeper=lambda _seconds: None,
                ),
                quotas=AwsQuotas(
                    client_factory=lambda service, _region: _CONTRACT_QUOTA_CLIENTS[service],
                    clock=lambda: datetime(2026, 9, 28, 9, 0, tzinfo=UTC),
                ),
                containers=ContainerInsightsSource(
                    settings,
                    client_factory=lambda _service, _region: ContractContainerInsights(),
                    clock=lambda: datetime(2026, 9, 28, 9, 0, tzinfo=UTC),
                ),
            ),
            region=AWS_REGION,
            known_account=AWS_KNOWN,
            denied_account=AWS_DENIED,
            unknown_account=AWS_UNKNOWN,
            supports=frozenset(
                {
                    ACCOUNT_DISCOVERY,
                    CREDENTIAL_BROKER,
                    COST_EXPORT,
                    COMMITMENT_REPORT,
                    TOPOLOGY_SOURCE,
                    QUOTA_SOURCE,
                    CONTAINER_SOURCE,
                }
            ),
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
def requires_port(subject: ProviderUnderTest) -> Callable[[str], None]:
    """Skip by name when a provider has not implemented the port under test."""

    def check(port: str) -> None:
        if port not in subject.supports:
            pytest.skip(f"{subject.name} does not implement {port} yet")

    return check
