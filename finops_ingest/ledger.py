"""The run ledger. What makes a collection idempotent, resumable and observable.

Three guarantees live here and each one is a database constraint rather than a
convention, because application code is not what holds when two workers claim
the same unit at the same instant.

A run is claimed by inserting its idempotency key, which is a hash of the
collector, the scope and the window. The wall clock is deliberately not part of
it: including it makes every run unique, which defeats the entire mechanism
while looking like it works. A duplicate claim is a no operation, not a second
run. ISS-008.

The watermark advances only after the write succeeds. Advancing first loses a
window of data silently, and nothing anywhere surfaces it. It also only ever
moves forward, so a backfill reading an older window cannot rewind the frontier
and cause everything after it to be read again.

A crashed run is reclaimable once its claim is older than the timeout. Without
that, one worker dying takes a scope out of collection permanently and the only
symptom is a number that stops changing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from finops_core.errors import CollectionError

Clock = Callable[[], datetime]

#: The statuses a claim can be taken back from. A run that reached a terminal
#: state is never reclaimed, because its result already exists.
RECLAIMABLE = ("CLAIMED", "RUNNING")


def _system_clock() -> datetime:
    return datetime.now(UTC)


def idempotency_key(
    collector: str, scope_key: str, window_start: datetime, window_end: datetime
) -> str:
    """A stable identity for one unit of work.

    Nothing here varies between two attempts at the same work. In particular
    there is no timestamp of when the attempt was made, only the window it
    covers, which is the whole point.
    """
    material = "|".join([collector, scope_key, window_start.isoformat(), window_end.isoformat()])
    return sha256(material.encode()).hexdigest()


@dataclass(frozen=True)
class RunClaim:
    """A unit of work this worker now owns."""

    run_id: UUID
    idempotency_key: str
    collector: str
    scope_key: str
    window_start: datetime
    window_end: datetime


class RunLedger:
    """Claims, completes and fails runs, and moves watermarks."""

    def __init__(
        self,
        connection: Connection,
        tenant_id: UUID,
        claim_timeout_minutes: int,
        clock: Clock = _system_clock,
    ) -> None:
        self._connection = connection
        self._tenant_id = tenant_id
        self._timeout = timedelta(minutes=claim_timeout_minutes)
        self._clock = clock

    # -- claiming ----------------------------------------------------------

    def claim(
        self, collector: str, scope_key: str, window_start: datetime, window_end: datetime
    ) -> RunClaim | None:
        """Take ownership of one unit of work, or return None if there is none to take.

        None means the work is already done or already in flight. It is not an
        error, it is the normal outcome of two workers reaching for the same
        thing, which is exactly what the unique constraint is for.
        """
        key = idempotency_key(collector, scope_key, window_start, window_end)
        run_id = uuid4()
        try:
            with self._connection.begin_nested():
                self._connection.execute(
                    text(
                        "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, "
                        "idempotency_key, started_at, status, as_of_window_start, "
                        "as_of_window_end) VALUES (:run, :tenant, :collector, :scope, "
                        ":key, :started, 'CLAIMED', :start, :end)"
                    ),
                    {
                        "run": run_id,
                        "tenant": self._tenant_id,
                        "collector": collector,
                        "scope": scope_key,
                        "key": key,
                        "started": self._clock(),
                        "start": window_start,
                        "end": window_end,
                    },
                )
        except IntegrityError:
            return self._reclaim(key, collector, scope_key, window_start, window_end)
        return RunClaim(
            run_id=run_id,
            idempotency_key=key,
            collector=collector,
            scope_key=scope_key,
            window_start=window_start,
            window_end=window_end,
        )

    def _reclaim(
        self,
        key: str,
        collector: str,
        scope_key: str,
        window_start: datetime,
        window_end: datetime,
    ) -> RunClaim | None:
        """Take back a claim whose owner has not been heard from since the timeout."""
        cutoff = self._clock() - self._timeout
        statuses = ", ".join(f"'{status}'" for status in RECLAIMABLE)
        row = self._connection.execute(
            text(
                "UPDATE ingest_run SET started_at = :now, status = 'CLAIMED' "
                "WHERE tenant_id = :tenant AND idempotency_key = :key "
                f"AND status IN ({statuses}) AND started_at < :cutoff "
                "RETURNING run_id"
            ),
            {"now": self._clock(), "tenant": self._tenant_id, "key": key, "cutoff": cutoff},
        ).first()
        if row is None:
            return None
        return RunClaim(
            run_id=row[0],
            idempotency_key=key,
            collector=collector,
            scope_key=scope_key,
            window_start=window_start,
            window_end=window_end,
        )

    # -- finishing ---------------------------------------------------------

    def running(self, claim: RunClaim) -> None:
        self._set_status(claim, "RUNNING")

    def complete(
        self, claim: RunClaim, items_written: int, bytes_read: int, status: str = "SUCCEEDED"
    ) -> None:
        """Record the result, then move the watermark. Never the other way round."""
        self._connection.execute(
            text(
                "UPDATE ingest_run SET status = :status, finished_at = :now, "
                "items_written = :items, bytes_read = :bytes, error_type = NULL, "
                "error_detail = NULL WHERE run_id = :run"
            ),
            {
                "status": status,
                "now": self._clock(),
                "items": items_written,
                "bytes": bytes_read,
                "run": claim.run_id,
            },
        )
        self._advance_watermark(claim)

    def fail(self, claim: RunClaim, error: CollectionError, items_written: int = 0) -> None:
        """Record the typed cause. The watermark does not move."""
        self._connection.execute(
            text(
                "UPDATE ingest_run SET status = 'FAILED', finished_at = :now, "
                "items_written = :items, error_type = :cause, error_detail = :detail "
                "WHERE run_id = :run"
            ),
            {
                "now": self._clock(),
                "items": items_written,
                "cause": error.cause,
                "detail": f"{error.detail}. {error.remediation}".strip(),
                "run": claim.run_id,
            },
        )

    def _set_status(self, claim: RunClaim, status: str) -> None:
        self._connection.execute(
            text("UPDATE ingest_run SET status = :status WHERE run_id = :run"),
            {"status": status, "run": claim.run_id},
        )

    # -- watermarks --------------------------------------------------------

    def _advance_watermark(self, claim: RunClaim) -> None:
        """Move the frontier forward, and only ever forward.

        GREATEST rather than assignment, because a backfill reading an older
        window must not rewind the frontier and cause every window after it to
        be collected again.
        """
        self._connection.execute(
            text(
                "INSERT INTO ingest_watermark (tenant_id, collector, scope_key, as_of, "
                "updated_at) VALUES (:tenant, :collector, :scope, :as_of, :now) "
                "ON CONFLICT (tenant_id, collector, scope_key) DO UPDATE SET "
                "as_of = GREATEST(ingest_watermark.as_of, EXCLUDED.as_of), "
                "updated_at = EXCLUDED.updated_at"
            ),
            {
                "tenant": self._tenant_id,
                "collector": claim.collector,
                "scope": claim.scope_key,
                "as_of": claim.window_end,
                "now": self._clock(),
            },
        )

    def watermark(self, collector: str, scope_key: str) -> datetime | None:
        """How far this collector has read for this scope, or None if never."""
        row = self._connection.execute(
            text(
                "SELECT as_of FROM ingest_watermark WHERE tenant_id = :tenant "
                "AND collector = :collector AND scope_key = :scope"
            ),
            {"tenant": self._tenant_id, "collector": collector, "scope": scope_key},
        ).first()
        return None if row is None else row[0]
