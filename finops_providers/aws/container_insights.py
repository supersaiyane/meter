"""Container Insights, and the four signals it will not give us.

**This adapter has never run against a real AWS account.** ISS-122 and ISS-002.
Every metric name and dimension below is checkable against AWS's published list and
against nothing else, so a wrong one shows up as a cluster with no figures rather
than as an error anybody can read. The fake alongside it in `finops_fakes` is what
every test above this layer actually exercises.

Container Insights only, no agent in the cluster. That was decided on 2026-09-20 and
spec section 6 records why. The decision has a cost and this is the four line
summary of it, so the next reader does not have to go looking:

1. **Requests need enhanced observability.** Without it a cluster publishes usage
   and no request at all, so requested against used is unavailable for that cluster
   and the screen says so per cluster. Never a request of zero, which would make a
   workload look infinitely wasteful.
2. **OOMKilled events are not reliably published.** So `oom_status` is always
   `UNOBSERVED` here, never `NOT_KILLED`. That is the gap that changes a
   recommendation: the plus 25 percent memory rule cannot be applied, and the
   rationale has to say the check could not be made rather than quietly applying the
   smaller margin to a workload that may have been killed.
3. **Orphaned persistent volumes** are not here. EBS describe calls give them, so
   they belong to P3's `EBS_UNATTACHED` class rather than being invented in a
   container adapter.
4. **Unused LoadBalancer services** are not here either, for the same reason: ELB
   metrics give them, and they are P3's `LOAD_BALANCER_IDLE`.

Batched at 500 queries per call at a one hour period, which is what P3's waste
adapter does and for the same reason: GetMetricData is charged per metric requested,
a finer period multiplies the data points without changing a daily peak, and a
cluster with four hundred pods would otherwise be hundreds of calls.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from finops_core.config import Settings
from finops_core.domain.account import AccountKey
from finops_core.domain.containers import (
    ClusterSlice,
    LaunchType,
    OomStatus,
    ReservationVsUse,
    Workload,
)
from finops_core.errors import Misconfigured
from finops_providers.aws.client import botocore_config, translate

COLLECTOR = "container_usage"

#: Where Container Insights publishes. One namespace, and the metric names below
#: are the published ones.
NAMESPACE = "ContainerInsights"

#: The documented GetMetricData request limit.
METRIC_QUERY_BATCH = 500  # allow-hardcoded: the documented GetMetricData request limit

#: One hour. A finer period multiplies data points and cannot move a daily peak.
PERIOD_SECONDS = 3600  # allow-hardcoded: matches P3's waste adapter, for the same billing reason

#: How far back a reservation is read. Fourteen days is the floor below which no
#: recommendation exists at all, so reading less could never produce one.
LOOKBACK_DAYS = 30  # allow-hardcoded: comfortably above MINIMUM_HISTORY

#: The metric that exists for every cluster, used to discover clusters at all.
CLUSTER_PROBE = "node_cpu_utilization"

#: Published only where enhanced observability is enabled. Its presence is how this
#: adapter decides whether requests are readable, rather than asking a setting it
#: cannot see.
REQUEST_PROBE = "pod_cpu_request"

_PREFIX = "m"


def _index_of(identifier: str) -> int | None:
    if not identifier.startswith(_PREFIX):
        return None
    try:
        return int(identifier[len(_PREFIX) :])
    except ValueError:
        return None


def _decimal(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


class _Query:
    """One metric to ask for, and what it is about."""

    __slots__ = ("cluster", "dimensions", "metric", "namespace", "statistic", "workload")

    def __init__(
        self,
        *,
        metric: str,
        statistic: str,
        dimensions: Sequence[tuple[str, str]],
        cluster: str,
        namespace: str = "",
        workload: str = "",
    ) -> None:
        self.metric = metric
        self.statistic = statistic
        self.dimensions = tuple(dimensions)
        self.cluster = cluster
        self.namespace = namespace
        self.workload = workload


class ContainerInsightsSource:
    """`ContainerSource` over CloudWatch. Reads only, per constraint 6."""

    def __init__(
        self,
        settings: Settings,
        *,
        client_factory: Any = None,
        clock: Any = None,
        session: Any = None,
    ) -> None:
        self._settings = settings
        self._session = session
        self._factory = client_factory or self._default_client
        self._clock = clock or (lambda: datetime.now(tz=_utc()))

    def _default_client(self, service: str, region: str) -> Any:
        maker = self._session or boto3
        return maker.client(service, region_name=region, config=botocore_config(self._settings))

    # -- discovery ---------------------------------------------------------

    def _cluster_names(self, client: Any, metric: str) -> set[str]:
        """Clusters that publish `metric`, from the metric list rather than a describe.

        Discovery through CloudWatch rather than through EKS describe calls, because
        a cluster the product cannot read metrics for is a cluster it cannot report
        on whatever EKS says exists.
        """
        found: set[str] = set()
        pages = client.get_paginator("list_metrics").paginate(
            Namespace=NAMESPACE,
            MetricName=metric,
            Dimensions=[{"Name": "ClusterName"}],
        )
        for page in pages:
            for entry in page.get("Metrics") or ():
                for dimension in entry.get("Dimensions") or ():
                    if dimension.get("Name") == "ClusterName":
                        name = str(dimension.get("Value") or "")
                        if name:
                            found.add(name)
        return found

    def list_clusters(self, account: AccountKey, region: str) -> Iterable[ClusterSlice]:
        """Every cluster publishing container metrics in this account and region."""
        scope = f"{account}:{region}"
        client = self._factory("cloudwatch", region)
        now = self._clock()
        try:
            names = self._cluster_names(client, CLUSTER_PROBE)
            with_requests = self._cluster_names(client, REQUEST_PROBE)
        except (BotoCoreError, ClientError) as error:
            raise translate(error, scope_key=scope, collector=COLLECTOR) from error

        configured = self._configured_clusters()
        missing = configured - names
        if missing:
            # Misconfigured and not SchemaDrift, per ADR-0026: a cluster this
            # deployment was told about and CloudWatch has never heard of means the
            # operator's configuration is wrong, not that our reading is.
            raise Misconfigured(
                scope_key=scope,
                collector=COLLECTOR,
                detail=(
                    f"configured clusters publish no container metrics here: {sorted(missing)}"
                ),
            )

        out: list[ClusterSlice] = []
        for name in sorted(names):
            enhanced = name in with_requests
            out.append(
                ClusterSlice(
                    cluster_name=name,
                    account_id=account.account_id,
                    region_id=region,
                    # EKS, because ContainerInsights publishes node metrics under
                    # this namespace for EKS. An ECS cluster is read elsewhere.
                    platform="EKS",
                    enhanced_observability=enhanced,
                    # Cost is the bill's answer, never this adapter's. A metrics
                    # source inventing a cost would put a modelled figure on a
                    # screen that says measured.
                    cost=None,
                    node_count=None,
                    spot_ratio=None,
                    packing_efficiency=None,
                    unmeasurable_reason=(
                        None
                        if enhanced
                        else (
                            "Enhanced observability is not enabled on this cluster, so "
                            "pod requests are not published and requested against used "
                            "cannot be stated"
                        )
                    ),
                    as_of=now,
                    collected_at=now,
                )
            )
        return tuple(out)

    def _configured_clusters(self) -> set[str]:
        """Cluster names this deployment was told to expect, if any.

        Empty by default, which means discover whatever is there. An operator who
        names clusters gets told when one of them is missing rather than quietly
        seeing a shorter list.
        """
        raw = getattr(self._settings, "container_clusters", "") or ""
        return {part.strip() for part in str(raw).split(",") if part.strip()}

    # -- reservations ------------------------------------------------------

    def reservations(self, account: AccountKey, region: str) -> Iterable[ReservationVsUse]:
        """Requested against used per workload, with requests where published."""
        scope = f"{account}:{region}"
        client = self._factory("cloudwatch", region)
        now = self._clock()
        end = now
        start = end - timedelta(days=LOOKBACK_DAYS)

        try:
            workloads = self._workload_dimensions(client)
            requested = self._cluster_names(client, REQUEST_PROBE)
        except (BotoCoreError, ClientError) as error:
            raise translate(error, scope_key=scope, collector=COLLECTOR) from error

        wanted: list[_Query] = []
        for cluster, namespace, service in sorted(workloads):
            dimensions = (
                ("ClusterName", cluster),
                ("Namespace", namespace),
                ("Service", service),
            )
            wanted.append(
                _Query(
                    metric="pod_cpu_usage_total",
                    statistic="Maximum",
                    dimensions=dimensions,
                    cluster=cluster,
                    namespace=namespace,
                    workload=service,
                )
            )
            wanted.append(
                _Query(
                    metric="pod_memory_working_set",
                    statistic="Maximum",
                    dimensions=dimensions,
                    cluster=cluster,
                    namespace=namespace,
                    workload=service,
                )
            )
            if cluster in requested:
                wanted.append(
                    _Query(
                        metric="pod_cpu_request",
                        statistic="Average",
                        dimensions=dimensions,
                        cluster=cluster,
                        namespace=namespace,
                        workload=service,
                    )
                )
                wanted.append(
                    _Query(
                        metric="pod_memory_request",
                        statistic="Average",
                        dimensions=dimensions,
                        cluster=cluster,
                        namespace=namespace,
                        workload=service,
                    )
                )

        peaks: dict[int, Decimal] = {}
        try:
            for offset in range(0, len(wanted), METRIC_QUERY_BATCH):
                batch = wanted[offset : offset + METRIC_QUERY_BATCH]
                for index, value in self._metric_data(client, batch, start, end).items():
                    peaks[offset + index] = value
        except (BotoCoreError, ClientError) as error:
            raise translate(error, scope_key=scope, collector=COLLECTOR) from error

        by_workload: dict[tuple[str, str, str], dict[str, Decimal]] = {}
        for index, query in enumerate(wanted):
            observed = peaks.get(index)
            if observed is None:
                # Absent, not zero. A metric that never published and a metric
                # reporting nothing are indistinguishable, and the honest reading
                # of that pair is unknown.
                continue
            key = (query.cluster, query.namespace, query.workload)
            by_workload.setdefault(key, {})[query.metric] = observed

        out: list[ReservationVsUse] = []
        for (cluster, namespace, service), figures in sorted(by_workload.items()):
            out.append(
                ReservationVsUse(
                    workload=Workload(
                        cluster_name=cluster,
                        namespace=namespace,
                        name=service,
                        # Container Insights names a Service, not a kind. Said
                        # rather than guessed at Deployment, which is right most of
                        # the time and wrong in a way nobody could see.
                        kind="Service",
                        launch_type=LaunchType.EC2,
                    ),
                    cpu_requested_millicores=figures.get("pod_cpu_request"),
                    memory_requested_mib=figures.get("pod_memory_request"),
                    cpu_used_p99_millicores=figures.get("pod_cpu_usage_total"),
                    memory_used_peak_mib=figures.get("pod_memory_working_set"),
                    # Never NOT_KILLED. See the module docstring, point two.
                    oom_status=OomStatus.UNOBSERVED,
                    observation_days=LOOKBACK_DAYS,
                    as_of=now,
                    collected_at=now,
                )
            )
        return tuple(out)

    def _workload_dimensions(self, client: Any) -> set[tuple[str, str, str]]:
        """Every cluster, namespace and service triple that publishes pod metrics."""
        found: set[tuple[str, str, str]] = set()
        pages = client.get_paginator("list_metrics").paginate(
            Namespace=NAMESPACE,
            MetricName="pod_cpu_usage_total",
            Dimensions=[{"Name": "ClusterName"}, {"Name": "Namespace"}, {"Name": "Service"}],
        )
        for page in pages:
            for entry in page.get("Metrics") or ():
                values = {
                    str(d.get("Name")): str(d.get("Value") or "")
                    for d in entry.get("Dimensions") or ()
                }
                triple = (
                    values.get("ClusterName", ""),
                    values.get("Namespace", ""),
                    values.get("Service", ""),
                )
                if all(triple):
                    found.add(triple)
        return found

    @staticmethod
    def _metric_data(
        client: Any, batch: Sequence[_Query], start: datetime, end: datetime
    ) -> dict[int, Decimal]:
        """The peak of each query in the batch, keyed by its position in it.

        A query with no values is absent from the result rather than zero, which is
        what keeps an unpublished request out of the request column.
        """
        queries = [
            {
                "Id": f"{_PREFIX}{index}",
                "MetricStat": {
                    "Metric": {
                        "Namespace": NAMESPACE,
                        "MetricName": one.metric,
                        "Dimensions": [
                            {"Name": name, "Value": value} for name, value in one.dimensions
                        ],
                    },
                    "Period": PERIOD_SECONDS,
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
                parsed = (_decimal(value) for value in result.get("Values") or ())
                present = [value for value in parsed if value is not None]
                if not present:
                    continue
                index = _index_of(str(result.get("Id") or ""))
                if index is None or index >= len(batch):
                    continue
                peak = max(present)
                # A paginated series arrives across pages, so a later page can carry
                # more of the same query's values. The peak of the peaks is the peak.
                seen = peaks.get(index)
                peaks[index] = peak if seen is None else max(seen, peak)
        return peaks


def _utc() -> Any:
    from datetime import UTC

    return UTC
