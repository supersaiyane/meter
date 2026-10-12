"""The invocation logs adapter, against stubbed Bedrock and Logs clients. TASK-P13-003, FEAT-082.

The test that matters most here is the first one. The invocation logs hold every prompt and
response, and the one thing standing between them and Meter is the query this adapter runs. So it
is held to aggregates: every value it returns is a count or a sum, grouped by a caller, a model or
an application, and it names no body field. P13 plan rule 1, and it is in the gate on purpose.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import pytest
from botocore.exceptions import ClientError

from finops_core import errors
from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_providers.aws.bedrock_invocations import (
    BEDROCK,
    CALLER,
    MODEL,
    SUMS,
    BedrockInvocationLogs,
    aggregate_query,
)

ACCOUNT = AccountKey(provider=Provider.AWS, account_id="111122223333")
REGION = "eu-west-1"
GROUP = "/aws/bedrock/invocations"
DAY = datetime(2026, 10, 11, tzinfo=UTC)
NEXT_DAY = datetime(2026, 10, 12, tzinfo=UTC)
NOW = datetime(2026, 10, 12, 6, 0, tzinfo=UTC)
AGENT = "arn:aws:sts::111122223333:assumed-role/support/triage"
MODEL_ID = "anthropic.claude-sonnet-4-20250514-v1:0"


def cells(**values: str) -> list[dict[str, str]]:
    return [{"field": field, "value": value} for field, value in values.items()]


def result(caller: str = AGENT, application: str | None = None, **counts: str) -> Any:
    row = {CALLER: caller, MODEL: MODEL_ID, "requests": "12", **counts}
    if application is not None:
        row["requestMetadata.app"] = application
    return [{"field": field, "value": value} for field, value in row.items()]


def denied(code: str, operation: str = "StartQuery") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


class StubBedrock:
    def __init__(self, config: dict[str, Any] | Exception) -> None:
        self._config = config

    def get_model_invocation_logging_configuration(self) -> dict[str, Any]:
        if isinstance(self._config, Exception):
            raise self._config
        return self._config


class StubLogs:
    def __init__(
        self,
        pages: list[dict[str, Any]] | None = None,
        start_error: Exception | None = None,
        statuses: list[str] | None = None,
    ) -> None:
        self.pages = pages or [{"status": "Complete", "results": []}]
        self.start_error = start_error
        self.statuses = statuses or []
        self.started: list[dict[str, Any]] = []
        self.asked: list[dict[str, Any]] = []

    def start_query(self, **kwargs: Any) -> dict[str, str]:
        if self.start_error is not None:
            raise self.start_error
        self.started.append(kwargs)
        return {"queryId": f"q-{len(self.started)}"}

    def get_query_results(self, **kwargs: Any) -> dict[str, Any]:
        self.asked.append(kwargs)
        if self.statuses:
            return {"status": self.statuses.pop(0), "results": []}
        if "nextToken" in kwargs:
            return self.pages[int(kwargs["nextToken"])]
        return self.pages[0]


def logs_for(
    settings: Settings,
    logs: StubLogs,
    config: dict[str, Any] | Exception | None = None,
) -> BedrockInvocationLogs:
    configured = {"loggingConfig": {"cloudWatchConfig": {"logGroupName": GROUP}}}
    bedrock = StubBedrock(configured if config is None else config)
    clients: dict[str, Any] = {"bedrock": bedrock, "logs": logs}
    ticks = iter(range(0, 100_000, 100))
    return BedrockInvocationLogs(
        settings,
        tenant_id="tenant",
        client_factory=lambda service, _region: clients[service],
        clock=lambda: NOW,
        sleeper=lambda _seconds: None,
        monotonic=lambda: float(next(ticks)),
    )


# --- the query holds aggregates and nothing else -----------------------------------------


@pytest.mark.parametrize("key", ["", "app"])
def test_the_query_returns_aggregates_and_names_no_body(key: str) -> None:
    query = aggregate_query(key)
    lowered = query.lower()
    # No body, no prompt, no response, no raw event, in any spelling the schema uses.
    for forbidden in ("body", "prompt", "message", "content", "fields ", "display"):
        assert forbidden not in lowered, forbidden
    # Exactly one stats stage, and the only stage before it a filter on the model being present.
    stages = [stage.strip() for stage in query.split("|")]
    assert len(stages) == 2
    assert stages[0] == f"filter ispresent({MODEL})"
    assert stages[1].startswith("stats ")
    # Every output is a count or a sum given a name, or a group.
    aggregates, _, groups = stages[1].removeprefix("stats ").partition(" by ")
    outputs = [part.strip() for part in aggregates.split(",")]
    assert outputs[0] == "count(*) as requests"
    named = set()
    for output in outputs[1:]:
        match = re.fullmatch(r"sum\(([\w.]+)\) as (\w+)", output)
        assert match is not None, output
        named.add(match.group(2))
    assert named == set(SUMS)
    expected_groups = [CALLER, MODEL] + ([f"requestMetadata.{key}"] if key else [])
    assert [group.strip() for group in groups.split(",")] == expected_groups


def test_the_sums_read_counts_only() -> None:
    assert all(field.endswith("Count") for field in SUMS.values())


def test_an_application_key_that_is_not_a_key_is_refused_before_any_query(
    settings: Settings,
) -> None:
    logs = StubLogs()
    bad = settings.model_copy(update={"ai_request_metadata_key": "app) | fields @message"})
    with pytest.raises(errors.Misconfigured, match="METER_AI_REQUEST_METADATA_KEY"):
        logs_for(bad, logs).usage(ACCOUNT, REGION, DAY, NEXT_DAY)
    assert logs.started == []


# --- reading ----------------------------------------------------------------------------


def test_a_day_of_logs_becomes_one_row_per_caller_model_and_application(
    settings: Settings,
) -> None:
    keyed = settings.model_copy(update={"ai_request_metadata_key": "app"})
    logs = StubLogs(
        [
            {
                "status": "Complete",
                "results": [
                    result(
                        application="support",
                        input_tokens="1200",
                        output_tokens="300",
                        cache_read_tokens="5000",
                    ),
                    result(caller="arn:aws:iam::111122223333:user/ana", output_tokens="40"),
                ],
            }
        ]
    )
    rows = list(logs_for(keyed, logs).usage(ACCOUNT, REGION, DAY, NEXT_DAY))

    assert [(r.caller, r.application) for r in rows] == [
        (AGENT, "support"),
        ("arn:aws:iam::111122223333:user/ana", ""),
    ]
    first = rows[0]
    assert (first.provider, first.account_id, first.workspace, first.model) == (
        BEDROCK,
        "111122223333",
        REGION,
        MODEL_ID,
    )
    assert (first.usage_date, first.requests) == (DAY.date(), 12)
    assert (
        first.input_tokens,
        first.output_tokens,
        first.cache_read_tokens,
        first.cache_write_tokens,
    ) == (1200, 300, 5000, 0)
    assert (first.as_of, first.collected_at) == (NEXT_DAY, NOW)
    (started,) = logs.started
    assert started["logGroupName"] == GROUP
    assert (started["startTime"], started["endTime"]) == (
        int(DAY.timestamp()),
        int(NEXT_DAY.timestamp()) - 1,
    )


def test_every_page_of_a_large_answer_is_read(settings: Settings) -> None:
    logs = StubLogs(
        [
            {"status": "Complete", "results": [result()], "nextToken": "1"},
            {"results": [result(caller="b")], "nextToken": "2"},
            {"results": [result(caller="c")]},
        ]
    )
    rows = list(logs_for(settings, logs).usage(ACCOUNT, REGION, DAY, NEXT_DAY))
    assert [r.caller for r in rows] == [AGENT, "b", "c"]


def test_a_window_of_two_days_is_two_queries_and_two_dates(settings: Settings) -> None:
    logs = StubLogs([{"status": "Complete", "results": [result()]}])
    two = datetime(2026, 10, 13, tzinfo=UTC)
    rows = list(logs_for(settings, logs).usage(ACCOUNT, REGION, DAY, two))
    assert len(logs.started) == 2
    assert [r.usage_date for r in rows] == [DAY.date(), NEXT_DAY.date()]


def test_a_day_with_no_calls_is_no_rows(settings: Settings) -> None:
    assert list(logs_for(settings, StubLogs()).usage(ACCOUNT, REGION, DAY, NEXT_DAY)) == []


def test_it_waits_for_a_running_query(settings: Settings) -> None:
    logs = StubLogs(
        [{"status": "Complete", "results": [result()]}], statuses=["Scheduled", "Running"]
    )
    assert len(list(logs_for(settings, logs).usage(ACCOUNT, REGION, DAY, NEXT_DAY))) == 1
    assert len(logs.asked) == 3


# --- every failure typed ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("logging", "where"),
    [({}, "nowhere"), ({"loggingConfig": {"s3Config": {"bucketName": "b"}}}, "to S3 only")],
)
def test_no_cloudwatch_log_group_is_not_opted_in_with_the_step(
    settings: Settings, logging: dict[str, Any], where: str
) -> None:
    logs = StubLogs()
    with pytest.raises(errors.NotOptedIn, match=where) as raised:
        logs_for(settings, logs, config=logging).usage(ACCOUNT, REGION, DAY, NEXT_DAY)
    assert "InvocationLogGroupPattern" in raised.value.detail
    assert logs.started == []


def test_a_role_that_cannot_read_the_configuration_is_access_denied(settings: Settings) -> None:
    refused = denied("AccessDeniedException", "GetModelInvocationLoggingConfiguration")
    with pytest.raises(errors.AccessDenied):
        logs_for(settings, StubLogs(), config=refused).usage(ACCOUNT, REGION, DAY, NEXT_DAY)


@pytest.mark.parametrize(
    ("code", "cause", "says"),
    [
        ("AccessDeniedException", errors.AccessDenied, "InvocationLogGroupPattern"),
        ("LimitExceededException", errors.Throttled, "as many Logs Insights queries"),
        ("ResourceNotFoundException", errors.Misconfigured, "does not exist"),
        ("ThrottlingException", errors.Throttled, "ThrottlingException"),
        ("MalformedQueryException", errors.SchemaDrift, "MalformedQueryException"),
    ],
)
def test_a_query_that_cannot_start_fails_typed(
    settings: Settings, code: str, cause: type[errors.CollectionError], says: str
) -> None:
    source = logs_for(settings, StubLogs(start_error=denied(code)))
    with pytest.raises(cause, match=says):
        source.usage(ACCOUNT, REGION, DAY, NEXT_DAY)


@pytest.mark.parametrize("status", ["Failed", "Cancelled", "Timeout", "Unknown"])
def test_a_query_that_ends_badly_is_throttled_for_the_next_run(
    settings: Settings, status: str
) -> None:
    with pytest.raises(errors.Throttled, match=status):
        logs_for(settings, StubLogs(statuses=[status])).usage(ACCOUNT, REGION, DAY, NEXT_DAY)


def test_a_query_that_never_finishes_is_throttled_and_not_waited_on(settings: Settings) -> None:
    logs = StubLogs(statuses=["Running"] * 100)
    with pytest.raises(errors.Throttled, match="had not finished"):
        logs_for(settings, logs).usage(ACCOUNT, REGION, DAY, NEXT_DAY)
    assert len(logs.asked) < 100


@pytest.mark.parametrize(
    "broken",
    [
        cells(**{CALLER: AGENT, "requests": "1"}),
        cells(**{CALLER: AGENT, MODEL: MODEL_ID}),
        result(input_tokens="twelve"),
        result(input_tokens="-3"),
        result(input_tokens="1.5"),
    ],
)
def test_a_result_the_aggregate_does_not_explain_is_drift(settings: Settings, broken: Any) -> None:
    logs = StubLogs([{"status": "Complete", "results": [broken]}])
    with pytest.raises(errors.SchemaDrift):
        list(logs_for(settings, logs).usage(ACCOUNT, REGION, DAY, NEXT_DAY))
