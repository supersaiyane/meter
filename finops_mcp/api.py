"""The only way this package reaches Meter: over the network, as a caller.

Constraint 8 and ADR-0009. The MCP server calls the HTTP API with the caller's
own token rather than importing the service layer, because two implementations
of an authorization rule is how an authorization bug is created. Everything a
tool is allowed to see is therefore decided by the same scope dependency and the
same repository guard that decide it for the web application, and neither can be
bypassed by adding a tool.

The client refuses a response that carries no `meta`. A response without the
envelope is either a route that forgot it or something that is not the API, and
handing either to a model as if it were data is how a partial total gets
presented as an organization total.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

#: Sent as `Authorization: Bearer <token>`, the same header the API's own
#: dependency reads. The facade adds no credential of its own, which is what
#: makes "the caller's token" true rather than aspirational.
BEARER = "Bearer "

#: How long a tool call waits. Short on purpose: a model waiting on a hung
#: request produces a worse answer than a model told the call failed.
DEFAULT_TIMEOUT_SECONDS = 10.0


class ApiError(RuntimeError):
    """The API refused or could not answer. Carries the status for the caller."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


class EnvelopeMissingError(RuntimeError):
    """A 200 with no `meta`. Not the contract, so not treated as data."""


class Transport(Protocol):
    """What the client needs from an HTTP library, and nothing more.

    Narrowed to one method so a test can substitute the API's own TestClient,
    which exercises the real routes, the real scope dependency and the real
    repository guard rather than a stub that agrees with the tool.
    """

    def get(self, url: str, *, headers: dict[str, str], params: dict[str, Any]) -> Any: ...


class MeterApi:
    """A caller of the Meter HTTP API. Holds no scope and no credential."""

    def __init__(
        self,
        base_url: str,
        transport: Transport | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport or httpx.Client(base_url=self._base_url, timeout=timeout)

    def get(self, path: str, token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """One GET, returning the envelope exactly as the API sent it.

        Nothing is unwrapped and nothing is reshaped. A tool that returned only
        `data` would strip `scope_coverage` and `as_of`, and a model with no
        coverage figure will state a partial total as a complete one,
        confidently. See the threat model, row I.
        """
        response = self._transport.get(
            path,
            headers={"Authorization": f"{BEARER}{token}"},
            params=params or {},
        )
        if response.status_code != 200:
            raise ApiError(response.status_code, _detail_of(response))
        payload = response.json()
        if not isinstance(payload, dict) or "meta" not in payload:
            raise EnvelopeMissingError(f"{path} answered 200 with no meta envelope")
        return payload


def _detail_of(response: Any) -> str:
    """The API's own words, never an exception string built here."""
    try:
        body = response.json()
    except Exception:
        return str(response.text)[:200]
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return str(body)[:200]
