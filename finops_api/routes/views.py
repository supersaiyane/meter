"""The report library's saved views. FEAT-068, TASK-P8-010, P8 spec section 7.

`GET`, `POST`, `PATCH` and `DELETE /reports/views`, and `GET /reports/views/{view_id}`. A view is
configuration and never data, section 5.6: a screen and its query, named. Nothing here reads a
figure, so the screen a view names is read afresh, in the opener's own scope, when it is
opened, and a view shared by a reader of the whole estate shows a narrowed colleague only what
their own scope reaches.

A view somebody else keeps private is not found, whether or not it exists, as a resource
outside a reader's scope is not found. A shared view the reader did not save is found and its
change refused, 403, because they can see it and are owed the reason rather than told it is
missing.

A refused change is answered rather than raised. The request's transaction rolls back on an
exception, and it would take with it the DENIED audit row the repository has just written.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.views import SavedViewRepository, ViewRow
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import Envelope, Meta, SavedViewIn, SavedViewOut, SavedViewPatchIn
from finops_core.domain.tenant import Scope

router = APIRouter(prefix=API_PREFIX, tags=["reports"])

#: What the coverage banner counts on these routes.
VIEWS = "saved views"
#: The most the library lists at once. The coverage says when there are more.
VIEW_LIMIT = 500
NO_SUCH_VIEW = "no such saved view"
NOT_YOURS = (
    "Only the person who saved this view may rename, share or delete it. Duplicate it to keep "
    "a copy of your own."
)


def view_out(row: ViewRow, scope: Scope) -> SavedViewOut:
    """A row as its reader sees it. `owned` is decided against the reader and never stored."""
    return SavedViewOut(
        view_id=row.view_id,
        name=row.name,
        screen_path=row.screen_path,
        query=row.query,
        visibility=row.visibility,
        owned=row.owner_id == scope.principal_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _meta(
    connection: Connection, scope: Scope, context: AccessContext, *, shown: int, total: int
) -> Meta:
    """The library as it stands at the moment it was read.

    A view is configuration held in Meter's own table rather than a fact about a cloud, so it
    has no source time of its own. What is true is that this is the library when it was read,
    which is what both timestamps say.
    """
    now = datetime.now(UTC)
    return build_meta(
        connection,
        scope,
        context,
        visible=shown,
        as_of=now,
        collected_at=now,
        coverage=(shown, total),
        coverage_unit=VIEWS,
    )


def _refusal(repository: SavedViewRepository, scope: Scope, view_id: UUID) -> JSONResponse:
    """Not found when the reader cannot open the view, forbidden when they can but did not save it.

    Read again here, after the refused write, so the answer reflects the view as it now stands.
    """
    if repository.view(scope, view_id) is None:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": NO_SUCH_VIEW})
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": NOT_YOURS})


@router.get("/reports/views", response_model=Envelope[list[SavedViewOut]])
def views(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[SavedViewOut]]:
    """The reader's own views and the tenant's shared ones, the latest changed first."""
    repository = SavedViewRepository(connection, context)
    rows = repository.views(scope, VIEW_LIMIT)
    meta = _meta(connection, scope, context, shown=len(rows), total=repository.count(scope))
    return Envelope(data=[view_out(row, scope) for row in rows], meta=meta)


@router.post(
    "/reports/views",
    response_model=Envelope[SavedViewOut],
    status_code=status.HTTP_201_CREATED,
)
def save_view(
    body: SavedViewIn,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[SavedViewOut]:
    """Save a screen and its query under a name, for the reader alone or for the tenant."""
    row = SavedViewRepository(connection, context).create(
        scope,
        name=body.name,
        screen_path=body.screen_path,
        query=body.query,
        visibility=body.visibility,
        at=datetime.now(UTC),
    )
    meta = _meta(connection, scope, context, shown=1, total=1)
    return Envelope(data=view_out(row, scope), meta=meta)


@router.get("/reports/views/{view_id}", response_model=Envelope[SavedViewOut])
def view(
    view_id: UUID,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[SavedViewOut]:
    """One view, to open. What it names is then read in the opener's scope, not the saver's."""
    row = SavedViewRepository(connection, context).view(scope, view_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NO_SUCH_VIEW)
    meta = _meta(connection, scope, context, shown=1, total=1)
    return Envelope(data=view_out(row, scope), meta=meta)


@router.patch("/reports/views/{view_id}", response_model=Envelope[SavedViewOut])
def change_view(
    view_id: UUID,
    body: SavedViewPatchIn,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[SavedViewOut] | JSONResponse:
    """Rename a view the reader saved, share it with the tenant, or make it private again."""
    repository = SavedViewRepository(connection, context)
    row = repository.change(
        scope, view_id, at=datetime.now(UTC), name=body.name, visibility=body.visibility
    )
    if row is None:
        return _refusal(repository, scope, view_id)
    meta = _meta(connection, scope, context, shown=1, total=1)
    return Envelope(data=view_out(row, scope), meta=meta)


@router.delete("/reports/views/{view_id}", response_model=Envelope[SavedViewOut])
def delete_view(
    view_id: UUID,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[SavedViewOut] | JSONResponse:
    """Delete a view the reader saved. The answer is the view as it was, in the envelope."""
    repository = SavedViewRepository(connection, context)
    row = repository.delete(scope, view_id)
    if row is None:
        return _refusal(repository, scope, view_id)
    meta = _meta(connection, scope, context, shown=1, total=1)
    return Envelope(data=view_out(row, scope), meta=meta)
