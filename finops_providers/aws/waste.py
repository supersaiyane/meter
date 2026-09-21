"""Reading many metrics without spending a fortune on it.

**Nothing in this file has ever made a call.** ISS-122.

One decision, and it is in the specification rather than left to judgement at
three in the afternoon: `GetMetricData` is charged **per metric requested**, so a
naive one call per instance implementation across a three hundred account estate
is a line item that would appear on our own platform cost screen. Requests are
batched at `METER_GETMETRICDATA_BATCH_SIZE`, which is 500, at a one hour period.

The one hour period has a second reason beyond cost. Every percentile in
`finops_query.waste` is computed over the series this returns, and a percentile
over daily points is the second largest value: the rule silently becomes "use the
max", which is the rule it exists to replace.

**An absent key means unobserved.** A series that returned no points is not a
series of zeroes, and it does not appear in the result at all. A caller reading an
absent key as zero utilization would recommend terminating a running system, which
is the most expensive possible instance of rendering a failure as a number.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.config import Settings
from finops_core.domain.metrics import MetricPoint
from finops_core.ports.metrics import MetricRequest
from finops_providers.aws.client import translate

COLLECTOR = "waste_metrics"
SCOPE = "billing"

#: One hour. Both for the bill and for the percentile, see the module docstring.
PERIOD_SECONDS = 3600

#: CloudWatch rejects an id that is not lowercase alphanumeric starting with a
#: letter, so the caller's key cannot be used directly and a positional id is
#: generated instead. The mapping back is held for the length of one batch.
_ID_PREFIX = "m"


class CloudWatchWasteMetrics:
    """Batched `GetMetricData`. Unproved, ISS-122."""

    def __init__(
        self,
        settings: Settings,
        *,
        client_factory: Callable[[str, str], Any],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(UTC))
        self._batch_size = int(settings.getmetricdata_batch_size)
        # Per account and region, because a metric read is an assumed role call
        # into the account that owns the resource.
        self._factory = client_factory

    def read_many(
        self,
        requests: Iterable[MetricRequest],
        window_start: datetime,
        window_end: datetime,
        period_seconds: int = PERIOD_SECONDS,
    ) -> Mapping[str, tuple[MetricPoint, ...]]:
        found: dict[str, tuple[MetricPoint, ...]] = {}
        # Grouped by account and region first, because one client can only read
        # its own. Batching across accounts would be a call that cannot be made.
        by_target: dict[tuple[str, str], list[MetricRequest]] = {}
        for request in requests:
            by_target.setdefault((request.account.account_id, request.region), []).append(request)

        for (account_id, region), group in by_target.items():
            client = self._factory(account_id, region)
            for batch in _in_batches(group, self._batch_size):
                found.update(
                    self._one_batch(client, batch, window_start, window_end, period_seconds)
                )
        return found

    def _one_batch(
        self,
        client: Any,
        batch: list[MetricRequest],
        window_start: datetime,
        window_end: datetime,
        period_seconds: int,
    ) -> dict[str, tuple[MetricPoint, ...]]:
        by_id = {f"{_ID_PREFIX}{index}": request for index, request in enumerate(batch)}
        queries = [
            {
                "Id": metric_id,
                "MetricStat": {
                    "Metric": {
                        "Namespace": request.namespace,
                        "MetricName": request.metric_name,
                        "Dimensions": [
                            {"Name": name, "Value": value}
                            for name, value in sorted(request.dimensions.items())
                        ],
                    },
                    "Period": period_seconds,
                    "Stat": request.statistic,
                },
                "ReturnData": True,
            }
            for metric_id, request in by_id.items()
        ]

        try:
            response = client.get_metric_data(
                MetricDataQueries=queries,
                StartTime=window_start,
                EndTime=window_end,
            )
        except (BotoCoreError, ClientError) as error:
            raise translate(error, scope_key=SCOPE, collector=COLLECTOR) from error

        out: dict[str, tuple[MetricPoint, ...]] = {}
        for result in response.get("MetricDataResults", []):
            request = by_id.get(str(result.get("Id", "")))
            if request is None:
                continue
            timestamps = result.get("Timestamps") or []
            values = result.get("Values") or []
            if not timestamps:
                # Absent, not zero. The key simply does not appear.
                continue
            now = self._clock()
            out[request.key] = tuple(
                MetricPoint(
                    # `at` is the instant the value describes, `as_of` is when the
                    # source considered it true, and `collected_at` is now.
                    # Constraint 10, and for a metric the first two coincide.
                    as_of=at,
                    collected_at=now,
                    at=at,
                    account_key=request.account,
                    namespace=request.namespace,
                    metric_name=request.metric_name,
                    statistic=request.statistic,
                    unit=str(result.get("Label", "")) or "None",
                    value=Decimal(str(value)),
                )
                for at, value in zip(timestamps, values, strict=False)
            )
        return out


def _in_batches(items: list[MetricRequest], size: int) -> Iterable[list[MetricRequest]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
