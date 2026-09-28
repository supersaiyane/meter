"""The paths the quota contract cannot reach, which are the AWS specific ones.

`tests/contract/test_quota_source.py` holds the sentences the fake and this adapter share.
What is left is everything about how AWS in particular answers, and the cases here are the
ones where a plausible implementation is quietly wrong:

- A support plan without Trusted Advisor. The adapter has to absorb it and report fewer
  measurable quotas rather than failing the account, and the reason has to name what
  happened.
- A metric that published a genuine zero. Zero is a measured figure, and a truth test
  instead of a None test moves the quota into the unmeasurable list. That was a real bug in
  the first draft of `_metric_data`.
- A usage above its own limit. The entity refuses to hold one, so the adapter has to choose
  between clamping, dropping the row and dropping the figure.
- More quotas than `GetMetricData` accepts in one request.

Nothing here has made a real call, ISS-122. The response keys are the ones
`test_response_shapes.py` checks against the botocore service models.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from botocore.exceptions import ClientError

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.quota import RequestStatus, UsageSource
from finops_core.errors import AccessDenied, Throttled
from finops_providers.aws.quotas import METRIC_QUERY_BATCH, AwsQuotas, normalise

NOW = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)
ACCOUNT = AccountKey(provider=Provider.AWS, account_id="111122223333")
REGION = "eu-west-1"

MEASURED = "L-1216C47A"
NO_METRIC = "L-0EA8095F"
BY_NAME = "L-53DA6B97"


def a_quota(code: str, **overrides: Any) -> dict[str, Any]:
    """One quota as Service Quotas describes it, with any field overridden."""
    raw: dict[str, Any] = {
        "ServiceCode": "ec2",
        "ServiceName": "Amazon EC2",
        "QuotaCode": code,
        "QuotaName": f"Quota {code}",
        "Value": 100.0,
        "Adjustable": True,
        "GlobalQuota": False,
    }
    raw.update(overrides)
    return raw


def with_metric(code: str, **overrides: Any) -> dict[str, Any]:
    return a_quota(
        code,
        UsageMetric={
            "MetricNamespace": "AWS/Usage",
            "MetricName": "ResourceCount",
            "MetricDimensions": {"Service": "EC2", "Resource": "vCPU"},
            "MetricStatisticRecommendation": "Maximum",
        },
        **overrides,
    )


class _Pages:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages

    def paginate(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return self._pages


class StubQuotas:
    def __init__(
        self,
        quotas: list[dict[str, Any]],
        *,
        requests: list[dict[str, Any]] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._quotas = quotas
        self._requests = requests or []
        self._raises = raises

    def get_paginator(self, name: str) -> Any:
        if self._raises is not None:
            raise self._raises
        if name == "list_services":
            return _Pages([{"Services": [{"ServiceCode": "ec2", "ServiceName": "Amazon EC2"}]}])
        if name == "list_service_quotas":
            return _Pages([{"Quotas": self._quotas}])
        if name == "list_requested_service_quota_change_history":
            return _Pages([{"RequestedQuotas": self._requests}])
        raise AssertionError(name)


class StubCloudWatch:
    """Answers with the values given, keyed by each quota's position across all batches.

    The offset matters. Query ids restart at q0 in every batch, because the adapter maps an
    id back to a position within the batch it sent. A stub that keyed on that position alone
    would answer for the first three quotas of the second batch as well, which is how the
    chunking test first passed with 503 measured quotas out of 500 asked about.
    """

    def __init__(self, values: dict[int, list[float]] | None = None) -> None:
        self.values = values or {}
        self.batches: list[int] = []

    def get_paginator(self, name: str) -> Any:
        assert name == "get_metric_data"
        outer = self

        class _P:
            def paginate(self, **kwargs: Any) -> list[dict[str, Any]]:
                queries = kwargs["MetricDataQueries"]
                offset = sum(outer.batches)
                outer.batches.append(len(queries))
                results = [
                    {"Id": query["Id"], "Values": outer.values[offset + position]}
                    for position, query in enumerate(queries)
                    if offset + position in outer.values
                ]
                return [{"MetricDataResults": results}]

        return _P()


class StubSupport:
    def __init__(self, *, subscribed: bool = True, flagged: list[list[str]] | None = None) -> None:
        self._subscribed = subscribed
        self._flagged = flagged if flagged is not None else []

    def describe_trusted_advisor_checks(self, **_kwargs: Any) -> Any:
        if not self._subscribed:
            raise ClientError(
                {"Error": {"Code": "SubscriptionRequiredException", "Message": "no plan"}},
                "DescribeTrustedAdvisorChecks",
            )
        return {"checks": [{"id": "check-1", "name": "Service Limits"}]}

    def describe_trusted_advisor_check_result(self, **_kwargs: Any) -> Any:
        return {"result": {"flaggedResources": [{"metadata": row} for row in self._flagged]}}


def source(
    quotas: list[dict[str, Any]],
    *,
    cloudwatch: StubCloudWatch | None = None,
    support: StubSupport | None = None,
    requests: list[dict[str, Any]] | None = None,
    raises: Exception | None = None,
) -> AwsQuotas:
    clients: dict[str, Any] = {
        "service-quotas": StubQuotas(quotas, requests=requests, raises=raises),
        "cloudwatch": cloudwatch or StubCloudWatch(),
        "support": support or StubSupport(),
    }
    return AwsQuotas(client_factory=lambda service, _region: clients[service], clock=lambda: NOW)


def only(quotas: Any, code: str) -> Any:
    found = [one for one in quotas if one.quota_code == code]
    assert len(found) == 1, f"expected exactly one {code}, got {len(found)}"
    return found[0]


# --- Trusted Advisor, and the support plan that does not include it -----------


def test_a_support_plan_without_trusted_advisor_reduces_coverage_rather_than_failing() -> None:
    """TASK-P5-003's third acceptance criterion.

    An account on a Developer plan has fewer measurable quotas. That is a true statement
    about the account rather than a failed collection, so nothing raises and every quota
    still produces a row.
    """
    quotas = tuple(
        source([a_quota(NO_METRIC)], support=StubSupport(subscribed=False)).list_quotas(
            ACCOUNT, REGION
        )
    )
    one = only(quotas, NO_METRIC)
    assert one.used is None
    assert one.usage_source is UsageSource.NONE
    assert "Trusted Advisor" in (one.unmeasurable_reason or "")
    assert "NotOptedIn" in (one.unmeasurable_reason or ""), (
        "the reason has to name the cause, or an operator cannot tell a missing support plan "
        "from a quota AWS simply does not publish usage for"
    )


def test_trusted_advisor_fills_a_quota_with_no_metric_of_its_own() -> None:
    """The third source, matched on names because the check carries no quota code."""
    quotas = tuple(
        source(
            [a_quota(BY_NAME, QuotaName="Application Load Balancers")],
            support=StubSupport(
                flagged=[[REGION, "Amazon EC2", "Application Load Balancers", "100", "43", "Y"]]
            ),
        ).list_quotas(ACCOUNT, REGION)
    )
    one = only(quotas, BY_NAME)
    assert one.used == Decimal("43")
    assert one.usage_source is UsageSource.TRUSTED_ADVISOR
    assert one.unmeasurable_reason is None


def test_a_flagged_resource_for_another_region_is_not_borrowed() -> None:
    """The check is not regional but its rows are, and a quota is per region."""
    quotas = tuple(
        source(
            [a_quota(BY_NAME, QuotaName="Application Load Balancers")],
            support=StubSupport(
                flagged=[
                    ["us-east-1", "Amazon EC2", "Application Load Balancers", "100", "43", "Y"]
                ]
            ),
        ).list_quotas(ACCOUNT, REGION)
    )
    assert only(quotas, BY_NAME).used is None


def test_a_short_metadata_row_is_skipped_rather_than_indexed_off_the_end() -> None:
    """The positional list is somebody else's format and can be any length."""
    quotas = tuple(
        source(
            [a_quota(BY_NAME)], support=StubSupport(flagged=[[REGION, "Amazon EC2"]])
        ).list_quotas(ACCOUNT, REGION)
    )
    assert only(quotas, BY_NAME).used is None


def test_normalise_ignores_case_and_punctuation_and_nothing_else() -> None:
    assert normalise("Application Load Balancers") == normalise("application load balancers")
    assert normalise("VPCs per Region") == normalise("VPCs  per-Region")
    # Word order is meaning, so it survives. Two different limits must not collide.
    assert normalise("rules per policy") != normalise("policies per rule")


# --- CloudWatch ---------------------------------------------------------------


def test_a_metric_that_published_zero_is_measured_at_zero() -> None:
    """Zero is a figure. A truth test instead of a None test loses it.

    That was a real bug in the first draft: `[v for v in values if v]` dropped `Decimal(0)`,
    which moved a quota with nothing running into the unmeasurable list and replaced a true
    zero with an admission of ignorance.
    """
    quotas = tuple(
        source([with_metric(MEASURED)], cloudwatch=StubCloudWatch({0: [0.0, 0.0]})).list_quotas(
            ACCOUNT, REGION
        )
    )
    one = only(quotas, MEASURED)
    assert one.used == Decimal("0")
    assert one.usage_source is UsageSource.AWS_USAGE_METRIC
    assert one.headroom == Decimal("1")


def test_a_metric_with_no_data_points_leaves_the_quota_unmeasured() -> None:
    """A metric that never published and one reporting nothing are indistinguishable."""
    quotas = tuple(
        source([with_metric(MEASURED)], cloudwatch=StubCloudWatch({})).list_quotas(ACCOUNT, REGION)
    )
    one = only(quotas, MEASURED)
    assert one.used is None
    assert one.unmeasurable_reason is not None


def test_the_peak_is_taken_rather_than_the_latest_or_the_mean() -> None:
    """A quota is about whether anything hit the wall, not about the typical hour."""
    quotas = tuple(
        source(
            [with_metric(MEASURED)], cloudwatch=StubCloudWatch({0: [10.0, 96.0, 12.0]})
        ).list_quotas(ACCOUNT, REGION)
    )
    assert only(quotas, MEASURED).used == Decimal("96")


def test_a_quota_with_no_usage_metric_is_never_asked_about() -> None:
    """The reason there is no hand written metric table here: AWS says which have one."""
    cloudwatch = StubCloudWatch({})
    tuple(source([a_quota(NO_METRIC)], cloudwatch=cloudwatch).list_quotas(ACCOUNT, REGION))
    assert cloudwatch.batches == [], "CloudWatch was asked about a quota it cannot answer for"


def test_more_quotas_than_one_request_holds_are_chunked() -> None:
    """A batch over the limit is rejected whole, so every quota would lose its figure."""
    many = [with_metric(f"L-{index:06d}") for index in range(METRIC_QUERY_BATCH + 3)]
    cloudwatch = StubCloudWatch({index: [7.0] for index in range(METRIC_QUERY_BATCH)})
    quotas = tuple(source(many, cloudwatch=cloudwatch).list_quotas(ACCOUNT, REGION))
    assert cloudwatch.batches == [METRIC_QUERY_BATCH, 3]
    assert len(quotas) == METRIC_QUERY_BATCH + 3
    assert sum(1 for one in quotas if one.is_measurable) == METRIC_QUERY_BATCH


# --- the limit, and the figures that contradict it ----------------------------


def test_a_quota_whose_value_service_quotas_could_not_determine_has_no_limit() -> None:
    """`ErrorReason` is the service saying so, and the row still exists."""
    quotas = tuple(
        source(
            [a_quota(NO_METRIC, ErrorReason={"ErrorCode": "DEPENDENCY_ACCESS_DENIED_ERROR"})]
        ).list_quotas(ACCOUNT, REGION)
    )
    one = only(quotas, NO_METRIC)
    assert one.quota_limit is None
    assert one.headroom is None


def test_a_usage_above_its_limit_loses_the_figure_and_keeps_the_quota() -> None:
    """Three options, and this is the least wrong of them.

    Clamping hides a misread behind a plausible number. Dropping the row hides the quota.
    Dropping the figure keeps the limit visible and says what happened.
    """
    quotas = tuple(
        source(
            [with_metric(MEASURED, Value=100.0)], cloudwatch=StubCloudWatch({0: [140.0]})
        ).list_quotas(ACCOUNT, REGION)
    )
    one = only(quotas, MEASURED)
    assert one.quota_limit == Decimal("100")
    assert one.used is None
    assert "above the limit" in (one.unmeasurable_reason or "")


# --- what is skipped, and why -------------------------------------------------


def test_a_resource_level_quota_is_skipped_because_it_is_a_different_grain() -> None:
    """The same code arrives once per resource, each with its own limit.

    Writing those as account quotas puts several rows under one identity and keeps whichever
    arrived last, which is a limit belonging to a resource nobody named.
    """
    quotas = tuple(
        source([a_quota(MEASURED), a_quota(NO_METRIC, QuotaAppliedAtLevel="RESOURCE")]).list_quotas(
            ACCOUNT, REGION
        )
    )
    assert {one.quota_code for one in quotas} == {MEASURED}


def test_a_quota_with_no_code_is_skipped_because_it_has_no_identity() -> None:
    quotas = tuple(source([a_quota(MEASURED), a_quota("  ")]).list_quotas(ACCOUNT, REGION))
    assert {one.quota_code for one in quotas} == {MEASURED}


def test_a_global_quota_carries_no_region() -> None:
    quotas = tuple(source([a_quota(NO_METRIC, GlobalQuota=True)]).list_quotas(ACCOUNT, REGION))
    assert only(quotas, NO_METRIC).region_id is None


def test_adjustability_comes_from_the_provider_rather_than_a_default() -> None:
    """FEAT-034 has to know before it offers a draft against a hard limit."""
    quotas = tuple(source([a_quota(NO_METRIC, Adjustable=False)]).list_quotas(ACCOUNT, REGION))
    assert only(quotas, NO_METRIC).is_adjustable is False


# --- failures become typed causes --------------------------------------------


def test_a_refused_read_raises_the_typed_cause() -> None:
    refusal = ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "ListServices")
    with pytest.raises(AccessDenied):
        tuple(source([], raises=refusal).list_quotas(ACCOUNT, REGION))


def test_a_throttled_read_raises_throttled_rather_than_returning_nothing() -> None:
    """An empty list would be an account with no quotas, which is a different claim."""
    refusal = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "ListServiceQuotas"
    )
    with pytest.raises(Throttled):
        tuple(source([], raises=refusal).list_quotas(ACCOUNT, REGION))


# --- the requests, read and never written ------------------------------------


def a_request(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "Id": "request-0001",
        "ServiceCode": "ec2",
        "QuotaCode": MEASURED,
        "QuotaName": "Running instances",
        "DesiredValue": 640.0,
        "Status": "PENDING",
        "Created": datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
        "LastUpdated": datetime(2026, 9, 22, 9, 0, tzinfo=UTC),
        "GlobalQuota": False,
    }
    raw.update(overrides)
    return raw


@pytest.mark.parametrize(
    "status",
    [
        "PENDING",
        "CASE_OPENED",
        "APPROVED",
        "DENIED",
        "CASE_CLOSED",
        "NOT_APPROVED",
        "INVALID_REQUEST",
    ],
)
def test_every_status_aws_documents_is_readable(status: str) -> None:
    """All seven, including the two the P5 spec missed.

    `NOT_APPROVED` and `INVALID_REQUEST` are in the botocore `RequestStatus` shape and were
    not in the specification. A narrower adapter would drop those requests silently.
    """
    requests = tuple(source([], requests=[a_request(Status=status)]).requests(ACCOUNT, REGION))
    assert len(requests) == 1
    assert requests[0].status is RequestStatus(status)


def test_a_status_outside_that_set_is_dropped_rather_than_guessed() -> None:
    """The schema would refuse it, and the reason is legible here rather than at the write."""
    requests = tuple(
        source(
            [], requests=[a_request(Status="SOMETHING_NEW"), a_request(Id="request-0002")]
        ).requests(ACCOUNT, REGION)
    )
    assert [one.request_id for one in requests] == ["request-0002"]


def test_a_request_whose_timestamps_contradict_each_other_is_dropped_not_reordered() -> None:
    """Sorting them into order would invent an ordering nobody observed.

    One malformed request must also not fail the account, so the others still arrive.
    """
    requests = tuple(
        source(
            [],
            requests=[
                a_request(
                    Created=datetime(2026, 9, 22, 9, 0, tzinfo=UTC),
                    LastUpdated=datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
                ),
                a_request(Id="request-0002"),
            ],
        ).requests(ACCOUNT, REGION)
    )
    assert [one.request_id for one in requests] == ["request-0002"]


def test_a_request_with_no_desired_value_is_dropped() -> None:
    """A draft against it would suggest lowering a limit, which nobody asked for."""
    requests = tuple(source([], requests=[a_request(DesiredValue=0.0)]).requests(ACCOUNT, REGION))
    assert requests == ()


def test_a_request_for_a_global_quota_carries_no_region() -> None:
    requests = tuple(source([], requests=[a_request(GlobalQuota=True)]).requests(ACCOUNT, REGION))
    assert requests[0].region_id is None


def test_a_refused_request_history_raises_the_typed_cause() -> None:
    refusal = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "no"}},
        "ListRequestedServiceQuotaChangeHistory",
    )
    with pytest.raises(AccessDenied):
        tuple(source([], raises=refusal).requests(ACCOUNT, REGION))
