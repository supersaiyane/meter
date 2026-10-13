"""The commitments the organization holds, what they saved, and what to buy. P14, FEAT-086 to 090.

TASK-P14-004 onwards, P14 spec section 8. Every read goes through the scope dependency and the
repository guard, constraint 3. The savings rate is scoped as the bill is, by account; what is held
and what to buy belong to the payer, ADR-0025, and are visible at global scope only.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.commitments import (
    CommitmentInventoryRepository,
    CommitmentPolicyRepository,
)
from finops_api.db.repositories.cost import CostRepository
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.exports import ExportSpec, exportable, rows_in
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import (
    CalendarMonthOut,
    CommitmentCalendarOut,
    CommitmentInventoryOut,
    CommitmentPolicyIn,
    CommitmentPolicyOut,
    Envelope,
    HeldCommitmentOut,
    Meta,
    SavingsRateMonthOut,
    SavingsRateOut,
)
from finops_core.domain.commitments import (
    DEFAULT_POLICY,
    DEFAULT_POLICY_REASON,
    UNREADABLE,
    CommitmentPolicy,
)
from finops_core.domain.tenant import Scope
from finops_query.commitment_calendar import Held, calendar
from finops_query.savings_rate import savings_rate

router = APIRouter(prefix=API_PREFIX, tags=["commitments"])

MONTHS = Query(default=12, ge=1, le=36, description="How many billing months, the newest last.")


def months_before(period: date, count: int) -> date:
    """The first day of the billing month `count` months before `period`."""
    index = period.year * 12 + period.month - 1 - count
    return date(index // 12, index % 12 + 1, 1)


@router.get("/commitments/savings-rate", response_model=Envelope[SavingsRateOut])
@exportable(
    ExportSpec(
        title="Effective savings rate",
        row_model=SavingsRateMonthOut,
        rows=rows_in("months"),
        metric="One minus Effective Cost over List Cost, measured, on usage lines with a List Cost",
    )
)
def commitments_savings_rate(
    months: int = MONTHS,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[SavingsRateOut]:
    """The effective savings rate by billing month, the oldest first. FEAT-087."""
    costs = CostRepository(connection, context)
    latest = costs.latest_period(scope)
    if latest is None:
        empty = SavingsRateOut(months=[])
        return Envelope(data=empty, meta=build_meta(connection, scope, context, visible=0))
    rows = costs.savings_rate_months(scope, months_before(latest, months - 1), latest)
    found = SavingsRateOut(
        months=[
            SavingsRateMonthOut(
                **vars(
                    savings_rate(
                        row[0],
                        effective_cost=row[1],
                        list_cost=row[2],
                        lines=int(row[3]),
                        lines_without_list_cost=int(row[4]),
                        effective_cost_without_list_cost=row[5],
                    )
                ),
                rate_basis="measured",
            )
            for row in rows
        ]
    )
    meta = build_meta(
        connection,
        scope,
        context,
        visible=costs.accounts_in(scope, latest),
        as_of=min((row[6] for row in rows), default=None),
        collected_at=max((row[7] for row in rows), default=None),
    )
    return Envelope(data=found, meta=meta)


#: What a narrowed reader is told: commitments belong to the payer, ADR-0025.
NEEDS_THE_PAYER = (
    "Commitments belong to the payer and cannot be apportioned to accounts, so they need a scope "
    "that covers the whole organization. See ADR-0025."
)


def _payer_only(scope: Scope) -> None:
    """A 404 for a narrowed reader, as `/cost/commitments` answers, never a list of nothing."""
    if not scope.is_global:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NEEDS_THE_PAYER)


def _payer_meta(
    connection: Connection, scope: Scope, context: AccessContext, rows: Sequence[Any]
) -> Meta:
    """One payer of one, ADR-0025, with the oldest truth and the newest fetch of the rows."""
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


@router.get("/commitments/inventory", response_model=Envelope[CommitmentInventoryOut])
@exportable(
    ExportSpec(
        title="Commitments held",
        row_model=HeldCommitmentOut,
        rows=rows_in("commitments"),
        metric="Each commitment's term, end and payment, measured, from the service that sold it",
    )
)
def commitments_inventory(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[CommitmentInventoryOut]:
    """Every commitment the organization holds, the soonest ending first. FEAT-086."""
    _payer_only(scope)
    rows = CommitmentInventoryRepository(connection, context).held(scope)
    found = CommitmentInventoryOut(
        commitments=[
            HeldCommitmentOut(
                **{name: getattr(row, name) for name in HeldCommitmentOut.model_fields}
            )
            for row in rows
        ],
        unreadable=list(UNREADABLE),
    )
    return Envelope(data=found, meta=_payer_meta(connection, scope, context, rows))


def _policy(connection: Connection, scope: Scope, context: AccessContext) -> CommitmentPolicyOut:
    row = CommitmentPolicyRepository(connection, context).current(scope)
    if row is None:
        return CommitmentPolicyOut(
            **vars(DEFAULT_POLICY),
            reason=DEFAULT_POLICY_REASON,
            updated_by=None,
            updated_at=None,
            is_default=True,
        )
    return CommitmentPolicyOut(
        target_coverage=row.target_coverage,
        term_years=row.term_years,
        payment_option=row.payment_option,
        ladder_limit=row.ladder_limit,
        reason=row.reason,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
        is_default=False,
    )


@router.get("/commitments/calendar", response_model=Envelope[CommitmentCalendarOut])
@exportable(
    ExportSpec(
        title="Commitment renewals",
        row_model=CalendarMonthOut,
        rows=rows_in("months"),
        metric="What ends each month and its share of the hourly commitment held",
    )
)
def commitments_calendar(
    months: int = MONTHS,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[CommitmentCalendarOut]:
    """What ends in each of the next months, against the ladder limit. FEAT-088."""
    _payer_only(scope)
    rows = CommitmentInventoryRepository(connection, context).held(scope)
    limit = _policy(connection, scope, context).ladder_limit
    found, total, basis = calendar(
        [Held(**{name: getattr(row, name) for name in Held.__dataclass_fields__}) for row in rows],
        today=datetime.now(UTC).date(),
        months=months,
        ladder_limit=limit,
    )
    out = CommitmentCalendarOut(
        months=[
            CalendarMonthOut(
                month=one.month,
                commitments=list(one.commitments),
                hourly_value=one.hourly_value,
                share=one.share,
                basis=one.basis,  # type: ignore[arg-type]
                over_limit=one.over_limit,
            )
            for one in found
        ],
        ladder_limit=limit,
        total_hourly_value=total,
        total_basis=basis,  # type: ignore[arg-type]
    )
    return Envelope(data=out, meta=_payer_meta(connection, scope, context, rows))


@router.get("/commitments/policy", response_model=Envelope[CommitmentPolicyOut])
def commitments_policy(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[CommitmentPolicyOut]:
    """What the tenant's purchase plans aim for, or the default nobody has changed. FEAT-088."""
    _payer_only(scope)
    found = _policy(connection, scope, context)
    when = [] if found.updated_at is None else [_Stamp(found.updated_at)]
    return Envelope(data=found, meta=_payer_meta(connection, scope, context, when))


@router.put("/commitments/policy", response_model=Envelope[CommitmentPolicyOut])
def change_commitments_policy(
    body: CommitmentPolicyIn,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[CommitmentPolicyOut] | JSONResponse:
    """Change the policy, with a reason. A person whose scope is the organization only."""
    repository = CommitmentPolicyRepository(connection, context)
    if not scope.is_global or scope.principal_id is None:
        # Answered rather than raised, so the rollback cannot take the DENIED audit row with it.
        repository.refuse(scope)
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN, content={"detail": NEEDS_THE_PAYER}
        )
    policy = CommitmentPolicy(
        target_coverage=body.target_coverage,
        term_years=body.term_years,
        payment_option=body.payment_option,
        ladder_limit=body.ladder_limit,
    )
    repository.change(scope, policy, reason=body.reason.strip(), at=datetime.now(UTC))
    found = _policy(connection, scope, context)
    stamp = [] if found.updated_at is None else [_Stamp(found.updated_at)]
    return Envelope(data=found, meta=_payer_meta(connection, scope, context, stamp))


class _Stamp:
    """A policy's change as a fact: true and fetched when it was made."""

    def __init__(self, at: datetime) -> None:
        self.as_of = at
        self.collected_at = at
