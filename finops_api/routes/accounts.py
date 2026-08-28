"""Accounts in scope, with the health of the role that reads them.

An account whose role is broken is still listed. Omitting it would shrink the
organization total and hide the reason a figure is missing, which is the failure
constraint 5 exists to prevent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.engine import Connection

from finops_api.db.repositories import AccessContext, AccountRepository
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import AccountOut, Envelope
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.tenant import Scope

router = APIRouter(prefix=API_PREFIX, tags=["accounts"])


def to_out(row: Any) -> AccountOut:
    return AccountOut(
        provider=str(row.provider),
        account_id=str(row.account_id),
        name=str(row.name),
        status=str(row.status),
        role_health=str(row.role_health),
        role_health_checked_at=row.role_health_checked_at,
        role_health_error=row.role_health_error,
        as_of=row.as_of,
        collected_at=row.collected_at,
    )


@router.get("/accounts", response_model=Envelope[list[AccountOut]])
def list_accounts(
    scope: Scope = Depends(get_scope),
    connection: Connection = Depends(get_connection),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[AccountOut]]:
    rows = AccountRepository(connection, context).list_in_scope(scope)
    return Envelope(
        data=[to_out(row) for row in rows],
        meta=build_meta(connection, scope, context, visible=len(rows), rows=rows),
    )


@router.post("/accounts/{account_id}/recheck", response_model=Envelope[AccountOut])
def recheck(
    account_id: str,
    request: Request,
    scope: Scope = Depends(get_scope),
    connection: Connection = Depends(get_connection),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[AccountOut]:
    """Force a role health recheck. A read only call, per constraint 6."""
    checker = getattr(request.app.state, "health_check", None)
    if checker is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="role health checking is not configured on this deployment",
        )

    repository = AccountRepository(connection, context)
    existing = repository.get_in_scope(scope, account_id)
    if existing is None:
        # Out of scope and absent get one answer. Telling them apart would let a
        # caller enumerate the accounts they cannot see.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such account")

    key = AccountKey(provider=Provider(str(existing.provider)), account_id=account_id)
    health = checker.check(key, request.app.state.settings.region_list[0])
    repository.set_role_health(
        scope,
        account_id,
        health=str(health.health),
        error=health.error or None,
        checked_at=health.collected_at or datetime.now(UTC),
    )
    refreshed = repository.get_in_scope(scope, account_id)
    assert refreshed is not None
    return Envelope(
        data=to_out(refreshed),
        meta=build_meta(connection, scope, context, visible=1, rows=[refreshed]),
    )
