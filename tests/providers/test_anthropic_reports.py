"""Anthropic's cost and usage reports, mapped, against recorded shapes. TASK-P13-005, FEAT-083.

The shapes are the ones Anthropic documents for its Admin API, read on 2026-10-12; no call has
reached Anthropic, ISS-285. The two rules that would be wrong quietly each have a test: an amount
is in cents and is divided by a hundred, and the usage report counts no requests, so a row says
None rather than zero.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest

from finops_core import errors
from finops_core.domain.ai import CACHE_READ, CACHE_WRITE, INPUT, OUTPUT, ProviderAccount
from finops_providers.anthropic.reports import (
    API_VERSION,
    COSTS,
    MESSAGES,
    PROVIDER_NAME,
    SERVICE_NAME,
    SOURCE,
    AnthropicReports,
)

ACCOUNT = ProviderAccount(
    provider="anthropic",
    organization_id="org-test",
    name="Test organization",
    key_secret_name="meter/test/ai/anthropic",
)
START = datetime(2026, 10, 1, tzinfo=UTC)
END = datetime(2026, 10, 3, tzinfo=UTC)
NOW = datetime(2026, 10, 3, 6, tzinfo=UTC)


def bucket(day: int, results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "starting_at": f"2026-10-0{day}T00:00:00Z",
        "ending_at": f"2026-10-0{day + 1}T00:00:00Z",
        "results": results,
    }


def cost(
    token_type: str | None, amount: Any, model: str | None = "claude-sonnet-4"
) -> dict[str, Any]:
    return {
        "currency": "USD",
        "amount": amount,
        "workspace_id": "wrkspc_a",
        "description": f"{model} Usage - {token_type}",
        "cost_type": "tokens" if token_type else "web_search",
        "model": model,
        "token_type": token_type,
    }


def reports(answers: dict[str, list[Any]], seen: list[httpx.Request]) -> AnthropicReports:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": answers[request.url.path], "has_more": False})

    return AnthropicReports(
        uuid4(),
        uuid4(),
        key=lambda: "test-key",
        transport=httpx.MockTransport(handler),
        clock=lambda: NOW,
    )


def test_costs_are_cents_become_dollars_and_name_their_model_and_token_type() -> None:
    seen: list[httpx.Request] = []
    answers = {
        COSTS: [
            bucket(
                1,
                [
                    cost("uncached_input_tokens", "1234.5"),
                    cost("output_tokens", "300"),
                    cost("cache_read_input_tokens", "12"),
                    cost("cache_creation.ephemeral_1h_input_tokens", "7"),
                    cost(None, "50", model=None),
                ],
            )
        ]
    }
    rows = list(reports(answers, seen).costs(ACCOUNT, START, END))

    assert [r.effective_cost for r in rows] == [
        Decimal("12.345"),
        Decimal("3"),
        Decimal("0.12"),
        Decimal("0.07"),
        Decimal("0.5"),
    ]
    assert [(r.x_ai_model, r.x_ai_token_type) for r in rows] == [
        ("claude-sonnet-4", INPUT),
        ("claude-sonnet-4", OUTPUT),
        ("claude-sonnet-4", CACHE_READ),
        ("claude-sonnet-4", CACHE_WRITE),
        (None, None),
    ]
    first = rows[0]
    assert (first.ingest_source, first.provider_name, first.service_name) == (
        SOURCE,
        PROVIDER_NAME,
        SERVICE_NAME,
    )
    assert (first.billing_account_id, first.sub_account_id, first.billing_currency) == (
        "org-test",
        "wrkspc_a",
        "USD",
    )
    assert first.billing_period_start == date(2026, 10, 1)
    assert (first.charge_period_start, first.charge_period_end) == (
        START,
        datetime(2026, 10, 2, tzinfo=UTC),
    )
    (request,) = seen
    assert request.url.params.get_list("group_by[]") == ["workspace_id", "description"]
    assert request.url.params["starting_at"] == "2026-10-01T00:00:00Z"
    assert request.url.params["ending_at"] == "2026-10-03T00:00:00Z"
    assert request.headers["x-api-key"] == "test-key"
    assert request.headers["anthropic-version"] == API_VERSION


def test_usage_counts_every_kind_of_token_and_no_requests() -> None:
    seen: list[httpx.Request] = []
    result = {
        "uncached_input_tokens": 900,
        "cache_creation": {"ephemeral_5m_input_tokens": 30, "ephemeral_1h_input_tokens": 20},
        "cache_read_input_tokens": 400,
        "output_tokens": 120,
        "server_tool_use": {"web_search_requests": 2},
        "api_key_id": "apikey_1",
        "workspace_id": None,
        "model": "claude-haiku-4",
        "service_tier": "standard",
    }
    (row,) = reports({MESSAGES: [bucket(1, [result])]}, seen).usage(ACCOUNT, START, END)

    assert (row.provider, row.account_id, row.usage_date, row.model) == (
        SOURCE,
        "org-test",
        date(2026, 10, 1),
        "claude-haiku-4",
    )
    assert (row.workspace, row.api_key_id, row.caller) == ("", "apikey_1", "")
    assert (
        row.input_tokens,
        row.output_tokens,
        row.cache_read_tokens,
        row.cache_write_tokens,
    ) == (900, 120, 400, 50)
    assert row.requests is None
    assert seen[0].url.params.get_list("group_by[]") == ["model", "workspace_id", "api_key_id"]
    assert seen[0].url.params["bucket_width"] == "1d"


NAIVE = {"starting_at": "2026-10-01T00:00:00", "ending_at": "2026-10-02T00:00:00", "results": []}


@pytest.mark.parametrize(
    ("path", "broken"),
    [
        (COSTS, [bucket(1, [cost("output_tokens", "lots")])]),
        (COSTS, [bucket(1, [cost("output_tokens", "NaN")])]),
        (COSTS, [{"starting_at": "yesterday", "ending_at": "today", "results": []}]),
        (COSTS, [NAIVE]),
        (MESSAGES, [bucket(1, [{"output_tokens": 5}])]),
        (MESSAGES, [bucket(1, [{"model": "m", "cache_creation": 3}])]),
        (MESSAGES, [bucket(1, [{"model": "m", "output_tokens": -1}])]),
    ],
)
def test_a_report_the_mapping_cannot_read_is_drift(path: str, broken: list[Any]) -> None:
    source = reports({COSTS: broken, MESSAGES: broken}, [])
    read = source.costs if path == COSTS else source.usage
    with pytest.raises(errors.SchemaDrift):
        list(read(ACCOUNT, START, END))


def test_a_refused_key_is_access_denied_for_this_organization() -> None:
    source = AnthropicReports(
        uuid4(),
        uuid4(),
        key=lambda: "test-key",
        transport=httpx.MockTransport(lambda _r: httpx.Response(403)),
    )
    with pytest.raises(errors.AccessDenied) as raised:
        list(source.usage(ACCOUNT, START, END))
    assert raised.value.scope_key == "anthropic:org-test"
