"""A GitHub App's credentials and GitHub's REST API, every failure typed. P15, FEAT-091, OPEN-13.

TASK-P15-002, spec section 5.1. The organization installs Meter's GitHub App on the repositories
that hold its Terraform, and the app's private key is a secret under `meter/<env>/codehost/`, read
by the worker when a request is about to be made; only the worker reaches the internet, ADR-0036.

**A token per request, never stored.** For each request this signs a JSON Web Token valid for ten
minutes, asks GitHub which installation holds the repository, and exchanges the token for an
installation token narrowed to that one repository and to the permissions the request needs. The
installation token lives in the request's session and nowhere else: it is not stored, logged or
put in a detail. Nothing GitHub says about a refused credential is kept, and every other message
has anything shaped like a token removed before it becomes a detail, `redact`.

**No retries.** A request that GitHub throttles, or that does not answer, fails typed; the
collector asks again on its next run, and each pull request is its own step, so a run that stops
part way leaves every other one as it was. Spec section 10.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from urllib.parse import quote

import httpx
import jwt

from finops_core.errors import (
    AccessDenied,
    CollectionError,
    Misconfigured,
    SchemaDrift,
    Throttled,
    Unreachable,
)
from finops_providers.ai_reports import redact

#: GitHub's REST API. GitHub Enterprise Server is outside P15.
BASE_URL: Final = "https://api.github.com"  # allow-hardcoded: GitHub's documented API host
#: The REST API version the recorded shapes in the tests come from.
API_VERSION: Final = "2022-11-28"  # allow-hardcoded: GitHub's documented REST API version
#: How long one request may take.
TIMEOUT_SECONDS: Final = 30.0  # allow-hardcoded: a bound on our own wait, not a provider limit
#: GitHub refuses an app token that expires more than ten minutes ahead, and advises dating its
#: issue a minute back against clock drift. So it is issued a minute ago, for ten minutes.
CLOCK_DRIFT_SECONDS: Final = 60  # allow-hardcoded: GitHub's documented allowance for drift
APP_TOKEN_SECONDS: Final = 600  # allow-hardcoded: GitHub's documented longest app token

#: What an installation token may do, narrowed to what the request needs.
READ: Final[Mapping[str, str]] = {"contents": "read", "pull_requests": "read"}
WRITE: Final[Mapping[str, str]] = {"contents": "write", "pull_requests": "write"}
METADATA: Final[Mapping[str, str]] = {"metadata": "read"}

RUNBOOK: Final = "docs/runbooks/code-host.md"

Clock = Callable[[], datetime]


def app_token(app_id: str, private_key: str, now: datetime) -> str:
    """A JSON Web Token naming the app, signed with its key, for ten minutes from a minute ago."""
    issued = int(now.timestamp()) - CLOCK_DRIFT_SECONDS
    claims = {"iat": issued, "exp": issued + APP_TOKEN_SECONDS, "iss": app_id}
    return jwt.encode(claims, private_key, algorithm="RS256")


@dataclass(frozen=True)
class Repository:
    """`owner/name`, parsed once, so no path is built from a string that is not one."""

    owner: str
    name: str

    @classmethod
    def parse(cls, text: str, *, scope_key: str, collector: str) -> Repository:
        owner, slash, name = text.partition("/")
        if not slash or not owner or not name or "/" in name:
            raise Misconfigured(
                scope_key=scope_key,
                collector=collector,
                detail=f"{text!r} is not a repository: it is written owner/name",
            )
        return cls(owner, name)

    @property
    def path(self) -> str:
        return f"/repos/{quote(self.owner, safe='')}/{quote(self.name, safe='')}"


class Session:
    """Calls to GitHub with one token. Every answer outside `answers` raises typed."""

    def __init__(self, client: httpx.Client, token: str, *, scope_key: str, collector: str) -> None:
        self._client = client
        self._token = token
        self.scope_key = scope_key
        self.collector = collector

    def call(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
        absent: str | None = None,
        answers: frozenset[int] = frozenset(),
    ) -> httpx.Response:
        """One request. A success, or a status the caller names in `answers`, is returned."""
        try:
            response = self._client.request(
                method,
                path,
                json=json,
                params=params,
                headers={"Authorization": f"Bearer {self._token}"},
            )
        except httpx.TimeoutException as error:
            raise self.unreachable(f"{method} {path} timed out") from error
        except httpx.HTTPError as error:
            raise self.unreachable(f"{method} {path}: {type(error).__name__}") from error
        if response.is_success or response.status_code in answers:
            return response
        raise self._typed(method, path, response, absent)

    def json(self, method: str, path: str, **options: Any) -> Any:
        """One request's answer as JSON."""
        return self.body(self.call(method, path, **options), f"{method} {path}")

    def body(self, response: httpx.Response, what: str) -> Any:
        try:
            return response.json()
        except ValueError as error:
            raise self.drift(f"{what} answered with something that is not JSON") from error

    def said(self, response: httpx.Response) -> str:
        """What GitHub said, with anything shaped like a token removed, cut short."""
        try:
            message = response.json().get("message")
        except (ValueError, AttributeError):
            message = None
        return redact(str(message) if message else response.text, self._token)

    def drift(self, detail: str) -> SchemaDrift:
        return SchemaDrift(scope_key=self.scope_key, collector=self.collector, detail=detail)

    def misconfigured(self, detail: str) -> Misconfigured:
        return Misconfigured(scope_key=self.scope_key, collector=self.collector, detail=detail)

    def unreachable(self, detail: str) -> Unreachable:
        return Unreachable(scope_key=self.scope_key, collector=self.collector, detail=detail)

    def _typed(
        self, method: str, path: str, response: httpx.Response, absent: str | None
    ) -> CollectionError:
        status = response.status_code
        where = f"HTTP {status} from {method} {path}"
        if _throttled(response):
            return Throttled(
                scope_key=self.scope_key,
                collector=self.collector,
                detail=f"{where}: GitHub's rate limit is spent; the next run asks again",
            )
        if status == 401:
            # Nothing GitHub says about a refused credential is kept.
            return AccessDenied(
                scope_key=self.scope_key,
                collector=self.collector,
                detail=f"{where}: GitHub refused the app's credential. Check the app id and that "
                f"the secret holds the app's current private key, {RUNBOOK}",
            )
        if status == 403:
            return AccessDenied(
                scope_key=self.scope_key,
                collector=self.collector,
                detail=f"{where}: the app may not do this here. It needs Contents and Pull "
                f"requests, read and write, {RUNBOOK}. {self.said(response)}",
            )
        if status == 404:
            return self.misconfigured(f"{where}: {absent or 'GitHub has no such thing'}")
        if response.is_server_error:
            return self.unreachable(f"{where}: {self.said(response)}")
        return self.drift(f"{where}: {self.said(response)}")


def _throttled(response: httpx.Response) -> bool:
    """GitHub's primary and secondary rate limits, which answer 429, or 403 saying so."""
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    if response.headers.get("x-ratelimit-remaining") == "0":
        return True
    return "rate limit" in response.text.lower()


def field(session: Session, body: Any, *keys: str | int) -> Any:
    """A value inside an answer, or SchemaDrift naming what was missing."""
    found = body
    for key in keys:
        try:
            found = found[key]
        except (KeyError, IndexError, TypeError) as error:
            path = ".".join(str(one) for one in keys)
            raise session.drift(f"GitHub's answer has no {path}") from error
    return found


class GitHubApp:
    """Meter's GitHub App: a session per request, with a token minted for it alone."""

    def __init__(
        self,
        *,
        app_id: str,
        private_key: Callable[[], str],
        collector: str,
        clock: Clock,
        transport: httpx.BaseTransport | None = None,
        base_url: str = BASE_URL,
    ) -> None:
        self._app_id = app_id
        self._private_key = private_key
        self._collector = collector
        self._clock = clock
        self._transport = transport
        self._base_url = base_url

    @contextmanager
    def session(
        self, repository: str, permissions: Mapping[str, str], *, narrowed: bool = True
    ) -> Iterator[tuple[Session, Repository]]:
        """A session for one repository, holding a token minted for it that ends with it.

        `narrowed` limits the token to the one repository; first contact lists the installation's
        repositories instead, with a token that may read their metadata alone.

        Raises:
            AccessDenied: GitHub refused the app's credential.
            Misconfigured: The key is not a private key, the repository is not written
                owner/name, the app is not installed on it, or is not granted `permissions`.
            Throttled: GitHub's rate limit is spent.
            Unreachable: GitHub did not answer.
        """
        scope_key = f"github:{repository}"
        repo = Repository.parse(repository, scope_key=scope_key, collector=self._collector)
        with httpx.Client(
            base_url=self._base_url,
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION},
            timeout=TIMEOUT_SECONDS,
            transport=self._transport,
        ) as client:
            app = Session(
                client, self._signed(scope_key), scope_key=scope_key, collector=self._collector
            )
            token = self._installation_token(app, repo, permissions, narrowed=narrowed)
            yield Session(client, token, scope_key=scope_key, collector=self._collector), repo

    def _signed(self, scope_key: str) -> str:
        try:
            return app_token(self._app_id, self._private_key(), self._clock())
        except jwt.PyJWTError as error:
            # The key is never in the detail, and neither is anything pyjwt said about it.
            raise Misconfigured(
                scope_key=scope_key,
                collector=self._collector,
                detail=f"the code host secret does not hold a private key in PEM form, {RUNBOOK}",
            ) from error

    @staticmethod
    def _installation_token(
        app: Session, repo: Repository, permissions: Mapping[str, str], *, narrowed: bool
    ) -> str:
        whose = f"{repo.owner}/{repo.name}"
        installation = app.json(
            "GET",
            f"{repo.path}/installation",
            absent=f"the app is not installed on {whose}, or there is no such repository",
        )
        number = field(app, installation, "id")
        asked: dict[str, Any] = {"permissions": dict(permissions)}
        if narrowed:
            asked["repositories"] = [repo.name]
        minted = app.call(
            "POST",
            f"/app/installations/{number}/access_tokens",
            json=asked,
            answers=frozenset({422}),
        )
        if minted.status_code == 422:
            granted = ", ".join(f"{name} {level}" for name, level in sorted(permissions.items()))
            raise app.misconfigured(
                f"GitHub would not grant {granted} on {whose}: {app.said(minted)}. The app's "
                f"permissions are set where it is registered, {RUNBOOK}"
            )
        return str(field(app, app.body(minted, "the installation token"), "token"))
