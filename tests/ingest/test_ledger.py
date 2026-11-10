"""Idempotency, resumability and the watermark, proved against a real database.

The guarantees here are the ones that fail silently when they fail. A run that
happens twice double counts. A watermark advanced before the write succeeds
skips a window and nothing reports it. A crashed run that cannot be reclaimed
takes a scope out of collection permanently, and the only symptom is a figure
that quietly stops changing.

None of that shows up as an error, which is why all three are database
constraints and why these tests run against PostgreSQL rather than a mock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import Engine, text

from finops_core.errors import AccessDenied, Throttled
from finops_ingest.ledger import RunLedger, idempotency_key

COLLECTOR = "org_tree"
SCOPE = "aws:111122223333:eu-west-1"
START = datetime(2026, 8, 24, 0, 0, tzinfo=UTC)
END = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
NOW = datetime(2026, 8, 24, 6, 5, tzinfo=UTC)
TIMEOUT_MINUTES = 30


class MovableClock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


# --- the key, with no database ----------------------------------------------


def test_the_key_does_not_depend_on_the_wall_clock() -> None:
    """A clock in the key makes every run unique, which defeats the mechanism."""
    first = idempotency_key(COLLECTOR, SCOPE, START, END)
    second = idempotency_key(COLLECTOR, SCOPE, START, END)
    assert first == second


def test_the_key_changes_with_every_part_of_the_work() -> None:
    base = idempotency_key(COLLECTOR, SCOPE, START, END)
    assert idempotency_key("other", SCOPE, START, END) != base
    assert idempotency_key(COLLECTOR, "aws:999:eu-west-1", START, END) != base
    assert idempotency_key(COLLECTOR, SCOPE, START + timedelta(hours=1), END) != base
    assert idempotency_key(COLLECTOR, SCOPE, START, END + timedelta(hours=1)) != base


# --- against a real database -------------------------------------------------
#
# Marked one by one rather than for the whole module, because the two tests
# above need no database and a module marker would exile them to the slow job
# for nothing.


def runs_for(engine: Engine, tenant: UUID) -> list[dict[str, object]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT * FROM ingest_run WHERE tenant_id = :t ORDER BY started_at"),
            {"t": tenant},
        ).mappings()
        return [dict(row) for row in rows]


def collect_once(engine: Engine, tenant: UUID, clock: MovableClock, written: list[int]) -> bool:
    """One attempt at the same unit of work. True when this attempt owned it."""
    with engine.begin() as connection:
        book = RunLedger(connection, tenant, TIMEOUT_MINUTES, clock=clock)
        claim = book.claim(COLLECTOR, SCOPE, START, END)
        if claim is None:
            return False
        book.running(claim)
        written.append(1)
        book.complete(claim, items_written=10, bytes_read=2048)
        return True


@pytest.mark.integration
def test_running_three_times_writes_one_result_set(engine: Engine, tenant_id: UUID) -> None:
    """The core idempotency guarantee. ISS-008."""
    clock = MovableClock(NOW)
    written: list[int] = []
    outcomes = [collect_once(engine, tenant_id, clock, written) for _ in range(3)]
    assert outcomes == [True, False, False]
    assert written == [1]
    assert len(runs_for(engine, tenant_id)) == 1


@pytest.mark.integration
def test_a_duplicate_claim_is_none_rather_than_an_error(engine: Engine, tenant_id: UUID) -> None:
    """Two workers reaching for the same unit is normal, not exceptional."""
    clock = MovableClock(NOW)
    with engine.begin() as connection:
        assert RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=clock).claim(
            COLLECTOR, SCOPE, START, END
        )
    with engine.begin() as connection:
        assert (
            RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=clock).claim(
                COLLECTOR, SCOPE, START, END
            )
            is None
        )


@pytest.mark.integration
def test_the_run_records_the_counters_and_the_window(engine: Engine, tenant_id: UUID) -> None:
    clock = MovableClock(NOW)
    with engine.begin() as connection:
        book = RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=clock)
        claim = book.claim(COLLECTOR, SCOPE, START, END)
        assert claim is not None
        book.complete(claim, items_written=42, bytes_read=9001)

    row = runs_for(engine, tenant_id)[0]
    assert row["status"] == "SUCCEEDED"
    assert row["items_written"] == 42
    assert row["bytes_read"] == 9001
    assert row["as_of_window_start"] == START
    assert row["as_of_window_end"] == END
    assert row["error_type"] is None


# --- watermarks --------------------------------------------------------------


@pytest.mark.integration
def test_the_watermark_starts_as_nothing(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        book = RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=MovableClock(NOW))
        assert book.watermark(COLLECTOR, SCOPE) is None


@pytest.mark.integration
def test_the_watermark_advances_on_success(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        book = RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=MovableClock(NOW))
        claim = book.claim(COLLECTOR, SCOPE, START, END)
        assert claim is not None
        book.complete(claim, items_written=1, bytes_read=1)
        assert book.watermark(COLLECTOR, SCOPE) == END


@pytest.mark.integration
def test_watermark_not_advanced_on_failure(engine: Engine, tenant_id: UUID) -> None:
    """Advancing on failure skips a window of data and nothing surfaces it."""
    with engine.begin() as connection:
        book = RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=MovableClock(NOW))
        claim = book.claim(COLLECTOR, SCOPE, START, END)
        assert claim is not None
        book.fail(claim, AccessDenied(scope_key=SCOPE, collector=COLLECTOR, detail="no role"))
        assert book.watermark(COLLECTOR, SCOPE) is None

    row = runs_for(engine, tenant_id)[0]
    assert row["status"] == "FAILED"
    assert row["error_type"] == "AccessDenied"
    assert "no role" in str(row["error_detail"])


@pytest.mark.integration
def test_a_failed_run_records_a_cause_the_database_accepts(engine: Engine, tenant_id: UUID) -> None:
    """The stored cause set mirrors the taxonomy, so an invented one is refused."""
    with engine.begin() as connection:
        book = RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=MovableClock(NOW))
        claim = book.claim(COLLECTOR, SCOPE, START, END)
        assert claim is not None
        book.fail(claim, Throttled(scope_key=SCOPE, collector=COLLECTOR))
    assert runs_for(engine, tenant_id)[0]["error_type"] == "Throttled"


@pytest.mark.integration
def test_the_watermark_only_ever_moves_forward(engine: Engine, tenant_id: UUID) -> None:
    """A backfill of an older window must not rewind the frontier."""
    clock = MovableClock(NOW)
    with engine.begin() as connection:
        book = RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=clock)
        claim = book.claim(COLLECTOR, SCOPE, START, END)
        assert claim is not None
        book.complete(claim, items_written=1, bytes_read=1)

    earlier_start = START - timedelta(days=7)
    earlier_end = END - timedelta(days=7)
    with engine.begin() as connection:
        book = RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=clock)
        backfill = book.claim(COLLECTOR, SCOPE, earlier_start, earlier_end)
        assert backfill is not None
        book.complete(backfill, items_written=1, bytes_read=1)
        assert book.watermark(COLLECTOR, SCOPE) == END


# --- reclaiming --------------------------------------------------------------


@pytest.mark.integration
def test_a_fresh_claim_cannot_be_taken_from_its_owner(engine: Engine, tenant_id: UUID) -> None:
    clock = MovableClock(NOW)
    with engine.begin() as connection:
        assert RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=clock).claim(
            COLLECTOR, SCOPE, START, END
        )
    clock.at = NOW + timedelta(minutes=TIMEOUT_MINUTES - 1)
    with engine.begin() as connection:
        assert (
            RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=clock).claim(
                COLLECTOR, SCOPE, START, END
            )
            is None
        )


@pytest.mark.integration
def test_crashed_run_is_reclaimable(engine: Engine, tenant_id: UUID) -> None:
    """Otherwise one worker dying removes a scope from collection permanently."""
    clock = MovableClock(NOW)
    with engine.begin() as connection:
        book = RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=clock)
        first = book.claim(COLLECTOR, SCOPE, START, END)
        assert first is not None
        book.running(first)

    clock.at = NOW + timedelta(minutes=TIMEOUT_MINUTES + 1)
    with engine.begin() as connection:
        book = RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=clock)
        retaken = book.claim(COLLECTOR, SCOPE, START, END)
        assert retaken is not None
        assert retaken.run_id == first.run_id
        book.complete(retaken, items_written=5, bytes_read=10)

    rows = runs_for(engine, tenant_id)
    assert len(rows) == 1, "reclaiming must take the row over, not add a second"
    assert rows[0]["status"] == "SUCCEEDED"


@pytest.mark.integration
def test_a_finished_run_is_never_reclaimed(engine: Engine, tenant_id: UUID) -> None:
    """Its result already exists. Retaking it would double count."""
    clock = MovableClock(NOW)
    with engine.begin() as connection:
        book = RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=clock)
        claim = book.claim(COLLECTOR, SCOPE, START, END)
        assert claim is not None
        book.complete(claim, items_written=1, bytes_read=1)

    clock.at = NOW + timedelta(days=30)
    with engine.begin() as connection:
        assert (
            RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=clock).claim(
                COLLECTOR, SCOPE, START, END
            )
            is None
        )


@pytest.mark.integration
def test_a_failed_run_can_be_retried_after_the_timeout(engine: Engine, tenant_id: UUID) -> None:
    """A failure is terminal for that attempt, so the retry is a fresh window claim."""
    clock = MovableClock(NOW)
    with engine.begin() as connection:
        book = RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=clock)
        claim = book.claim(COLLECTOR, SCOPE, START, END)
        assert claim is not None
        book.fail(claim, Throttled(scope_key=SCOPE, collector=COLLECTOR))

    later_end = END + timedelta(hours=6)
    with engine.begin() as connection:
        book = RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=clock)
        assert book.claim(COLLECTOR, SCOPE, START, later_end) is not None


@pytest.mark.integration
def test_two_scopes_do_not_block_each_other(engine: Engine, tenant_id: UUID) -> None:
    clock = MovableClock(NOW)
    with engine.begin() as connection:
        book = RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=clock)
        assert book.claim(COLLECTOR, SCOPE, START, END) is not None
        assert book.claim(COLLECTOR, "aws:444455556666:eu-west-1", START, END) is not None
    assert len(runs_for(engine, tenant_id)) == 2


@pytest.mark.integration
def test_two_tenants_can_run_the_same_unit_of_work(engine: Engine, tenant_id: UUID) -> None:
    """The same account onboarded twice must not starve one of the two tenants."""
    from uuid import uuid4

    other = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenant (tenant_id, name) VALUES (:id, :name)"),
            {"id": other, "name": f"tenant-{other}"},
        )
    clock = MovableClock(NOW)
    with engine.begin() as connection:
        assert RunLedger(connection, tenant_id, TIMEOUT_MINUTES, clock=clock).claim(
            COLLECTOR, SCOPE, START, END
        )
    with engine.begin() as connection:
        assert RunLedger(connection, other, TIMEOUT_MINUTES, clock=clock).claim(
            COLLECTOR, SCOPE, START, END
        )
