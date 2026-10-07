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

A request may narrow its scope to one account, FEAT-075, and do nothing else with
it. The account is looked up through the scope the resolver gave, and a scope is
only ever narrowed to an account it already permits, so the parameter can neither
build a scope nor widen one.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from functools import lru_cache
from typing import Any
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.engine import Connection

from finops_api.db.repositories.accounts import AccountRepository
from finops_api.db.repositories.base import AccessContext
from finops_core.config import Settings, load_settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.identity import Entitlement, Principal
from finops_core.domain.tenant import Scope
from finops_core.errors import AccessDenied

REQUEST_ID_HEADER = "X-Request-Id"
AUTHORIZATION = "Authorization"
BEARER = "Bearer "

#: An account number as a provider writes it: twelve digits for AWS, and the letters, digits
#: and hyphens of a GCP project or an Azure subscription. Anything else is refused before a
#: query is built from it.
ACCOUNT_NUMBER = r"^[A-Za-z0-9-]{1,64}$"

#: The one answer for an account outside the scope and for one that does not exist.
NOT_IN_SCOPE = "No account by that number is in this session's scope."


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


def get_tickets(request: Request) -> Any:
    """Where an accepted recommendation goes, or None.

    None when the application was assembled without a sink, which is the current
    default: OPEN-05 has been open since 2026-08-23 and no adapter has been chosen.
    The lifecycle works without one, and a recommendation accepted with no sink
    configured simply carries no ticket reference.

    Returning None rather than raising is deliberate. A product that refused to
    accept a recommendation because nobody had picked a ticketing system would be
    holding its own feature hostage to a decision that is not urgent.
    """
    return getattr(request.app.state, "tickets", None)


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


def get_access_context(request_id: str = Depends(get_request_id)) -> AccessContext:
    """What every audit row this request writes is stamped with.

    `principal_id` stays unset until principals are persisted. The audit row is
    written either way, because a read by an unrecorded reader is still a read
    that happened, and dropping the row would hide it completely.
    """
    return AccessContext(request_id=request_id)


def get_scope(
    request: Request,
    principal: Principal = Depends(get_principal),
    context: AccessContext = Depends(get_access_context),
    chosen_account: str | None = Query(
        default=None,
        pattern=ACCOUNT_NUMBER,
        description=(
            "Narrow this request to one account, FEAT-075. It narrows what the session may "
            "read and never widens it: an account outside the scope is not found."
        ),
    ),
) -> Scope:
    """The scope this request may read. Resolved, never supplied by the caller.

    Stamped with the authenticated principal, ADR-0029, so a row that belongs to a person
    is confined to that person by the guard rather than by every route remembering to.

    A caller may narrow it to one account the resolved scope already reaches, FEAT-075, which
    is how the account chosen in the address reaches every route at once. The account is
    looked up through the scope in a transaction of its own rather than the request's, so the
    assistant, which reads no table while it waits on a model, does not hold one open for the
    whole answer.
    """
    entitlement: Entitlement = request.app.state.entitlements.resolve(principal)
    scope = replace(entitlement.scope, principal_id=principal.principal_id)
    if chosen_account is None:
        return scope
    with request.app.state.engine.begin() as connection:
        row = AccountRepository(connection, context).get_in_scope(scope, chosen_account)
    if row is None:
        # Outside the scope and absent get one answer, as the recheck route gives: telling
        # them apart would let a caller enumerate the accounts they cannot see.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_IN_SCOPE)
    return scope.narrowed_to(
        AccountKey(provider=Provider(str(row.provider)), account_id=str(row.account_id))
    )
