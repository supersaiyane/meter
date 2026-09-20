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

import csv
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from io import StringIO
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.engine import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.cost import (
    GROUPABLE,
    AnomalyRepository,
    CommitmentCoverageRepository,
    CommitmentRepository,
    CostRepository,
    previous_month,
)
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import (
    CommitmentCoverageOut,
    CommitmentsOut,
    CommitmentUseOut,
    CostAnomaliesOut,
    CostAnomalyOut,
    CostDayOut,
    CostSliceOut,
    CostSummaryOut,
    CostTotalOut,
    Envelope,
)
from finops_core.domain.cost import BillingPeriod
from finops_core.domain.tenant import Scope
from finops_query.anomaly import MINIMUM_HISTORY

router = APIRouter(prefix=API_PREFIX, tags=["cost"])

#: What a caller gets when the tenant has no cost at all. A 404 says the thing
#: does not exist. A zero would say the estate spent nothing, which is a claim
#: nobody has earned the right to make.
NO_COST = "No billing period has been collected for this tenant yet."

#: What a caller gets when no commitment has ever been collected. Distinct
#: from an estate that holds no commitments, which is an empty list and a
#: sentence saying so.
NO_COMMITMENTS = "No commitment window has been collected for this tenant yet."


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


def _fraction(part: Decimal, whole: Decimal) -> Decimal | None:
    """`part` over `whole`, or None where there is no whole.

    None rather than zero, and the distinction carries a screen. Zero says the
    commitment was wasted or the estate is uncovered, which are claims a reader
    acts on. None says the question has no answer here, which is a different
    sentence, and a queued commitment or a service with no eligible spend is the
    second case.
    """
    if whole == 0:
        return None
    return part / whole


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
        visible=repository.accounts_in(scope, resolved),
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
        # Accounts, because that is the unit the coverage banner names. The
        # line item count went here first and rendered as "showing all 450
        # accounts" on an estate with five.
        visible=repository.accounts_in(scope, current_period),
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
        visible=repository.accounts_in(scope, resolved),
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
        visible=repository.accounts_in(scope, resolved),
        as_of=totals[0][3],
        collected_at=totals[0][4],
    )
    return Envelope(data=series, meta=meta)


@router.get("/cost/anomalies", response_model=Envelope[CostAnomaliesOut])
def cost_anomalies(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[CostAnomaliesOut]:
    """Days that did not look like the days before them.

    The payload carries how many days of cost the scope has, because an empty
    list means two opposite things. An estate with a fortnight of history and no
    anomalies is behaving. An estate with four days of history has not been
    judged at all, and a screen that renders both as "no anomalies" tells the
    second one a reassuring lie.
    """
    repository = AnomalyRepository(connection, context)
    rows = repository.worst_first(scope)
    found = CostAnomaliesOut(
        anomalies=[
            CostAnomalyOut(
                account_id=str(row.sub_account_id),
                service_name=str(row.service_name),
                day=row.day,
                observed=Decimal(row.observed),
                baseline=Decimal(row.baseline),
                delta=Decimal(row.delta),
                deviations=None if row.deviations is None else Decimal(row.deviations),
                severity=str(row.severity),
                why=str(row.why),
            )
            for row in rows
        ],
        days_collected=repository.judged_days(scope),
        days_needed=MINIMUM_HISTORY,
    )
    # Accounts, not anomalies. The banner counts accounts, and `len(rows)` there
    # rendered "4 missing, outside your scope" above a single finding for a reader who
    # could see the whole estate. That is the third time a row count has reached this
    # slot, after the line item count that read "showing all 450 accounts".
    meta = build_meta(
        connection, scope, context, visible=repository.accounts_judged(scope), rows=rows
    )
    return Envelope(data=found, meta=meta)


@router.get("/cost/commitments", response_model=Envelope[CommitmentsOut])
def cost_commitments(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[CommitmentsOut]:
    """What was committed, what it consumed, and what it covered.

    Two reads of two tables at two grains, and the route is what holds them to one
    window. Utilization is per commitment and coverage is per service, because a
    dollar of covered spend cannot be attributed to one of several overlapping
    plans, and a payload that put coverage on a commitment would be reporting a
    number nobody measured.

    Both tables are `PayerWide` in the guard, so a caller scoped to fewer than all
    accounts reads nothing here. A commitment is bought by the payer and consumed
    by whichever accounts ran the usage, and no API reports which, so there is no
    honest way to narrow it. Reading nothing is the right answer and the screen
    says why.
    """
    uses = CommitmentRepository(connection, context)
    window = uses.latest_window(scope)
    if window is None:
        raise HTTPException(status_code=404, detail=NO_COMMITMENTS)

    rows = uses.worst_first(scope, window)
    slices = CommitmentCoverageRepository(connection, context).slices(scope, window)

    commitments = [
        CommitmentUseOut(
            commitment_id=str(row.commitment_id),
            commitment_type=str(row.commitment_type),
            status=str(row.status),
            term_start=row.term_start,
            term_end=row.term_end,
            committed=Decimal(row.committed),
            used=Decimal(row.used),
            wasted=Decimal(row.wasted),
            utilization=_fraction(Decimal(row.used), Decimal(row.committed)),
        )
        for row in rows
    ]
    found = CommitmentsOut(
        window_start=window,
        window_end=rows[0].window_end if rows else _period_end(window),
        commitments=commitments,
        coverage=[
            CommitmentCoverageOut(
                commitment_type=str(row.commitment_type),
                dimension=str(row.dimension),
                dimension_value=str(row.dimension_value),
                eligible_spend=Decimal(row.eligible_spend),
                covered_spend=Decimal(row.covered_spend),
                coverage=_fraction(Decimal(row.covered_spend), Decimal(row.eligible_spend)),
            )
            for row in slices
        ],
        # Summed from the rows being returned, so the total cannot disagree with
        # the list underneath it.
        wasted_total=sum((one.wasted for one in commitments), Decimal("0")),
    )
    meta = build_meta(
        connection,
        scope,
        context,
        # One payer, wholly visible, rather than a count of commitments against a
        # count of accounts. The default coverage compares `visible` to the number of
        # accounts in the organization, and passing a row count there produced
        # "4 of 5 accounts" on a screen showing four commitments, which is the same
        # defect the cost screen had when a line item count reached the accounts slot.
        #
        # A commitment belongs to the payer and to no account, and this route is only
        # reachable by a scope that sees all of them, so the coverage is complete by
        # construction and says so in its own unit.
        visible=1,
        coverage=(1, 1),
        coverage_unit="payer",
        rows=[*rows, *slices],
    )
    return Envelope(data=found, meta=meta)


#: The header row, and the whole reason this endpoint is not a generic dump.
#:
#: Every money column names its measure. A spreadsheet column headed "cost" is a
#: column somebody will reconcile against an invoice and then argue about, because
#: amortized and billed differ by exactly the commitment discount and nothing in a
#: bare number says which one is in the cell. FOCUS 1.1 calls them EffectiveCost and
#: BilledCost, and those names travel with the file.
EXPORT_HEADER = (
    "billing_period",
    "account_id",
    "service_name",
    "tag_value",
    "effective_cost_amortized_usd",
    "billed_cost_usd",
    "line_items",
    # Both timestamps, per constraint 10, and on every row rather than in a header
    # comment. A CSV cannot carry the meta envelope the JSON routes carry, and the
    # envelope exists so a reader can tell stale from fresh. A spreadsheet outlives
    # the moment it was downloaded, gets mailed on and pasted into a deck, so the
    # freshness has to travel in the cells or it does not travel.
    "as_of",
    "collected_at",
    # The scope coverage, on every row, for the reason FEAT-045 gives: a spreadsheet
    # that leaves the product without its coverage becomes a number in a board pack
    # with no way back to what it meant. A file drawn from two of three hundred
    # accounts is not the estate, and a reader who pastes one row into a deck has
    # taken the coverage with them.
    "accounts_in_file",
    "accounts_in_organization",
)


def _csv(header: tuple[str, ...], rows: Iterable[Sequence[object]]) -> str:
    """The file, built through the csv module rather than by joining on commas.

    A service name with a comma in it, or a tag value with a quote, breaks a hand
    joined line in a way that shifts every later column by one and still opens in a
    spreadsheet. That is worse than failing.
    """
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


@router.get("/cost/export")
def cost_export(
    tag: str = Query(default="team", min_length=1, max_length=128),
    period: date | None = None,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Response:
    """One period as CSV, at the grain finance asks for. FEAT-045.

    Generated from the same repository, the same scope predicate and the same
    unallocated bucket the screens read, so the file cannot drift from what a reader
    was shown. Summing the amortized column gives the figure on `/cost/summary`, and
    a test asserts that by summing it.

    Not an envelope, because this is a file rather than a payload: a caller saves it
    and opens it in a spreadsheet, and a JSON wrapper round a CSV is a wrapper
    somebody has to strip by hand.
    """
    repository = CostRepository(connection, context)
    resolved = _resolve(repository, scope, period)
    rows = repository.for_export(scope, resolved, tag)
    totals = repository.period_total(scope, resolved)
    as_of, collected_at = totals[0][3], totals[0][4]
    # The same two numbers the coverage banner shows, from the same place, so the
    # screen and the file cannot disagree about how much of the estate this is.
    meta = build_meta(
        connection,
        scope,
        context,
        visible=repository.accounts_in(scope, resolved),
        as_of=as_of,
        collected_at=collected_at,
    )

    body = _csv(
        EXPORT_HEADER,
        (
            (
                resolved.isoformat(),
                account,
                service,
                # `unallocated` is a row like any other here. An export that quietly
                # dropped what it could not attribute would report a smaller estate
                # than exists, and the gap is the first thing finance finds.
                tag_value,
                f"{Decimal(effective):.4f}",
                f"{Decimal(billed):.4f}",
                int(line_items),
                as_of.isoformat(),
                collected_at.isoformat(),
                meta.scope_coverage.visible,
                meta.scope_coverage.total,
            )
            for account, service, tag_value, effective, billed, line_items in rows
        ),
    )
    return Response(
        content=body,
        media_type="text/csv",
        headers={
            # Named for the period, so two downloads do not overwrite each other in
            # a downloads folder, which is where every one of these files ends up.
            "Content-Disposition": (f'attachment; filename="meter-cost-{resolved.isoformat()}.csv"')
        },
    )
