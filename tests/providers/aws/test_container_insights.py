"""How the Container Insights adapter turns an hourly series into one figure.

The contract suite's stub returns a single value per series, and on a single value the
99th percentile, the maximum and the latest are all the same number. So the reduction
is tested here, on series where they differ, because a reduction nobody has watched
pick the wrong value is one that may already be doing so.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from finops_providers.aws.container_insights import (
    ContainerInsightsSource,
    _Query,
    _reduce,
)

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def hours(values: list[int]) -> list[tuple[datetime | None, Decimal]]:
    return [(T0 + timedelta(hours=i), Decimal(v)) for i, v in enumerate(values)]


def test_cpu_is_the_99th_percentile_and_not_the_maximum() -> None:
    """The defect this file was written against.

    The adapter used to keep the maximum and store it in a field named for the
    percentile. With one spike in two hundred hours the two differ, and the rule the
    rationale states is the percentile.
    """
    series = hours([100] * 199 + [900])
    assert _reduce(series, "max") == Decimal(900)
    assert _reduce(series, "p99") == Decimal(100)


def test_memory_is_the_peak_because_a_percentile_of_memory_kills() -> None:
    series = hours([100] * 199 + [900])
    assert _reduce(series, "max") == Decimal(900)


def test_a_request_is_its_latest_value_not_its_largest() -> None:
    """A request lowered last week would otherwise overstate the saving."""
    series = hours([2048] * 100 + [1024] * 50)
    assert _reduce(series, "latest") == Decimal(1024)


def test_latest_is_chosen_by_timestamp_not_by_position() -> None:
    """GetMetricData returns newest first by default, so position cannot be trusted."""
    series = list(reversed(hours([2048] * 10 + [1024])))
    assert _reduce(series, "latest") == Decimal(1024)


def test_an_unknown_reduction_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ValueError, match="no reduction"):
        _reduce(hours([1, 2]), "mean")


class _Pages:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages

    def paginate(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return self._pages


class _Client:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages

    def get_paginator(self, _name: str) -> _Pages:
        return _Pages(self._pages)


def test_the_series_is_gathered_across_pages_before_it_is_reduced() -> None:
    """A percentile of one page is not a percentile of the series."""
    first = [{"Id": "m0", "Values": [100.0] * 150, "Timestamps": [T0] * 150}]
    second = [{"Id": "m0", "Values": [100.0] * 49 + [900.0], "Timestamps": [T0] * 50}]
    client = _Client([{"MetricDataResults": first}, {"MetricDataResults": second}])
    query = _Query(
        metric="pod_cpu_usage_total",
        statistic="Maximum",
        reduce="p99",
        dimensions=(("ClusterName", "c"),),
        cluster="c",
    )
    figures = ContainerInsightsSource._metric_data(client, [query], T0, T0)
    assert figures == {0: Decimal(100)}


def test_a_series_with_no_values_is_absent_rather_than_zero() -> None:
    client = _Client([{"MetricDataResults": [{"Id": "m0", "Values": []}]}])
    query = _Query(
        metric="pod_cpu_request",
        statistic="Average",
        reduce="latest",
        dimensions=(("ClusterName", "c"),),
        cluster="c",
    )
    assert ContainerInsightsSource._metric_data(client, [query], T0, T0) == {}
