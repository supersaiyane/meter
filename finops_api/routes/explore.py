"""Cost Explorer's query, `GET /cost/explore`. FEAT-065, TASK-P8-007.

The question a practitioner asks first, answered from the rows the cost screen always read:
cost grouped two ways at once, over the FOCUS columns in `EXPLORABLE` and the tag keys on the
period's own line items, filtered, daily or monthly, and set against the period immediately
before it. It sits behind the same scope dependency and repository guard as `/cost`, carries
coverage and failures in the envelope like every route, and computes no figure differently.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.cost import CostRepository
from finops_api.db.repositories.explore import (
    ALWAYS_HELD,
    EXPLORABLE,
    METRICS,
    ROW_LIMIT,
    TAG,
    TAG_KEY_LIMIT,
    ExploreRepository,
    Filter,
    Grouping,
)
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.exports import ExportSpec, View, exportable, rows_in
from finops_api.exports.cells import header
from finops_api.routes import API_PREFIX, build_meta
from finops_api.routes.cost import NO_COST
from finops_api.schemas import (
    Envelope,
    ExploreGroupingOut,
    ExploreOut,
    ExplorePointOut,
    ExploreRowOut,
    ExploreWindowOut,
    GeographyRefOut,
    Meta,
)
from finops_core.domain.explore import (
    METRIC_NAMES,
    Granularity,
    Metric,
    PeriodError,
    Preset,
    Window,
    previous,
    window_for,
)
from finops_core.domain.geography import geography_of
from finops_core.domain.tenant import Scope

router = APIRouter(prefix=API_PREFIX, tags=["cost"])

#: The most values one filter holds, and the longest value and name. A filter is chosen from a
#: table a person is reading, and a list longer than this was not chosen by a person.
MOST_VALUES = 20
LONGEST_VALUE = 256
LONGEST_NAME = 128

#: The grouping whose rows the geography map can place. TASK-P8-017.
REGION = "region"

SAME_TWICE = "Group by two different things, or by one."
NOT_A_COLUMN = "That is not a column Cost Explorer groups or filters by."
TAG_NEEDS_KEY = "Grouping by a tag needs the tag key."
KEY_WITHOUT_TAG = "A tag key goes with a tag grouping, and this grouping is a column."
NOT_AN_ALLOWED_KEY = (
    f"That tag key is not among the {TAG_KEY_LIMIT} most used on this period's line items, so "
    "Cost Explorer does not group or filter by it."
)
DATES_WITHOUT_CUSTOM = "A start and an end go with a custom period, and this period is a preset."
HALF_A_TAG_FILTER = "A tag filter needs a tag key and at least one value."
TOO_MANY_VALUES = (
    f"A filter holds at most {MOST_VALUES} values, each at most {LONGEST_VALUE} characters."
)


def asked_filters(
    service: list[str] = Query(default=[]),
    service_category: list[str] = Query(default=[]),
    account: list[str] = Query(default=[]),
    region: list[str] = Query(default=[]),
    availability_zone: list[str] = Query(default=[]),
    charge_category: list[str] = Query(default=[]),
    commitment_discount_type: list[str] = Query(default=[]),
    commitment_discount_status: list[str] = Query(default=[]),
) -> dict[str, list[str]]:
    """The column filters as asked, one parameter per column in `EXPLORABLE`."""
    asked = {
        "service": service,
        "service_category": service_category,
        "account": account,
        "region": region,
        "availability_zone": availability_zone,
        "charge_category": charge_category,
        "commitment_discount_type": commitment_discount_type,
        "commitment_discount_status": commitment_discount_status,
    }
    return {name: values for name, values in asked.items() if values}


def _axis(grouping: ExploreGroupingOut | None) -> str:
    """One axis in the words a heading uses: a FOCUS column's name, or the tag key."""
    if grouping is None:
        return ""
    if grouping.tag_key is not None:
        return f"Tag {grouping.tag_key}"
    return header(grouping.dimension)


def _explore_headers(view: View) -> dict[str, str]:
    """The grouping columns by what they group, and the two periods by their dates."""
    found: ExploreOut = view.data
    return {
        "first": _axis(found.group_by),
        "second": _axis(found.then_by) or "Second grouping",
        "this_period": f"{found.current.start} to {found.current.end}",
        "previous_period": f"{found.previous.start} to {found.previous.end}",
    }


def _explore_grouping(view: View) -> str:
    found: ExploreOut = view.data
    return " then ".join(axis for axis in (_axis(found.group_by), _axis(found.then_by)) if axis)


def _explore_period(view: View) -> str:
    found: ExploreOut = view.data
    return (
        f"{found.current.start} to {found.current.end}, set against "
        f"{found.previous.start} to {found.previous.end}, {found.granularity}"
    )


def _explore_note(view: View) -> str:
    """The groups past the row limit, which the screen names and the rows do not hold."""
    found: ExploreOut = view.data
    if not found.rows_omitted:
        return ""
    return (
        f"The {found.rows_omitted} smallest groups are not rows here, as on the screen. "
        f"Together they cost {found.omitted_this_period} this period."
    )


@router.get("/cost/explore", response_model=Envelope[ExploreOut])
@exportable(
    ExportSpec(
        title="Cost Explorer",
        row_model=ExploreRowOut,
        rows=rows_in("rows"),
        headers=_explore_headers,
        grouping=_explore_grouping,
        period=_explore_period,
        metric=lambda view: header(view.data.metric),
        note=_explore_note,
    )
)
def cost_explore(
    group_by: str = Query(default="service", max_length=LONGEST_NAME),
    group_by_tag: str | None = Query(default=None, min_length=1, max_length=LONGEST_NAME),
    then_by: str | None = Query(default=None, max_length=LONGEST_NAME),
    then_by_tag: str | None = Query(default=None, min_length=1, max_length=LONGEST_NAME),
    period: Preset = "mtd",
    start: date | None = None,
    end: date | None = None,
    granularity: Granularity = "daily",
    metric: Metric = "effective_cost",
    tag_key: str | None = Query(default=None, min_length=1, max_length=LONGEST_NAME),
    tag_value: list[str] = Query(default=[]),
    asked: dict[str, list[str]] = Depends(asked_filters),
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[ExploreOut]:
    """Cost grouped two ways over a period, set against the one immediately before it."""
    today = datetime.now(UTC).date()
    current = _window(period, today, start, end)
    before = previous(current, period)
    costs = CostRepository(connection, context)
    latest = costs.latest_period(scope)
    if latest is None:
        raise HTTPException(status_code=404, detail=NO_COST)
    explore = ExploreRepository(connection, context)
    tag_keys = explore.tag_keys(scope, current)
    first = _grouping(group_by, group_by_tag, tag_keys)
    second = None if then_by is None else _grouping(then_by, then_by_tag, tag_keys)
    if second == first:
        raise HTTPException(status_code=422, detail=SAME_TWICE)
    filters = _filters(asked, tag_key, tag_value, tag_keys)
    totals = explore.totals(scope, current, before, metric, filters)
    available = _available(totals)
    if metric not in available:
        raise HTTPException(status_code=422, detail=_not_held(metric))
    earliest = explore.earliest_period(scope)
    compared = earliest is not None and before.start >= earliest
    rows, groups = _table(
        explore, scope, (current, before), metric, (first, second), filters, compared=compared
    )
    named = explore.named_series(scope, current, metric, first, filters)
    points = explore.series(scope, current, metric, first, filters, granularity, named)
    this_total = Decimal(totals[0] or 0) if int(totals[2]) > 0 else None
    previous_total = Decimal(totals[1] or 0) if compared else None
    data = ExploreOut(
        metric=metric,
        metrics_available=available,
        period=period,
        granularity=granularity,
        current=ExploreWindowOut(start=current.start, end=current.end),
        previous=ExploreWindowOut(start=before.start, end=before.end),
        is_open=current.end >= today,
        collected_from=earliest,
        previous_collected=compared,
        group_by=_grouping_out(first),
        then_by=None if second is None else _grouping_out(second),
        tag_keys=tag_keys,
        total_this_period=this_total,
        total_previous_period=previous_total,
        series=named,
        points=[_point(row) for row in points],
        rows=rows,
        row_limit=ROW_LIMIT,
        rows_omitted=groups - len(rows),
        omitted_this_period=(this_total or Decimal(0)) - _sum(row.this_period for row in rows),
        omitted_previous_period=None
        if previous_total is None
        else previous_total - _sum(row.previous_period or Decimal(0) for row in rows),
        region_geographies=_placed(rows) if first.dimension == REGION else {},
    )
    meta = _meta(connection, scope, context, (costs, explore), current, latest)
    return Envelope(data=data, meta=meta)


def _placed(rows: Sequence[ExploreRowOut]) -> dict[str, GeographyRefOut]:
    """The geography of each region row, by the geography map's own rule. TASK-P8-017.

    A region whose prefix no table knows is left out rather than given a geography, which is
    how the geography map treats it too: counted, named, and never placed by a guess.
    """
    found: dict[str, GeographyRefOut] = {}
    for row in rows:
        placed = geography_of(row.first)
        if placed is not None:
            found[row.first] = GeographyRefOut(key=placed.key, name=placed.name)
    return found


def _window(period: Preset, today: date, start: date | None, end: date | None) -> Window:
    if period != "custom" and (start is not None or end is not None):
        raise HTTPException(status_code=422, detail=DATES_WITHOUT_CUSTOM)
    try:
        return window_for(period, today, start, end)
    except PeriodError as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from refused


def _grouping(dimension: str, tag_key: str | None, tag_keys: Sequence[str]) -> Grouping:
    if dimension == TAG:
        if tag_key is None:
            raise HTTPException(status_code=422, detail=TAG_NEEDS_KEY)
        if tag_key not in tag_keys:
            raise HTTPException(status_code=422, detail=NOT_AN_ALLOWED_KEY)
        return Grouping(TAG, tag_key)
    if dimension not in EXPLORABLE:
        raise HTTPException(status_code=422, detail=NOT_A_COLUMN)
    if tag_key is not None:
        raise HTTPException(status_code=422, detail=KEY_WITHOUT_TAG)
    return Grouping(dimension)


def _filters(
    asked: Mapping[str, list[str]],
    tag_key: str | None,
    tag_value: list[str],
    tag_keys: Sequence[str],
) -> list[Filter]:
    chosen = [Filter(Grouping(name), _values(values)) for name, values in asked.items()]
    if tag_key is None and not tag_value:
        return chosen
    if tag_key is None or not tag_value:
        raise HTTPException(status_code=422, detail=HALF_A_TAG_FILTER)
    if tag_key not in tag_keys:
        raise HTTPException(status_code=422, detail=NOT_AN_ALLOWED_KEY)
    return [*chosen, Filter(Grouping(TAG, tag_key), _values(tag_value))]


def _values(values: Sequence[str]) -> tuple[str, ...]:
    if len(values) > MOST_VALUES or any(not 0 < len(value) <= LONGEST_VALUE for value in values):
        raise HTTPException(status_code=422, detail=TOO_MANY_VALUES)
    return tuple(values)


def _available(totals: Sequence[Any]) -> list[str]:
    """The measures this view can sum: the two always held, and any other no line item lacks."""
    lines = int(totals[2]) + int(totals[3])
    missing = {"list_cost": int(totals[4]), "contracted_cost": int(totals[5])}
    return [
        metric
        for metric in METRICS
        if metric in ALWAYS_HELD or (lines > 0 and missing.get(metric, 1) == 0)
    ]


def _not_held(metric: str) -> str:
    return (
        f"{METRIC_NAMES[metric]} is not on every line item in this view, so a sum of it would "
        "be short. Effective Cost is on every one."
    )


def _table(
    explore: ExploreRepository,
    scope: Scope,
    windows: tuple[Window, Window],
    metric: str,
    groupings: tuple[Grouping, Grouping | None],
    filters: Sequence[Filter],
    *,
    compared: bool,
) -> tuple[list[ExploreRowOut], int]:
    """The rows within the limit, then any unallocated row the limit would have dropped."""
    current, before = windows
    kept = explore.rows(scope, current, before, metric, groupings, filters, ROW_LIMIT)
    groups = int(kept[0][4]) if kept else 0
    found = [tuple(row[:4]) for row in kept]
    if groups > len(kept):
        seen = {(row[0], row[1]) for row in found}
        extra = explore.unallocated_rows(scope, current, before, metric, groupings, filters)
        found += [tuple(row[:4]) for row in extra if (row[0], row[1]) not in seen]
    rows = [
        ExploreRowOut(
            first=str(first),
            second=None if second is None else str(second),
            this_period=Decimal(this),
            previous_period=Decimal(prior) if compared else None,
        )
        for first, second, this, prior in found
    ]
    return rows, groups


def _meta(
    connection: Connection,
    scope: Scope,
    context: AccessContext,
    repositories: tuple[CostRepository, ExploreRepository],
    current: Window,
    latest: date,
) -> Meta:
    """Coverage and freshness of the estate the view draws on.

    A window with nothing billed yet, the first of a month, still has an estate behind it, so
    it borrows the newest period's accounts and timestamps rather than reporting none.
    """
    costs, explore = repositories
    accounts, as_of, collected_at = explore.window_facts(scope, current)
    if as_of is None:
        newest = costs.period_total(scope, latest)[0]
        accounts, as_of, collected_at = costs.accounts_in(scope, latest), newest[3], newest[4]
    return build_meta(
        connection, scope, context, visible=int(accounts), as_of=as_of, collected_at=collected_at
    )


def _grouping_out(grouping: Grouping) -> ExploreGroupingOut:
    return ExploreGroupingOut(dimension=grouping.dimension, tag_key=grouping.tag_key)


def _point(row: Sequence[Any]) -> ExplorePointOut:
    bucket, series, cost = row
    return ExplorePointOut(
        bucket=bucket, series=None if series is None else str(series), cost=Decimal(cost)
    )


def _sum(values: Any) -> Decimal:
    return sum(values, Decimal(0))
