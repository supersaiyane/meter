"""OpenAI's cost and usage reports, mapped, against recorded shapes. TASK-P13-004, FEAT-083.

The shapes are the ones OpenAI documents for its organization API, read on 2026-10-12; no call
has reached OpenAI, ISS-285. Each test is one rule of the mapping: a line item names its model and
token type or names none, cached input is not counted twice, a project is the sub account, and a
result the mapping cannot read is drift and never a zero.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest

from finops_core import errors
from finops_core.domain.ai import CACHE_READ, INPUT, OUTPUT, ProviderAccount
from finops_providers.openai.reports import (
    COMPLETIONS,
    COSTS,
    PROVIDER_NAME,
    SERVICE_NAME,
    SOURCE,
    OpenAiReports,
)

ACCOUNT = ProviderAccount(
    provider="openai",
    organization_id="org-test",
    name="Test organization",
    key_secret_name="meter/test/ai/openai",
)
START = datetime(2026, 10, 1, tzinfo=UTC)
END = datetime(2026, 10, 3, tzinfo=UTC)
DAY_ONE = int(START.timestamp())
DAY_TWO = DAY_ONE + 86400
NOW = datetime(2026, 10, 3, 6, tzinfo=UTC)


def bucket(start: int, results: list[dict[str, Any]]) -> dict[str, Any]:
    return {"object": "bucket", "start_time": start, "end_time": start + 86400, "results": results}


def cost(line: str | None, value: Any, project: str | None = "proj-a") -> dict[str, Any]:
    return {
        "object": "organization.costs.result",
        "amount": {"value": value, "currency": "usd"},
        "line_item": line,
        "project_id": project,
    }


def reports(answers: dict[str, list[dict[str, Any]]], seen: list[httpx.Request]) -> OpenAiReports:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"object": "page", "data": answers[request.url.path], "has_more": False}
        )

    return OpenAiReports(
        uuid4(),
        uuid4(),
        key=lambda: "test-key",
        transport=httpx.MockTransport(handler),
        clock=lambda: NOW,
    )


def test_costs_become_focus_rows_from_openai_with_their_model_and_token_type() -> None:
    seen: list[httpx.Request] = []
    answers = {
        COSTS: [
            bucket(
                DAY_ONE,
                [
                    cost("gpt-4o-2024-08-06, input", 1.25),
                    cost("gpt-4o-2024-08-06, cached input", "0.5"),
                    cost("gpt-4o-2024-08-06, output", 3),
                ],
            ),
            bucket(DAY_TWO, [cost("web search tool calls", 0.2, project=None)]),
        ]
    }
    rows = list(reports(answers, seen).costs(ACCOUNT, START, END))

    assert [(r.x_ai_model, r.x_ai_token_type) for r in rows] == [
        ("gpt-4o-2024-08-06", INPUT),
        ("gpt-4o-2024-08-06", CACHE_READ),
        ("gpt-4o-2024-08-06", OUTPUT),
        (None, None),
    ]
    first = rows[0]
    assert (first.ingest_source, first.provider_name, first.service_name) == (
        SOURCE,
        PROVIDER_NAME,
        SERVICE_NAME,
    )
    assert (first.billing_account_id, first.sub_account_id) == ("org-test", "proj-a")
    assert (first.billed_cost, first.effective_cost, first.billing_currency) == (
        Decimal("1.25"),
        Decimal("1.25"),
        "USD",
    )
    assert (first.billing_period_start, first.billing_period_end) == (
        date(2026, 10, 1),
        date(2026, 11, 1),
    )
    assert (first.charge_period_start, first.charge_period_end) == (
        START,
        datetime(2026, 10, 2, tzinfo=UTC),
    )
    assert first.as_of == first.charge_period_end and first.collected_at == NOW
    assert rows[3].sub_account_id is None
    assert len({row.source_fingerprint for row in rows}) == 4
    (request,) = seen
    assert request.url.params.get_list("group_by") == ["line_item", "project_id"]
    assert request.url.params["bucket_width"] == "1d"
    assert (int(request.url.params["start_time"]), int(request.url.params["end_time"])) == (
        DAY_ONE,
        int(END.timestamp()),
    )
    assert request.headers["authorization"] == "Bearer test-key"


def test_usage_counts_cached_input_once_and_names_project_key_and_user() -> None:
    seen: list[httpx.Request] = []
    result = {
        "object": "organization.usage.completions.result",
        "input_tokens": 1000,
        "input_cached_tokens": 400,
        "output_tokens": 250,
        "num_model_requests": 12,
        "project_id": "proj-a",
        "api_key_id": "key-1",
        "user_id": "user-9",
        "model": "gpt-4o-mini",
    }
    rows = list(
        reports({COMPLETIONS: [bucket(DAY_ONE, [result])]}, seen).usage(ACCOUNT, START, END)
    )

    (row,) = rows
    assert (row.provider, row.account_id, row.usage_date, row.model) == (
        SOURCE,
        "org-test",
        date(2026, 10, 1),
        "gpt-4o-mini",
    )
    assert (row.workspace, row.api_key_id, row.caller) == ("proj-a", "key-1", "user-9")
    assert (row.input_tokens, row.cache_read_tokens, row.output_tokens, row.requests) == (
        600,
        400,
        250,
        12,
    )
    assert seen[0].url.params.get_list("group_by") == [
        "model",
        "project_id",
        "api_key_id",
        "user_id",
    ]


def test_a_usage_result_without_its_groups_reads_as_unreported_not_as_someone() -> None:
    result = {"input_tokens": 5, "output_tokens": 1, "num_model_requests": 1, "model": "m"}
    (row,) = reports({COMPLETIONS: [bucket(DAY_ONE, [result])]}, []).usage(ACCOUNT, START, END)
    assert (row.workspace, row.api_key_id, row.caller) == ("", "", "")


@pytest.mark.parametrize(
    ("path", "broken"),
    [
        (COSTS, [bucket(DAY_ONE, [cost("gpt, input", "lots")])]),
        (COSTS, [bucket(DAY_ONE, [cost("gpt, input", None)])]),
        (COSTS, [{"results": []}]),
        (COSTS, [{"start_time": DAY_ONE, "end_time": DAY_TWO}]),
        (COMPLETIONS, [bucket(DAY_ONE, [{"input_tokens": 5}])]),
        (COMPLETIONS, [bucket(DAY_ONE, [{"model": "m", "input_tokens": -1}])]),
        (COMPLETIONS, [bucket(DAY_ONE, [{"model": "m", "input_tokens": "5"}])]),
    ],
)
def test_a_report_the_mapping_cannot_read_is_drift(path: str, broken: list[Any]) -> None:
    source = reports({COSTS: broken, COMPLETIONS: broken}, [])
    read = source.costs if path == COSTS else source.usage
    with pytest.raises(errors.SchemaDrift):
        list(read(ACCOUNT, START, END))


def test_a_refused_key_is_access_denied_for_this_organization() -> None:
    source = OpenAiReports(
        uuid4(),
        uuid4(),
        key=lambda: "test-key",
        transport=httpx.MockTransport(lambda _r: httpx.Response(401)),
    )
    with pytest.raises(errors.AccessDenied) as raised:
        list(source.costs(ACCOUNT, START, END))
    assert raised.value.scope_key == "openai:org-test"
