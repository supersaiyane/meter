"""Every field these adapters read, checked against the model boto3 builds clients from.

ISS-200, ISS-202, ISS-209 and ISS-211 all say the same thing about four different adapters: the
response shapes in them were read from the AWS documentation and from nothing else, and the tests
answer from a literal, so a field name that does not exist would pass every gate this project has
and fail on the first real call.

**This does not make a real call and does not claim to.** What it does is remove the part of that
risk that is about names. `botocore` ships the JSON service models that `boto3` itself uses to
build every client, they are versioned with the SDK, and they are the same source the
documentation is generated from. A key this project reads that is absent from the output shape is
a key AWS will never send, and that is knowable offline.

What remains, and what keeps all four issues open, is everything a shape cannot tell you:
whether a field is populated in practice, whether an empty list means none or means not
permitted, how throttling actually arrives, and whether the semantics match what the adapter
assumes. Those need a real account, which is ISS-002.

The declared sets below are also the only written record of what each adapter depends on, which
is worth having on its own: adding a read without adding it here fails, and that is the point.
"""

from __future__ import annotations

import json
import pathlib

import botocore
import botocore.session
import pytest
from botocore.model import ListShape, MapShape, StructureShape

#: What each adapter reads, per operation. Service, operation, then every response key it touches
#: at any depth, because the checker walks the shape rather than only its top level.
READS: dict[tuple[str, str], set[str]] = {
    # FEAT-082, TASK-P13-003. Where the invocation logs go, and one aggregate query's answer.
    ("bedrock", "GetModelInvocationLoggingConfiguration"): {
        "loggingConfig",
        "cloudWatchConfig",
        "logGroupName",
        "s3Config",
    },
    ("logs", "StartQuery"): {"queryId"},
    ("logs", "GetQueryResults"): {"results", "status", "nextToken", "field", "value"},
    # FEAT-083, TASK-P13-004. An AI provider organization's admin key, by the secret's name.
    ("secretsmanager", "GetSecretValue"): {"SecretString"},
    # FEAT-030, ISS-200. The inventory, one advanced query against the aggregator.
    ("config", "SelectAggregateResourceConfig"): {"Results", "NextToken"},
    # FEAT-031, ISS-202. Three EC2 reads and one IAM read.
    ("ec2", "DescribeTransitGatewayAttachments"): {
        "TransitGatewayAttachments",
        "TransitGatewayAttachmentId",
        "TransitGatewayId",
        "TransitGatewayOwnerId",
        "ResourceId",
        "ResourceType",
        "ResourceOwnerId",
        "State",
        "NextToken",
    },
    ("ec2", "DescribeVpcPeeringConnections"): {
        "VpcPeeringConnections",
        "VpcPeeringConnectionId",
        "AccepterVpcInfo",
        "RequesterVpcInfo",
        "VpcId",
        "OwnerId",
        "Region",
        "NextToken",
    },
    ("ec2", "DescribeVpcEndpointConnections"): {
        "VpcEndpointConnections",
        "VpcEndpointId",
        "VpcEndpointOwner",
        "ServiceId",
        "NextToken",
    },
    ("iam", "ListRoles"): {
        "Roles",
        "RoleName",
        "Arn",
        "AssumeRolePolicyDocument",
        "Marker",
        "IsTruncated",
    },
    # FEAT-057, ISS-209. The state file, one object read.
    ("s3", "GetObject"): {"Body"},
    # FEAT-076, TASK-P10-003. The payer's invoices, one paginated list per billing period.
    ("invoicing", "ListInvoiceSummaries"): {
        "InvoiceSummaries",
        "AccountId",
        "InvoiceId",
        "IssuedDate",
        "DueDate",
        "Entity",
        "InvoicingEntity",
        "BillingPeriod",
        "Month",
        "Year",
        "InvoiceType",
        "OriginalInvoiceId",
        "BaseCurrencyAmount",
        "TotalAmount",
        "TotalAmountBeforeTax",
        "CurrencyCode",
        "AmountBreakdown",
        "Taxes",
        "NextToken",
    },
    # FEAT-071, TASK-P9-004. The price list: its versions, then each version's products. A product
    # is a JSON string, so what is read inside it is held to the API reference's sample instead,
    # tests/providers/aws/test_price_list.py.
    ("pricing", "ListPriceLists"): {
        "PriceLists",
        "PriceListArn",
        "RegionCode",
        "CurrencyCode",
        "NextToken",
    },
    ("pricing", "GetProducts"): {"PriceList", "NextToken"},
    # FEAT-071, TASK-P9-012. Savings Plans rates, through the relay, which follows the token.
    ("savingsplans", "DescribeSavingsPlansOfferingRates"): {
        "searchResults",
        "savingsPlanOffering",
        "offeringId",
        "paymentOption",
        "planType",
        "durationSeconds",
        "currency",
        "rate",
        "unit",
        "productType",
        "serviceCode",
        "usageType",
        "operation",
        "properties",
        "name",
        "value",
        "nextToken",
    },
    # FEAT-071, TASK-P9-013. Spot readings, through the relay, botocore's own paginator.
    ("ec2", "DescribeSpotPriceHistory"): {
        "SpotPriceHistory",
        "AvailabilityZone",
        "InstanceType",
        "ProductDescription",
        "SpotPrice",
        "Timestamp",
        "NextToken",
    },
    # TASK-P9-006. Compute Optimizer, a Region and an account at a time, every ranked option.
    ("compute-optimizer", "GetEC2InstanceRecommendations"): {
        "instanceRecommendations",
        "instanceArn",
        "finding",
        "currentInstanceType",
        "lookBackPeriodInDays",
        "recommendationOptions",
        "instanceType",
        "rank",
        "performanceRisk",
        "migrationEffort",
        "platformDifferences",
        "savingsOpportunity",
        "estimatedMonthlySavings",
        "value",
        "nextToken",
    },
    # FEAT-072, TASK-P9-005. EC2's description of its types, every figure the spec stores.
    ("ec2", "DescribeInstanceTypes"): {
        "InstanceTypes",
        "InstanceType",
        "CurrentGeneration",
        "ProcessorInfo",
        "SupportedArchitectures",
        "BurstablePerformanceSupported",
        "VCpuInfo",
        "DefaultVCpus",
        "MemoryInfo",
        "SizeInMiB",
        "NetworkInfo",
        "NetworkPerformance",
        "NetworkCards",
        "BaselineBandwidthInGbps",
        "PeakBandwidthInGbps",
        "EbsInfo",
        "EbsOptimizedInfo",
        "BaselineBandwidthInMbps",
        "MaximumBandwidthInMbps",
        "GpuInfo",
        "Gpus",
        "Count",
        "NextToken",
    },
    # FEAT-060, ISS-211. The budgets, one paginated describe.
    ("budgets", "DescribeBudgets"): {
        "Budgets",
        "BudgetName",
        "BudgetLimit",
        "Amount",
        "Unit",
        "TimeUnit",
        "BudgetType",
        "CostFilters",
        "TimePeriod",
        "Start",
        "End",
        "NextToken",
    },
    # FEAT-033, ISS-122. Service Quotas for limits, and it names its own usage metric, which
    # is why `UsageMetric` and its four members are read rather than a metric table being
    # kept in the adapter.
    ("service-quotas", "ListServices"): {"Services", "ServiceCode", "ServiceName", "NextToken"},
    ("service-quotas", "ListServiceQuotas"): {
        "Quotas",
        "ServiceCode",
        "ServiceName",
        "QuotaCode",
        "QuotaName",
        "Value",
        "Adjustable",
        "GlobalQuota",
        "QuotaAppliedAtLevel",
        "ErrorReason",
        "UsageMetric",
        "MetricNamespace",
        "MetricName",
        "MetricDimensions",
        "MetricStatisticRecommendation",
        "NextToken",
    },
    # FEAT-034. The tracking half, which is the half actually missing today.
    ("service-quotas", "ListRequestedServiceQuotaChangeHistory"): {
        "RequestedQuotas",
        "Id",
        "ServiceCode",
        "QuotaCode",
        "QuotaName",
        "DesiredValue",
        "Status",
        "Created",
        "LastUpdated",
        "GlobalQuota",
        "NextToken",
    },
    ("cloudwatch", "GetMetricData"): {"MetricDataResults", "Id", "Values", "NextToken"},
    ("support", "DescribeTrustedAdvisorChecks"): {"checks", "id", "name"},
    # `metadata` is a bare list of strings with no keys, so a shape check can confirm the
    # field exists and nothing more. What each position means is the weakest assumption in
    # `finops_providers/aws/quotas.py` and is stated there rather than here.
    ("support", "DescribeTrustedAdvisorCheckResult"): {
        "result",
        "flaggedResources",
        "metadata",
        "region",
    },
    # The two service API counters, for quotas nothing else publishes usage for.
    ("ec2", "DescribeVpcs"): {"Vpcs", "NextToken"},
    ("ec2", "DescribeAddresses"): {"Addresses"},
    # FEAT-038, TASK-P7-004. Declared before the adapter existed, which is the order that caught
    # the request status defect in P5. Converse rather than InvokeModel, because its tool use
    # shape is the same for every model Bedrock carries, so OPEN-10's answer is a setting.
    ("bedrock-runtime", "Converse"): {
        "output",
        "message",
        "content",
        "text",
        "toolUse",
        "toolUseId",
        "name",
        "input",
        "stopReason",
        "usage",
        "inputTokens",
        "outputTokens",
    },
    # FEAT-077, TASK-P11-003. AppRegistry's applications, the tag and stacks that mark their
    # resources, and the owner their attribute groups name.
    ("servicecatalog-appregistry", "ListApplications"): {"applications", "id", "name", "nextToken"},
    ("servicecatalog-appregistry", "GetApplication"): {"applicationTag"},
    ("servicecatalog-appregistry", "ListAssociatedResources"): {
        "resources",
        "resourceType",
        "arn",
        "nextToken",
    },
    ("servicecatalog-appregistry", "ListAttributeGroupsForApplication"): {
        "attributeGroupsDetails",
        "id",
        "nextToken",
    },
    ("servicecatalog-appregistry", "GetAttributeGroup"): {"attributes"},
    # FEAT-077, TASK-P11-004. The event that created a resource and who made the call.
    ("cloudtrail", "LookupEvents"): {
        "Events",
        "EventId",
        "EventName",
        "EventTime",
        "CloudTrailEvent",
        "NextToken",
    },
}

#: Which key carries the continuation token, per operation. Separate from the reads because this
#: is the one a shape check alone would pass and a real call would hang on: IAM pages on `Marker`
#: and everything else here pages on `NextToken`, and an adapter that sent the wrong one would
#: read the first page forever.
TOKENS: dict[tuple[str, str], str] = {
    ("config", "SelectAggregateResourceConfig"): "NextToken",
    ("ec2", "DescribeTransitGatewayAttachments"): "NextToken",
    ("ec2", "DescribeVpcPeeringConnections"): "NextToken",
    ("ec2", "DescribeVpcEndpointConnections"): "NextToken",
    ("iam", "ListRoles"): "Marker",
    ("budgets", "DescribeBudgets"): "NextToken",
    ("invoicing", "ListInvoiceSummaries"): "NextToken",
    ("pricing", "ListPriceLists"): "NextToken",
    ("pricing", "GetProducts"): "NextToken",
    ("ec2", "DescribeInstanceTypes"): "NextToken",
    ("ec2", "DescribeSpotPriceHistory"): "NextToken",
    ("service-quotas", "ListServices"): "NextToken",
    ("service-quotas", "ListServiceQuotas"): "NextToken",
    ("service-quotas", "ListRequestedServiceQuotaChangeHistory"): "NextToken",
    ("cloudwatch", "GetMetricData"): "NextToken",
    ("ec2", "DescribeVpcs"): "NextToken",
    ("cloudtrail", "LookupEvents"): "NextToken",
}


def members_of(shape: object, seen: set[str] | None = None) -> set[str]:
    """Every member name in a shape, at any depth.

    Recursive because the names this project reads are nested: `BudgetLimit` is on a budget and
    `Amount` is on the limit, and a check on the top level alone would pass an adapter reading a
    field that does not exist two levels down, which is exactly the mistake being guarded.

    `seen` guards the recursion. Several AWS shapes refer to themselves, directly or through a
    list, and without it this walks until the stack ends.
    """
    seen = seen if seen is not None else set()
    found: set[str] = set()
    if isinstance(shape, StructureShape):
        if shape.name in seen:
            return found
        seen.add(shape.name)
        for name, member in shape.members.items():
            found.add(name)
            found |= members_of(member, seen)
    elif isinstance(shape, ListShape):
        found |= members_of(shape.member, seen)
    elif isinstance(shape, MapShape):
        found |= members_of(shape.value, seen)
    return found


@pytest.fixture(scope="module")
def loader() -> botocore.session.Session:
    return botocore.session.get_session()


@pytest.mark.parametrize(("service", "operation"), sorted(READS))
def test_every_field_the_adapter_reads_exists_in_the_service_model(
    service: str, operation: str, loader: botocore.session.Session
) -> None:
    """The check. A key absent here is a key AWS will never send.

    Failing this means one of two things and both are worth stopping for: the adapter invented a
    name, or AWS renamed one and the SDK moved with it. The second is why this runs against the
    installed botocore rather than a copy taken once.
    """
    model = loader.get_service_model(service).operation_model(operation)
    output = model.output_shape
    assert output is not None, f"{service}.{operation} declares no output shape"
    available = members_of(output)
    missing = sorted(READS[(service, operation)] - available)
    assert not missing, (
        f"{service}.{operation} has no such field: {missing}. "
        f"The adapter reads a name the service model does not have, so a real call returns "
        f"nothing for it. Check the field against botocore {botocore.__version__}."
    )


@pytest.mark.parametrize(("service", "operation"), sorted(TOKENS))
def test_the_continuation_token_is_the_one_the_service_uses(service: str, operation: str) -> None:
    """The failure a shape check alone would pass and a real call would hang on.

    An adapter that sends the wrong token key gets the first page every time, forever, and on an
    estate small enough to fit in one page it looks perfect. Read from the paginator
    configuration botocore ships, which is what the SDK's own paginators are built from.
    """
    path = pathlib.Path(botocore.__file__).parent / "data" / service
    versions = sorted(p for p in path.iterdir() if p.is_dir())
    config: dict[str, dict[str, str | list[str]]] = {}
    for version in versions:
        paginators = version / "paginators-1.json"
        if paginators.exists():
            config = json.loads(paginators.read_text())["pagination"]
    assert operation in config, (
        f"{service}.{operation} is not paginated according to botocore, so the adapter should "
        f"not be sending a continuation token for it"
    )
    declared = config[operation]
    # `output_token` is what the response carries; the adapter has to send it back as
    # `input_token`. Some operations declare a list of tokens, so the first is taken.
    expected = declared["input_token"]
    expected_name = expected if isinstance(expected, str) else expected[0]
    assert TOKENS[(service, operation)] == expected_name, (
        f"{service}.{operation} pages on {expected_name!r}, not "
        f"{TOKENS[(service, operation)]!r}. Sending the wrong key reads page one forever."
    )


#: What each adapter sends. The check below is the other half of a first call failing: a shape
#: check passes an adapter that reads the right fields from a request the service will refuse.
SENDS: dict[tuple[str, str], set[str]] = {
    # The configuration takes nothing; the query its window, its text and the one log group.
    ("bedrock", "GetModelInvocationLoggingConfiguration"): set(),
    ("logs", "StartQuery"): {"logGroupName", "startTime", "endTime", "queryString"},
    ("logs", "GetQueryResults"): {"queryId"},
    ("secretsmanager", "GetSecretValue"): {"SecretId"},
    ("config", "SelectAggregateResourceConfig"): {"ConfigurationAggregatorName", "Expression"},
    ("ec2", "DescribeTransitGatewayAttachments"): set(),
    ("ec2", "DescribeVpcPeeringConnections"): set(),
    ("ec2", "DescribeVpcEndpointConnections"): set(),
    ("iam", "ListRoles"): set(),
    ("s3", "GetObject"): {"Bucket", "Key"},
    ("budgets", "DescribeBudgets"): {"AccountId"},
    ("invoicing", "ListInvoiceSummaries"): {"Selector", "Filter"},
    ("pricing", "ListPriceLists"): {"ServiceCode", "EffectiveDate", "CurrencyCode"},
    ("pricing", "GetProducts"): {"ServiceCode", "FormatVersion", "Filters"},
    ("savingsplans", "DescribeSavingsPlansOfferingRates"): {
        "savingsPlanTypes",
        "savingsPlanPaymentOptions",
        "products",
        "filters",
        "maxResults",
    },
    # The window's two ends, and every zone and product description.
    ("ec2", "DescribeSpotPriceHistory"): {"StartTime", "EndTime", "MaxResults"},
    # One account a request, and Graviton asked for through the architecture preference.
    ("compute-optimizer", "GetEC2InstanceRecommendations"): {
        "accountIds",
        "recommendationPreferences",
    },
    # Every type, unfiltered: the hub's Region describes all it supports.
    ("ec2", "DescribeInstanceTypes"): set(),
    ("service-quotas", "ListServices"): set(),
    ("service-quotas", "ListServiceQuotas"): {"ServiceCode"},
    ("service-quotas", "ListRequestedServiceQuotaChangeHistory"): set(),
    # All three required, and a window that is missing one is refused rather than defaulted.
    ("cloudwatch", "GetMetricData"): {"MetricDataQueries", "StartTime", "EndTime"},
    ("support", "DescribeTrustedAdvisorChecks"): {"language"},
    ("support", "DescribeTrustedAdvisorCheckResult"): {"checkId", "language"},
    ("ec2", "DescribeVpcs"): set(),
    ("ec2", "DescribeAddresses"): set(),
    # Every application, then each one by its id.
    ("servicecatalog-appregistry", "ListApplications"): set(),
    ("servicecatalog-appregistry", "GetApplication"): {"application"},
    ("servicecatalog-appregistry", "ListAssociatedResources"): {"application"},
    ("servicecatalog-appregistry", "ListAttributeGroupsForApplication"): {"application"},
    ("servicecatalog-appregistry", "GetAttributeGroup"): {"attributeGroup"},
    # By resource name inside the documented window; the service requires nothing.
    ("cloudtrail", "LookupEvents"): set(),
}


@pytest.mark.parametrize(("service", "operation"), sorted(SENDS))
def test_the_request_carries_every_parameter_the_service_requires(
    service: str, operation: str, loader: botocore.session.Session
) -> None:
    """A request missing a required parameter is refused before it reads anything.

    The other half of a first call failing, and invisible to the shape check above: an adapter
    can read exactly the right fields from a call the service never accepts. Asserted in the
    direction that matters, that everything required is sent, rather than that nothing extra is,
    because an extra parameter is usually a filter and is usually deliberate.
    """
    model = loader.get_service_model(service).operation_model(operation)
    shape = model.input_shape
    required = set(shape.required_members) if shape is not None else set()
    unsent = sorted(required - SENDS[(service, operation)])
    assert not unsent, (
        f"{service}.{operation} requires {unsent}, which the adapter does not send. "
        f"The service refuses the call before it returns anything."
    )


#: Errors each operation declares that `translate` does not map, and which therefore arrive as
#: `SchemaDrift`. Pinned rather than fixed, because the fix is a taxonomy decision: see ISS-215.
#:
#: SchemaDrift is deliberate and is not a silent zero, which is the property that matters most.
#: It is also the wrong word for most of these. A wrong aggregator name or a state file path that
#: does not exist is a misconfiguration, and telling an operator their schema has drifted sends
#: them to look for an API change when the fix is one setting.
#:
#: This list is here so that a code AWS adds in a future SDK shows up as a failure rather than
#: quietly joining the fall through.
FALLS_THROUGH: dict[tuple[str, str], set[str]] = {
    ("config", "SelectAggregateResourceConfig"): {
        # Our own request being wrong, which is SchemaDrift on purpose: it says we are wrong,
        # and Misconfigured says the operator is. ADR-0026.
        "InvalidExpressionException",
        "InvalidLimitException",
        "InvalidNextTokenException",
    },
    ("ec2", "DescribeTransitGatewayAttachments"): set(),
    ("ec2", "DescribeVpcPeeringConnections"): set(),
    ("ec2", "DescribeVpcEndpointConnections"): set(),
    ("iam", "ListRoles"): {"ServiceFailure"},
    # NoSuchKey left on 2026-09-28: it is Misconfigured now, under ADR-0026.
    ("s3", "GetObject"): {"InvalidObjectState"},
    ("budgets", "DescribeBudgets"): {
        "ExpiredNextTokenException",
        "InternalErrorException",
        "InvalidNextTokenException",
        "InvalidParameterException",
        "NotFoundException",
    },
    # The Invoicing API refuses as AccessDeniedException and throttles as ThrottlingException,
    # both mapped. What is left is our own request being wrong, a payer the API does not know,
    # and the service failing, SchemaDrift for now as ISS-215 records for every adapter here.
    ("invoicing", "ListInvoiceSummaries"): {
        "InternalServerException",
        "ResourceNotFoundException",
        "ValidationException",
    },
    # The Price List API refuses as AccessDeniedException and throttles as ThrottlingException,
    # both mapped. What is left is a page token that expired or is wrong, our own request being
    # wrong, a service or price list the API does not know, and the service failing: SchemaDrift
    # for now, as ISS-215 records for every adapter here.
    ("pricing", "ListPriceLists"): {
        "ExpiredNextTokenException",
        "InternalErrorException",
        "InvalidNextTokenException",
        "InvalidParameterException",
        "NotFoundException",
        "ResourceNotFoundException",
    },
    ("pricing", "GetProducts"): {
        "ExpiredNextTokenException",
        "InternalErrorException",
        "InvalidNextTokenException",
        "InvalidParameterException",
        "NotFoundException",
    },
    # Service Quotas throttles as TooManyRequestsException and refuses as
    # AccessDeniedException, both of which translate maps. What is left is our own request
    # being wrong, a page token that expired, and the service failing: SchemaDrift for the
    # first, and the transient group ISS-215 names for the other two.
    ("service-quotas", "ListServices"): {
        "IllegalArgumentException",
        "InvalidPaginationTokenException",
        "ServiceException",
    },
    ("service-quotas", "ListServiceQuotas"): {
        "IllegalArgumentException",
        "InvalidPaginationTokenException",
        # A service code that does not exist. It comes from ListServices, so this can only
        # mean we sent something wrong, which is what SchemaDrift is for.
        "NoSuchResourceException",
        "ServiceException",
    },
    ("service-quotas", "ListRequestedServiceQuotaChangeHistory"): {
        "IllegalArgumentException",
        "InvalidPaginationTokenException",
        "NoSuchResourceException",
        "ServiceException",
    },
    ("cloudwatch", "GetMetricData"): {"InvalidNextToken"},
    # Support declares only these two. Notably it does NOT declare
    # SubscriptionRequiredException, which is what an account without Business or Enterprise
    # support actually receives and which NOT_OPTED_IN_CODES maps. OPEN-03 depends on that
    # code, so the pin cannot prove it and only a real account can: the adapter absorbs the
    # NotOptedIn either way, so the worst case is a plan without Trusted Advisor arriving as
    # SchemaDrift in the reason sentence rather than as NotOptedIn.
    ("support", "DescribeTrustedAdvisorChecks"): {"InternalServerError"},
    ("support", "DescribeTrustedAdvisorCheckResult"): {"InternalServerError"},
    # Savings Plans declares two, both our request or the service failing: SchemaDrift for now,
    # ISS-215. It throttles and refuses with codes it does not declare, which translate maps.
    ("savingsplans", "DescribeSavingsPlansOfferingRates"): {
        "InternalServerException",
        "ValidationException",
    },
    # Compute Optimizer's not enabled codes become NotOptedIn in the adapter itself, ISS-004;
    # what is left here reaches translate as SchemaDrift, ISS-215.
    ("compute-optimizer", "GetEC2InstanceRecommendations"): {
        "InternalServerException",
        "InvalidParameterValueException",
        "MissingAuthenticationToken",
        "OptInRequiredException",
        "ResourceNotFoundException",
        "ServiceUnavailableException",
    },
    # EC2 declares no modelled errors at all for either counter, nor for its instance types.
    ("ec2", "DescribeVpcs"): set(),
    ("ec2", "DescribeInstanceTypes"): set(),
    ("ec2", "DescribeSpotPriceHistory"): set(),
    ("ec2", "DescribeAddresses"): set(),
    # AppRegistry. An application deleted between the list and the read is ResourceNotFound and
    # fails the account and Region as SchemaDrift, loud and never an owner of nobody, ISS-215.
    ("servicecatalog-appregistry", "ListApplications"): {
        "InternalServerException",
        "ValidationException",
    },
    ("servicecatalog-appregistry", "GetApplication"): {
        "ConflictException",
        "InternalServerException",
        "ResourceNotFoundException",
        "ValidationException",
    },
    ("servicecatalog-appregistry", "ListAssociatedResources"): {
        "InternalServerException",
        "ResourceNotFoundException",
        "ValidationException",
    },
    ("servicecatalog-appregistry", "ListAttributeGroupsForApplication"): {
        "InternalServerException",
        "ResourceNotFoundException",
        "ValidationException",
    },
    ("servicecatalog-appregistry", "GetAttributeGroup"): {
        "ConflictException",
        "InternalServerException",
        "ResourceNotFoundException",
        "ValidationException",
    },
    # Bedrock's invocation logging configuration, TASK-P13-003: the service failing, loud.
    ("bedrock", "GetModelInvocationLoggingConfiguration"): {"InternalServerException"},
    # Logs Insights. LimitExceeded, too many queries already running, is Throttled and a group the
    # configuration names that does not exist is Misconfigured, both in the adapter itself; the
    # rest is a query this adapter builds wrong or the service failing, loud, ISS-215.
    ("logs", "StartQuery"): {
        "InvalidParameterException",
        "LimitExceededException",
        "MalformedQueryException",
        "ResourceNotFoundException",
        "ServiceUnavailableException",
    },
    ("logs", "GetQueryResults"): {
        "InvalidParameterException",
        "ResourceNotFoundException",
        "ServiceUnavailableException",
    },
    # An AI provider's key. A secret the account names that does not exist is Misconfigured in
    # the reader itself; the rest is the key's encryption or the service failing, loud.
    ("secretsmanager", "GetSecretValue"): {
        "DecryptionFailure",
        "InternalServiceError",
        "InvalidParameterException",
        "InvalidRequestException",
        "ResourceNotFoundException",
    },
    # CloudTrail's event history. Each is a request this adapter builds wrong or a trail the
    # account cannot look up in, and fails the account and Region loud, never as nobody.
    ("cloudtrail", "LookupEvents"): {
        "InvalidEventCategoryException",
        "InvalidLookupAttributesException",
        "InvalidMaxResultsException",
        "InvalidNextTokenException",
        "InvalidTimeRangeException",
        "OperationNotPermittedException",
        "UnsupportedOperationException",
    },
}


@pytest.mark.parametrize(("service", "operation"), sorted(FALLS_THROUGH))
def test_the_errors_that_fall_through_are_the_ones_we_have_accepted(
    service: str, operation: str, loader: botocore.session.Session
) -> None:
    """Which declared errors `translate` does not name, pinned so a new one is visible.

    Every code here arrives as SchemaDrift, which is loud and is never a zero, so nothing is
    hidden by it. It is still the wrong word for most of them, and ISS-215 records that.

    The assertion is equality rather than a subset in either direction. A code leaving this list
    means somebody mapped it and should say so; a code joining it means the SDK added one and
    nobody looked, which is the case that would otherwise pass unnoticed for a year.
    """
    from finops_providers.aws.client import (
        ACCESS_DENIED_CODES,
        MISCONFIGURED_CODES,
        NOT_OPTED_IN_CODES,
        THROTTLE_CODES,
    )

    mapped = (
        set(ACCESS_DENIED_CODES)
        | set(THROTTLE_CODES)
        | set(NOT_OPTED_IN_CODES)
        | set(MISCONFIGURED_CODES)
    )
    model = loader.get_service_model(service).operation_model(operation)
    declared = {
        shape.metadata.get("error", {}).get("code", shape.name) for shape in model.error_shapes
    }
    assert declared - mapped == FALLS_THROUGH[(service, operation)], (
        f"{service}.{operation}: the set of errors falling through to SchemaDrift has changed. "
        f"Either one was mapped, which is good and should be recorded here, or the SDK declares "
        f"a new one, which is the case this test exists to surface. ISS-215."
    )


def test_the_request_status_vocabulary_is_the_one_the_service_model_declares(
    loader: botocore.session.Session,
) -> None:
    """The check that found a real defect on the day it was written.

    The P5 spec's section 5.3 lists five request statuses. `RequestStatus` in the service
    model has seven: `NOT_APPROVED` and `INVALID_REQUEST` as well. The spec was written from
    the documentation and those two were missed, and the narrow vocabulary had already
    reached a check constraint in migration 0020 before this test was added.

    What it would have cost: the adapter reads such a request successfully, the database
    refuses the row, and the failure presents as an IntegrityError from the quotas collector.
    That reads as a fault in the write path, so the first person to see it looks there rather
    than at a constraint written from a document. And it only happens on a real account,
    which is ISS-122, so a customer finds it rather than us.

    An eighth value AWS adds now fails here, which is the point: this is an enum somebody
    else owns, mirrored into a StrEnum, a check constraint and a screen's labels.
    """
    from finops_core.domain.quota import RequestStatus

    declared = set(loader.get_service_model("service-quotas").shape_for("RequestStatus").enum)
    assert {status.value for status in RequestStatus} == declared, (
        f"RequestStatus and the service model disagree. Declared but not in the enum: "
        f"{sorted(declared - {s.value for s in RequestStatus})}. In the enum but not "
        f"declared: {sorted({s.value for s in RequestStatus} - declared)}. Widening this "
        f"needs a migration: the vocabulary is a check constraint in 0020 as well."
    )


def test_the_relay_follows_the_token_savings_plans_uses(loader: botocore.session.Session) -> None:
    """TASK-P9-012. botocore has no paginator for the rates, so `TOKENS` cannot hold them and the
    relay follows the token by hand. The name it follows must be the one the model declares on
    both sides, or the relay reads the first page forever."""
    from finops_relay.relay import _TOKENS

    model = loader.get_service_model("savingsplans").operation_model(
        "DescribeSavingsPlansOfferingRates"
    )
    shared = set(model.input_shape.members) & set(model.output_shape.members)
    assert shared & set(_TOKENS) == {"nextToken"}
