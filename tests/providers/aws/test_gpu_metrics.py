"""GPU utilization from the CloudWatch agent's NVIDIA metrics, against a stub. TASK-P13-006.

The metrics are listed per instance before they are read, because an accelerator's metric is
named by dimensions besides the instance that are not known in advance. An instance whose agent
publishes nothing yields no row, never nought percent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from botocore.exceptions import ClientError

from finops_core import errors
from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_providers.aws.gpu_metrics import METRIC, CloudWatchGpuMetrics

ACCOUNT = AccountKey(provider=Provider.AWS, account_id="111122223333")
REGION = "eu-west-1"
DAY = datetime(2026, 10, 12, tzinfo=UTC)
NEXT_DAY = datetime(2026, 10, 13, tzinfo=UTC)
NOW = datetime(2026, 10, 13, 6, tzinfo=UTC)


def accelerator(instance: str, index: int) -> dict[str, Any]:
    return {
        "Namespace": "CWAgent",
        "MetricName": METRIC,
        "Dimensions": [
            {"Name": "InstanceId", "Value": instance},
            {"Name": "index", "Value": str(index)},
            {"Name": "name", "Value": "NVIDIA A10G"},
        ],
    }


class StubCloudWatch:
    """Lists the accelerators it was told of and answers each statistic from a table."""

    def __init__(
        self,
        published: dict[str, int],
        values: dict[str, dict[str, float]],
        failure: Exception | None = None,
    ) -> None:
        self.published = published
        self.values = values
        self.failure = failure
        self.listed: list[dict[str, Any]] = []
        self.read: list[list[dict[str, Any]]] = []

    def get_paginator(self, name: str) -> Any:
        if self.failure:
            raise self.failure
        stub = self

        class Paginator:
            def paginate(self, **kwargs: Any) -> Any:
                if name == "list_metrics":
                    stub.listed.append(kwargs)
                    instance = kwargs["Dimensions"][0]["Value"]
                    count = stub.published.get(instance, 0)
                    yield {"Metrics": [accelerator(instance, i) for i in range(count)]}
                    return
                queries = kwargs["MetricDataQueries"]
                stub.read.append(queries)
                results = []
                for query in queries:
                    stat = query["MetricStat"]
                    dimensions = {d["Name"]: d["Value"] for d in stat["Metric"]["Dimensions"]}
                    key = f"{dimensions['InstanceId']}/{dimensions['index']}"
                    value = stub.values[key][stat["Stat"]]
                    results.append({"Id": query["Id"], "Timestamps": [DAY], "Values": [value]})
                yield {"MetricDataResults": results}

        return Paginator()


def metrics(settings: Settings, cloudwatch: StubCloudWatch) -> CloudWatchGpuMetrics:
    return CloudWatchGpuMetrics(
        settings,
        tenant_id="tenant",
        client_factory=lambda _service, _region: cloudwatch,
        clock=lambda: NOW,
    )


def test_an_instance_is_the_mean_of_its_accelerators_and_the_highest_peak(
    settings: Settings,
) -> None:
    cloudwatch = StubCloudWatch(
        published={"i-gpu-1": 2},
        values={
            "i-gpu-1/0": {"Average": 30.0, "Maximum": 80.0, "SampleCount": 1440.0},
            "i-gpu-1/1": {"Average": 10.0, "Maximum": 95.5, "SampleCount": 1440.0},
        },
    )
    source = metrics(settings, cloudwatch)
    (row,) = source.utilization(ACCOUNT, REGION, ["i-gpu-1"], DAY, NEXT_DAY)

    assert (row.instance_id, row.usage_date, row.gpu_count, row.samples) == (
        "i-gpu-1",
        DAY.date(),
        2,
        2880,
    )
    assert (row.average_percent, row.peak_percent) == (Decimal("20.00"), Decimal("95.50"))
    assert (row.account_id, row.region_id, row.as_of, row.collected_at) == (
        "111122223333",
        REGION,
        NEXT_DAY,
        NOW,
    )
    (listed,) = cloudwatch.listed
    assert listed["Namespace"] == settings.gpu_metrics_namespace
    assert listed["MetricName"] == METRIC
    (read,) = cloudwatch.read
    assert {q["MetricStat"]["Stat"] for q in read} == {"Average", "Maximum", "SampleCount"}
    assert all(q["MetricStat"]["Period"] == 86400 for q in read)


def test_an_instance_that_publishes_nothing_has_no_row(settings: Settings) -> None:
    cloudwatch = StubCloudWatch(published={}, values={})
    rows = metrics(settings, cloudwatch).utilization(ACCOUNT, REGION, ["i-quiet"], DAY, NEXT_DAY)
    assert list(rows) == []
    assert cloudwatch.read == []


def test_no_instance_asks_nothing(settings: Settings) -> None:
    cloudwatch = StubCloudWatch(published={}, values={})
    assert list(metrics(settings, cloudwatch).utilization(ACCOUNT, REGION, [], DAY, NEXT_DAY)) == []
    assert cloudwatch.listed == []


def test_a_namespace_the_deployment_names_is_the_one_read(settings: Settings) -> None:
    cloudwatch = StubCloudWatch(published={}, values={})
    custom = settings.model_copy(update={"gpu_metrics_namespace": "Fleet/GPU"})
    list(metrics(custom, cloudwatch).utilization(ACCOUNT, REGION, ["i-1"], DAY, NEXT_DAY))
    assert cloudwatch.listed[0]["Namespace"] == "Fleet/GPU"


@pytest.mark.parametrize("bad", [140.0, -2.0])
def test_a_reading_that_is_not_a_percentage_is_drift(settings: Settings, bad: float) -> None:
    cloudwatch = StubCloudWatch(
        published={"i-1": 1},
        values={"i-1/0": {"Average": bad, "Maximum": bad, "SampleCount": 10.0}},
    )
    with pytest.raises(errors.SchemaDrift, match="percentage"):
        list(metrics(settings, cloudwatch).utilization(ACCOUNT, REGION, ["i-1"], DAY, NEXT_DAY))


@pytest.mark.parametrize(
    ("code", "cause"),
    [("AccessDenied", errors.AccessDenied), ("Throttling", errors.Throttled)],
)
def test_a_refused_read_fails_typed(
    settings: Settings, code: str, cause: type[errors.CollectionError]
) -> None:
    refused = ClientError({"Error": {"Code": code, "Message": code}}, "ListMetrics")
    cloudwatch = StubCloudWatch(published={}, values={}, failure=refused)
    with pytest.raises(cause):
        list(metrics(settings, cloudwatch).utilization(ACCOUNT, REGION, ["i-1"], DAY, NEXT_DAY))
