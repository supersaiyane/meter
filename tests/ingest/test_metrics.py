"""What Meter publishes about itself.

Two of these matter more than the rest. The percentage must not compute its
denominator from its numerator, which is ISS-016 in a different place and always
reports a hundred percent. And a collector with nothing stalled must still
publish a zero, because a metric that only appears when something is wrong
cannot be alarmed on absence, and the alarm then dies quietly with the publisher
it was watching.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from finops_ingest.metrics import (
    NAMESPACE,
    STALL_ALERT_CADENCE_MULTIPLE,
    Measurement,
    freshness_measurements,
    publish,
    screen_and_alert_thresholds,
)

AT = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)


class Rows:
    """A connection that answers the two queries with fixed rows."""

    def __init__(self, totals: list[dict[str, Any]], stalled: list[dict[str, Any]]) -> None:
        self._totals = totals
        self._stalled = stalled

    def execute(self, statement: Any, parameters: Any = None) -> Rows:  # noqa: ARG002
        self._last = "stalled" if parameters else "totals"
        return self

    def mappings(self) -> list[dict[str, Any]]:
        return self._stalled if self._last == "stalled" else self._totals


class Recorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def put_metric_data(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


def test_the_percentage_is_over_the_total_not_over_the_stalled() -> None:
    """A denominator taken from the numerator always reports a hundred percent."""
    connection = Rows(
        totals=[{"collector": "org_tree", "total": 40}],
        stalled=[{"collector": "org_tree", "stalled": 4, "total": 4}],
    )

    by_name = {m.name: m.value for m in freshness_measurements(connection)}

    assert by_name["StalledScopes"] == 4
    assert by_name["TotalScopes"] == 40
    assert by_name["StalledScopePercent"] == 10.0


def test_a_healthy_collector_still_publishes_a_zero() -> None:
    """Otherwise the alarm cannot tell healthy from a publisher that stopped."""
    connection = Rows(totals=[{"collector": "org_tree", "total": 12}], stalled=[])

    measurements = freshness_measurements(connection)
    by_name = {m.name: m.value for m in measurements}

    assert len(measurements) == 3
    assert by_name["StalledScopes"] == 0.0
    assert by_name["StalledScopePercent"] == 0.0


def test_a_collector_with_no_scopes_does_not_divide_by_zero() -> None:
    connection = Rows(totals=[{"collector": "platform_cost", "total": 0}], stalled=[])

    by_name = {m.name: m.value for m in freshness_measurements(connection)}

    assert by_name["StalledScopePercent"] == 0.0


def test_the_page_fires_later_than_the_screen_turns_amber() -> None:
    """Paging on the threshold the screen already shows pages an operator for
    something they are looking at, which is how a page gets muted."""
    screen, alert = screen_and_alert_thresholds()

    assert alert > screen


def test_every_metric_carries_its_collector_and_nothing_finer() -> None:
    """A dimension per scope is thousands of metrics at three hundred accounts,
    which is a bill this product would flag."""
    connection = Rows(totals=[{"collector": "org_tree", "total": 3}], stalled=[])

    for measurement in freshness_measurements(connection):
        assert set(measurement.dimensions) == {"Collector"}


def test_publishing_nothing_calls_nothing() -> None:
    """An empty PutMetricData is a billed API call that carries no information."""
    recorder = Recorder()

    assert publish(recorder, [], clock=lambda: AT) == 0
    assert recorder.calls == []


def test_measurements_are_batched_under_the_api_limit() -> None:
    """One call is always enough today. The batching exists so that adding a
    collector does not silently stop the metrics."""
    recorder = Recorder()
    many = [Measurement("StalledScopes", 1.0, "Count", {"Collector": f"c{i}"}) for i in range(1500)]

    sent = publish(recorder, many, clock=lambda: AT)

    assert sent == 1500
    assert [len(call["MetricData"]) for call in recorder.calls] == [1000, 500]
    assert {call["Namespace"] for call in recorder.calls} == {NAMESPACE}


def test_a_datum_carries_the_timestamp_it_was_measured_at() -> None:
    """Not the time CloudWatch received it. A late publish must not make a stale
    measurement look current, which is constraint 10 in a different place."""
    datum = Measurement("StalledScopes", 2.0, "Count", {"Collector": "org_tree"}).as_datum(AT)

    assert datum["Timestamp"] == AT
    assert datum["Dimensions"] == [{"Name": "Collector", "Value": "org_tree"}]


@pytest.mark.parametrize("multiple", [STALL_ALERT_CADENCE_MULTIPLE])
def test_the_alert_multiple_is_the_one_the_alarm_uses(multiple: int) -> None:
    """Three, and the alarm description says three. If these drift, the runbook
    describes a threshold that is not the one that fired."""
    assert multiple == 3
