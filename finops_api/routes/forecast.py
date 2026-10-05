"""The spend forecast, `GET /cost/forecast`. FEAT-066, TASK-P8-008.

The first producer of forecast provenance, under ADR-0015's four conditions as the owner chose to
meet them on 2026-10-05: a weekday profile, an 80 percent band from the method's own backtest,
withheld with fewer than three months to test on or a median miss above 15 percent, and the word
forecast on every figure. The arithmetic is `finops_query.forecast`; this module reads, hands the
days over, and reports what comes back.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Final

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.cost import CostRepository
from finops_api.db.repositories.forecast import ForecastRepository
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.routes import API_PREFIX, build_meta
from finops_api.routes.cost import NO_COST
from finops_api.schemas import (
    Envelope,
    ForecastDayOut,
    ForecastMonthOut,
    ForecastOut,
    ForecastRangeOut,
    ForecastTestOut,
)
from finops_core.domain.tenant import Scope
from finops_query.forecast import (
    AHEAD_MONTHS,
    INTERVAL_PERCENT,
    MAX_HELD_OUT,
    MAX_MEDIAN_MISS,
    METHOD,
    METHOD_DETAIL,
    MIN_HELD_OUT,
    Outcome,
    ahead,
    band,
    month_end,
)

router = APIRouter(prefix=API_PREFIX, tags=["cost"])

#: How far back the history is read: the most months tested, the furthest month ahead, and the
#: eight weeks of profile behind the oldest test, rounded up to whole months.
HISTORY_MONTHS: Final = MAX_HELD_OUT + AHEAD_MONTHS + 3


@router.get("/cost/forecast", response_model=Envelope[ForecastOut])
def cost_forecast(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[ForecastOut]:
    """This month's total and the next three months', each a range or the reason none is shown."""
    costs = CostRepository(connection, context)
    latest = costs.latest_period(scope)
    forecasts = ForecastRepository(connection, context)
    first, last = forecasts.collected(scope)
    if latest is None or first is None or last is None:
        raise HTTPException(status_code=404, detail=NO_COST)
    month_start = datetime.now(UTC).date().replace(day=1)
    cut = last + timedelta(days=1)
    daily = forecasts.daily(scope, max(first, months_before(month_start, HISTORY_MONTHS)), last)
    this_month = month_end(daily, month_start, cut)
    data = ForecastOut(
        method=METHOD,
        method_detail=METHOD_DETAIL,
        interval_percent=INTERVAL_PERCENT,
        max_median_miss=MAX_MEDIAN_MISS,
        min_held_out=MIN_HELD_OUT,
        billed_through=last,
        billed_to_date=sum((cost for day, cost in daily.items() if day >= month_start), Decimal(0)),
        month_end=_month(this_month),
        days=[
            ForecastDayOut(day=point.day, billed=point.actual, low=point.low, high=point.high)
            for point in this_month.days
        ],
        ahead=[_month(outcome) for outcome in ahead(daily, month_start, cut)],
        backtest=_backtest(this_month),
    )
    totals = costs.period_total(scope, latest)[0]
    meta = build_meta(
        connection,
        scope,
        context,
        visible=costs.accounts_in(scope, latest),
        as_of=totals[3],
        collected_at=totals[4],
    )
    return Envelope(data=data, meta=meta)


def months_before(month: date, count: int) -> date:
    """The first of the month `count` months before `month`."""
    index = month.year * 12 + month.month - 1 - count
    return date(index // 12, index % 12 + 1, 1)


def _month(outcome: Outcome) -> ForecastMonthOut:
    figure = outcome.figure
    return ForecastMonthOut(
        month=outcome.month,
        figure=None if figure is None else ForecastRangeOut(low=figure.low, high=figure.high),
        withheld=outcome.withheld,
        median_miss=outcome.median_miss,
        held_out=sum(1 for test in outcome.tests if test.usable),
    )


def _backtest(outcome: Outcome) -> list[ForecastTestOut]:
    """Each tested month, with today's band applied to what was forecast for it, where shown.

    A withheld forecast shows its misses and no ranges, because a range in its backtest would be
    the figure it was not allowed to show, arrived at by the side door.
    """
    usable = [test for test in outcome.tests if test.usable]
    edges = band(usable) if outcome.figure is not None else None
    rows = []
    for test in usable:
        low = None if edges is None else test.estimate * (1 + edges[0])
        high = None if edges is None else test.estimate * (1 + edges[1])
        rows.append(
            ForecastTestOut(
                month=test.month,
                actual=test.actual,
                miss=test.miss,
                low=low,
                high=high,
                within=None if low is None or high is None else low <= test.actual <= high,
            )
        )
    return rows
