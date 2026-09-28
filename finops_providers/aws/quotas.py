"""Quotas, their limits, and usage from whichever of three sources has any.

**Nothing in this file has ever made a call.** ISS-122. It is written against the
botocore service models and the AWS documentation, and its tests answer from literals.
What has been checked offline is every field name it reads, in
`tests/providers/aws/test_response_shapes.py`, against the models boto3 builds its own
clients from. That removes the part of the risk that is about names and leaves the part
that is about meaning.

Four things carry this file.

**Service Quotas names its own usage metric, so the metric table is not ours.** Each
`ServiceQuota` may carry a `UsageMetric` with the namespace, the metric name, the
dimensions and a recommended statistic. The adapter reads that and asks CloudWatch for
exactly what AWS said to ask for. The obvious alternative, a hand written map from quota
code to metric name, would be a few hundred lines of guesses that go stale silently
every time AWS publishes a metric for a quota that had none. A quota with no
`UsageMetric` is unmeasurable from CloudWatch by AWS's own account, which is a much
stronger statement than our table not having an entry for it.

**Every quota produces a row, measured or not.** A quota nothing can measure is written
with `usage_source` of NONE, a null usage and a sentence saying which reason applies. It
is never omitted and never zero. Most quotas in a real estate are in this state, and
that ratio is the honest summary of how much of this problem AWS lets anybody solve, so
hiding it would be hiding the finding.

**Trusted Advisor is matched by name, and that is the weakest mapping here.** The service
limits check returns `flaggedResources` whose `metadata` is a positional list of strings:
region, service name, limit name, limit, usage, status. There is no quota code in it. So
a Trusted Advisor figure is joined to a Service Quotas quota by comparing service name
and quota name after normalisation, and names are somebody else's display strings. This
is the part a real account will correct first, and it is stated here rather than buried,
in the same spirit as `_reservation_money` in `commitment.py`.

**Nothing here submits a quota increase.** Constraint 6 and P5 spec section 6.
`RequestServiceQuotaIncrease` does not appear in this file and the org reader role does
not grant it. `requests()` reads the history AWS already keeps, which is the half of
FEAT-034 that is actually missing: nobody loses a quota increase for want of the button,
they lose it because nobody checked whether it was ever approved.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.domain.account import AccountKey
from finops_core.domain.quota import (
    QuotaIncreaseRequest,
    QuotaUsage,
    RequestStatus,
    UsageSource,
)
from finops_core.errors import CollectionError, NotOptedIn
from finops_providers.aws.client import translate

COLLECTOR = "quotas"

#: The largest number of queries `GetMetricData` accepts in one request. A batch over this
#: is rejected whole, so the queries are chunked rather than sent hopefully.
METRIC_QUERY_BATCH = 500  # allow-hardcoded: the documented GetMetricData request limit

#: How far back a usage figure is read. A day, because `AWS/Usage` metrics are gauges and a
#: quota is about the peak rather than the average: the question is whether anything hit the
#: wall, not what the typical hour looked like. Shorter than a day and a nightly batch never
#: appears; longer and a limit raised last week still reads as nearly full.
USAGE_LOOKBACK_HOURS = 24  # allow-hardcoded: the window a peak is taken over, see above

#: One hour per data point over that window. Finer resolution costs more data points for a
#: figure that is then reduced to its maximum anyway.
USAGE_PERIOD_SECONDS = 3600  # allow-hardcoded: the resolution of the window above

#: Used where a quota declares a metric but recommends no statistic. Maximum rather than
#: Average, for the reason the window is a day: the peak is the finding.
DEFAULT_STATISTIC = "Maximum"  # allow-hardcoded: a quota is about its peak, not its mean

#: `GetMetricData` query ids have to start with a lower case letter, so a quota code cannot
#: be one. The index into the batch is, and the batch is the map back.
_QUERY_PREFIX = "q"

#: A quota applied per resource rather than per account changes the grain: the same code
#: appears once per resource and each has its own limit. Reading those as account quotas
#: would write one row per resource under one identity and keep whichever arrived last.
RESOURCE_LEVEL = "RESOURCE"

TRUSTED_ADVISOR_LANGUAGE = "en"  # allow-hardcoded: the only language whose strings are read

#: The Trusted Advisor check whose name has been stable for years. Matched on the name
#: because the check id is an opaque string that differs between partitions.
SERVICE_LIMITS_CHECK = "Service Limits"

#: Positions in a flagged resource's `metadata`, which is a bare list of strings with no
#: keys. Named here so the indexing reads as a decision rather than as magic.
_TA_REGION = 0
_TA_SERVICE = 1
_TA_LIMIT_NAME = 2
_TA_USED = 4

#: The reasons a quota carries no usage. Each is a sentence, because the screen shows it per
#: quota and a reason reading "not measured" would teach a reader the explanations here are
#: empty so they stop reading the ones that are not.
NO_METRIC_DECLARED = "Service Quotas declares no usage metric for this quota"
METRIC_PUBLISHED_NOTHING = "The usage metric AWS publishes for this quota returned no data"
ADVISOR_UNAVAILABLE = (
    "Only Trusted Advisor reports usage for this quota, and it could not be read: {detail}"
)
USAGE_ABOVE_LIMIT = (
    "The measured usage was above the limit, which is a misread rather than a full quota"
)


def _system_clock() -> datetime:
    return datetime.now(UTC)


def _decimal(raw: Any) -> Decimal | None:
    """A number from a provider, or None. Never a zero standing in for a failure."""
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return None


def normalise(name: str) -> str:
    """A display name reduced to something two providers might agree on.

    Only used for the Trusted Advisor join, which is the mapping this module is least sure
    of. Case, punctuation and runs of whitespace go; the words stay in order.
    """
    return " ".join("".join(c if c.isalnum() else " " for c in name).lower().split())


@dataclass(frozen=True)
class _Declared:
    """A quota as Service Quotas described it, before anything measured its usage."""

    service_code: str
    service_name: str
    quota_code: str
    quota_name: str
    limit: Decimal | None
    is_adjustable: bool
    is_global: bool
    namespace: str
    metric_name: str
    dimensions: tuple[tuple[str, str], ...]
    statistic: str

    @property
    def has_metric(self) -> bool:
        """Whether AWS itself says a CloudWatch metric reports this quota's usage."""
        return bool(self.namespace and self.metric_name)

    @property
    def key(self) -> tuple[str, str]:
        return (self.service_code, self.quota_code)

    @property
    def advisor_key(self) -> tuple[str, str]:
        return (normalise(self.service_name), normalise(self.quota_name))


Counter = Callable[[Any], Decimal | None]


def _count_vpcs(client: Any) -> Decimal | None:
    pages = client.get_paginator("describe_vpcs").paginate()
    return Decimal(sum(len(page.get("Vpcs") or ()) for page in pages))


def _count_addresses(client: Any) -> Decimal | None:
    # DescribeAddresses does not paginate, which is why it is not asked to.
    return Decimal(len(client.describe_addresses().get("Addresses") or ()))


#: A usage figure counted by asking a service directly, for the few quotas where the count
#: is one call away and nothing else publishes it. Keyed by (service code, quota code), and
#: the value is the client it needs and the count it makes.
#:
#: Deliberately small. Every entry is a call per account per region per collection on a
#: twelve hourly cadence, and a registry grown to cover every countable quota would be a
#: reimplementation of Service Quotas with worse coverage. The two here exist so the third
#: source is a real path with a real test rather than a paragraph in a specification.
COUNTERS: Mapping[tuple[str, str], tuple[str, Counter]] = {
    ("vpc", "L-F678F1CE"): ("ec2", _count_vpcs),
    ("ec2", "L-0263D0A3"): ("ec2", _count_addresses),
}


class AwsQuotas:
    """Every quota in one account and region, with usage where anything publishes it.

    Read only, per constraint 6. The client factory takes a service and a region so one
    instance can reach Service Quotas, CloudWatch, Support and the counters above without
    this class knowing how a session is built.
    """

    def __init__(
        self,
        *,
        client_factory: Callable[[str, str], Any],
        clock: Callable[[], datetime] = _system_clock,
    ) -> None:
        self._client_for = client_factory
        self._clock = clock

    # --- the port ------------------------------------------------------------

    def list_quotas(self, account: AccountKey, region: str) -> Iterable[QuotaUsage]:
        """Every quota for the account and region, with usage where published.

        Raises:
            AccessDenied: The session may not read quotas in this account.
            NotOptedIn: The quota service has never been enabled here.
            Throttled: The provider rejected the call rate.
            Unreachable: The quota endpoint did not answer.
            SchemaDrift: A quota arrived in a shape this adapter cannot read.
        """
        at = self._clock()
        scope = f"{account.account_id}:{region}"
        declared = self._declared(region, scope)

        measured: dict[tuple[str, str], tuple[Decimal, UsageSource]] = {}
        reasons: dict[tuple[str, str], str] = {}

        self._add_metric_usage(declared, region, scope, measured)
        self._add_counted_usage(declared, region, scope, measured)
        self._add_advisor_usage(declared, region, measured, reasons)

        return tuple(self._row(one, account, region, at, measured, reasons) for one in declared)

    def requests(self, account: AccountKey, region: str) -> Iterable[QuotaIncreaseRequest]:
        """Every increase request AWS has a record of, whatever became of it.

        Read only. Meter never creates one, per spec section 6, and `submitted_by_meter` in
        the schema is a column that can only say so.

        Raises:
            AccessDenied: The session may not read the request history.
            NotOptedIn: Service Quotas has never been enabled here.
            Throttled: The provider rejected the call rate.
            Unreachable: The endpoint did not answer.
            SchemaDrift: A request arrived in a shape this adapter cannot read.
        """
        at = self._clock()
        scope = f"{account.account_id}:{region}"
        client = self._client_for("service-quotas", region)
        found: list[QuotaIncreaseRequest] = []
        try:
            pages = client.get_paginator("list_requested_service_quota_change_history").paginate()
            for page in pages:
                for raw in page.get("RequestedQuotas") or ():
                    built = self._request(raw, account, region, at)
                    if built is not None:
                        found.append(built)
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=scope, collector=COLLECTOR) from failure
        return tuple(found)

    # --- Service Quotas, which supplies every limit --------------------------

    def _declared(self, region: str, scope: str) -> tuple[_Declared, ...]:
        client = self._client_for("service-quotas", region)
        found: list[_Declared] = []
        try:
            for service_code, service_name in self._services(client):
                pages = client.get_paginator("list_service_quotas").paginate(
                    ServiceCode=service_code
                )
                for page in pages:
                    for raw in page.get("Quotas") or ():
                        one = self._declare(raw, service_code, service_name)
                        if one is not None:
                            found.append(one)
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=scope, collector=COLLECTOR) from failure
        return tuple(found)

    @staticmethod
    def _services(client: Any) -> tuple[tuple[str, str], ...]:
        pages = client.get_paginator("list_services").paginate()
        return tuple(
            (str(raw.get("ServiceCode") or ""), str(raw.get("ServiceName") or ""))
            for page in pages
            for raw in page.get("Services") or ()
            if raw.get("ServiceCode")
        )

    @staticmethod
    def _declare(raw: Any, service_code: str, service_name: str) -> _Declared | None:
        quota_code = str(raw.get("QuotaCode") or "").strip()
        if not quota_code:
            # A quota with no code has no identity to upsert on and would arrive as a new
            # row every run.
            return None
        if raw.get("QuotaAppliedAtLevel") == RESOURCE_LEVEL:
            return None

        metric = raw.get("UsageMetric") or {}
        dimensions = metric.get("MetricDimensions") or {}
        return _Declared(
            service_code=service_code,
            service_name=str(raw.get("ServiceName") or service_name),
            quota_code=quota_code,
            quota_name=str(raw.get("QuotaName") or quota_code),
            # `ErrorReason` is Service Quotas saying it could not determine the value. The
            # limit is then unknown rather than zero, and the row still exists.
            limit=None if raw.get("ErrorReason") else _decimal(raw.get("Value")),
            is_adjustable=bool(raw.get("Adjustable")),
            is_global=bool(raw.get("GlobalQuota")),
            namespace=str(metric.get("MetricNamespace") or ""),
            metric_name=str(metric.get("MetricName") or ""),
            dimensions=tuple(sorted((str(k), str(v)) for k, v in dimensions.items())),
            statistic=str(metric.get("MetricStatisticRecommendation") or DEFAULT_STATISTIC),
        )

    # --- CloudWatch, the largest source --------------------------------------

    def _add_metric_usage(
        self,
        declared: Sequence[_Declared],
        region: str,
        scope: str,
        into: dict[tuple[str, str], tuple[Decimal, UsageSource]],
    ) -> None:
        wanted = [one for one in declared if one.has_metric]
        if not wanted:
            return
        client = self._client_for("cloudwatch", region)
        end = self._clock()
        start = end - timedelta(hours=USAGE_LOOKBACK_HOURS)
        try:
            for offset in range(0, len(wanted), METRIC_QUERY_BATCH):
                batch = wanted[offset : offset + METRIC_QUERY_BATCH]
                for index, value in self._metric_data(client, batch, start, end).items():
                    into[batch[index].key] = (value, UsageSource.AWS_USAGE_METRIC)
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=scope, collector=COLLECTOR) from failure

    @staticmethod
    def _metric_data(
        client: Any, batch: Sequence[_Declared], start: datetime, end: datetime
    ) -> dict[int, Decimal]:
        """The peak of each query in the batch, keyed by its position in it.

        A query that came back with no values is absent from the result rather than zero. A
        metric that has never published anything and a metric reporting no consumption are
        indistinguishable here, and the honest reading of the pair is unknown.
        """
        queries = [
            {
                "Id": f"{_QUERY_PREFIX}{index}",
                "MetricStat": {
                    "Metric": {
                        "Namespace": one.namespace,
                        "MetricName": one.metric_name,
                        "Dimensions": [
                            {"Name": name, "Value": value} for name, value in one.dimensions
                        ],
                    },
                    "Period": USAGE_PERIOD_SECONDS,
                    "Stat": one.statistic,
                },
                "ReturnData": True,
            }
            for index, one in enumerate(batch)
        ]
        peaks: dict[int, Decimal] = {}
        pages = client.get_paginator("get_metric_data").paginate(
            MetricDataQueries=queries, StartTime=start, EndTime=end
        )
        for page in pages:
            for result in page.get("MetricDataResults") or ():
                # `is not None` and not a truth test: a genuine zero is a measured figure,
                # and dropping it would move the quota into the unmeasurable list.
                parsed = (_decimal(v) for v in result.get("Values") or ())
                present = [v for v in parsed if v is not None]
                if not present:
                    continue
                index = _index_of(str(result.get("Id") or ""))
                if index is None or index >= len(batch):
                    continue
                peak = max(present)
                # A paginated series arrives across pages, so a later page can carry more of
                # the same query's values. The peak of the peaks is the peak.
                peaks[index] = max(peaks.get(index, peak), peak)
        return peaks

    # --- the service APIs, for the few quotas with a one call count ----------

    def _add_counted_usage(
        self,
        declared: Sequence[_Declared],
        region: str,
        scope: str,
        into: dict[tuple[str, str], tuple[Decimal, UsageSource]],
    ) -> None:
        for one in declared:
            if one.key in into or one.key not in COUNTERS:
                continue
            service, count = COUNTERS[one.key]
            try:
                counted = count(self._client_for(service, region))
            except (ClientError, BotoCoreError) as failure:
                raise translate(failure, scope_key=scope, collector=COLLECTOR) from failure
            if counted is not None:
                into[one.key] = (counted, UsageSource.SERVICE_API)

    # --- Trusted Advisor, which needs a support tier -------------------------

    def _add_advisor_usage(
        self,
        declared: Sequence[_Declared],
        region: str,
        into: dict[tuple[str, str], tuple[Decimal, UsageSource]],
        reasons: dict[tuple[str, str], str],
    ) -> None:
        """Fill what is still unmeasured from the service limits check, if it can be read.

        A missing support tier is `NotOptedIn` and is absorbed here rather than raised. That
        is TASK-P5-003's third acceptance criterion and it is the right shape: an account on
        a Developer plan has fewer measurable quotas, which is a true statement about that
        account rather than a failed collection.
        """
        outstanding = [one for one in declared if one.key not in into]
        if not outstanding:
            return
        try:
            flagged = self._advisor_usage(region)
        except CollectionError as refusal:
            detail = f"{type(refusal).__name__}: {refusal.detail}"
            for one in outstanding:
                reasons[one.key] = ADVISOR_UNAVAILABLE.format(detail=detail)
            return

        for one in outstanding:
            found = flagged.get(one.advisor_key)
            if found is not None:
                into[one.key] = (found, UsageSource.TRUSTED_ADVISOR)
            else:
                reasons[one.key] = (
                    METRIC_PUBLISHED_NOTHING if one.has_metric else NO_METRIC_DECLARED
                )

    def _advisor_usage(self, region: str) -> dict[tuple[str, str], Decimal]:
        client = self._client_for("support", region)
        try:
            checks = client.describe_trusted_advisor_checks(language=TRUSTED_ADVISOR_LANGUAGE)
            check_id = next(
                (
                    str(check.get("id"))
                    for check in checks.get("checks") or ()
                    if str(check.get("name") or "") == SERVICE_LIMITS_CHECK
                ),
                None,
            )
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=region, collector=COLLECTOR) from failure
        if check_id is None:
            # The check being absent is a different fact from it being forbidden, and both
            # reach a reader through the same sentence: nothing measured these quotas.
            raise NotOptedIn(
                scope_key=region,
                collector=COLLECTOR,
                detail=f"Trusted Advisor has no check named {SERVICE_LIMITS_CHECK}",
            )
        try:
            result = client.describe_trusted_advisor_check_result(
                checkId=check_id, language=TRUSTED_ADVISOR_LANGUAGE
            )
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=region, collector=COLLECTOR) from failure

        usage: dict[tuple[str, str], Decimal] = {}
        for resource in (result.get("result") or {}).get("flaggedResources") or ():
            metadata = resource.get("metadata") or ()
            if len(metadata) <= _TA_USED:
                continue
            if str(metadata[_TA_REGION] or "") not in (region, ""):
                continue
            used = _decimal(metadata[_TA_USED])
            if used is None:
                continue
            usage[
                (
                    normalise(str(metadata[_TA_SERVICE] or "")),
                    normalise(str(metadata[_TA_LIMIT_NAME] or "")),
                )
            ] = used
        return usage

    # --- assembly ------------------------------------------------------------

    def _row(
        self,
        one: _Declared,
        account: AccountKey,
        region: str,
        at: datetime,
        measured: Mapping[tuple[str, str], tuple[Decimal, UsageSource]],
        reasons: Mapping[tuple[str, str], str],
    ) -> QuotaUsage:
        found = measured.get(one.key)
        used, source = found if found is not None else (None, UsageSource.NONE)
        reason = None if used is not None else reasons.get(one.key, NO_METRIC_DECLARED)
        if used is not None and one.limit is not None and used > one.limit:
            # `QuotaUsage` refuses to hold a usage above its ceiling, and rightly: it is a
            # misread rather than a full quota. Clamping would hide the misread and dropping
            # the row would hide the quota, so the figure goes, the limit stays, and the
            # reason says what happened instead of the quota looking simply unmeasured.
            used, source, reason = None, UsageSource.NONE, USAGE_ABOVE_LIMIT
        return QuotaUsage(
            account_key=account,
            region_id=None if one.is_global else region,
            service_code=one.service_code,
            quota_code=one.quota_code,
            quota_name=one.quota_name,
            quota_limit=one.limit,
            used=used,
            usage_source=source,
            is_adjustable=one.is_adjustable,
            unmeasurable_reason=reason,
            as_of=at,
            collected_at=at,
        )

    @staticmethod
    def _request(
        raw: Any, account: AccountKey, region: str, at: datetime
    ) -> QuotaIncreaseRequest | None:
        request_id = str(raw.get("Id") or "").strip()
        desired = _decimal(raw.get("DesiredValue"))
        created, updated = raw.get("Created"), raw.get("LastUpdated")
        if not request_id or desired is None or desired <= 0:
            return None
        if not isinstance(created, datetime) or not isinstance(updated, datetime):
            # Without both timestamps there is nothing to show in a tracking list, which is
            # the whole of what this read is for.
            return None
        try:
            status = RequestStatus(str(raw.get("Status") or ""))
        except ValueError:
            # A status outside AWS's own documented set would be refused by the schema, so
            # the row is dropped here where the reason is legible rather than at the write.
            return None
        try:
            return QuotaIncreaseRequest(
                account_key=account,
                request_id=request_id,
                region_id=None if raw.get("GlobalQuota") else region,
                service_code=str(raw.get("ServiceCode") or ""),
                quota_code=str(raw.get("QuotaCode") or ""),
                quota_name=str(raw.get("QuotaName") or ""),
                desired_value=desired,
                status=status,
                requested_at=created,
                last_updated_at=updated,
                as_of=at,
                collected_at=at,
            )
        except ValueError:
            # The timestamps are passed through as they arrived and the row is dropped if
            # they contradict each other. Sorting them into order would be inventing an
            # ordering nobody observed, and one malformed request must not fail the account.
            return None


def _index_of(query_id: str) -> int | None:
    if not query_id.startswith(_QUERY_PREFIX):
        return None
    try:
        return int(query_id[len(_QUERY_PREFIX) :])
    except ValueError:
        return None
