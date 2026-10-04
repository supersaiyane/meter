"""The assistant's toolbox, against a transport that records what it was asked.

TASK-P7-006. The evaluation sets prove the toolbox against the real routes. These pin what
it refuses on its own: an argument, which it does not repeat back; a status other than
success; and a body that is not the route's envelope, which never reaches a model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pytest

from finops_api.toolbox import ApiToolbox
from finops_api.tools import TOOLS_BY_NAME
from finops_core.domain.insight import SCREEN_PATH, Provenance
from finops_query.insight import ToolUnavailableError

TOKEN = "a-session-token"
SLICE = {"name": "AmazonEC2", "effective_cost": "812.40", "billed_cost": "900.00", "line_items": 40}
META = {
    "as_of": "2026-07-31T00:00:00Z",
    "collected_at": "2026-08-01T06:00:00Z",
    "scope_coverage": {"visible": 2, "total": 5, "unit": "accounts"},
    "failures": [],
}


@dataclass
class Response:
    status_code: int
    body: Any

    def json(self) -> Any:
        return self.body


@dataclass
class Recording:
    response: Response
    asked: list[tuple[str, dict[str, str]]] = field(default_factory=list)

    def get(self, url: str, *, headers: dict[str, str], params: dict[str, Any]) -> Response:
        assert params == {}, "every tool takes no arguments, so none reach a route"
        self.asked.append((url, headers))
        return self.response


def toolbox(response: Response) -> tuple[ApiToolbox, Recording]:
    transport = Recording(response)
    return ApiToolbox(transport, TOKEN), transport


def test_a_call_reads_the_route_as_the_asker_and_types_what_it_returns() -> None:
    tools, transport = toolbox(Response(200, {"data": [SLICE], "meta": META}))

    output = tools.call("get_cost_by_service", {})

    ((url, headers),) = transport.asked
    assert url == TOOLS_BY_NAME["get_cost_by_service"].path
    assert headers == {"Authorization": f"Bearer {TOKEN}"}
    assert output.envelope["data"][0]["effective_cost"] == Decimal("812.40")
    assert '"effective_cost":"812.40"' in output.text
    assert (output.provenance, output.screen) == (Provenance.MEASURED, "/cost")


def test_an_argument_is_refused_and_not_repeated_back() -> None:
    tools, transport = toolbox(Response(200, {"data": [], "meta": META}))

    with pytest.raises(ToolUnavailableError) as refused:
        tools.call("get_cost_by_account", {"account_id": "fake-product-a"})

    assert "fake-product-a" not in str(refused.value)
    assert transport.asked == [], "nothing reached the API"


def test_a_refusal_from_the_api_is_not_data() -> None:
    tools, _ = toolbox(Response(403, {"detail": "out of scope"}))
    with pytest.raises(ToolUnavailableError, match="403"):
        tools.call("get_cost_by_service", {})


def test_a_success_without_its_envelope_is_not_data() -> None:
    tools, _ = toolbox(Response(200, {"data": [SLICE]}))
    with pytest.raises(ToolUnavailableError, match="not its envelope"):
        tools.call("get_cost_by_service", {})


def test_a_tool_that_does_not_exist_is_not_called() -> None:
    tools, transport = toolbox(Response(200, {}))
    with pytest.raises(ToolUnavailableError):
        tools.call("forecast_next_month", {})
    assert transport.asked == []


def test_every_tool_is_offered_with_no_arguments() -> None:
    tools, _ = toolbox(Response(200, {}))
    schemas = tools.schemas()
    assert {schema.name for schema in schemas} == set(TOOLS_BY_NAME)
    assert all(schema.parameters == {"type": "object", "properties": {}} for schema in schemas)


def test_every_screen_a_tool_names_is_one_a_refusal_will_link_to() -> None:
    """A refusal carries its tool's screen, and `Refusal` refuses anything looser than a plain
    path. A tool naming one that does not match fails here, not when somebody is refused."""
    named = {spec.name: spec.screen for spec in TOOLS_BY_NAME.values() if spec.screen}
    assert named, "no tool names a screen, so this proves nothing"
    assert {name: path for name, path in named.items() if not SCREEN_PATH.fullmatch(path)} == {}
