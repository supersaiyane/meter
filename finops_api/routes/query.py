"""The query governance routes, per P2 spec section 8.2.

Three of the eight the specification names. The other five read data that does
not exist yet: enforcement and its revoke need TASK-P2-016, parked on the AWS
infrastructure ISS-122 records as never provisioned; accuracy needs FEAT-018;
and the two remediation routes need TASK-P2-019. Shipping them against empty
tables would answer a question with a confident nothing, which is the one answer
this product may not give.

`scope_coverage` on every response counts unreachable instances, so a total
drawn from part of an estate says so. That is why the instances route sits
beside the findings route rather than behind it.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.query import (
    QueryFindingRepository,
    SurfaceInstanceRepository,
)
from finops_api.deps import get_access_context, get_connection, get_scope, get_settings
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import (
    Envelope,
    QueryFindingDetailOut,
    QueryFindingOut,
    SurfaceInstanceOut,
)
from finops_core.config import Settings
from finops_core.domain.tenant import Scope

router = APIRouter(prefix=API_PREFIX, tags=["query"])


def _finding(row: Any) -> QueryFindingOut:
    return QueryFindingOut(
        finding_id=row.finding_id,
        dashboard_uid=row.dashboard_uid,
        dashboard_title=row.dashboard_title,
        panel_title=row.panel_id,
        folder_uid=row.folder_uid,
        engine=row.engine,
        origin=row.origin,
        refresh_seconds=row.refresh_seconds,
        window_seconds=row.range_seconds,
        runs_per_day=row.runs_per_day,
        scan_bytes_per_run=row.scan_bytes_per_run,
        monthly_cost=row.cost_month_usd,
        provenance=row.provenance,
        measured_runs=row.measured_runs,
        severity=row.severity,
        # Null rather than a placeholder. The screen decides what an absence
        # reads as; the API does not put a word in its mouth.
        owner=row.owner_email,
        owner_source=row.owner_source,
        why=row.why,
        as_of=row.as_of,
        collected_at=row.collected_at,
    )


@router.get("/query/findings", response_model=Envelope[list[QueryFindingOut]])
def query_findings(
    scope: Scope = Depends(get_scope),
    connection: Connection = Depends(get_connection),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[QueryFindingOut]]:
    rows = QueryFindingRepository(connection, context).ranked(scope)
    findings = [_finding(row) for row in rows]
    return Envelope(
        data=findings,
        meta=build_meta(
            connection,
            scope,
            context,
            visible=len(findings),
            rows=rows,
            # Workspaces, not findings. How many findings came back says nothing
            # about how much of the estate they were drawn from, and an
            # unreachable workspace hides an unknown number of them.
            coverage=SurfaceInstanceRepository(connection, context).coverage(scope),
        ),
    )


@router.get("/query/findings/{finding_id}", response_model=Envelope[QueryFindingDetailOut])
def query_finding(
    finding_id: UUID,
    scope: Scope = Depends(get_scope),
    connection: Connection = Depends(get_connection),
    context: AccessContext = Depends(get_access_context),
    settings: Settings = Depends(get_settings),
) -> Envelope[QueryFindingDetailOut]:
    row = QueryFindingRepository(connection, context).one(scope, finding_id)
    if row is None:
        # A finding outside the caller's scope is indistinguishable from one
        # that does not exist, deliberately: a 404 that differed from a 403
        # would tell an unauthorised caller that the row is there.
        raise HTTPException(status_code=404, detail="no such finding")

    base = _finding(row)
    target = row.target or {}
    detail = QueryFindingDetailOut(
        **base.model_dump(),
        query_text=row.query_text,
        targets=list(target.get("targets") or ()),
        region=target.get("region"),
        last_editor=row.last_editor,
        rate_usd_per_gib=settings.query_logs_scan_price_per_gb,
        # FEAT-018 publishes this. Until it does the field is null and the
        # screen says the accuracy is not yet published, which is worse looking
        # and more honest than a number nobody measured.
        accuracy_percent=None,
    )
    return Envelope(
        data=detail,
        meta=build_meta(
            connection,
            scope,
            context,
            visible=1,
            rows=[row],
            coverage=SurfaceInstanceRepository(connection, context).coverage(scope),
        ),
    )


@router.get("/query/instances", response_model=Envelope[list[SurfaceInstanceOut]])
def query_instances(
    scope: Scope = Depends(get_scope),
    connection: Connection = Depends(get_connection),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[SurfaceInstanceOut]]:
    rows = SurfaceInstanceRepository(connection, context).all_with_counts(scope)
    instances = [
        SurfaceInstanceOut(
            instance_id=row.instance_id,
            name=row.name,
            kind=row.kind,
            endpoint=row.endpoint,
            account_id=row.account_id,
            region_id=row.region_id,
            reachable=row.reachable,
            unreachable_reason=row.unreachable_reason,
            # Unknown, not zero, when the instance could not be read. An
            # unreachable workspace reporting a count of nought would make the
            # findings list look complete when it is not.
            #
            # The other half of that distinction: a workspace that was read and
            # holds nothing is a zero, not an unknown. The outer join gives null
            # for both, and passing that through would render "nothing to see"
            # and "we could not look" identically.
            query_count=(row.query_count or 0) if row.reachable else None,
            as_of=row.as_of,
            collected_at=row.collected_at,
        )
        for row in rows
    ]
    repository = SurfaceInstanceRepository(connection, context)
    return Envelope(
        data=instances,
        meta=build_meta(
            connection,
            scope,
            context,
            visible=len(instances),
            rows=rows,
            # An unreachable workspace is listed and is still not covered, so
            # the count here is smaller than the number of rows on the page.
            coverage=repository.coverage(scope),
        ),
    )
