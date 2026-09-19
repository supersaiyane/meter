"""The cost surface, per P1 spec section 8.

Four routes over one table. Allocation is not a fifth thing: it is the same
rows grouped by a tag key, and a separate implementation of that would be a
second implementation of one query.

**An open period says so in the payload.** Whether a billing period is still
accruing is known here, because this is the side that knows what today is
relative to the period's exclusive end. A frontend inferring it from a date
would have to carry the same calendar rule, and two copies of a calendar rule
is one that is eventually wrong in one of them.

**No route guesses a period.** Each takes one, or asks the repository which is
latest. A default of "this month" answers a different question in the first
minute of a new month than it did in the last minute of the old one.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.cost import GROUPABLE, CostRepository, previous_month
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import (
    CostDayOut,
    CostSliceOut,
    CostSummaryOut,
    CostTotalOut,
    Envelope,
)
from finops_core.domain.cost import BillingPeriod
from finops_core.domain.tenant import Scope

router = APIRouter(prefix=API_PREFIX, tags=["cost"])

#: What a caller gets when the tenant has no cost at all. A 404 says the thing
#: does not exist. A zero would say the estate spent nothing, which is a claim
#: nobody has earned the right to make.
NO_COST = "No billing period has been collected for this tenant yet."


def _period_end(start: date) -> date:
    return date(start.year + (start.month // 12), (start.month % 12) + 1, 1)


def _total(period: date, row: Any, at: datetime) -> CostTotalOut:
    """One period's figures, with whether it is still accruing."""
    effective, billed, line_items, *_ = row
    return CostTotalOut(
        period=period,
        is_open=BillingPeriod(start=period, end=_period_end(period)).is_open(at=at),
        effective_cost=Decimal(effective),
        billed_cost=Decimal(billed),
        line_items=int(line_items),
    )


def _resolve(repository: CostRepository, scope: Scope, asked: date | None) -> date:
    """The period the caller asked for, or the newest one there is."""
    if asked is not None:
        return asked
    latest = repository.latest_period(scope)
    if latest is None:
        raise HTTPException(status_code=404, detail=NO_COST)
    return latest


def _slices(rows: Any) -> list[CostSliceOut]:
    return [
        CostSliceOut(
            name=str(name),
            effective_cost=Decimal(effective),
            billed_cost=Decimal(billed),
            line_items=int(count),
        )
        for name, effective, billed, count in rows
    ]


def _grouped(
    connection: Connection,
    scope: Scope,
    context: AccessContext,
    period: date | None,
    dimension: str,
) -> Envelope[list[CostSliceOut]]:
    """Shared by the two grouping routes, which differ only in the column.

    The dimension is one of this module's own constants and never anything a
    caller sent, so it cannot become a column name arriving from a request.
    """
    if dimension not in GROUPABLE:
        raise ValueError(f"{dimension} is not a grouping this API offers")
    repository = CostRepository(connection, context)
    resolved = _resolve(repository, scope, period)
    rows = repository.grouped(scope, resolved, dimension)
    totals = repository.period_total(scope, resolved)
    meta = build_meta(
        connection,
        scope,
        context,
        visible=len(rows),
        as_of=totals[0][3],
        collected_at=totals[0][4],
    )
    return Envelope(data=_slices(rows), meta=meta)


@router.get("/cost/summary", response_model=Envelope[CostSummaryOut])
def cost_summary(
    period: date | None = None,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[CostSummaryOut]:
    """This period set against the one before it."""
    repository = CostRepository(connection, context)
    at = datetime.now(UTC)
    current_period = _resolve(repository, scope, period)

    rows = repository.period_total(scope, current_period)
    current = _total(current_period, rows[0], at)

    earlier = previous_month(current_period)
    earlier_rows = repository.period_total(scope, earlier)
    # A period with no line items is not a period that cost nothing. It is a
    # period nobody collected, and a change computed against it would be a
    # number invented out of an absence.
    has_previous = int(earlier_rows[0][2]) > 0
    previous = _total(earlier, earlier_rows[0], at) if has_previous else None

    change = None if previous is None else current.effective_cost - previous.effective_cost
    summary = CostSummaryOut(current=current, previous=previous, change=change)

    meta = build_meta(
        connection,
        scope,
        context,
        visible=current.line_items,
        as_of=rows[0][3],
        collected_at=rows[0][4],
    )
    return Envelope(data=summary, meta=meta)


@router.get("/cost/by-service", response_model=Envelope[list[CostSliceOut]])
def cost_by_service(
    period: date | None = None,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[CostSliceOut]]:
    """Services, worst first."""
    return _grouped(connection, scope, context, period, "service")


@router.get("/cost/by-account", response_model=Envelope[list[CostSliceOut]])
def cost_by_account(
    period: date | None = None,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[CostSliceOut]]:
    """Accounts, worst first, and only the ones this scope reaches."""
    return _grouped(connection, scope, context, period, "account")


@router.get("/cost/allocation", response_model=Envelope[list[CostSliceOut]])
def cost_allocation(
    tag: str = Query(min_length=1, max_length=128),
    period: date | None = None,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[CostSliceOut]]:
    """The same rows grouped by one tag key, unallocated bucket included.

    The tag key is a value inside a JSONB lookup and not a column name, so
    unlike the groupings above it cannot name a column. It is bounded anyway,
    because an unbounded string from a request has no business reaching a query.
    """
    repository = CostRepository(connection, context)
    resolved = _resolve(repository, scope, period)
    rows = repository.by_tag(scope, resolved, tag)
    totals = repository.period_total(scope, resolved)
    meta = build_meta(
        connection,
        scope,
        context,
        visible=len(rows),
        as_of=totals[0][3],
        collected_at=totals[0][4],
    )
    return Envelope(data=_slices(rows), meta=meta)


@router.get("/cost/trend", response_model=Envelope[list[CostDayOut]])
def cost_trend(
    period: date | None = None,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[CostDayOut]]:
    """Effective cost per day inside the period, oldest first."""
    repository = CostRepository(connection, context)
    resolved = _resolve(repository, scope, period)
    rows = repository.daily(scope, resolved)
    totals = repository.period_total(scope, resolved)
    series = [CostDayOut(day=day, effective_cost=Decimal(cost)) for day, cost in rows]
    meta = build_meta(
        connection,
        scope,
        context,
        visible=len(series),
        as_of=totals[0][3],
        collected_at=totals[0][4],
    )
    return Envelope(data=series, meta=meta)
