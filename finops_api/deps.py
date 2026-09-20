"""Request dependencies, and the first of the two scope enforcement points.

Constraint 3 in CLAUDE.md: scope is enforced in a request dependency and again
in a repository guard, independently. This is the first one. The second lives in
`finops_api.guards` and does not trust this one, which is the whole point: a
route that forgets to declare `scope` still cannot read out of scope data.

The scope comes from the entitlement resolver and never from the request. A
route that builds a `Scope` out of a query parameter defeats both checks at
once, because the repository will faithfully apply whatever scope it is handed.
That case is not preventable here and is not pretended to be: it is why every
read writes the scope it evaluated to `audit_event`, so a fabricated scope is at
least visible afterwards.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.engine import Connection

from finops_api.db.repositories.base import AccessContext
from finops_core.config import Settings, load_settings
from finops_core.domain.identity import Entitlement, Principal
from finops_core.domain.tenant import Scope
from finops_core.errors import AccessDenied

REQUEST_ID_HEADER = "X-Request-Id"
AUTHORIZATION = "Authorization"
BEARER = "Bearer "


@lru_cache(maxsize=1)
def get_settings(request: Request) -> Settings:
    """The configuration this application was built with.

    From `app.state` when `create_app` was given one, and from the environment
    otherwise. Reading the environment unconditionally made `create_app`'s
    `settings` argument a lie for every route that took this dependency: the
    application was assembled with one configuration and its routes answered
    from another, which is two sources for one fact.
    """
    configured = getattr(request.app.state, "settings", None)
    return configured if configured is not None else load_settings()


def get_request_id(request: Request) -> str:
    """The id every log line and every audit row for this request carries."""
    existing = request.headers.get(REQUEST_ID_HEADER)
    return existing or str(uuid4())


def get_connection(request: Request) -> Iterator[Connection]:
    """One transaction per request, so a read and its audit row commit together."""
    with request.app.state.engine.begin() as connection:
        yield connection


def get_principal(
    request: Request,
    authorization: str | None = Header(default=None, alias=AUTHORIZATION),
) -> Principal:
    """Who is asking. Absent, malformed and forged all get one answer."""
    if not authorization or not authorization.startswith(BEARER):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    token = authorization.removeprefix(BEARER)
    try:
        session = request.app.state.signer.verify(token)
    except AccessDenied as refused:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=refused.remediation
        ) from refused
    return Principal(
        principal_id=session.principal_id,
        display_name=session.subject,
        tenant_id=session.tenant_id,
        groups=frozenset(),
    )


def get_scope(request: Request, principal: Principal = Depends(get_principal)) -> Scope:
    """The scope this request may read. Resolved, never supplied by the caller."""
    entitlement: Entitlement = request.app.state.entitlements.resolve(principal)
    return entitlement.scope


def get_access_context(request_id: str = Depends(get_request_id)) -> AccessContext:
    """What every audit row this request writes is stamped with.

    `principal_id` stays unset until principals are persisted. The audit row is
    written either way, because a read by an unrecorded reader is still a read
    that happened, and dropping the row would hide it completely.
    """
    return AccessContext(request_id=request_id)
