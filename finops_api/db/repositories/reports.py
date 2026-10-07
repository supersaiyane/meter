"""Export records, and what a scheduled run adds to them. FEAT-067 and FEAT-069.

`record_run` writes one row per file in the transaction of the read it records, because an
export that skipped it would be a copy of the estate nobody could trace. A scheduled run adds
its schedule, its kept file and its outcome to that same row, or records a run that made no
file with its typed cause, TASK-P8-011. `RunRepository` reads a person's runs for the Scheduled
screen, `ByPrincipal`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Row, Select, func
from sqlalchemy.engine import Connection

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_core.domain.tenant import Scope

#: A run's row, read through `Any` as the other repositories read theirs.
RunRow = Row[*tuple[Any, ...]]


def record_run(
    connection: Connection,
    *,
    tenant_id: UUID,
    principal_id: str,
    view_path: str,
    view_query: str,
    scope_accounts: Sequence[str] | None,
    file_format: str,
    rows: int,
    size: int,
    truncated: bool,
    made_at: datetime,
    as_of: datetime | None = None,
    collected_at: datetime | None = None,
) -> UUID:
    """One row for one export file, in the transaction of the read it records.

    `scope_accounts` is None for a global scope and the named accounts otherwise, so a narrowed
    scope that named none is recorded as exactly that rather than as everything.
    """
    run_id = uuid4()
    connection.execute(
        models.report_run.insert().values(
            run_id=run_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            view_path=view_path,
            view_query=view_query,
            scope_global=scope_accounts is None,
            scope_accounts=[] if scope_accounts is None else sorted(scope_accounts),
            format=file_format,
            row_count=rows,
            byte_count=size,
            truncated=truncated,
            made_at=made_at,
            status="STREAMED",
            as_of=as_of,
            collected_at=collected_at,
            finished_at=made_at,
        )
    )
    return run_id


def _not_before_made(finished_at: datetime) -> Any:
    """The finish, or the making where the two clocks disagree. The runner and the request that
    made the file read different clocks, possibly in different containers, and a run recorded as
    finishing before it was made is refused by the table, rightly."""
    return func.greatest(models.report_run.c.made_at, finished_at)


def mark_kept(
    connection: Connection,
    *,
    run_id: UUID,
    schedule_id: UUID,
    storage_key: str,
    sent: bool,
    finished_at: datetime,
) -> None:
    """A rendered file kept in the store for its schedule, SENT when a sender took it.

    The row is the one the responder wrote when the file was made, so one file keeps one record:
    the schedule and the key are added to it rather than written beside it.
    """
    connection.execute(
        models.report_run.update()
        .where(models.report_run.c.run_id == run_id)
        .values(
            schedule_id=schedule_id,
            storage_key=storage_key,
            status="SENT" if sent else "RENDERED",
            finished_at=_not_before_made(finished_at),
        )
    )


def mark_failed(
    connection: Connection,
    *,
    run_id: UUID,
    schedule_id: UUID,
    cause: str,
    detail: str,
    finished_at: datetime,
    storage_key: str | None = None,
) -> None:
    """A file that was made and then not kept, or kept and not sent, with the typed cause.

    A file kept and not sent keeps its key, so its recipient can still fetch it.
    """
    connection.execute(
        models.report_run.update()
        .where(models.report_run.c.run_id == run_id)
        .values(
            schedule_id=schedule_id,
            storage_key=storage_key,
            status="FAILED",
            failure_cause=cause,
            failure_detail=detail,
            finished_at=_not_before_made(finished_at),
        )
    )


def record_failed_run(
    connection: Connection,
    *,
    tenant_id: UUID,
    principal_id: str,
    schedule_id: UUID,
    view_path: str,
    view_query: str,
    scope_accounts: Sequence[str] | None,
    file_format: str,
    cause: str,
    detail: str,
    made_at: datetime,
) -> UUID:
    """A scheduled run that made no file, with the typed cause, so its recipient reads why."""
    run_id = uuid4()
    connection.execute(
        models.report_run.insert().values(
            run_id=run_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            view_path=view_path,
            view_query=view_query,
            scope_global=scope_accounts is None,
            scope_accounts=[] if scope_accounts is None else sorted(scope_accounts),
            format=file_format,
            row_count=0,
            byte_count=0,
            truncated=False,
            made_at=made_at,
            schedule_id=schedule_id,
            status="FAILED",
            failure_cause=cause,
            failure_detail=detail,
            finished_at=made_at,
        )
    )
    return run_id


class RunRepository(ScopedRepository):
    """The runs made for the reader: the files they exported and the ones schedules rendered.

    `ByPrincipal`, ADR-0029: a run is read by the person it was made for and by nobody else.
    """

    table = models.report_run
    resource = "report_run"

    def runs(self, scope: Scope, limit: int) -> Sequence[RunRow]:
        """The reader's runs, the latest made first."""
        statement = (
            self.scoped_select(scope)
            .order_by(self.table.c.made_at.desc(), self.table.c.run_id)
            .limit(limit)
        )
        rows: Sequence[RunRow] = self.fetch(scope, statement)
        return rows

    def count(self, scope: Scope) -> int:
        """How many the reader has, so a list cut at its limit says it was cut."""
        projected = self.scoped_select(scope).with_only_columns(func.count())
        rows: Sequence[RunRow] = self.fetch(scope, cast("Select[*tuple[object, ...]]", projected))
        return int(rows[0][0])

    def run(self, scope: Scope, run_id: UUID) -> RunRow | None:
        """One run, or None when the reader has none of that id."""
        rows: Sequence[RunRow] = self.fetch(
            scope, self.scoped_select(scope).where(self.table.c.run_id == run_id)
        )
        return rows[0] if rows else None
