"""How busy each GPU instance's accelerators were, from the CloudWatch agent's NVIDIA metrics.

P13 spec section 5.6, TASK-P13-006, FEAT-084, OPEN-33. The CloudWatch agent publishes
`nvidia_smi_utilization_gpu` for each accelerator on an instance it runs on, in the namespace the
agent is configured with, `CWAgent` unless somebody changed it. One metric per accelerator, each
with the instance's id and the accelerator's index among its dimensions, so the metrics are
listed first, by instance, and only then read: a GetMetricData request names a metric by every
dimension it has, and the ones besides the instance are not known in advance.

For each instance and day this reads the average, the peak and the number of readings of every
accelerator, then gives the instance the mean of its accelerators' averages, the highest peak and
the total readings. An instance whose agent publishes nothing yields no row, which the screen
reads as not published and never as nought percent.

GetMetricData is charged per metric requested, USD 0.01 per 1,000 at the list price (modelled),
and an instance with eight accelerators is 24 metrics a day: three statistics each.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Final

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from finops_core.config import Settings
from finops_core.domain.account import AccountKey
from finops_core.domain.ai import GpuUtilization
from finops_core.errors import SchemaDrift
from finops_providers.aws.client import botocore_config, translate

COLLECTOR = "gpu_utilization"
METRIC: Final = "nvidia_smi_utilization_gpu"
INSTANCE: Final = "InstanceId"
#: One reading a day per statistic: the collector reads a day at a time.
PERIOD_SECONDS: Final = 86400  # allow-hardcoded: one day, the grain the table stores
#: The documented ceiling on queries in one GetMetricData request.
BATCH: Final = 500  # allow-hardcoded: the documented GetMetricData request limit
STATISTICS: Final = ("Average", "Maximum", "SampleCount")

ClientFactory = Callable[[str, str], Any]
Readings = dict[tuple[str, datetime], dict[int, dict[str, Decimal]]]


class CloudWatchGpuMetrics:
    """`GpuMetrics` over CloudWatch, in one member account's session. Reads only."""

    def __init__(
        self,
        settings: Settings,
        tenant_id: Any,
        *,
        session: Any = None,
        client_factory: ClientFactory | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._tenant_id = tenant_id
        self._session = session
        self._factory = client_factory or self._default_client
        self._clock = clock or (lambda: datetime.now(UTC))

    def _default_client(self, service: str, region: str) -> Any:
        maker = self._session or boto3
        return maker.client(service, region_name=region, config=botocore_config(self._settings))

    # -- the port ----------------------------------------------------------

    def utilization(
        self,
        account: AccountKey,
        region: str,
        instances: Sequence[str],
        start: datetime,
        end: datetime,
    ) -> Iterable[GpuUtilization]:
        scope = f"{account}:{region}"
        if not instances:
            return ()
        client = self._factory("cloudwatch", region)
        namespace = self._settings.gpu_metrics_namespace
        try:
            metrics = {
                instance: self._accelerators(client, namespace, instance) for instance in instances
            }
            readings = self._read(client, namespace, metrics, start, end, scope)
        except (ClientError, BotoCoreError) as error:
            raise translate(error, scope, COLLECTOR) from error
        at = self._clock()
        rows: list[GpuUtilization] = []
        for (instance, day), per_gpu in sorted(readings.items()):
            complete = [gpu for gpu in per_gpu.values() if set(STATISTICS) <= gpu.keys()]
            if not complete:
                continue
            ends = min(day + timedelta(days=1), end)
            mean = sum((gpu["Average"] for gpu in complete), Decimal(0)) / len(complete)
            rows.append(
                GpuUtilization(
                    tenant_id=self._tenant_id,
                    account_id=account.account_id,
                    region_id=region,
                    instance_id=instance,
                    usage_date=day.date(),
                    gpu_count=len(complete),
                    average_percent=_percent(mean, scope),
                    peak_percent=_percent(max(gpu["Maximum"] for gpu in complete), scope),
                    samples=int(sum(gpu["SampleCount"] for gpu in complete)),
                    as_of=ends,
                    collected_at=max(at, ends),
                )
            )
        return tuple(rows)

    # -- reading -----------------------------------------------------------

    @staticmethod
    def _accelerators(client: Any, namespace: str, instance: str) -> list[list[dict[str, str]]]:
        """The full dimension set of each accelerator metric this instance publishes."""
        found: list[list[dict[str, str]]] = []
        pages = client.get_paginator("list_metrics").paginate(
            Namespace=namespace,
            MetricName=METRIC,
            Dimensions=[{"Name": INSTANCE, "Value": instance}],
        )
        for page in pages:
            for metric in page.get("Metrics") or ():
                dimensions = [
                    {"Name": str(one.get("Name")), "Value": str(one.get("Value"))}
                    for one in metric.get("Dimensions") or ()
                ]
                if dimensions:
                    found.append(dimensions)
        return found

    @staticmethod
    def _read(
        client: Any,
        namespace: str,
        metrics: dict[str, list[list[dict[str, str]]]],
        start: datetime,
        end: datetime,
        scope: str,
    ) -> Readings:
        """Each statistic of each accelerator, per instance and day."""
        queries: list[tuple[str, int, str, dict[str, Any]]] = [
            (
                instance,
                gpu,
                statistic,
                {"Namespace": namespace, "MetricName": METRIC, "Dimensions": dimensions},
            )
            for instance, accelerators in metrics.items()
            for gpu, dimensions in enumerate(accelerators)
            for statistic in STATISTICS
        ]
        readings: Readings = {}
        for first in range(0, len(queries), BATCH):
            batch = queries[first : first + BATCH]
            request = [
                {
                    "Id": f"q{index}",
                    "MetricStat": {"Metric": metric, "Period": PERIOD_SECONDS, "Stat": statistic},
                    "ReturnData": True,
                }
                for index, (_instance, _gpu, statistic, metric) in enumerate(batch)
            ]
            pages = client.get_paginator("get_metric_data").paginate(
                MetricDataQueries=request, StartTime=start, EndTime=end
            )
            for page in pages:
                for result in page.get("MetricDataResults") or ():
                    identifier = str(result.get("Id") or "")
                    if not identifier.startswith("q") or not identifier[1:].isdigit():
                        continue
                    position = int(identifier[1:])
                    if position >= len(batch):
                        continue
                    instance, gpu, statistic, _metric = batch[position]
                    stamps = result.get("Timestamps") or ()
                    values = result.get("Values") or ()
                    for stamp, raw in zip(stamps, values, strict=False):
                        statistics = readings.setdefault((instance, _day(stamp)), {})
                        statistics.setdefault(gpu, {})[statistic] = _decimal(raw, scope)
        return readings


def _day(stamp: Any) -> datetime:
    moment = stamp if isinstance(stamp, datetime) else datetime.fromisoformat(str(stamp))
    return moment.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _decimal(raw: Any, scope: str) -> Decimal:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError) as error:
        raise SchemaDrift(
            scope_key=scope, collector=COLLECTOR, detail=f"{raw!r} is not a reading"
        ) from error
    if not value.is_finite():
        raise SchemaDrift(scope_key=scope, collector=COLLECTOR, detail=f"{raw!r} is not a reading")
    return value


def _percent(value: Decimal, scope: str) -> Decimal:
    if not Decimal(0) <= value <= Decimal(100):
        raise SchemaDrift(
            scope_key=scope,
            collector=COLLECTOR,
            detail=f"a GPU utilization of {value} is not a percentage",
        )
    return value.quantize(Decimal("0.01"))
