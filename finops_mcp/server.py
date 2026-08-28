"""The MCP server, which is a facade and never a second implementation.

It ships inside the `meter-api` image and is selected by the container command
rather than built as a fourth image. A separate image would duplicate the whole
dependency tree for one module and would need its own build, scan, signature and
repository, which is how a deployable ends up outside the security gates.
A001-F08 and ADR-0009.

Every tool is registered from the same `TOOLS` table, so adding a tool means
adding a row rather than writing a handler. A handler written by hand is a
handler that can forget the envelope, forget the token, or reach somewhere it
should not.

The token comes from the caller's own request headers and nothing else. There is
no service credential here to fall back to, which is deliberate: a facade with
its own credential is an authorization bypass with a nice interface.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

from mcp.server.mcpserver import Context, MCPServer

from finops_mcp.api import BEARER, MeterApi
from finops_mcp.tools import TOOLS, ToolSpec

SERVER_NAME = "meter"

#: Read case insensitively, because a header name's case is decided by whatever
#: proxy sat in front of us.
AUTHORIZATION = "authorization"


class MissingTokenError(RuntimeError):
    """No caller token. The tool refuses rather than answering as somebody else."""


def token_from(headers: Mapping[str, str] | None) -> str:
    """The caller's bearer token, or an error.

    There is no default and no fallback. An unauthenticated tool call has no
    scope, and the only safe answer to "whose data is this" when nobody said is
    to not answer.
    """
    if not headers:
        raise MissingTokenError("no request headers, so no caller to act as")
    for name, value in headers.items():
        if name.lower() != AUTHORIZATION:
            continue
        if not value.startswith(BEARER):
            raise MissingTokenError("authorization header is not a bearer token")
        return value.removeprefix(BEARER)
    raise MissingTokenError("no authorization header on the tool call")


def make_handler(spec: ToolSpec, api: MeterApi) -> Callable[[Context], dict[str, Any]]:
    """Bind one row of the tool table to one handler.

    The envelope is returned exactly as the API sent it. Unwrapping it to `data`
    would read as tidier and would remove `scope_coverage` and `as_of` from the
    model's view, which is the difference between "23 accounts, 40 percent of the
    organization" and "23 accounts".
    """

    def handler(ctx: Context) -> dict[str, Any]:
        return api.get(spec.path, token_from(getattr(ctx, "headers", None)))

    handler.__name__ = spec.name
    handler.__doc__ = spec.description
    # The declared return type is the API's own envelope model, so the schema the
    # SDK advertises is generated from it rather than described again here. Left
    # as `dict` the SDK would advertise "an object, any keys", which is true and
    # useless, and would let a field change on the API without changing anything
    # a model can see.
    handler.__annotations__["return"] = spec.envelope
    return handler


def build_server(api: MeterApi, server: MCPServer | None = None) -> MCPServer:
    """Register every tool in the table. Returns the server for a caller to run.

    Registration is counted against the table by a test. A server that silently
    registered nothing would start, answer `tools/list` with an empty list, and
    look like a model that chose not to use its tools.
    """
    built = server or MCPServer(name=SERVER_NAME)
    for spec in TOOLS:
        built.add_tool(
            make_handler(spec, api),
            name=spec.name,
            description=spec.description,
        )
    return built


def api_base_url() -> str:
    """Where the API is, from the environment, with no default.

    A default of localhost would work in development and point a deployed facade
    at itself. See ADR-0017: configuration has no defaults in code.
    """
    url = os.environ.get("METER_API_BASE_URL")
    if not url:
        raise RuntimeError("METER_API_BASE_URL is not set")
    return url


def bootstrap() -> Any:
    """The ASGI application the container serves.

    A factory, and served by the same uvicorn as the API, so the two processes
    differ by their command and by nothing else. That is what makes "a second
    process in the same image" true rather than a claim: same base image, same
    scan, same signature, same repository. A fourth image would need its own of
    each, which is how a deployable ends up outside the security gates. A001-F08.
    """
    return build_server(MeterApi(api_base_url())).streamable_http_app()
