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

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.engine import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.query import (
    AdhocQueryRepository,
    QueryFindingRepository,
    SurfaceInstanceRepository,
)
from finops_api.deps import get_access_context, get_connection, get_scope, get_settings
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import (
    AdhocQueryOut,
    Envelope,
    FailureOut,
    QueryFindingDetailOut,
    QueryFindingOut,
    QueryGroupOut,
    RemediationOut,
    SurfaceInstanceOut,
)
from finops_core.config import Settings
from finops_core.domain.query import SurfaceInstance, SurfaceKind, WriteLevel
from finops_core.domain.tenant import Scope
from finops_ingest.remediation import apply_panel_rewrite, undo_change
from finops_query.gate import rule_from
from finops_query.severity import (
    CAUSE_LABEL,
    ENGINE_SCAN,
    severity_for,
    thresholds_from,
)

router = APIRouter(prefix=API_PREFIX, tags=["query"])


def _unreadable(rows: Any) -> tuple[FailureOut, ...]:
    """Unreachable workspaces, as failures on the envelope.

    A gap with no cause beside it is a gap the interface has to guess at, and it
    guessed wrong: it told the reader the missing part was outside their scope
    when Meter itself had been refused. ISS-152.
    """
    return tuple(
        FailureOut(
            scope_key=row.name,
            collector="query_audit",
            cause=row.unreachable_reason,
            remediation=(
                f"Meter could not read {row.name}. Check the workspace permits the "
                f"Meter reader role, then rerun the query audit collector."
            ),
            occurrences=1,
            # When the workspace was last read, which is the collected_at on the
            # row. Not now: the failure is as old as the reading that found it,
            # and stamping it with the request time would make a stale problem
            # look like it had just happened.
            last_seen_at=row.collected_at,
        )
        for row in rows
    )


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
        # Defaulted the same way the grouping query defaults it, so a row
        # written before the column existed files under the same group here.
        cause=row.cause or ENGINE_SCAN,
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
    surfaces = SurfaceInstanceRepository(connection, context)
    return Envelope(
        data=findings,
        meta=build_meta(
            connection,
            scope,
            context,
            visible=len(findings),
            rows=rows,
            extra_failures=_unreadable(surfaces.unreachable(scope)),
            # Workspaces, not findings. How many findings came back says nothing
            # about how much of the estate they were drawn from, and an
            # unreachable workspace hides an unknown number of them.
            coverage=surfaces.coverage(scope),
            coverage_unit="workspaces",
        ),
    )


@router.get("/query/groups", response_model=Envelope[list[QueryGroupOut]])
def query_groups(
    scope: Scope = Depends(get_scope),
    connection: Connection = Depends(get_connection),
    context: AccessContext = Depends(get_access_context),
    settings: Settings = Depends(get_settings),
) -> Envelope[list[QueryGroupOut]]:
    """Findings summed by cause, worst group first. ADR-0016.

    A separate route rather than a shape on the findings route, because the two
    answer different questions and a caller that wanted the list would otherwise
    have to know which shape it was getting.
    """
    bands = thresholds_from(settings)
    rows = QueryFindingRepository(connection, context).grouped(scope)
    surfaces = SurfaceInstanceRepository(connection, context)
    groups = [
        QueryGroupOut(
            cause=row.cause,
            label=CAUSE_LABEL.get(row.cause, row.cause),
            findings=row.findings,
            monthly_cost=row.monthly_cost,
            severity=severity_for(row.monthly_cost, bands),
            as_of=row.as_of,
            collected_at=row.collected_at,
        )
        for row in rows
    ]
    return Envelope(
        data=groups,
        meta=build_meta(
            connection,
            scope,
            context,
            visible=len(groups),
            rows=rows,
            extra_failures=_unreadable(surfaces.unreachable(scope)),
            coverage=surfaces.coverage(scope),
            coverage_unit="workspaces",
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

    surfaces = SurfaceInstanceRepository(connection, context)
    applied = QueryFindingRepository(connection, context).latest_change(scope, finding_id)
    base = _finding(row)
    target = row.target or {}
    detail = QueryFindingDetailOut(
        **base.model_dump(),
        query_text=row.query_text,
        targets=list(target.get("targets") or ()),
        region=target.get("region"),
        last_editor=row.last_editor,
        rate_usd_per_gib=settings.query_logs_scan_price_per_gb,
        # So the screen can decide whether an undo control exists at all. A
        # control that looks available and does nothing is worse than an absent
        # one, which is the rule TASK-P2-025 states for revoke and holds here.
        applied_change_id=(applied.change_id if applied is not None else None),
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
            extra_failures=_unreadable(surfaces.unreachable(scope)),
            coverage=surfaces.coverage(scope),
            coverage_unit="workspaces",
        ),
    )


def _instance_for(
    connection: Connection, context: AccessContext, scope: Scope, row: Any
) -> SurfaceInstance:
    """The domain instance a remediation writes to.

    Built from the stored row rather than taken from a collector, because the
    API has no collector and the surface adapter only needs enough to address
    the workspace. It is still scoped: an instance outside the caller's scope
    is not found, and the write never starts.
    """
    found = next(
        (
            instance
            for instance in SurfaceInstanceRepository(connection, context).all_with_counts(scope)
            if instance.instance_id == row.instance_id
        ),
        None,
    )
    if found is None:
        raise HTTPException(status_code=404, detail="no such instance")
    return SurfaceInstance(
        surface_id=str(found.name),
        name=str(found.name),
        kind=SurfaceKind.MANAGED_GRAFANA,
        location=str(found.endpoint),
        reachable=bool(found.reachable),
        unreachable_cause=found.unreachable_reason,
    )


def _control_of(request: Request) -> Any:
    """The surface adapter a remediation writes through, or None.

    Injected at `create_app` like the health check, and absent by default. A
    deployment that has not configured one gets a refusal naming that, rather
    than a route that reports success over a write nothing performed.
    """
    return getattr(request.app.state, "remediation_control", None)


def _violates(row: Any, settings: Settings) -> bool:
    """Whether this finding is an explicit policy violation.

    The plan's own rule for this task: do not rewrite anything that is not one.
    A judgement call is a recommendation, and rewriting somebody's dashboard on
    a judgement call is how a remediation feature gets switched off for good.

    The same rule the CI gate blocks on, from the same settings, so a panel
    refused at merge and a panel remediated in place are the same shape.
    """
    # Lowercased, because the engine has two spellings for one fact: the
    # classifier produces `logs_insights` and `ck_query_definition__engine_valid`
    # stores `LOGS_INSIGHTS`. Comparing them raw matches neither, and the rule
    # then quietly finds no violation anywhere, which is the worst way for a
    # policy check to fail.
    return rule_from(settings).broken_by(
        str(row.engine).lower(), row.refresh_seconds or 0, row.range_seconds
    )


@router.post("/query/remediate/{finding_id}", response_model=Envelope[RemediationOut])
def remediate(
    finding_id: UUID,
    request: Request,
    scope: Scope = Depends(get_scope),
    connection: Connection = Depends(get_connection),
    context: AccessContext = Depends(get_access_context),
    settings: Settings = Depends(get_settings),
) -> Envelope[RemediationOut]:
    """Bring one panel back inside the policy, subject to the write level.

    Architectural constraint 6 makes v1 read only, and this does not change
    that: `query_write_level` defaults to `none` everywhere, so this route
    refuses on an untouched deployment. Enabling it is a decision somebody
    signs rather than one they inherit, which is what FEAT-017 asks for.

    The change is a single field. The refresh is raised to the same threshold
    the reports warn at and the gate blocks on, because a remediation that
    lands on a different number from the one the product has been quoting
    teaches a reader that neither is real.
    """
    repository = QueryFindingRepository(connection, context)
    row = repository.one(scope, finding_id)
    if row is None:
        raise HTTPException(status_code=404, detail="no such finding")

    surfaces = SurfaceInstanceRepository(connection, context)
    meta = build_meta(
        connection,
        scope,
        context,
        visible=1,
        rows=[row],
        coverage=surfaces.coverage(scope),
        coverage_unit="workspaces",
    )

    if not _violates(row, settings):
        return Envelope(
            data=RemediationOut(
                finding_id=finding_id,
                applied=False,
                detail=(
                    "this finding is not an explicit policy violation, and a "
                    "judgement call is a recommendation rather than a remediation"
                ),
            ),
            meta=meta,
        )

    control = _control_of(request)
    if control is None:
        return Envelope(
            data=RemediationOut(
                finding_id=finding_id,
                applied=False,
                detail="no remediation control is configured for this deployment",
            ),
            meta=meta,
        )

    outcome = apply_panel_rewrite(
        connection=connection,
        tenant_id=scope.tenant_id,
        instance=_instance_for(connection, context, scope, row),
        control=control,
        fingerprint=str(row.fingerprint),
        changes={"refresh_seconds": settings.query_refresh_warn_seconds},
        write_level=WriteLevel(settings.query_write_level),
        applied_by=str(context.principal_id),
        query_pk=row.query_id,
        instance_pk=row.instance_id,
    )
    return Envelope(
        data=RemediationOut(
            finding_id=finding_id,
            applied=outcome.applied,
            reverted=outcome.reverted,
            detail=outcome.detail,
            change_id=outcome.change_id,
        ),
        meta=meta,
    )


@router.post("/query/remediate/{finding_id}/undo", response_model=Envelope[RemediationOut])
def undo_remediation(
    finding_id: UUID,
    request: Request,
    scope: Scope = Depends(get_scope),
    connection: Connection = Depends(get_connection),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[RemediationOut]:
    """Put back what the last remediation replaced.

    The last one, not an arbitrary earlier one: undoing out of order restores a
    state a later change already replaced. It takes no write level, because
    undoing is how somebody stops a change they did not want, and gating the
    exit behind the same flag as the entrance would trap them.
    """
    repository = QueryFindingRepository(connection, context)
    row = repository.one(scope, finding_id)
    if row is None:
        raise HTTPException(status_code=404, detail="no such finding")

    surfaces = SurfaceInstanceRepository(connection, context)
    meta = build_meta(
        connection,
        scope,
        context,
        visible=1,
        rows=[row],
        coverage=surfaces.coverage(scope),
        coverage_unit="workspaces",
    )
    change = repository.latest_change(scope, finding_id)
    if change is None:
        return Envelope(
            data=RemediationOut(
                finding_id=finding_id,
                applied=False,
                detail="nothing to undo: this finding has no change that is still applied",
            ),
            meta=meta,
        )

    control = _control_of(request)
    if control is None:
        return Envelope(
            data=RemediationOut(
                finding_id=finding_id,
                applied=False,
                change_id=change.change_id,
                detail="no remediation control is configured for this deployment",
            ),
            meta=meta,
        )

    outcome = undo_change(
        connection=connection,
        tenant_id=scope.tenant_id,
        instance=_instance_for(connection, context, scope, row),
        control=control,
        change_id=change.change_id,
        reverted_by=str(context.principal_id),
    )
    return Envelope(
        data=RemediationOut(
            finding_id=finding_id,
            applied=outcome.applied,
            reverted=outcome.reverted,
            detail=outcome.detail,
            change_id=change.change_id,
        ),
        meta=meta,
    )


@router.get("/query/adhoc", response_model=Envelope[list[AdhocQueryOut]])
def query_adhoc(
    scope: Scope = Depends(get_scope),
    connection: Connection = Depends(get_connection),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[AdhocQueryOut]]:
    """Queries that ran and belong to no panel and no alert rule. FEAT-051.

    Coverage is workspaces, the same denominator the other query routes use,
    even though these rows hang off no workspace. It is the right one anyway:
    an account whose workspaces could not be read is an account whose panels
    are unknown, and a query is ad hoc only if no panel claims it. Reporting a
    full coverage here while a workspace was unreadable would assert that
    nothing claims these queries when Meter could not check.
    """
    rows = AdhocQueryRepository(connection, context).most_expensive(scope)
    queries = [
        AdhocQueryOut(
            adhoc_id=row.adhoc_id,
            account_id=row.account_id,
            region_id=row.region_id,
            query_text=row.query_text,
            runs=row.runs,
            scan_bytes=row.scan_bytes,
            cost_usd=row.cost_usd,
            principal=row.principal,
            as_of=row.as_of,
            collected_at=row.collected_at,
        )
        for row in rows
    ]
    instances = SurfaceInstanceRepository(connection, context)
    unreadable = instances.unreachable(scope)
    return Envelope(
        data=queries,
        meta=build_meta(
            connection,
            scope,
            context,
            visible=len(queries),
            rows=rows,
            extra_failures=_unreadable(unreadable),
            coverage=instances.coverage(scope),
            coverage_unit="workspaces",
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
            refresh_floor_seconds=row.refresh_floor_seconds,
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
            extra_failures=_unreadable(row for row in rows if not row.reachable),
            # An unreachable workspace is listed and is still not covered, so
            # the count here is smaller than the number of rows on the page.
            coverage=repository.coverage(scope),
            coverage_unit="workspaces",
        ),
    )
