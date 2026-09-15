"""Reading dashboards and alert rules out of a Grafana workspace.

Extracted from the prototype, and the error handling is deliberately not
extracted with it.

The prototype wrapped every call in `except Exception: return []`. A workspace
the token cannot read therefore reported zero dashboards, which renders as "this
workspace costs nothing" rather than as "we could not look". That is constraint
5 exactly, and it is the failure this whole product exists to make impossible,
so a new module in `finops_providers` cannot reproduce it. Every failure here
becomes one of the six typed causes and propagates.

It uses httpx rather than `urllib.request`, which the prototype used. That is
not a preference: `urllib.request` is forbidden by
`scripts/ci/check_forbidden_imports.py`, because CVE-2026-15806's acceptance in
`security/policy/accepted.yaml` rests on nobody importing it. Deleting the
prototype removes the last importer, and the exclusion goes with it.

Amazon Managed Grafana only, per OPEN-04 re answered 2026-09-02. A self hosted
or Grafana Cloud workspace is a second implementation of this module rather than
a change to it, which is why the reading sits behind a port.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from finops_core.errors import (
    AccessDenied,
    CollectionError,
    NotOptedIn,
    SchemaDrift,
    Throttled,
    Unreachable,
)

LOGGER = logging.getLogger("meter.grafana")

COLLECTOR = "query_audit"

#: Grafana's search endpoint caps at 5000 and does not paginate past it. A
#: workspace with more dashboards than this returns a truncated list and says
#: nothing about it, so the count is compared against the cap and a truncated
#: read is refused rather than accepted. See `search_dashboards`.
SEARCH_LIMIT = 5000

#: What each HTTP status means in this product's closed taxonomy. Anything not
#: listed becomes SchemaDrift rather than NoData, for the same reason the AWS
#: adapter does it: an unknown failure rendered as a zero is the defect the
#: taxonomy exists to prevent.
_STATUS_CAUSES: dict[int, type[CollectionError]] = {
    401: AccessDenied,
    403: AccessDenied,
    404: NotOptedIn,
    408: Unreachable,
    429: Throttled,
    502: Unreachable,
    503: Unreachable,
    504: Unreachable,
}


@dataclass(frozen=True)
class Workspace:
    """One Grafana workspace, however it was discovered."""

    id: str
    name: str
    endpoint: str
    status: str = "ACTIVE"

    @property
    def scope_key(self) -> str:
        """How a failure against this workspace is recorded and reported."""
        return f"grafana:{self.id}"


def endpoint_from_url(raw: str) -> str | None:
    """The host part of a configured workspace URL, or None.

    Accepts a bare host or a full URL, because both are written in practice and
    a configuration that silently ignored one of them would produce a missing
    workspace nobody could explain.
    """
    cleaned = (raw or "").strip()
    if not cleaned:
        return None
    for prefix in ("https://", "http://"):
        cleaned = cleaned.removeprefix(prefix)
    return cleaned.split("/")[0] or None


def translate(error: Exception, scope_key: str) -> CollectionError:
    """Turn an HTTP failure into exactly one of the six causes."""
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        # The body explains why, and a 403 from Grafana names the permission.
        # Truncated, because it is somebody else's output going into our log.
        body = error.response.text[:300]
        cause = _STATUS_CAUSES.get(status, SchemaDrift)
        return cause(
            scope_key=scope_key,
            collector=COLLECTOR,
            detail=f"HTTP {status}: {body}".strip(),
        )
    if isinstance(error, httpx.TimeoutException):
        return Unreachable(scope_key=scope_key, collector=COLLECTOR, detail=f"timed out: {error}")
    if isinstance(error, httpx.HTTPError):
        return Unreachable(
            scope_key=scope_key, collector=COLLECTOR, detail=f"{type(error).__name__}: {error}"
        )
    return SchemaDrift(
        scope_key=scope_key, collector=COLLECTOR, detail=f"{type(error).__name__}: {error}"
    )


class GrafanaClient:
    """A read only caller of one Grafana workspace's HTTP API.

    Holds a token it did not mint. Minting one is a separate concern with its
    own cleanup guarantees, and mixing the two is how a throwaway service
    account outlives the run that created it.
    """

    def __init__(
        self,
        workspace: Workspace,
        token: str,
        timeout_seconds: float,
        transport: Any = None,
    ) -> None:
        self._workspace = workspace
        self._client = transport or httpx.Client(
            # The host comes from workspace discovery or from configuration.
            # Only the scheme is fixed, and it is not negotiable for a call
            # carrying a bearer token.
            base_url=f"https://{workspace.endpoint}",  # allow-hardcoded: scheme, not endpoint
            timeout=timeout_seconds,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )

    def _get(self, path: str) -> Any:
        """One GET. Raises a typed cause, never returns an empty answer."""
        try:
            response = self._client.get(path)
            response.raise_for_status()
            return response.json()
        except CollectionError:
            raise
        except Exception as error:
            failure = translate(error, self._workspace.scope_key)
            LOGGER.warning(
                "grafana %s failed for %s: %s",
                path,
                self._workspace.endpoint,
                failure.detail,
            )
            raise failure from error

    def search_dashboards(self) -> tuple[dict[str, Any], ...]:
        """Every dashboard in the workspace.

        Raises `SchemaDrift` when the result is exactly at the cap. Grafana does
        not report that it truncated, so a workspace with 5,000 dashboards
        silently returns 5,000 and the rest are invisible. Refusing is better
        than auditing an unknown fraction of an estate and calling it the estate.
        """
        found = self._get(f"/api/search?type=dash-db&limit={SEARCH_LIMIT}")
        if not isinstance(found, list):
            raise SchemaDrift(
                scope_key=self._workspace.scope_key,
                collector=COLLECTOR,
                detail=f"search returned {type(found).__name__}, expected a list",
            )
        if len(found) >= SEARCH_LIMIT:
            raise SchemaDrift(
                scope_key=self._workspace.scope_key,
                collector=COLLECTOR,
                detail=(
                    f"search returned {len(found)} dashboards, at the {SEARCH_LIMIT} cap. "
                    "The list is truncated and Grafana does not say by how much."
                ),
            )
        return tuple(found)

    def dashboard(self, uid: str) -> dict[str, Any]:
        """One dashboard, with its meta wrapper, as the analyser expects it."""
        found = self._get(f"/api/dashboards/uid/{uid}")
        if not isinstance(found, dict):
            raise SchemaDrift(
                scope_key=self._workspace.scope_key,
                collector=COLLECTOR,
                detail=f"dashboard {uid} returned {type(found).__name__}, expected an object",
            )
        return found

    def alert_rules(self) -> tuple[dict[str, Any], ...]:
        """Grafana managed alert rules.

        `NotOptedIn` is the honest cause when provisioning is unavailable: the
        workspace has not enabled the API, which is a configuration state rather
        than a failure, and it is reported as such rather than as no rules.
        """
        found = self._get("/api/v1/provisioning/alert-rules")
        if not isinstance(found, list):
            raise SchemaDrift(
                scope_key=self._workspace.scope_key,
                collector=COLLECTOR,
                detail=f"alert rules returned {type(found).__name__}, expected a list",
            )
        return tuple(found)

    def org_preferences(self) -> dict[str, Any]:
        """Organization preferences, which is where the refresh floor lives.

        An empty mapping when the workspace has none, which is a configuration
        state rather than a failure: a workspace nobody has set a floor on is
        the estate FEAT-014 exists to find.
        """
        found = self._get("/api/org/preferences")
        if found is None:
            return {}
        if not isinstance(found, dict):
            raise SchemaDrift(
                scope_key=self._workspace.scope_key,
                collector=COLLECTOR,
                detail=f"org preferences returned {type(found).__name__}, expected an object",
            )
        return found

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GrafanaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
