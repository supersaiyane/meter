"""The AI providers' shared report client, through a mock transport. TASK-P13-004, FEAT-083.

Every failure typed, every page followed, and the key in no detail: P13 plan rule 2. A provider's
message about a refused key can echo the key, so the test that matters most is that nothing the
client raises carries it, in any form.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from finops_core import errors
from finops_providers.ai_reports import RETRIES, ReportApi, redact

KEY = "sk-admin-test-not-a-real-key-000000"


def api(handler: Callable[[httpx.Request], httpx.Response], waits: list[float]) -> ReportApi:
    return ReportApi(
        base_url="https://provider.invalid",
        headers=lambda: {"Authorization": f"Bearer {KEY}"},
        scope_key="openai:org-x",
        collector="openai_usage",
        transport=httpx.MockTransport(handler),
        sleeper=waits.append,
    )


def page(data: list[Any], following: str | None = None) -> httpx.Response:
    body: dict[str, Any] = {"object": "page", "data": data, "has_more": following is not None}
    if following:
        body["next_page"] = following
    return httpx.Response(200, json=body)


def test_every_page_is_followed_and_the_key_is_sent() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        cursor = request.url.params.get("page")
        return {None: page([1, 2], "p2"), "p2": page([3], "p3"), "p3": page([4])}[cursor]

    assert list(api(handler, []).pages("/v1/r", {"limit": 2})) == [1, 2, 3, 4]
    assert [request.url.params.get("page") for request in seen] == [None, "p2", "p3"]
    assert all(request.headers["authorization"] == f"Bearer {KEY}" for request in seen)
    assert all(request.url.params["limit"] == "2" for request in seen)


def test_a_slow_down_is_waited_for_as_the_provider_says_then_answered() -> None:
    answers = iter([httpx.Response(429, headers={"retry-after": "7"}), page([1])])
    waits: list[float] = []
    assert list(api(lambda _r: next(answers), waits).pages("/v1/r", {})) == [1]
    assert waits == [7.0]


def test_a_provider_that_keeps_saying_slow_down_is_throttled() -> None:
    waits: list[float] = []
    with pytest.raises(errors.Throttled, match="429"):
        api(lambda _r: httpx.Response(429), waits).get("/v1/r", {})
    assert waits == [1.0, 2.0, 4.0]
    assert len(waits) == RETRIES


def test_a_wait_the_provider_asks_for_is_capped() -> None:
    answers = iter([httpx.Response(429, headers={"retry-after": "3600"}), page([])])
    waits: list[float] = []
    list(api(lambda _r: next(answers), waits).pages("/v1/r", {}))
    assert waits == [60.0]


@pytest.mark.parametrize("status", [500, 502, 503])
def test_a_provider_failing_on_its_side_is_unreachable_after_the_retries(status: int) -> None:
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(status, text="upstream fell over")

    with pytest.raises(errors.Unreachable, match=str(status)):
        api(handler, []).get("/v1/r", {})
    assert len(calls) == RETRIES + 1


def test_a_timeout_is_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(errors.Unreachable, match="timed out"):
        api(handler, []).get("/v1/r", {})


@pytest.mark.parametrize(
    ("status", "body", "cause"),
    [
        (401, {"error": {"message": f"Incorrect API key provided: {KEY}"}}, errors.AccessDenied),
        (
            403,
            {"error": {"message": f"key {KEY[:12]}...{KEY[-4:]} lacks scope"}},
            errors.AccessDenied,
        ),
        (404, {"error": {"message": f"not found for {KEY}"}}, errors.NotOptedIn),
        (400, {"error": {"message": f"bad request with {KEY}"}}, errors.SchemaDrift),
        (500, {"error": {"message": f"oops {KEY}"}}, errors.Unreachable),
    ],
)
def test_no_failure_carries_the_key_in_any_form(
    status: int, body: dict[str, Any], cause: type[errors.CollectionError]
) -> None:
    with pytest.raises(cause) as raised:
        api(lambda _r: httpx.Response(status, json=body), []).get("/v1/r", {})
    said = f"{raised.value} {raised.value.detail}"
    assert KEY not in said
    assert KEY[:12] not in said and "sk-" not in said
    if cause is errors.AccessDenied:
        # Nothing the provider said about a refused key is kept at all.
        assert json.dumps(body)[:20] not in said
        assert "admin key was refused" in said


@pytest.mark.parametrize(
    ("answer", "says"),
    [
        (httpx.Response(200, text="<html>not json</html>"), "not JSON"),
        (httpx.Response(200, json={"object": "page", "has_more": False}), "without a data list"),
        (httpx.Response(200, json={"data": [], "has_more": True}), "named no next page"),
    ],
)
def test_an_answer_the_mapping_cannot_read_is_drift(answer: httpx.Response, says: str) -> None:
    with pytest.raises(errors.SchemaDrift, match=says):
        list(api(lambda _r: answer, []).pages("/v1/r", {}))


def test_redact_removes_the_key_and_anything_shaped_like_one() -> None:
    said = redact(f"refused {KEY} and sk-proj-AbC***xyz and {'x' * 40}", KEY)
    assert KEY not in said and "sk-proj" not in said and "x" * 40 not in said
    assert len(redact("y " * 400)) <= 300


def test_the_key_is_read_only_when_a_request_is_made() -> None:
    reads: list[int] = []

    def headers() -> dict[str, str]:
        reads.append(1)
        return {"x-api-key": KEY}

    client = ReportApi(
        base_url="https://provider.invalid",
        headers=headers,
        scope_key="s",
        collector="c",
        transport=httpx.MockTransport(lambda _r: page([])),
    )
    assert reads == []
    list(client.pages("/v1/r", {}))
    list(client.pages("/v1/r", {}))
    assert reads == [1]
