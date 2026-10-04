"""The assistant's tools: the API's own routes, called with the asker's own token.

TASK-P7-006, P7 spec section 5.1, constraint 8 and ADR-0009. Every call here is an HTTP
GET of a route a screen reads, carrying the bearer token of the person who asked, so it
passes the same scope dependency, the same repository guard and writes the same audit row
as the screen would. There is no second implementation of an authorization rule here, and
no repository is imported: this module could not widen what an asker sees if it tried.

**The transport is anything that can GET a path.** The application's own test client in
tests, which exercises the real routes, and an HTTP client in production. The envelope is
validated against the route's own model before anything reads it, so a response that is
not the contract never reaches a model as if it were data.

**Every tool takes no arguments.** A model that passes some anyway is told the call was
not made, and is not told back what it passed, because the argument it tried to slip in
may be the account an attack was reaching for.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from finops_api.deps import AUTHORIZATION, BEARER
from finops_api.tools import TOOLS, ToolSpec
from finops_core.ports.llm import ToolSchema
from finops_query.insight import ToolOutput, ToolUnavailableError


class Transport(Protocol):
    """What the toolbox needs of an HTTP client, and nothing more."""

    def get(self, url: str, *, headers: dict[str, str], params: dict[str, Any]) -> Any: ...


class ApiToolbox:
    """The asker's tools, each one a route called with the asker's token."""

    def __init__(
        self, transport: Transport, token: str, tools: tuple[ToolSpec, ...] = TOOLS
    ) -> None:
        self._transport = transport
        self._token = token
        self._tools = {spec.name: spec for spec in tools}

    def schemas(self) -> tuple[ToolSchema, ...]:
        return tuple(spec.schema() for spec in self._tools.values())

    def call(self, name: str, arguments: Mapping[str, Any]) -> ToolOutput:
        """One route, read as the asker.

        Raises:
            ToolUnavailableError: The tool does not exist, was passed arguments, was refused by
                the API, or answered with something that is not its envelope.
        """
        spec = self._tools.get(name)
        if spec is None:
            raise ToolUnavailableError("there is no tool by that name")
        if arguments:
            raise ToolUnavailableError(f"{name} takes no arguments, so it was not called")
        response = self._transport.get(
            spec.path, headers={AUTHORIZATION: f"{BEARER}{self._token}"}, params={}
        )
        if response.status_code != 200:
            raise ToolUnavailableError(
                f"{name} was refused by the API, status {response.status_code}"
            )
        try:
            envelope = spec.envelope.model_validate(response.json())
        except ValueError:
            raise ToolUnavailableError(
                f"{name} answered with something that is not its envelope, so none of it is used"
            ) from None
        return ToolOutput(
            envelope=envelope.model_dump(mode="python"),
            text=envelope.model_dump_json(),
            provenance=spec.provenance,
            screen=spec.screen,
        )
