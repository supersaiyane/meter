"""The commitment collector over a real database.

The contract suite checks the port and the adapters. What this asks is whether the
right rows land: two grains kept apart, a window replaced rather than accumulated,
an expired commitment written rather than filtered, and a payer with nothing
reported as nothing rather than as a failure.

The last class is the one worth reading. It writes rows the application would never
produce, straight past the collector, and asserts the database refuses them.
Constraint 11: if application code is the only thing preventing a bad row, the bad
row will eventually exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from finops_core.errors import AccessDenied
from finops_fakes import fixtures
from finops_fakes.commitment import FakeCommitmentReport, days
from finops_ingest.collectors.commitment import DAYS_READ, CommitmentCollector
from finops_ingest.registry import CollectorContext

pytestmark = pytest.mark.integration

#: Inside August, so the collector's own month arithmetic produces the window the
#: fake is built around.
NOW = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
WINDOW_START = date(2026, 8, 1)
WINDOW_END = date(2026, 9, 1)


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


def collect(engine: Engine, tenant: UUID, report: object, *, run_id: UUID | None = None) -> int:
    with engine.begin() as connection:
        outcome = CommitmentCollector(report, clock=lambda: NOW)(
            CollectorContext(
                unit=Unit(tenant_id=tenant),
                connection=connection,
                run_id=run_id if run_id is not None else uuid4(),
            )
        )
    return int(outcome.items_written)


def uses(engine: Engine, tenant: UUID) -> list[tuple[str, str, Decimal, Decimal]]:
    with engine.connect() as connection:
        return [
            (row[0], row[1], row[2], row[3])
            for row in connection.execute(
                text(
                    "SELECT commitment_id, status, committed, wasted FROM commitment_use "
                    "WHERE tenant_id = :t ORDER BY wasted DESC"
                ),
                {"t": tenant},
            )
        ]


def coverages(engine: Engine, tenant: UUID) -> list[tuple[str, str, Decimal, Decimal]]:
    with engine.connect() as connection:
        return [
            (row[0], row[1], row[2], row[3])
            for row in connection.execute(
                text(
                    "SELECT commitment_type, dimension_value, eligible_spend, covered_spend "
                    "FROM commitment_coverage WHERE tenant_id = :t ORDER BY dimension_value"
                ),
                {"t": tenant},
            )
        ]


def day_rows(engine: Engine, tenant: UUID) -> list[tuple[str, date, Decimal, Decimal]]:
    with engine.connect() as connection:
        return [
            (row[0], row[1], row[2], row[3])
            for row in connection.execute(
                text(
                    "SELECT commitment_type, day, committed, covered_spend FROM commitment_day "
                    "WHERE tenant_id = :t ORDER BY day, commitment_type"
                ),
                {"t": tenant},
            )
        ]


#: The days the fake reports for the collector's read, ending the day before `NOW`.
EXPECTED_DAYS = days(NOW.date() - timedelta(days=DAYS_READ), NOW.date(), at=fixtures.AS_OF)


class TestBothGrainsAreWritten:
    def test_the_three_tables_are_filled_and_the_count_is_their_sum(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        written = collect(engine, tenant_id, FakeCommitmentReport())
        assert len(uses(engine, tenant_id)) == 4
        assert len(coverages(engine, tenant_id)) == 3
        assert EXPECTED_DAYS
        assert len(day_rows(engine, tenant_id)) == len(EXPECTED_DAYS)
        assert written == 4 + 3 + len(EXPECTED_DAYS)

    def test_the_days_end_the_day_before_the_run_and_never_include_it(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        collect(engine, tenant_id, FakeCommitmentReport())
        found = [day for _, day, _, _ in day_rows(engine, tenant_id)]
        assert max(found) < NOW.date()
        assert min(found) >= NOW.date() - timedelta(days=DAYS_READ)

    def test_the_wasted_money_is_carried_rather_than_recomputed_on_read(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        collect(engine, tenant_id, FakeCommitmentReport())
        worst = uses(engine, tenant_id)[0]
        assert worst[0] == "fake-ri-rds"
        assert worst[3] > Decimal("0")

    def test_an_expired_commitment_is_written_rather_than_filtered(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # The money was spent, and the coverage gap the expiry leaves is the
        # finding. A collector that dropped it would make the estate look like it
        # never had the commitment.
        collect(engine, tenant_id, FakeCommitmentReport())
        assert "EXPIRED" in {status for _, status, _, _ in uses(engine, tenant_id)}

    def test_a_commitment_that_has_not_started_is_written_with_nothing_committed(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        collect(engine, tenant_id, FakeCommitmentReport())
        queued = [row for row in uses(engine, tenant_id) if row[1] == "QUEUED"]
        assert queued
        assert queued[0][2] == Decimal("0")


class TestRunningItTwice:
    def test_a_second_run_replaces_the_window_rather_than_accumulating_it(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # Four runs a day would otherwise show a reader the same wasted dollar four
        # times, and they would stop believing the total.
        collect(engine, tenant_id, FakeCommitmentReport())
        collect(engine, tenant_id, FakeCommitmentReport())
        assert len(uses(engine, tenant_id)) == 4
        assert len(coverages(engine, tenant_id)) == 3
        # A day reread is a day replaced, which is how a late bill's correction lands.
        assert len(day_rows(engine, tenant_id)) == len(EXPECTED_DAYS)

    def test_the_second_run_owns_the_rows(self, engine: Engine, tenant_id: UUID) -> None:
        collect(engine, tenant_id, FakeCommitmentReport())
        second = uuid4()
        collect(engine, tenant_id, FakeCommitmentReport(), run_id=second)
        with engine.connect() as connection:
            runs = {
                row[0]
                for row in connection.execute(
                    text("SELECT DISTINCT ingest_run_id FROM commitment_use WHERE tenant_id = :t"),
                    {"t": tenant_id},
                )
            }
        # One run, and the later one. A row still naming the first run is a row the
        # ledger would attribute to a collection that did not produce it.
        assert runs == {second}


class TestWhenThereIsNothing:
    def test_a_payer_with_no_commitments_writes_nothing_and_does_not_fail(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """`NoData` is a fact about the estate, not a broken collection.

        The screen's job in that case is to say the estate holds no commitments,
        which it cannot do if the run is marked failed.
        """
        assert collect(engine, tenant_id, FakeCommitmentReport(holds_nothing=True)) == 0
        assert uses(engine, tenant_id) == []
        assert coverages(engine, tenant_id) == []

    def test_a_typed_failure_is_not_swallowed(self, engine: Engine, tenant_id: UUID) -> None:
        # Only NoData is absorbed. An access failure is a failure, and rendering it
        # as an estate with no commitments would be the zero constraint 5 forbids.
        with pytest.raises(AccessDenied):
            collect(engine, tenant_id, FakeCommitmentReport(AccessDenied))


class TestWhatItRefuses:
    def test_it_refuses_without_a_run_id(self, engine: Engine, tenant_id: UUID) -> None:
        with engine.begin() as connection, pytest.raises(ValueError, match="run id"):
            CommitmentCollector(FakeCommitmentReport(), clock=lambda: NOW)(
                CollectorContext(unit=Unit(tenant_id=tenant_id), connection=connection, run_id=None)
            )


class TestScope:
    def test_one_tenant_does_not_see_another(self, engine: Engine, tenant_id: UUID) -> None:
        neighbour = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO tenant (tenant_id, name) VALUES (:id, :name)"),
                {"id": neighbour, "name": f"tenant-{neighbour}"},
            )
        collect(engine, neighbour, FakeCommitmentReport())
        assert uses(engine, tenant_id) == []
        assert len(uses(engine, neighbour)) == 4


class TestTheDatabaseRefusesBadRows:
    """Rows the application would never build, written anyway.

    Constraint 11. Every assertion here would pass vacuously if the constraint were
    absent, so each one writes the violating row directly and requires the database
    to be what stops it.
    """

    def _insert(self, engine: Engine, tenant: UUID, **overrides: object) -> None:
        row: dict[str, object] = {
            "id": uuid4(),
            "tenant": tenant,
            "run": uuid4(),
            "commitment": f"direct-{uuid4()}",
            "type": "SavingsPlan",
            "status": "ACTIVE",
            "term_start": date(2026, 1, 1),
            "term_end": date(2027, 1, 1),
            "window_start": WINDOW_START,
            "window_end": WINDOW_END,
            "committed": Decimal("100.00"),
            "used": Decimal("60.00"),
            "wasted": Decimal("40.00"),
            "as_of": NOW,
            "collected_at": NOW,
        }
        row.update(overrides)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO commitment_use (use_id, tenant_id, ingest_run_id, "
                    "commitment_id, commitment_type, status, term_start, term_end, "
                    "window_start, window_end, committed, used, wasted, as_of, collected_at) "
                    "VALUES (:id, :tenant, :run, :commitment, :type, :status, :term_start, "
                    ":term_end, :window_start, :window_end, :committed, :used, :wasted, "
                    ":as_of, :collected_at)"
                ),
                row,
            )

    def _insert_coverage(self, engine: Engine, tenant: UUID, **overrides: object) -> None:
        row: dict[str, object] = {
            "id": uuid4(),
            "tenant": tenant,
            "run": uuid4(),
            "type": "SavingsPlan",
            "dimension": "SERVICE",
            "value": f"direct-{uuid4()}",
            "start": WINDOW_START,
            "end": WINDOW_END,
            "eligible": Decimal("100.00"),
            "covered": Decimal("10.00"),
            "at": NOW,
        }
        row.update(overrides)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO commitment_coverage (coverage_id, tenant_id, ingest_run_id, "
                    "commitment_type, dimension, dimension_value, window_start, window_end, "
                    "eligible_spend, covered_spend, as_of, collected_at) "
                    "VALUES (:id, :tenant, :run, :type, :dimension, :value, :start, :end, "
                    ":eligible, :covered, :at, :at)"
                ),
                row,
            )

    def test_a_well_formed_row_is_accepted(self, engine: Engine, tenant_id: UUID) -> None:
        # The control. Without it, every refusal below could be passing because the
        # insert is malformed for some reason that has nothing to do with the
        # constraint being named.
        self._insert(engine, tenant_id)
        self._insert_coverage(engine, tenant_id)

    def test_the_three_money_columns_must_agree(self, engine: Engine, tenant_id: UUID) -> None:
        with pytest.raises(IntegrityError, match="wasted_is_the_difference"):
            self._insert(engine, tenant_id, wasted=Decimal("39.00"))

    def test_a_status_outside_the_three_is_refused(self, engine: Engine, tenant_id: UUID) -> None:
        with pytest.raises(IntegrityError, match="status"):
            self._insert(engine, tenant_id, status="PROBABLY_FINE")

    def test_a_term_that_ends_before_it_starts_is_refused(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        with pytest.raises(IntegrityError, match="term_ends_after_it_starts"):
            self._insert(engine, tenant_id, term_start=date(2027, 1, 1), term_end=date(2026, 1, 1))

    def test_covering_more_than_was_eligible_is_refused(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        with pytest.raises(IntegrityError, match="covered_within_eligible"):
            self._insert_coverage(
                engine, tenant_id, eligible=Decimal("100.00"), covered=Decimal("101.00")
            )

    def test_an_unknown_coverage_dimension_is_refused(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # A free text dimension is one a screen cannot label, so a third one is a
        # migration rather than a row.
        with pytest.raises(IntegrityError, match="dimension"):
            self._insert_coverage(engine, tenant_id, dimension="INSTANCE_FAMILY")


class TestTheDatabaseRefusesBadDays:
    """TASK-P8-013. The same rule for a day: written directly, refused by the database."""

    def _insert_day(self, engine: Engine, tenant: UUID, **overrides: object) -> None:
        row: dict[str, object] = {
            "id": uuid4(),
            "tenant": tenant,
            "run": uuid4(),
            "type": "SavingsPlan",
            "day": date(2026, 8, 3),
            "committed": Decimal("10.00"),
            "used": Decimal("8.00"),
            "eligible": Decimal("40.00"),
            "covered": Decimal("8.00"),
            "as_of": datetime(2026, 8, 4, tzinfo=UTC),
            "collected_at": NOW,
        }
        row.update(overrides)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO commitment_day (day_id, tenant_id, ingest_run_id, "
                    "commitment_type, day, committed, used, eligible_spend, covered_spend, "
                    "as_of, collected_at) VALUES (:id, :tenant, :run, :type, :day, "
                    ":committed, :used, :eligible, :covered, :as_of, :collected_at)"
                ),
                row,
            )

    def test_a_well_formed_day_is_accepted(self, engine: Engine, tenant_id: UUID) -> None:
        self._insert_day(engine, tenant_id)

    def test_a_kind_is_said_once_a_day(self, engine: Engine, tenant_id: UUID) -> None:
        self._insert_day(engine, tenant_id)
        with pytest.raises(IntegrityError, match="kind_day"):
            self._insert_day(engine, tenant_id)

    def test_using_more_than_was_committed_is_refused(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        with pytest.raises(IntegrityError, match="used_within_committed"):
            self._insert_day(engine, tenant_id, used=Decimal("10.01"))

    def test_covering_more_than_was_eligible_is_refused(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        with pytest.raises(IntegrityError, match="covered_within_eligible"):
            self._insert_day(engine, tenant_id, covered=Decimal("40.01"))

    def test_negative_money_is_refused(self, engine: Engine, tenant_id: UUID) -> None:
        with pytest.raises(IntegrityError, match="money_is_not_negative"):
            self._insert_day(engine, tenant_id, eligible=Decimal("-1"), covered=Decimal("-2"))

    def test_a_day_fetched_before_it_was_true_is_refused(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        with pytest.raises(IntegrityError, match="collected_after_as_of"):
            self._insert_day(engine, tenant_id, collected_at=datetime(2026, 8, 3, tzinfo=UTC))
