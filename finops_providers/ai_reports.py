"""Reading an AI provider's admin reports over HTTPS, with every failure typed. P13, FEAT-083.

OpenAI's and Anthropic's cost and usage reports are paged JSON behind an admin key, and both page
the same way: `has_more` and `next_page` in the answer, `page` in the next request. This holds the
part they share, so each provider's adapter is only its mapping: one GET at a time through the NAT
gateway only the worker may use, ADR-0036, retried a bounded number of times when the provider
asks Meter to slow down or fails on its side, and every failure one of the typed causes.

**The key never leaves this module.** It is read when the first request is made, through a
callable the composition hands in, and it travels in a header the provider names. An error a
provider returns can echo a key, masked or not, so nothing a provider says about a refused key is
kept, and every other message is cut short and has anything shaped like a key removed before it
becomes a detail, `redact`. P13 plan rule 2.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterator, Mapping
from typing import Any, Final

import httpx

from finops_core.errors import (
    AccessDenied,
    CollectionError,
    NotOptedIn,
    SchemaDrift,
    Throttled,
    Unreachable,
)

#: How long one request may take. The reports are a few kilobytes a day.
TIMEOUT_SECONDS: Final = 30.0  # allow-hardcoded: a bound on our own wait, not a provider limit
#: How many times a request the provider asked Meter to slow down for, or failed on its side, is
#: tried again before the run fails typed. The next run reads the period again.
RETRIES: Final = 3  # allow-hardcoded: a bound on our own retries, not a provider limit
#: The longest Meter honours a provider's Retry-After, so one run cannot wait an hour.
MAX_WAIT_SECONDS: Final = 60.0  # allow-hardcoded: a bound on our own wait, not a provider limit
#: How much of a provider's error body becomes a detail: enough to read, not a whole page.
DETAIL_CHARACTERS: Final = 300  # allow-hardcoded: a bound on what we keep, not a provider limit

#: Anything shaped like a provider key, masked or not, so it is never written into a detail.
_KEYLIKE: Final = re.compile(r"(sk-[A-Za-z0-9_*.\-]+|[A-Za-z0-9_\-]{32,})")

Headers = Callable[[], Mapping[str, str]]


def redact(text: str, key: str | None = None) -> str:
    """A provider's message with the key, and anything shaped like one, removed, and cut short."""
    if key:
        text = text.replace(key, "[redacted]")
    return _KEYLIKE.sub("[redacted]", text)[:DETAIL_CHARACTERS]


class ReportApi:
    """GETs against one provider's report API, for one organization, every failure typed."""

    def __init__(
        self,
        *,
        base_url: str,
        headers: Headers,
        scope_key: str,
        collector: str,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base_url = base_url
        self._headers = headers
        self._scope = scope_key
        self._collector = collector
        self._transport = transport
        self._sleeper = sleeper
        self._client: httpx.Client | None = None
        self._key: str | None = None

    def _http(self) -> httpx.Client:
        # Built on first use, so the key is read only when a request is about to be made.
        if self._client is None:
            headers = dict(self._headers())
            # The bare key, without the scheme a header puts before it, so `redact` finds it.
            self._key = next(
                (
                    v.removeprefix("Bearer ").strip()
                    for k, v in headers.items()
                    if k.lower() in ("authorization", "x-api-key")
                ),
                None,
            )
            self._client = httpx.Client(
                base_url=self._base_url,
                headers={**headers, "Accept": "application/json"},
                timeout=TIMEOUT_SECONDS,
                transport=self._transport,
            )
        return self._client

    def pages(self, path: str, params: Mapping[str, Any]) -> Iterator[Any]:
        """Every item of every page, following `next_page` while `has_more` says there is one."""
        query = dict(params)
        while True:
            answer = self.get(path, query)
            data = answer.get("data") if isinstance(answer, dict) else None
            if not isinstance(data, list):
                raise self._drift(f"{path} answered without a data list")
            yield from data
            if not answer.get("has_more"):
                return
            following = answer.get("next_page")
            if not following:
                raise self._drift(f"{path} said it had more and named no next page")
            query["page"] = following

    def get(self, path: str, params: Mapping[str, Any]) -> Any:
        """One GET, retried while the provider asks Meter to wait or fails on its side."""
        failure: CollectionError | None = None
        for attempt in range(RETRIES + 1):
            if attempt:
                self._sleeper(self._wait(failure, attempt))
            try:
                response = self._http().get(path, params=params)
            except httpx.TimeoutException:
                failure = Unreachable(
                    scope_key=self._scope, collector=self._collector, detail=f"{path} timed out"
                )
                continue
            except httpx.HTTPError as error:
                failure = Unreachable(
                    scope_key=self._scope,
                    collector=self._collector,
                    detail=f"{path}: {type(error).__name__}",
                )
                continue
            if response.is_success:
                try:
                    return response.json()
                except ValueError as error:
                    raise self._drift(f"{path} answered with something that is not JSON") from error
            failure = self._typed(path, response)
            if not isinstance(failure, Throttled | Unreachable):
                raise failure
        assert failure is not None
        raise failure

    # -- failures ----------------------------------------------------------

    def _typed(self, path: str, response: httpx.Response) -> CollectionError:
        status = response.status_code
        if status in (401, 403):
            # Nothing the provider says about a refused key is kept: its message can name the key.
            return AccessDenied(
                scope_key=self._scope,
                collector=self._collector,
                detail=f"HTTP {status} from {path}: the admin key was refused. Check it is an "
                "admin key for this organization and has not been revoked",
            )
        said = redact(response.text, self._key)
        if status == 404:
            return NotOptedIn(
                scope_key=self._scope,
                collector=self._collector,
                detail=f"HTTP 404 from {path}: this organization has no such report. {said}",
            )
        if status == 429:
            failure = Throttled(
                scope_key=self._scope, collector=self._collector, detail=f"HTTP 429 from {path}"
            )
            failure.retry_after = response.headers.get("retry-after")  # type: ignore[attr-defined]
            return failure
        if response.is_server_error:
            return Unreachable(
                scope_key=self._scope,
                collector=self._collector,
                detail=f"HTTP {status} from {path}: {said}",
            )
        return SchemaDrift(
            scope_key=self._scope,
            collector=self._collector,
            detail=f"HTTP {status} from {path}: {said}",
        )

    def _drift(self, detail: str) -> SchemaDrift:
        return SchemaDrift(scope_key=self._scope, collector=self._collector, detail=detail)

    @staticmethod
    def _wait(failure: CollectionError | None, attempt: int) -> float:
        """The provider's Retry-After where it gave one, else doubling from one second, capped."""
        stated = getattr(failure, "retry_after", None)
        try:
            seconds = float(stated) if stated is not None else float(2 ** (attempt - 1))
        except ValueError:
            seconds = float(2 ** (attempt - 1))
        return max(0.0, min(seconds, MAX_WAIT_SECONDS))
