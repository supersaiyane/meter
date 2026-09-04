"""What the classifier recognises, including the shapes nobody writes any more.

Grafana has changed how a CloudWatch target names its log groups twice, and all
three shapes are still in real dashboards. A classifier that only reads the
newest one prices an old dashboard at zero, which reads as "this dashboard is
free" rather than as "this dashboard was not understood". That is the failure
these tests exist for.

Two known defects are pinned here rather than fixed, because TASK-P2-002 is an
extraction. Both are recorded as issues and both are fixed later, where the
golden diff shows what moved.
"""

from __future__ import annotations

import pytest

from finops_query import classify


def test_the_three_log_group_shapes_are_all_read() -> None:
    """Objects, a list of names, and a single name. All three are real."""
    modern = {"logGroups": [{"name": "/app/api", "arn": "arn:ignored"}]}
    by_arn = {"logGroups": [{"arn": "arn:aws:logs:eu-west-1:000000000000:log-group:/app/x:*"}]}
    listed = {"logGroupNames": ["/app/one", "/app/two"]}
    single = {"logGroupName": "/app/legacy"}

    assert classify.log_groups_of(modern) == ("/app/api",)
    assert classify.log_groups_of(by_arn) == (
        "arn:aws:logs:eu-west-1:000000000000:log-group:/app/x:*",
    )
    assert classify.log_groups_of(listed) == ("/app/one", "/app/two")
    assert classify.log_groups_of(single) == ("/app/legacy",)


def test_a_log_group_named_twice_is_counted_once() -> None:
    """Cost is summed per group, so a duplicate would double the estimate."""
    target = {"logGroups": [{"name": "/app/api"}], "logGroupName": "/app/api"}

    assert classify.log_groups_of(target) == ("/app/api",)


def test_log_group_order_is_kept() -> None:
    """The label a person reads is these joined in order."""
    target = {"logGroupNames": ["/z", "/a", "/m"]}

    assert classify.log_groups_of(target) == ("/z", "/a", "/m")


def test_empty_and_blank_log_groups_are_dropped() -> None:
    target = {"logGroups": [{"name": ""}, {"name": "  "}, {"name": "/app/real"}]}

    assert classify.log_groups_of(target) == ("/app/real",)


def test_a_string_datasource_is_accepted() -> None:
    """Old dashboards name a datasource by string rather than by object."""
    found = classify.classify({"expr": "up"}, "prometheus")

    assert found.engine == "prometheus"


@pytest.mark.parametrize(
    ("time_from", "expected"),
    [
        ("now-7d", 604800),
        ("now-30m", 1800),
        ("now-1y", 31536000),
        ("now/d", 86400),
        ("now/w", 604800),
        ("2026-01-01T00:00:00Z", None),
        (None, None),
        (12345, None),
    ],
)
def test_relative_ranges_are_read_and_absolute_ones_are_not(
    time_from: object, expected: int | None
) -> None:
    """None means unknown rather than zero. The cost model treats them
    differently and pricing an absolute range at zero would make every
    dashboard that uses one look free."""
    assert classify.relative_range_seconds(time_from) == expected


@pytest.mark.parametrize(
    ("refresh", "expected"),
    [("30s", 30), ("1m", 60), ("1h", 3600), ("", 0), (None, 0), ("banana", 0), (5, 0)],
)
def test_refresh_intervals_are_read(refresh: object, expected: int) -> None:
    assert classify.refresh_seconds(refresh) == expected


def test_a_month_is_thirty_days() -> None:
    """Grafana's `M` unit. An approximation, and the prototype's own."""
    assert classify.UNIT_SECONDS["M"] == 2592000


def test_rows_are_flattened_and_their_children_are_found() -> None:
    """A version that did not recurse would price nothing on any dashboard
    using rows, which is most of them, and report zero findings rather than an
    error."""
    panels = [
        {"type": "row", "panels": [{"id": 1, "title": "inside"}]},
        {"id": 2, "title": "outside"},
    ]

    assert [p["title"] for p in classify.iter_panels(panels)] == ["inside", "outside"]


def test_a_row_inside_a_row_is_still_flattened() -> None:
    panels = [{"type": "row", "panels": [{"type": "row", "panels": [{"id": 1, "title": "deep"}]}]}]

    assert [p["title"] for p in classify.iter_panels(panels)] == ["deep"]


def test_the_classification_renders_the_shape_the_goldens_record() -> None:
    found = classify.classify(
        {"queryMode": "Logs", "expression": "fields @message", "logGroups": [{"name": "/a"}]},
        {"type": "cloudwatch"},
    )

    assert found.as_dict() == {
        "engine": "logs_insights",
        "query": "fields @message",
        "region": None,
        "log_groups": ["/a"],
        "namespace": None,
        "target_label": "/a",
    }


# --- the two known defects, pinned rather than fixed --------------------------


def test_a_metric_expression_containing_filter_is_misread_as_logs() -> None:
    """ISS-132. `classify` decides a CloudWatch target is Logs Insights if its
    expression merely contains "filter ", which matches the metric maths FILTER
    function. The target below is a metric query and is priced as a log scan.

    Pinned rather than fixed, because TASK-P2-002 is an extraction. Fixing it
    moves real numbers and belongs in a commit where the golden diff shows
    which ones.
    """
    metric_maths = {"expression": "FILTER (SEARCH('{AWS/EC2}', 'Average'), 5)"}

    found = classify.classify(metric_maths, {"type": "cloudwatch"})

    assert found.engine == "logs_insights", "ISS-132: pinned, not endorsed"


def test_an_unknown_datasource_reports_itself_as_an_engine() -> None:
    """ISS-133. The datasource type is copied into `engine` before anything has
    checked that it names an engine, so a Postgres panel reports engine
    "postgres". No rate exists for it, so it is priced at zero rather than
    refused, and a zero reads as free rather than as unknown."""
    found = classify.classify({"rawSql": "SELECT 1"}, {"type": "postgres"})

    assert found.engine == "postgres", "ISS-133: pinned, not endorsed"
    assert found.engine not in classify.BILLED_ENGINES
