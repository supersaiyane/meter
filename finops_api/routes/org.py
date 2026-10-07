"""The organization tree, with out of scope branches marked rather than removed.

Pruning is the tempting version and it is wrong. A user looking at a tree with
gaps they cannot explain concludes the data is broken, and they are half right:
what is broken is the tree they were shown. Marking a branch unreachable keeps
the shape honest and says why the numbers stop there.

The node itself is still returned for an unreachable branch, because structure
is not cost data. What is withheld is anything derived from reading inside it,
which for P0 is nothing beyond the name, and the flag is what tells the frontend
not to render a figure against it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Connection

from finops_api.db.repositories import AccessContext, OrgRepository
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.exports import ExportSpec, exportable, listed
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import Envelope, OrgNodeOut
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.org import OrgNodeType
from finops_core.domain.tenant import Scope

router = APIRouter(prefix=API_PREFIX, tags=["org"])


def reachable_for(row: Any, scope: Scope) -> bool:
    """Structure is always visible. Whether an account can be read is the scope's answer."""
    if str(row.node_type) != OrgNodeType.ACCOUNT.value:
        return True
    return scope.permits(AccountKey(provider=Provider.AWS, account_id=str(row.node_id)))


@router.get("/org/tree", response_model=Envelope[list[OrgNodeOut]])
@exportable(ExportSpec(title="Organisation", row_model=OrgNodeOut, rows=listed))
def org_tree(
    scope: Scope = Depends(get_scope),
    connection: Connection = Depends(get_connection),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[OrgNodeOut]]:
    rows = OrgRepository(connection, context).list_tree(scope)
    nodes = [
        OrgNodeOut(
            node_id=str(row.node_id),
            node_type=str(row.node_type),
            parent_node_id=row.parent_node_id,
            name=str(row.name),
            path=str(row.path),
            depth=int(row.depth),
            reachable=reachable_for(row, scope),
            as_of=row.as_of,
            collected_at=row.collected_at,
        )
        for row in rows
    ]
    visible = sum(
        1 for node in nodes if node.reachable and node.node_type == OrgNodeType.ACCOUNT.value
    )
    return Envelope(
        data=nodes,
        meta=build_meta(connection, scope, context, visible=visible, rows=rows),
    )
