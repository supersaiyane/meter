"""Report schedules and the runs they make. FEAT-069, TASK-P8-011, P8 spec sections 5.7 and 7.

`GET`, `POST`, `PATCH` and `DELETE /reports/schedules`; `GET /reports/runs`; and
`GET /reports/runs/{run_id}/file`, which checks scope again before it hands a file over.

A schedule is its owner's alone, so another person's is not found. Its view must be one the owner
can open, and its route must be one a screen exports, both checked here and the first held again
by the database. A run is the reader's own: the files they exported and the ones schedules
rendered for them. A stored file is handed back only while the reader's access still covers what
the file was made under, because a file made under a wider scope than the reader now holds is a
copy of rows they can no longer see.

A refused change is answered rather than raised, as on the saved view routes, so the DENIED
audit row the repository wrote survives the request.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.reports import RunRepository, RunRow
from finops_api.db.repositories.schedules import ScheduleRepository, ScheduleRow
from finops_api.db.repositories.views import SavedViewRepository
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.exports.responder import MEDIA_TYPES, exported_path
from finops_api.routes import API_PREFIX, build_meta
from finops_api.routes.views import NO_SUCH_VIEW
from finops_api.schemas import (
    Envelope,
    Meta,
    ReportRunOut,
    ScheduleIn,
    ScheduleOut,
    SchedulePatchIn,
    SchedulesOut,
)
from finops_core.domain.report_schedule import Cadence, next_run_after
from finops_core.domain.tenant import Scope
from finops_core.errors import CollectionError, NoData

router = APIRouter(prefix=API_PREFIX, tags=["reports"])

SCHEDULES = "schedules"
RUNS = "report runs"
#: The most runs the list returns at once. The coverage says when there are more.
RUN_LIMIT = 500
NO_SUCH_SCHEDULE = "no such schedule"
NO_SUCH_RUN = "no such report run"
NOT_EXPORTED = (
    "This is not a route a screen exports. Schedule a saved view from its screen, where the "
    "Export list names the routes the screen reads."
)
NO_FILE = (
    "This run kept no file. A file somebody exported was downloaded at the time and not kept, "
    "and a run that failed made none."
)
GONE = "The file this run kept is no longer in the store."
NARROWED = (
    "Your access has narrowed since this file was made, so it is not handed over. The "
    "schedule's next run makes it again, within the access you hold then."
)
NOT_KEPT = "This deployment keeps no report files, because no bucket is configured."
RETENTION = (
    "Files are kept until a retention period is decided, OPEN-15, and nothing deletes them yet."
)
DELIVERY = (
    "Nothing is sent yet: where reports go, email or Slack, is OPEN-11. Each file is kept and "
    "listed here for the person it was made for."
)


def schedule_out(row: ScheduleRow, view_name: str | None, screen_path: str | None) -> ScheduleOut:
    return ScheduleOut(
        schedule_id=row.schedule_id,
        view_id=row.view_id,
        view_name=view_name,
        screen_path=screen_path,
        export_path=row.export_path,
        format=row.format,
        cadence=row.cadence,
        recipients=list(row.recipients),
        enabled=row.enabled,
        next_run_at=row.next_run_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def run_out(row: RunRow) -> ReportRunOut:
    return ReportRunOut(
        run_id=row.run_id,
        schedule_id=row.schedule_id,
        view_path=row.view_path,
        view_query=row.view_query,
        format=row.format,
        status=row.status,
        rows=row.row_count,
        bytes=row.byte_count,
        truncated=row.truncated,
        failure_cause=row.failure_cause,
        failure_detail=row.failure_detail,
        has_file=row.storage_key is not None,
        made_at=row.made_at,
        finished_at=row.finished_at,
        as_of=row.as_of,
        collected_at=row.collected_at,
    )


def _meta(
    connection: Connection,
    scope: Scope,
    context: AccessContext,
    *,
    shown: int,
    total: int,
    unit: str,
) -> Meta:
    """Meter's own records, read now, so both timestamps are the read, as on the views routes."""
    now = datetime.now(UTC)
    return build_meta(
        connection,
        scope,
        context,
        visible=shown,
        as_of=now,
        collected_at=now,
        coverage=(shown, total),
        coverage_unit=unit,
    )


def _not_found(detail: str) -> JSONResponse:
    """Answered, not raised, so the DENIED audit row the repository wrote commits."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": detail})


# --- schedules -------------------------------------------------------------------------------


@router.get("/reports/schedules", response_model=Envelope[SchedulesOut])
def schedules(
    request: Request,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[SchedulesOut]:
    """The reader's schedules, and whether this deployment renders and keeps what they make."""
    rows = ScheduleRepository(connection, context).schedules(scope)
    data = SchedulesOut(
        rendering=request.app.state.report_store is not None,
        retention=RETENTION,
        delivery=DELIVERY,
        schedules=[schedule_out(row, row.view_name, row.screen_path) for row in rows],
    )
    meta = _meta(connection, scope, context, shown=len(rows), total=len(rows), unit=SCHEDULES)
    return Envelope(data=data, meta=meta)


@router.post(
    "/reports/schedules",
    response_model=Envelope[ScheduleOut],
    status_code=status.HTTP_201_CREATED,
)
def create_schedule(
    body: ScheduleIn,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[ScheduleOut]:
    """Render a saved view's route for each recipient on a cadence, starting at its next time."""
    view = SavedViewRepository(connection, context).view(scope, body.view_id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NO_SUCH_VIEW)
    path = exported_path(body.export_path)
    if path is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=NOT_EXPORTED)
    now = datetime.now(UTC)
    row = ScheduleRepository(connection, context).create(
        scope,
        view_id=body.view_id,
        export_path=path,
        file_format=body.format,
        cadence=body.cadence,
        recipients=body.recipients,
        next_run_at=next_run_after(Cadence(body.cadence), now),
        at=now,
    )
    meta = _meta(connection, scope, context, shown=1, total=1, unit=SCHEDULES)
    return Envelope(data=schedule_out(row, view.name, view.screen_path), meta=meta)


@router.patch("/reports/schedules/{schedule_id}", response_model=Envelope[ScheduleOut])
def change_schedule(
    schedule_id: UUID,
    body: SchedulePatchIn,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[ScheduleOut] | JSONResponse:
    """Pause or resume a schedule, or change its format, cadence or recipients."""
    repository = ScheduleRepository(connection, context)
    current = repository.schedule(scope, schedule_id)
    now = datetime.now(UTC)
    values: dict[str, Any] = {}
    if body.format is not None:
        values["format"] = body.format
    if body.recipients is not None:
        values["recipients"] = body.recipients
    if body.enabled is not None:
        values["enabled"] = body.enabled
    if current is not None and (body.cadence is not None or body.enabled):
        # A new cadence, or a schedule resumed, runs next at its next time from now, rather than
        # at a time it passed while paused.
        cadence = body.cadence or current.cadence
        values["cadence"] = cadence
        values["next_run_at"] = next_run_after(Cadence(cadence), now)
    row = repository.change(scope, schedule_id, at=now, values=values)
    if row is None:
        return _not_found(NO_SUCH_SCHEDULE)
    view = (
        None
        if row.view_id is None
        else SavedViewRepository(connection, context).view(scope, row.view_id)
    )
    meta = _meta(connection, scope, context, shown=1, total=1, unit=SCHEDULES)
    return Envelope(
        data=schedule_out(row, view.name if view else None, view.screen_path if view else None),
        meta=meta,
    )


@router.delete("/reports/schedules/{schedule_id}", response_model=Envelope[ScheduleOut])
def delete_schedule(
    schedule_id: UUID,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[ScheduleOut] | JSONResponse:
    """Stop and remove a schedule. The runs it made, and their files, stay with their readers."""
    row = ScheduleRepository(connection, context).delete(scope, schedule_id)
    if row is None:
        return _not_found(NO_SUCH_SCHEDULE)
    meta = _meta(connection, scope, context, shown=1, total=1, unit=SCHEDULES)
    return Envelope(data=schedule_out(row, None, None), meta=meta)


# --- runs ------------------------------------------------------------------------------------


@router.get("/reports/runs", response_model=Envelope[list[ReportRunOut]])
def runs(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[ReportRunOut]]:
    """The reader's runs, the latest first: what they exported and what schedules made them."""
    repository = RunRepository(connection, context)
    rows = repository.runs(scope, RUN_LIMIT)
    meta = _meta(
        connection, scope, context, shown=len(rows), total=repository.count(scope), unit=RUNS
    )
    return Envelope(data=[run_out(row) for row in rows], meta=meta)


@router.get("/reports/runs/{run_id}/file")
def run_file(
    run_id: UUID,
    request: Request,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Response:
    """A kept file, handed back while the reader's access still covers what it was made under."""
    run = RunRepository(connection, context).run(scope, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NO_SUCH_RUN)
    if run.storage_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NO_FILE)
    if not still_within(run, scope):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=NARROWED)
    store = request.app.state.report_store
    if store is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=NOT_KEPT)
    try:
        body = store.get(run.storage_key)
    except NoData as missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GONE) from missing
    except CollectionError as failure:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(failure)
        ) from failure
    return Response(
        content=body,
        media_type=MEDIA_TYPES[run.format],
        headers={
            "Content-Disposition": f'attachment; filename="{file_name(run)}"',
            "Cache-Control": "no-store",
        },
    )


def still_within(run: RunRow, scope: Scope) -> bool:
    """True while the reader's scope covers every account the file was made under.

    A reader of the whole estate covers anything. A narrowed reader covers a file made for a
    narrowed scope whose accounts they all still hold, and never one made for the whole estate.
    """
    if scope.is_global:
        return True
    if run.scope_global:
        return False
    held = {account.account_id for account in scope.accounts}
    return set(run.scope_accounts) <= held


def file_name(run: RunRow) -> str:
    """meter, the route, the day: the name the export gave the same file when it was made."""
    slug = re.sub(r"[^a-z0-9]+", "-", run.view_path.removeprefix(API_PREFIX).lower()).strip("-")
    return f"meter-{slug or 'report'}-{run.made_at:%Y-%m-%d}.{run.format}"
