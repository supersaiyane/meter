"""Meter's own cost, by module and day.

Constraint 7 in CLAUDE.md. A tool that reports other people's spending without
reporting its own is asking for a trust it has not earned, so this is a first
class route rather than something behind a flag.

`unallocated` appears here as a module like any other. Hiding it would make the
self metering report look tidier and under count, and a self metering report
that under counts is worse than none because it is believed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Connection

from finops_api.db.repositories import AccessContext, PlatformCostRepository
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.exports import ExportSpec, exportable, listed
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import Envelope, PlatformCostOut
from finops_core.domain.tenant import Scope

router = APIRouter(prefix=API_PREFIX, tags=["platform"])


@router.get("/platform/cost", response_model=Envelope[list[PlatformCostOut]])
@exportable(
    ExportSpec(
        title="Platform cost",
        row_model=PlatformCostOut,
        rows=listed,
        metric="Amortized cost of Meter's own resources",
    )
)
def platform_cost(
    scope: Scope = Depends(get_scope),
    connection: Connection = Depends(get_connection),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[PlatformCostOut]]:
    rows = PlatformCostRepository(connection, context).by_day_and_module(scope)
    costs = [
        PlatformCostOut(
            day=row.day,
            module=str(row.module),
            service=str(row.service),
            amortized_cost=row.amortized_cost,
            as_of=row.as_of,
            collected_at=row.collected_at,
        )
        for row in rows
    ]
    return Envelope(
        data=costs,
        meta=build_meta(
            connection,
            scope,
            context,
            visible=len(costs),
            rows=rows,
            # Modules, not accounts, and distinct modules rather than daily
            # rows. Counting the rows reported `42 modules` over the four the
            # screen draws, because the roll up happens above this.
            coverage=(len({row.module for row in rows}), len({row.module for row in rows})),
            coverage_unit="modules",
        ),
    )
