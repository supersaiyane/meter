"""Reading executions out of CloudTrail and query history.

Most of these assert a distinction rather than a value. An undercounted run rate
reads as a cheaper query, a zero reads as a query nobody ran, and both are wrong
in a way that looks like an answer.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from botocore.exceptions import ClientError

from finops_core.errors import CollectionError, SchemaDrift
from finops_core.ports.query import QueryEvidence
from finops_providers.aws.query_evidence import CloudTrailQueryEvidence
from finops_query.parser import GrafanaQueryParser

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
QUERY = "fields @timestamp, @message | filter @message like /ERROR/"


def start_query_event(query: str = QUERY, groups: list[str] | None = None) -> dict[str, Any]:
    return {
        "CloudTrailEvent": json.dumps(
            {
                "eventName": "StartQuery",
                "requestParameters": {
                    "queryString": query,
                    "logGroupNames": groups if groups is not None else ["/aws/ecs/meter-api"],
                },
            }
        )
    }


def metric_event(namespace: str = "AWS/ECS", metric: str = "CPUUtilization") -> dict[str, Any]:
    return {
        "CloudTrailEvent": json.dumps(
            {
                "eventName": "GetMetricData",
                "requestParameters": {
                    "metricDataQueries": [
                        {"metricStat": {"metric": {"namespace": namespace, "metricName": metric}}}
                    ]
                },
            }
        )
    }


class Trail:
    """A CloudTrail that answers from a script, one page per call."""

    def __init__(
        self,
        pages: dict[str, list[dict[str, Any]]] | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.pages = pages or {}
        self.failure = failure
        self.calls = 0

    def lookup_events(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        name = kwargs["LookupAttributes"][0]["AttributeValue"]
        pages = self.pages.get(name, [])
        index = 1 if kwargs.get("NextToken") else 0
        if index >= len(pages):
            return {"Events": []}
        page = dict(pages[index])
        if index == 0 and len(pages) > 1:
            page["NextToken"] = "more"
        return page


class Logs:
    def __init__(
        self,
        queries: list[dict[str, Any]] | None = None,
        stats: dict[str, Any] | None = None,
        describe_failure: Exception | None = None,
        results_failure: Exception | None = None,
    ) -> None:
        self.queries = queries or []
        self.stats = stats or {}
        self.describe_failure = describe_failure
        self.results_failure = results_failure

    def describe_queries(self, **_kwargs: Any) -> dict[str, Any]:
        if self.describe_failure is not None:
            raise self.describe_failure
        return {"queries": self.queries}

    def get_query_results(self, **kwargs: Any) -> dict[str, Any]:
        if self.results_failure is not None:
            raise self.results_failure
        return {"statistics": self.stats.get(kwargs["queryId"], {})}


def evidence(
    trail: Trail, logs: Logs | None = None, read_bytes: bool = True
) -> CloudTrailQueryEvidence:
    resolved = logs or Logs()

    def factory(service: str, _account: str, _region: str) -> Any:
        return resolved if service == "logs" else trail

    return CloudTrailQueryEvidence(
        client_factory=factory, parser=GrafanaQueryParser(), now=lambda: NOW, read_bytes=read_bytes
    )


def observe(source: CloudTrailQueryEvidence, days: int = 30) -> Any:
    return source.observations(account_id="111122223333", region="eu-west-2", lookback_days=days)


def test_it_satisfies_the_port() -> None:
    assert isinstance(evidence(Trail()), QueryEvidence)


def test_runs_are_counted_from_start_query_events() -> None:
    trail = Trail({"StartQuery": [{"Events": [start_query_event(), start_query_event()]}]})
    bundle = observe(evidence(trail, read_bytes=False))
    (record,) = bundle["logs"].values()
    assert record["runs"] == 2
    assert record["log_groups"] == {"/aws/ecs/meter-api"}


def test_every_page_is_followed() -> None:
    # A cap here would silently undercount a busy account, and an undercounted
    # run rate reads as a cheaper query.
    trail = Trail(
        {"StartQuery": [{"Events": [start_query_event()]}, {"Events": [start_query_event()]}]}
    )
    bundle = observe(evidence(trail, read_bytes=False))
    (record,) = bundle["logs"].values()
    assert record["runs"] == 2


def test_a_query_nobody_ran_is_absent_rather_than_zero() -> None:
    # Absent means unobserved. A zero would say the query never ran, which is a
    # claim about the world rather than a report of what was seen.
    bundle = observe(evidence(Trail(), read_bytes=False))
    assert bundle["logs"] == {}
    assert bundle["gmd_by_metric"] == {}


def test_the_window_it_reports_is_the_window_it_was_asked_for() -> None:
    bundle = observe(evidence(Trail(), read_bytes=False), days=7)
    assert bundle["lookback_days"] == 7


def test_bytes_are_attached_from_query_history() -> None:
    trail = Trail({"StartQuery": [{"Events": [start_query_event()]}]})
    logs = Logs(
        queries=[{"queryId": "q-1", "queryString": QUERY}],
        stats={"q-1": {"bytesScanned": 2_147_483_648}},
    )
    bundle = observe(evidence(trail, logs))
    (record,) = bundle["logs"].values()
    assert record["bytes"] == 2_147_483_648.0
    assert record["runs_bytes"] == [2_147_483_648.0]


def test_missing_history_still_leaves_the_run_count() -> None:
    """Best effort, on purpose.

    Failing because bytes were unavailable would throw away the run counts too,
    and runs alone are still a measurement.
    """
    trail = Trail({"StartQuery": [{"Events": [start_query_event()]}]})
    bundle = observe(evidence(trail, Logs(queries=[], stats={})))
    (record,) = bundle["logs"].values()
    assert record["runs"] == 1
    assert record["runs_bytes"] == []


def test_one_unreadable_query_does_not_cost_the_window() -> None:
    trail = Trail({"StartQuery": [{"Events": [start_query_event()]}]})
    logs = Logs(
        queries=[{"queryId": "q-1", "queryString": QUERY}],
        results_failure=ClientError({"Error": {"Code": "ThrottlingException"}}, "GetQueryResults"),
    )
    bundle = observe(evidence(trail, logs))
    (record,) = bundle["logs"].values()
    assert record["runs"] == 1


def test_metric_calls_are_bucketed_by_namespace_and_metric() -> None:
    trail = Trail({"GetMetricData": [{"Events": [metric_event(), metric_event()]}]})
    bundle = observe(evidence(trail, read_bytes=False))
    assert bundle["gmd_by_metric"] == {"aws/ecs|cpuutilization": 2}


def test_a_failed_lookup_raises_a_typed_cause() -> None:
    trail = Trail(failure=ClientError({"Error": {"Code": "AccessDeniedException"}}, "LookupEvents"))
    with pytest.raises(CollectionError):
        observe(evidence(trail, read_bytes=False))


def test_an_unreadable_event_is_drift_rather_than_a_skipped_run() -> None:
    # Skipping it would undercount silently, which is the one failure this
    # module cannot afford.
    trail = Trail({"StartQuery": [{"Events": [{"CloudTrailEvent": "not json"}]}]})
    with pytest.raises(SchemaDrift):
        observe(evidence(trail, read_bytes=False))
