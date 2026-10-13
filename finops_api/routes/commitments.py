"""The commitments the organization holds, what they saved, and what to buy. P14, FEAT-086 to 090.

TASK-P14-004 onwards, P14 spec section 8. Every read goes through the scope dependency and the
repository guard, constraint 3. The savings rate is scoped as the bill is, by account; what is held
and what to buy belong to the payer, ADR-0025, and are visible at global scope only.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.cost import CostRepository
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.exports import ExportSpec, exportable, rows_in
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import Envelope, SavingsRateMonthOut, SavingsRateOut
from finops_core.domain.tenant import Scope
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
