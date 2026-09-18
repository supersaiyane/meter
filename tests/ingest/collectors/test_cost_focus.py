"""Writing the bill, twice, and getting the same bill.

AWS restates a billing period continuously and can restate a closed one. So the
question this collector has to answer is not whether it can write rows. It is
whether writing the same period again leaves the same rows, and whether writing
a corrected row lands on the row it corrects rather than beside it.

One day of data hides all of it. That is how ISS-175 and ISS-177 both survived,
and it is why these tests ingest twice rather than once.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core import errors
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.registry import CollectorContext
from finops_providers.fake.cur import (
    CLOSED_PERIOD,
    CORRECTED_FINGERPRINT,
    ESTATE,
    OPEN_PERIOD,
    RETRACTED_FINGERPRINT,
    FakeCostExport,
    restate,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


@pytest.fixture(autouse=True, scope="module")
def _leave_the_partitions_as_we_found_them(engine: Engine) -> Iterator[None]:
    """Partitions are not tenant scoped, so they are shared by every test.

    These tests create the months the fake estate bills in, and
    `test_maintenance_creates_the_months_and_is_then_a_no_op` in the retention
    suite asserts an exact count of the partitions it creates. Leaving ours
    behind makes that assertion depend on which file pytest ran first, which is
    a test that measures the ordering rather than the code.

    Only partitions this module added are removed, by difference against a
    snapshot taken before it ran, and only ever inside the throwaway container
    the `engine` fixture starts.
    """
    from finops_ingest.collectors.partitions import existing_partitions

    parents = ("cost_focus_daily", "cost_provider_extra")
    with engine.connect() as connection:
        before = {parent: set(existing_partitions(connection, parent)) for parent in parents}
    yield
    with engine.begin() as connection:
        for parent, names in before.items():
            for name in set(existing_partitions(connection, parent)) - names:
                connection.execute(text(f"DROP TABLE IF EXISTS {name}"))


def partitions_for(connection: object) -> None:
    """Every month the fake estate touches, plus the one it does not.

    `partition_maintenance` does this in a running system. Doing it here rather
    than in the collector is the point of `test_a_period_with_no_partition_fails`.
    """
    for month in (date(2026, 6, 1), CLOSED_PERIOD, OPEN_PERIOD):
        ensure_partition(connection, "cost_focus_daily", month)


def ingest(
    engine: Engine,
    tenant: UUID,
    export: FakeCostExport | None = None,
    run_id: UUID | None = None,
) -> int:
    with engine.begin() as connection:
        partitions_for(connection)
        collector = CostFocusCollector(export or FakeCostExport(), clock=lambda: NOW)
        outcome = collector(
            CollectorContext(
                unit=Unit(tenant_id=tenant),
                connection=connection,
                run_id=run_id or uuid4(),
            )
        )
    return int(outcome.items_written)


def rows_for(engine: Engine, tenant: UUID) -> list[tuple[str, Decimal]]:
    with engine.connect() as connection:
        return [
            (row[0], row[1])
            for row in connection.execute(
                text(
                    "SELECT source_fingerprint, effective_cost FROM cost_focus_daily "
                    "WHERE tenant_id = :t ORDER BY source_fingerprint"
                ),
                {"t": tenant},
            )
        ]


class TestWritingTheSamePeriodTwice:
    def test_the_second_run_leaves_the_same_rows(self, engine: Engine, tenant_id: UUID) -> None:
        """Counted and compared, not argued from the presence of an upsert."""
        first_written = ingest(engine, tenant_id)
        first = rows_for(engine, tenant_id)
        assert first_written == len(first)

        ingest(engine, tenant_id)
        assert rows_for(engine, tenant_id) == first

    def test_it_writes_only_the_period_the_export_says_is_latest(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # The estate holds three periods. Writing all of them would pass every
        # other test here and quietly make each run cost three times as much.
        ingest(engine, tenant_id)
        with engine.connect() as connection:
            periods = set(
                connection.execute(
                    text(
                        "SELECT DISTINCT billing_period_start FROM cost_focus_daily "
                        "WHERE tenant_id = :t"
                    ),
                    {"t": tenant_id},
                ).scalars()
            )
        assert periods == {OPEN_PERIOD}


class TestARestatedRowLandsOnTheRowItCorrects:
    def test_a_changed_cost_updates_in_place(self, engine: Engine, tenant_id: UUID) -> None:
        """The whole reason the fingerprint hashes no cost.

        If it did, the corrected row would carry a different fingerprint, land
        beside the original, and the month would grow by one copy of every
        correction AWS ever issued.

        The restatement lands in the closed period, so the export handed to the
        collector holds only that period. Ingesting the estate whole would write
        the open month, where nothing was restated, and this test would pass
        against a collector that did nothing at all.
        """
        closed = tuple(row for row in ESTATE if row.billing_period_start == CLOSED_PERIOD)
        ingest(engine, tenant_id, export=FakeCostExport(rows=closed))
        before = dict(rows_for(engine, tenant_id))
        assert before[CORRECTED_FINGERPRINT], "the row about to be corrected is not there"

        ingest(engine, tenant_id, export=FakeCostExport(rows=restate(closed)))
        after = dict(rows_for(engine, tenant_id))

        assert len(after) == len(before), "a corrected row landed beside the original"
        assert after[CORRECTED_FINGERPRINT] != before[CORRECTED_FINGERPRINT]
        changed = [key for key in before if before[key] != after.get(key)]
        assert changed == [CORRECTED_FINGERPRINT], f"more than the correction moved: {changed}"

    def test_a_retracted_row_is_still_there_because_this_task_does_not_delete(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """Deliberately not in this task, and asserted so it stays that way.

        Retraction is the only destructive operation in the ingest path and it
        gets its own commit and its own review, TASK-P1-005. A delete arriving
        here by accident would be the most expensive kind of drive by.
        """
        closed = tuple(row for row in ESTATE if row.billing_period_start == CLOSED_PERIOD)
        ingest(engine, tenant_id, export=FakeCostExport(rows=closed))
        ingest(engine, tenant_id, export=FakeCostExport(rows=restate(closed)))
        assert RETRACTED_FINGERPRINT in dict(rows_for(engine, tenant_id))

    def test_the_run_id_moves_to_the_run_that_last_saw_the_row(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """TASK-P1-005 deletes on exactly this.

        A row re seen by this run carries this run's id. A row that was not re
        seen keeps an older one, which is the only signal that AWS retracted it.
        """
        first, second = uuid4(), uuid4()
        ingest(engine, tenant_id, run_id=first)
        ingest(engine, tenant_id, run_id=second)
        with engine.connect() as connection:
            ids = set(
                connection.execute(
                    text(
                        "SELECT DISTINCT ingest_run_id FROM cost_focus_daily WHERE tenant_id = :t"
                    ),
                    {"t": tenant_id},
                ).scalars()
            )
        assert ids == {second}


class TestFailuresAreTypedAndNeverZero:
    def test_a_typed_failure_reaches_the_caller_as_itself(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # The worker catches exactly the six domain errors and records the cause
        # against the scope. Swallowing it here would report a successful run
        # that wrote nothing, which reads as an estate that spent nothing.
        with pytest.raises(errors.AccessDenied):
            ingest(engine, tenant_id, export=FakeCostExport(failure=errors.AccessDenied))

    def test_an_export_that_has_published_nothing_says_so(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        with pytest.raises(errors.NoData):
            ingest(engine, tenant_id, export=FakeCostExport(rows=()))

    def test_a_missing_run_id_is_a_programming_error_and_not_a_collection_one(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """Nothing about the provider is wrong.

        A CollectionError here would be recorded against the scope and send
        somebody to look at AWS for a context the caller assembled wrongly.
        """
        with engine.begin() as connection:
            partitions_for(connection)
            collector = CostFocusCollector(FakeCostExport(), clock=lambda: NOW)
            with pytest.raises(ValueError, match="run id"):
                collector(CollectorContext(unit=Unit(tenant_id=tenant_id), connection=connection))

    def test_a_period_with_no_partition_fails_rather_than_misfiling(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """Constraint 11. The invariant is a schema rule, not a convention.

        Application code that quietly created the missing partition would be
        exactly the convention that is eventually not there, and the cost would
        land in the wrong month without anybody being told.
        """
        from dataclasses import replace

        from sqlalchemy.exc import DatabaseError

        # A period no other test creates a partition for. Partitions are shared
        # across tenants and the engine is session scoped, so asserting this
        # against the estate's own months passes or fails depending on which
        # tests ran first, which is a test that measures the ordering.
        orphan = date(2029, 1, 1)
        row = replace(
            ESTATE[0],
            billing_period_start=orphan,
            billing_period_end=date(2029, 2, 1),
        )

        with engine.begin() as connection:
            partitions_for(connection)
            collector = CostFocusCollector(FakeCostExport(rows=(row,)), clock=lambda: NOW)
            with pytest.raises(DatabaseError):
                collector(
                    CollectorContext(
                        unit=Unit(tenant_id=tenant_id), connection=connection, run_id=uuid4()
                    )
                )


class TestWhichTimestampIsWhose:
    def test_as_of_is_the_charges_and_collected_at_is_ours(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """Constraint 10. Conflating them makes a stale number look fresh."""
        ingest(engine, tenant_id)
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT as_of, collected_at, charge_period_end FROM cost_focus_daily "
                    "WHERE tenant_id = :t LIMIT 1"
                ),
                {"t": tenant_id},
            ).one()
        as_of, collected_at, charge_end = row
        assert collected_at == NOW
        assert as_of == charge_end
        assert collected_at >= as_of
