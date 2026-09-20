"""Runs, their typed failures, and how stale each collector is.

A run carries the cause and the remediation, never a raw exception string. An
exception message is written for whoever wrote the code; a remediation is
written for whoever has to fix the account, and those are rarely the same
person.

Freshness is judged per collector against that collector's own cadence, because
a daily collector and an hourly one cannot share a threshold. The interval comes
from `collector_schedule`, which is where ADR-0012 puts it so an operator can
change it without a deploy.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Connection

from finops_api.db.repositories import (
    AccessContext,
    IngestRunRepository,
    ScheduleRepository,
    WatermarkRepository,
)
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import Envelope, FreshnessOut, RunOut
from finops_core.constants import STALE_AFTER_CADENCE_MULTIPLE
from finops_core.domain.tenant import Scope

router = APIRouter(prefix=API_PREFIX, tags=["ingest"])

RECENT_RUNS = 50


@router.get("/ingest/runs", response_model=Envelope[list[RunOut]])
def recent_runs(
    scope: Scope = Depends(get_scope),
    connection: Connection = Depends(get_connection),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[RunOut]]:
    rows = IngestRunRepository(connection, context).recent(scope, limit=RECENT_RUNS)
    runs = [
        RunOut(
            run_id=str(row.run_id),
            collector=str(row.collector),
            scope_key=str(row.scope_key),
            status=str(row.status),
            started_at=row.started_at,
            finished_at=row.finished_at,
            items_written=int(row.items_written),
            error_type=row.error_type,
            error_detail=row.error_detail,
        )
        for row in rows
    ]
    # A run record is both the fact and the fetch, so the timestamps come from
    # the newest run rather than from `freshness_of`, which found no `as_of`
    # column here and reported the page as never collected however many runs it
    # was showing. Newest rather than oldest: this is a log, and a log is as
    # fresh as its last entry. ISS-159.
    newest = rows[0] if rows else None
    return Envelope(
        data=runs,
        meta=build_meta(
            connection,
            scope,
            context,
            visible=len(runs),
            as_of=newest.as_of_window_end if newest is not None else None,
            collected_at=(newest.finished_at or newest.started_at) if newest is not None else None,
            # Runs, not accounts. This page shows the most recent few of however
            # many the tenant has, and saying `8 of 8 accounts` over a five
            # account estate was a claim about the wrong thing entirely.
            coverage=IngestRunRepository(connection, context).coverage(scope, shown=len(runs)),
            coverage_unit="runs",
        ),
    )


def staleness(row: Any, cadences: dict[str, int], at: datetime) -> FreshnessOut:
    collector = str(row.collector)
    cadence = cadences.get(collector)
    age = (at - row.as_of).total_seconds()
    return FreshnessOut(
        collector=collector,
        scope_key=str(row.scope_key),
        as_of=row.as_of,
        cadence_seconds=cadence,
        age_seconds=age,
        # A collector with no schedule row cannot be judged, so it is reported
        # as stale rather than as fine. An unknown cadence is not a healthy one.
        state=(
            "stale"
            if cadence is None or age > cadence * STALE_AFTER_CADENCE_MULTIPLE
            else "current"
        ),
    )


def never_collected(row: Any, cadences: dict[str, int]) -> FreshnessOut:
    """A pair that has been attempted and has never once succeeded.

    Absent from this page until ISS-163, because the page listed watermarks and
    a watermark only exists after a success. The collector a reader most wants
    to find on a freshness page is the one that has never worked, and it was the
    one the page left out.
    """
    return FreshnessOut(
        collector=str(row.collector),
        scope_key=str(row.scope_key),
        # Null, not the epoch and not now. There has never been a moment when
        # this was true at the source, and any number here would name one.
        as_of=None,
        cadence_seconds=cadences.get(str(row.collector)),
        age_seconds=None,
        state="never_collected",
        cause=row.error_type,
    )


@router.get("/health/freshness", response_model=Envelope[list[FreshnessOut]])
def freshness(
    scope: Scope = Depends(get_scope),
    connection: Connection = Depends(get_connection),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[FreshnessOut]]:
    cadences = ScheduleRepository(connection, context).cadences(scope)
    rows = WatermarkRepository(connection, context).list_all(scope)
    at = datetime.now(UTC)
    unstarted = IngestRunRepository(connection, context).never_succeeded(scope)
    entries = sorted(
        [staleness(row, cadences, at) for row in rows]
        + [never_collected(row, cadences) for row in unstarted],
        key=lambda entry: (entry.collector, entry.scope_key),
    )
    # A watermark records as_of and updated_at rather than collected_at, so the
    # timestamps are passed rather than inferred. The oldest is the honest one:
    # a set of collectors is only as fresh as the one furthest behind.
    oldest_as_of = min((row.as_of for row in rows), default=None)
    oldest_update = min((row.updated_at for row in rows), default=None)
    return Envelope(
        data=entries,
        meta=build_meta(
            connection,
            scope,
            context,
            visible=len(entries),
            as_of=oldest_as_of,
            collected_at=oldest_update,
            # Collectors, not accounts. Every collector with a watermark is
            # shown, so this page is complete by construction and says so.
            coverage=(len(entries), len(entries)),
            coverage_unit="collectors",
        ),
    )
