"""Plans priced before deployment, and how close the estimates came. P16, FEAT-095 to 097.

TASK-P16-008, spec section 8. Plans, estimates and comparisons belong to the organization, a plan
naming no account until it is applied, spec section 5.8 and ADR-0025, so a narrowed reader is
answered 404 with the reason, as the commitment routes answer, never with a list of nothing. Every
read goes through the scope dependency and the repository guard, constraint 3. The routes only
read: the worker prices and comments, ADR-0036, and a plan's arrival is TASK-P16-010's.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.estimates import (
    EstimateComparisonRepository,
    EstimateLineRepository,
    EstimateRow,
    PlanEstimateRepository,
    PlannedChangeRepository,
    PlanPullRequestRepository,
    PlanRepository,
)
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.exports import ExportSpec, exportable, rows_in
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import (
    Envelope,
    EstimateAccuracyOut,
    EstimateAccuracyRowOut,
    EstimateComparisonOut,
    EstimateComponentOut,
    EstimateLineOut,
    EstimatesOut,
    Meta,
    PlanEstimateDetailOut,
    PlanEstimateOut,
)
from finops_core.domain.tenant import Scope
from finops_query.estimate_accuracy import WINDOW_DAYS, WITHIN_PERCENT, Verdict, accuracy

router = APIRouter(prefix=API_PREFIX, tags=["estimates"])

NEEDS_THE_ORGANIZATION = (
    "A plan names no account until it is applied, so its estimate belongs to the organization "
    "and needs a scope that covers the whole of it. See ADR-0025 and the P16 spec, section 5.8."
)
NO_SUCH_PLAN = "No plan has that identifier."
ASSUMPTIONS = (
    "Modelled from AWS's on demand list prices, 730 hours a month, in USD, at the price list "
    "version each component names. Commitment discounts are not applied. A change Meter cannot "
    "price says why and adds nothing to the totals."
)
NEWEST = Query(default=200, ge=1, le=1000, description="How many plans, the newest first.")


def _organization_only(scope: Scope) -> None:
    """A 404 for a narrowed reader, as the commitment routes answer, never a list of nothing."""
    if not scope.is_global:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NEEDS_THE_ORGANIZATION)


def _meta(
    connection: Connection, scope: Scope, context: AccessContext, rows: Sequence[Any]
) -> Meta:
    """One organization of one, ADR-0025, with the oldest truth and the newest fetch."""
    return build_meta(
        connection,
        scope,
        context,
        visible=1,
        coverage=(1, 1),
        coverage_unit="payer",
        as_of=min((row.as_of for row in rows), default=None),
        collected_at=max((row.collected_at for row in rows), default=None),
    )


def _plan_out(
    plan: EstimateRow, estimate: EstimateRow | None, pull_request: EstimateRow | None
) -> PlanEstimateOut:
    def priced(name: str) -> Any:
        return None if estimate is None else getattr(estimate, name)

    return PlanEstimateOut(
        plan_id=plan.plan_id,
        repository=plan.repository,
        pull_request=plan.pull_request,
        head_sha=plan.head_sha,
        folder=plan.folder,
        status=plan.status,
        reason=plan.reason,
        received_at=plan.received_at,
        monthly_before=priced("monthly_before"),
        monthly_after=priced("monthly_after"),
        monthly_change=priced("monthly_change"),
        currency=priced("currency"),
        priced_lines=priced("priced_lines"),
        unpriced_lines=priced("unpriced_lines"),
        comment_status=priced("comment_status"),
        comment_url=priced("comment_url"),
        comment_reason=priced("comment_reason"),
        pull_request_state=None if pull_request is None else pull_request.state,
        as_of=plan.as_of,
        collected_at=plan.collected_at if estimate is None else estimate.collected_at,
    )


def _plans_out(
    connection: Connection, scope: Scope, context: AccessContext, plans: Sequence[EstimateRow]
) -> list[PlanEstimateOut]:
    """Each plan with its estimate and its pull request's state, read for these plans alone."""
    estimates = {
        row.plan_id: row
        for row in PlanEstimateRepository(connection, context).of(
            scope, [plan.plan_id for plan in plans]
        )
    }
    states = {
        (row.repository, row.pull_request): row
        for row in PlanPullRequestRepository(connection, context).of(
            scope, {plan.repository for plan in plans}
        )
    }
    return [
        _plan_out(
            plan, estimates.get(plan.plan_id), states.get((plan.repository, plan.pull_request))
        )
        for plan in plans
    ]


@router.get("/estimates/accuracy", response_model=Envelope[EstimateAccuracyOut])
@exportable(
    ExportSpec(
        title="Estimate accuracy",
        row_model=EstimateAccuracyRowOut,
        rows=rows_in("types"),
        metric=(
            "Estimates modelled from list prices, set against thirty measured billed days at list "
            "cost: how many came within 10 percent, and the median absolute percentage error"
        ),
    )
)
def estimate_accuracy(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[EstimateAccuracyOut]:
    """Accuracy by resource type and in all, from the judged comparisons alone. FEAT-097."""
    _organization_only(scope)
    rows = EstimateComparisonRepository(connection, context).every(scope)
    judged = accuracy(
        (row.resource_type, Verdict(row.verdict), row.variance_percent) for row in rows
    )
    found = EstimateAccuracyOut(
        types=[
            EstimateAccuracyRowOut(
                resource_type=one.resource_type,
                compared=one.compared,
                within=one.within,
                median_error_percent=one.median_error_percent,
            )
            for one in judged
        ],
        within_percent=WITHIN_PERCENT,
        window_days=WINDOW_DAYS,
        pending=sum(1 for row in rows if row.verdict == Verdict.PENDING),
        not_compared=sum(1 for row in rows if row.verdict == Verdict.NOT_COMPARED),
    )
    return Envelope(data=found, meta=_meta(connection, scope, context, rows))


@router.get("/estimates", response_model=Envelope[EstimatesOut])
@exportable(
    ExportSpec(
        title="Plan estimates",
        row_model=PlanEstimateOut,
        rows=rows_in("plans"),
        metric="Each plan's monthly estimate, modelled from AWS's on demand list prices",
    )
)
def estimates(
    limit: int = NEWEST,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[EstimatesOut]:
    """The plans received, the newest first, each with its estimate and comment. FEAT-095."""
    _organization_only(scope)
    plans = PlanRepository(connection, context).newest(scope, limit + 1)
    shown = plans[:limit]
    found = EstimatesOut(
        plans=_plans_out(connection, scope, context, shown), more=len(plans) > limit
    )
    return Envelope(data=found, meta=_meta(connection, scope, context, shown))


def _comparison_out(row: EstimateRow) -> EstimateComparisonOut:
    fields = (name for name in EstimateComparisonOut.model_fields if name != "basis")
    return EstimateComparisonOut(**{name: getattr(row, name) for name in fields})


def _line_out(
    line: EstimateRow, change: EstimateRow | None, comparison: EstimateRow | None
) -> EstimateLineOut:
    return EstimateLineOut(
        address=line.address,
        resource_type=line.resource_type,
        actions=list(line.actions),
        region=line.region,
        monthly_before=line.monthly_before,
        monthly_after=line.monthly_after,
        reason=line.reason,
        notes=list(line.notes),
        unknown=[] if change is None else list(change.unknown),
        withheld=[] if change is None else list(change.withheld),
        components=[EstimateComponentOut(**part) for part in line.components],
        comparison=None if comparison is None else _comparison_out(comparison),
    )


def _by_address(rows: Sequence[EstimateRow]) -> Mapping[str, EstimateRow]:
    return {row.address: row for row in rows}


@router.get("/estimates/{plan_id}", response_model=Envelope[PlanEstimateDetailOut])
@exportable(
    ExportSpec(
        title="Plan estimate",
        row_model=EstimateLineOut,
        rows=rows_in("lines"),
        metric="Each change's monthly figures, modelled from AWS's on demand list prices",
        note="Each line's priced components and its comparison with the bill are on the screen",
    )
)
def estimate(
    plan_id: UUID,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[PlanEstimateDetailOut]:
    """One plan's lines, the unpriced first, and what every figure rests on. FEAT-095."""
    _organization_only(scope)
    plan = PlanRepository(connection, context).one(scope, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NO_SUCH_PLAN)
    [shown] = _plans_out(connection, scope, context, [plan])
    lines = EstimateLineRepository(connection, context).of(scope, [plan_id])
    changes = _by_address(PlannedChangeRepository(connection, context).of(scope, [plan_id]))
    compared = _by_address(EstimateComparisonRepository(connection, context).of(scope, [plan_id]))
    ordered = sorted(lines, key=lambda line: (line.reason is None, line.address))
    found = PlanEstimateDetailOut(
        plan=shown,
        lines=[
            _line_out(line, changes.get(line.address), compared.get(line.address))
            for line in ordered
        ],
        assumptions=ASSUMPTIONS,
    )
    return Envelope(data=found, meta=_meta(connection, scope, context, [shown]))
