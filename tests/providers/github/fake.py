"""GitHub's REST API as a mock transport, from recorded shapes. TASK-P15-002.

Each body is trimmed from the example GitHub's REST reference publishes for that endpoint, API
version 2022-11-28, to the fields Meter reads and a few beside them, so a test reads like the
answer it stands in for. Spec section 9: nothing here has been seen from a real installation yet.
A route not set answers 404 as GitHub does, so a call a test did not expect fails typed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from functools import cache
from typing import Any

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from finops_providers.github.app import GitHubApp
from finops_providers.github.code_host import COLLECTOR, GitHubCodeHost

REPOSITORY = "acme/infra"
REPO = f"/repos/{REPOSITORY}"
INSTALLATION = 4242
APP_ID = "1001"
#: An installation token in GitHub's shape. Not a real one.
TOKEN = "ghs_testTokenNotRealAAAAAAAAAAAAAAAAAAAAAA"
NOW = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)
BASE_SHA = "a" * 40
BASE_TREE = "b" * 40


@cache
def private_key() -> rsa.RSAPrivateKey:
    """One key per test run: generating one takes long enough to notice."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def private_key_pem() -> str:
    return (
        private_key()
        .private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        .decode()
    )


def not_found() -> httpx.Response:
    return httpx.Response(
        404,
        json={
            "message": "Not Found",
            "documentation_url": "https://docs.github.com/rest",
            "status": "404",
        },
    )


class FakeGitHub:
    """Answers by method and path, and records every request it was sent."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self._routes: dict[tuple[str, str], Callable[[httpx.Request], httpx.Response]] = {}
        self.on(
            "GET",
            f"{REPO}/installation",
            200,
            {"id": INSTALLATION, "app_id": int(APP_ID), "account": {"login": "acme"}},
        )
        self.on(
            "POST",
            f"/app/installations/{INSTALLATION}/access_tokens",
            201,
            {
                "token": TOKEN,
                "expires_at": "2026-10-15T11:00:00Z",
                "permissions": {"contents": "write", "pull_requests": "write"},
                "repository_selection": "selected",
            },
        )

    def on(
        self,
        method: str,
        path: str,
        status: int = 200,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Answer `method path` with `status` and `body`, freshly built for each request."""

        def answer(_request: httpx.Request) -> httpx.Response:
            if isinstance(body, str):
                return httpx.Response(status, text=body, headers=headers)
            return httpx.Response(status, json=body, headers=headers)

        self._routes[(method, path)] = answer

    def answer(
        self, method: str, path: str, handler: Callable[[httpx.Request], httpx.Response]
    ) -> None:
        self._routes[(method, path)] = handler

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self._routes.get((request.method, request.url.path))
        return route(request) if route is not None else not_found()

    def asked(self, method: str, path: str) -> list[httpx.Request]:
        return [one for one in self.requests if (one.method, one.url.path) == (method, path)]

    def sent(self, method: str, path: str) -> Any:
        """The JSON body of the one request sent to `method path`."""
        (request,) = self.asked(method, path)
        return json.loads(request.content)

    def app(self, key: Callable[[], str] = private_key_pem) -> GitHubApp:
        return GitHubApp(
            app_id=APP_ID,
            private_key=key,
            collector=COLLECTOR,
            clock=lambda: NOW,
            transport=httpx.MockTransport(self.handle),
            base_url="https://github.invalid",
        )

    def host(self) -> GitHubCodeHost:
        return GitHubCodeHost(self.app())


def pull(number: int = 7, **fields: Any) -> dict[str, Any]:
    """A pull request as GET /repos/{owner}/{repo}/pulls/{number} answers, trimmed."""
    body: dict[str, Any] = {
        "number": number,
        "html_url": f"https://github.com/{REPOSITORY}/pull/{number}",
        "state": "open",
        "title": "Remove unattached volume vol-0abc",
        "merged": False,
        "merged_by": None,
        "mergeable": True,
        "mergeable_state": "clean",
        "draft": False,
        "head": {"ref": "meter/remediation-rec-41", "sha": "c" * 40},
        "base": {"ref": "main", "sha": BASE_SHA},
    }
    body.update(fields)
    return body
