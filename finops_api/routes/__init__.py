"""The P0 routes, and the pieces every one of them shares.

Two helpers live here because getting either wrong quietly would undo the whole
freshness contract.

`freshness_of` takes the oldest timestamp in a set, not the newest. A list of
figures is only as fresh as its stalest member, and reporting the newest would
mean one recently refreshed account makes a page of month old numbers look
current.

`coverage_for` counts the organization, not the visible set. Computing the
denominator from what the caller can see always reports full coverage, which is
ISS-016 exactly and why it survives review.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy.engine import Connection

from finops_api.db.repositories import (
    AccessContext,
    AccountRepository,
    SyncErrorRepository,
)
from finops_api.schemas import FailureOut, Meta
from finops_core.domain.tenant import Scope

API_PREFIX = "/api/v1"


def freshness_of(rows: Sequence[Any]) -> tuple[datetime | None, datetime | None]:
    """The stalest `as_of` and `collected_at` in a set, or None when it is empty.

    Only rows carrying both are considered. Not every table is a fact table:
    `ingest_watermark` records `as_of` and `updated_at` rather than
    `collected_at`, and a helper that guessed which field to substitute would be
    inventing a provenance claim. A route with a table like that passes its own
    timestamps in instead.
    """
    stamps = [
        (row.as_of, row.collected_at)
        for row in rows
        if getattr(row, "as_of", None) is not None
        and getattr(row, "collected_at", None) is not None
    ]
    if not stamps:
        return None, None
    return min(s[0] for s in stamps), min(s[1] for s in stamps)


def open_failures(
    connection: Connection, scope: Scope, context: AccessContext
) -> tuple[FailureOut, ...]:
    """Everything currently broken in this scope, with what to do about it.

    Carried on every response rather than behind its own endpoint, because a
    failure a reader has to go looking for is a failure they will not see while
    they are reading the number it affects.
    """
    rows = SyncErrorRepository(connection, context).open_errors(scope)
    return tuple(
        FailureOut(
            scope_key=str(row.scope_key),
            collector=str(row.collector),
            cause=str(row.error_type),
            remediation=str(row.remediation),
            occurrences=int(row.occurrences),
            last_seen_at=row.last_seen_at,
        )
        for row in rows
    )


def build_meta(
    connection: Connection,
    scope: Scope,
    context: AccessContext,
    visible: int,
    rows: Sequence[Any] = (),
    as_of: datetime | None = None,
    collected_at: datetime | None = None,
    coverage: tuple[int, int] | None = None,
    coverage_unit: str = "accounts",
    extra_failures: Sequence[FailureOut] = (),
) -> Meta:
    """The envelope every route returns, assembled the same way each time.

    A route whose rows are not facts passes its timestamps explicitly rather
    than letting this guess at fields that are not there.

    `coverage` is for a route whose estate is not measured in accounts. The
    query routes read workspaces, and a findings list drawn from one of two
    workspaces is partial in a way that counting accounts cannot express.
    """
    if as_of is None and collected_at is None:
        as_of, collected_at = freshness_of(rows)
    if coverage is not None:
        visible, total = coverage
    elif scope.chosen is not None:
        # The reader chose this one account, FEAT-075, so coverage is counted against the
        # choice: stated, by the owner's decision of 2026-10-06, rather than reported as a
        # partial view. Every view nobody narrowed keeps the organization's total, ISS-016.
        total = 1
    else:
        total = AccountRepository(connection, context).count_in_organization(scope)
    return Meta.build(
        visible=visible,
        total=max(total, visible),
        unit=coverage_unit,
        as_of=as_of,
        collected_at=collected_at,
        failures=(*open_failures(connection, scope, context), *extra_failures),
        chosen=None if scope.chosen is None else scope.chosen.account_id,
    )
