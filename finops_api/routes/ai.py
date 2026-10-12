"""AI spend: by provider, model, token, feature and caller, who called what, and the GPU fleet.

TASK-P13-007, FEAT-081 to 085, P13 spec sections 5.7 and 8. Three reads of what the P13 collectors
stored, each a billing period, the newest unless one is asked for, and every figure saying how it
was arrived at: cost is measured, a cost per token measured where the bill counted the tokens and
modelled where a usage report did, a cost per request and a caller's cost modelled always. Each
read goes through the scope dependency and the repository guard, so a provider's spend, which no
account grant names, is visible at global scope only.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.ai import (
    AiCostRepository,
    AiProviderAccountRepository,
    AiUsageRepository,
    GpuUtilizationRepository,
)
from finops_api.db.repositories.cost import CostRepository
from finops_api.deps import get_access_context, get_connection, get_scope, get_settings
from finops_api.exports import ExportSpec, exportable, rows_in
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import (
    AiCallerOut,
    AiCallersOut,
    AiConnectionOut,
    AiGpuFleetOut,
    AiGpuOut,
    AiSpendOut,
    AiSpendRowOut,
    Envelope,
)
from finops_core.config import Settings
from finops_core.domain.ai import TOKEN_TYPES
from finops_core.domain.tenant import Scope
from finops_query import ai

router = APIRouter(prefix=API_PREFIX, tags=["ai"])

#: Which column of `ai_usage_daily` holds each token type.
TOKEN_COLUMNS = {token_type: f"{token_type}_tokens" for token_type in TOKEN_TYPES}
PERIOD = Query(default=None, description="Billing period, its first day. The newest if omitted.")


def _next_month(period: date) -> date:
    return date(period.year + (period.month == 12), period.month % 12 + 1, 1)


def _period(asked: date | None, repository: AiCostRepository, scope: Scope) -> date | None:
    """The period asked for, or the newest the bill holds for this reader; None for none."""
    if asked is None:
        return repository.latest_period(scope)
    if asked.day != 1:
        raise HTTPException(status_code=422, detail="a billing period starts on its first day")
    return asked


def _lines(rows: Sequence[Any]) -> list[ai.Line]:
    lines = []
    for row in rows:
        cloud = row.ingest_source == ai.CLOUD_BILL
        lines.append(
            ai.Line(
                source=row.ingest_source,
                provider=row.provider_name,
                # A cloud line's account is the member account; a provider's, its organization.
                account=(row.sub_account_id or row.billing_account_id)
                if cloud
                else row.billing_account_id,
                workspace=row.region_id if cloud else row.sub_account_id,
                day=row.charge_period_start.date(),
                model=row.x_ai_model,
                token_type=row.x_ai_token_type,
                tokens=None if row.x_ai_tokens is None else Decimal(row.x_ai_tokens),
                caller=row.x_iam_principal,
                resource_id=row.resource_id,
                tags=row.tags or {},
                cost=Decimal(row.effective_cost),
                as_of=row.as_of,
                collected_at=row.collected_at,
            )
        )
    return lines


def _usage(rows: Sequence[Any]) -> list[ai.Usage]:
    return [
        ai.Usage(
            source=row.provider,
            account=row.account_id,
            workspace=row.workspace,
            day=row.usage_date,
            model=row.model,
            caller=row.caller,
            application=row.application,
            tokens={kind: int(getattr(row, column)) for kind, column in TOKEN_COLUMNS.items()},
            requests=row.requests,
        )
        for row in rows
    ]


def _accounts(connection: Connection, context: AccessContext, scope: Scope, period: date) -> int:
    """The accounts this reader sees spending in the period, so coverage counts accounts.

    Not the accounts holding AI spend: a reader who sees every account, two of which use a model,
    is seeing all of the estate, and counting two would draw the screen as a partial view. ISS-288.
    """
    return CostRepository(connection, context).accounts_in(scope, period)


def _self_billed(connected: Sequence[Any], lines: Sequence[ai.Line]) -> set[str]:
    """The sources that bill themselves: every connected provider, and any the bill shows."""
    shown = {line.source for line in lines if line.source != ai.CLOUD_BILL}
    return {row.provider for row in connected} | shown


@router.get("/ai/spend", response_model=Envelope[AiSpendOut])
@exportable(
    ExportSpec(
        title="AI spend",
        row_model=AiSpendRowOut,
        rows=rows_in("rows"),
        grouping=lambda view: f"By {view.query.get('group_by', 'provider')}",
        metric="Effective cost, measured; per token and per request as each row says",
    )
)
def ai_spend(
    period: date | None = PERIOD,
    group_by: str = Query(
        default="provider", pattern="^(provider|model|token_type|feature|caller)$"
    ),
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
    settings: Settings = Depends(get_settings),
) -> Envelope[AiSpendOut]:
    """AI spend for a billing period, grouped as asked, worst first."""
    costs = AiCostRepository(connection, context)
    connected = AiProviderAccountRepository(connection, context).active(scope)
    links = [
        AiConnectionOut(provider=row.provider, organization_id=row.organization_id, name=row.name)
        for row in connected
    ]
    chosen = _period(period, costs, scope)
    if chosen is None:
        empty = AiSpendOut(
            period=None, group_by=group_by, total_cost=None, rows=[], connected=links
        )
        return Envelope(data=empty, meta=build_meta(connection, scope, context, visible=0))
    rows = costs.lines(scope, chosen)
    lines = _lines(rows)
    used = AiUsageRepository(connection, context).between(scope, chosen, _next_month(chosen))
    grouped = ai.spend(
        lines,
        _usage(used),
        group_by,
        tag_key=settings.ai_request_metadata_key,
        self_billed=_self_billed(connected, lines),
    )
    found = AiSpendOut(
        period=chosen,
        group_by=group_by,
        total_cost=sum((line.cost for line in lines), Decimal(0)),
        rows=[AiSpendRowOut(**vars(row)) for row in grouped],
        connected=links,
    )
    visible = _accounts(connection, context, scope, chosen)
    return Envelope(
        data=found, meta=build_meta(connection, scope, context, visible=visible, rows=rows)
    )


@router.get("/ai/callers", response_model=Envelope[AiCallersOut])
@exportable(
    ExportSpec(
        title="AI callers",
        row_model=AiCallerOut,
        rows=rows_in("callers"),
        metric="Tokens and requests, measured; cost, modelled from the bill's unit cost",
    )
)
def ai_callers(
    period: date | None = PERIOD,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[AiCallersOut]:
    """Who called which model, most costly first; a caller the bill priced nothing for, last."""
    costs = AiCostRepository(connection, context)
    chosen = _period(period, costs, scope)
    if chosen is None:
        empty = AiCallersOut(period=None, callers=[])
        return Envelope(data=empty, meta=build_meta(connection, scope, context, visible=0))
    lines = _lines(costs.lines(scope, chosen))
    used = AiUsageRepository(connection, context).between(scope, chosen, _next_month(chosen))
    connected = AiProviderAccountRepository(connection, context).active(scope)
    rows = ai.callers(lines, _usage(used), self_billed=_self_billed(connected, lines))
    found = AiCallersOut(
        period=chosen,
        callers=[
            AiCallerOut(
                source=row.source,
                account_id=row.account,
                caller=row.caller,
                application=row.application,
                model=row.model,
                tokens=row.tokens,
                requests=row.requests,
                modelled_cost=row.modelled_cost,
                modelled_cost_basis=ai.MODELLED,
            )
            for row in rows
        ],
    )
    visible = _accounts(connection, context, scope, chosen)
    return Envelope(
        data=found, meta=build_meta(connection, scope, context, visible=visible, rows=used)
    )


def utilization_of(row: ai.GpuRow) -> str:
    """Whether an instance's agent published for every day it was billed, some, or none."""
    if row.days_published == 0:
        return "not published"
    if row.days_published < row.days_billed:
        return "partly published"
    return "published"


@router.get("/ai/gpu", response_model=Envelope[AiGpuFleetOut])
@exportable(
    ExportSpec(
        title="GPU instances",
        row_model=AiGpuOut,
        rows=rows_in("instances"),
        metric="Hours and effective cost from the bill; utilization from the agent, measured",
    )
)
def ai_gpu(
    period: date | None = PERIOD,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[AiGpuFleetOut]:
    """Each GPU instance the bill names, most costly first, how busy it was or not published."""
    costs = AiCostRepository(connection, context)
    chosen = _period(period, costs, scope) if period is not None else costs.latest_gpu_period(scope)
    if chosen is None:
        empty = AiGpuFleetOut(period=None, instances=[])
        return Envelope(data=empty, meta=build_meta(connection, scope, context, visible=0))
    billed = costs.gpu_lines(scope, chosen)
    published = GpuUtilizationRepository(connection, context).between(
        scope, chosen, _next_month(chosen)
    )
    rows = ai.gpu(
        [
            ai.GpuLine(
                account=row.sub_account_id or "",
                region=row.region_id,
                instance_id=row.resource_id,
                usage_type=row.x_usage_type,
                day=row.charge_period_start.date(),
                hours=None if row.consumed_quantity is None else Decimal(row.consumed_quantity),
                cost=Decimal(row.effective_cost),
            )
            for row in billed
        ],
        [
            ai.GpuDay(
                account=row.account_id,
                instance_id=row.instance_id,
                day=row.usage_date,
                average_percent=Decimal(row.average_percent),
                peak_percent=Decimal(row.peak_percent),
            )
            for row in published
        ],
    )
    found = AiGpuFleetOut(
        period=chosen,
        instances=[
            AiGpuOut(
                account_id=row.account,
                region_id=row.region,
                instance_id=row.instance_id,
                instance_type=row.instance_type,
                hours=row.hours,
                cost=row.cost,
                days_billed=row.days_billed,
                days_published=row.days_published,
                average_percent=row.average_percent,
                peak_percent=row.peak_percent,
                utilization=utilization_of(row),
            )
            for row in rows
        ],
    )
    meta = build_meta(
        connection,
        scope,
        context,
        visible=_accounts(connection, context, scope, chosen),
        rows=[*billed, *published],
    )
    return Envelope(data=found, meta=meta)
