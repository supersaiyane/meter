"""The facade's contract with the API, which needs no database.

Split from the tests that need one, because a module level `pytestmark` applies
to the whole file and these would have been deselected alongside them. A test
nobody runs is a test that does not exist, and this file holds the drift gate.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from finops_api.main import p0_routers
from finops_api.schemas import Envelope
from finops_mcp.api import EnvelopeMissingError, MeterApi
from finops_mcp.server import MissingTokenError, build_server, token_from
from finops_mcp.tools import TOOLS, TOOLS_BY_NAME


def test_every_tool_declares_the_route_s_own_model() -> None:
    """The drift gate. A field added to the API without touching the tool table
    fails here rather than reaching a model as an undocumented key."""
    declared = {}
    for router in p0_routers():
        for route in router.routes:
            path = getattr(route, "path", None)
            model = getattr(route, "response_model", None)
            if path is not None and model is not None:
                declared[path] = model

    for spec in TOOLS:
        assert spec.path in declared, f"{spec.name} points at a route that does not exist"
        assert spec.envelope is declared[spec.path], (
            f"{spec.name} advertises a different model to the route it calls"
        )


def test_every_tool_reads_and_none_writes() -> None:
    """Constraint 6, read only in v1, and ADR-0007, no free form query tool."""
    methods = {}
    for router in p0_routers():
        for route in router.routes:
            path = getattr(route, "path", None)
            if path is not None:
                methods[path] = set(getattr(route, "methods", set()))

    for spec in TOOLS:
        assert methods[spec.path] == {"GET"}, f"{spec.name} calls a route that is not a read"


def test_the_advertised_schema_is_the_api_s_schema() -> None:
    """Generated, not written out again. The two would drift within a release."""
    spec = TOOLS_BY_NAME["list_accounts"]
    inner = spec.envelope.__pydantic_generic_metadata__["args"][0]
    assert spec.output_schema() == Envelope[inner].model_json_schema()


def test_the_server_registers_every_tool_and_not_zero() -> None:
    """A server that registered nothing would start and answer tools/list with
    an empty list, which reads as a model choosing not to use its tools."""
    server = build_server(MeterApi("http://unused.invalid"))
    registered = asyncio.run(server.list_tools())

    assert len(registered) == len(TOOLS) > 0
    assert {tool.name for tool in registered} == {spec.name for spec in TOOLS}


def test_a_call_with_no_token_refuses_rather_than_answering() -> None:
    """There is no service credential to fall back to, deliberately."""
    with pytest.raises(MissingTokenError):
        token_from(None)
    with pytest.raises(MissingTokenError):
        token_from({"x-other": "value"})
    with pytest.raises(MissingTokenError):
        token_from({"Authorization": "Basic abc"})


def test_the_header_name_is_read_case_insensitively() -> None:
    """Whatever proxy sits in front decides the case, not us."""
    assert token_from({"authorization": "Bearer abc"}) == "abc"
    assert token_from({"AUTHORIZATION": "Bearer abc"}) == "abc"


class Bare:
    """A transport answering 200 with something that is not the envelope."""

    status_code = 200

    def get(
        self,
        url: str,  # noqa: ARG002
        *,
        headers: dict[str, str],  # noqa: ARG002
        params: dict[str, Any],  # noqa: ARG002
    ) -> Bare:
        return self

    def json(self) -> dict[str, Any]:
        return {"data": [1, 2, 3]}


def test_a_two_hundred_without_meta_is_not_treated_as_data() -> None:
    """Either a route forgot the envelope or that is not the API. Both are
    reasons to refuse, not reasons to hand it to a model."""
    with pytest.raises(EnvelopeMissingError):
        MeterApi("http://unused.invalid", transport=Bare()).get("/api/v1/accounts", "t")


def test_both_container_commands_name_something_that_exists() -> None:
    """A CMD naming a symbol that is not there is a container that never starts,
    and nothing else in the build would notice.

    This test was written after finding exactly that: the image named
    `finops_api.main:app`, which had never existed.
    """
    import re
    from importlib import import_module
    from pathlib import Path

    dockerfile = Path(__file__).resolve().parents[2] / "docker" / "Dockerfile.api"
    targets = re.findall(r"(finops_\w+(?:\.\w+)*):(\w+)", dockerfile.read_text(encoding="utf-8"))

    assert len(targets) >= 2, "expected the API and the MCP server to both be named"
    for module_name, attribute in targets:
        module = import_module(module_name)
        assert hasattr(module, attribute), f"{module_name}:{attribute} does not exist"


class Refusing:
    """A transport answering with a body that is not JSON."""

    status_code = 503
    text = "upstream unavailable"

    def get(self, url: str, **kwargs: Any) -> Refusing:  # noqa: ARG002
        return self

    def json(self) -> dict[str, Any]:
        raise ValueError("not json")


def test_a_failure_reports_the_api_s_own_words() -> None:
    """Never an exception string built here. The caller needs to know what the
    API said, not what this module thought about it."""
    from finops_mcp.api import ApiError

    with pytest.raises(ApiError) as raised:
        MeterApi("http://unused.invalid", transport=Refusing()).get("/api/v1/accounts", "t")

    assert raised.value.status == 503
    assert "upstream unavailable" in raised.value.detail


def test_the_api_location_has_no_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """A localhost default would work in development and point a deployed facade
    at itself. ADR-0017: configuration has no defaults in code."""
    from finops_mcp.server import api_base_url

    monkeypatch.delenv("METER_API_BASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        api_base_url()

    monkeypatch.setenv("METER_API_BASE_URL", "http://api:8000")
    assert api_base_url() == "http://api:8000"
