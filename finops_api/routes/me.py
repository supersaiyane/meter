"""Who the caller is and what they can reach.

The scope summary is a count and not a list of every account, because a viewer
scoped to three hundred accounts does not need three hundred identifiers to know
they can see everything. The coverage figure in `meta` is the part that matters
and it is on every response anyway.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.engine import Connection

from finops_api.db.repositories import AccessContext
from finops_api.deps import get_access_context, get_connection, get_principal, get_scope
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import Envelope
from finops_core.domain.identity import Principal
from finops_core.domain.tenant import Scope

router = APIRouter(prefix=API_PREFIX, tags=["me"])


class MeOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    principal_id: str
    display_name: str
    tenant_id: str
    tiers: tuple[str, ...]
    is_global: bool
    accounts_in_scope: int


@router.get("/me", response_model=Envelope[MeOut])
def me(
    principal: Principal = Depends(get_principal),
    scope: Scope = Depends(get_scope),
    connection: Connection = Depends(get_connection),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[MeOut]:
    visible = -1 if scope.is_global else len(scope.accounts)
    meta = build_meta(connection, scope, context, visible=max(visible, 0))
    if scope.is_global:
        # A global viewer sees everything, so visible is the organization total
        # rather than an enumerated set. Reporting zero here would render as a
        # user who can see nothing.
        meta = meta.model_copy(
            update={
                "scope_coverage": meta.scope_coverage.model_copy(
                    update={"visible": meta.scope_coverage.total}
                )
            }
        )
    return Envelope(
        data=MeOut(
            principal_id=principal.principal_id,
            display_name=principal.display_name,
            tenant_id=str(principal.tenant_id),
            tiers=tuple(sorted(principal.groups)),
            is_global=scope.is_global,
            accounts_in_scope=meta.scope_coverage.visible,
        ),
        meta=meta,
    )
