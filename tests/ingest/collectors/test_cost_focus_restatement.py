"""Retraction: the only destructive operation in the ingest path.

AWS restates a billing period continuously. A line item can change size, which
the upsert handles, and a line item can disappear. If nothing removes the
disappeared one, a charge AWS withdrew stays on Meter's bill forever and the
total drifts above the invoice by exactly the sum of every correction ever
issued.

The danger is that a period read half way looks exactly like a period where
half the charges were withdrawn. A collector that cannot tell those apart will
remove a real bill the first time Athena throttles, and the run will report
success while doing it. Every test here is about that difference.
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
from finops_core.domain.cost import CostRecord
from finops_fakes.cur import (
    CLOSED_PERIOD,
    ESTATE,
    OLDEST_PERIOD,
    OPEN_PERIOD,
    RETRACTED_FINGERPRINT,
    FakeCostExport,
    restate,
)
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.registry import CollectorContext

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
CLOSED = tuple(row for row in ESTATE if row.billing_period_start == CLOSED_PERIOD)
OLDEST = tuple(row for row in ESTATE if row.billing_period_start == OLDEST_PERIOD)


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


class HalfARead:
    """An export that hands over some of a period and then fails.

    This is the shape the AWS adapter refuses to produce, because it buffers a
    whole period before returning anything. A future adapter that streamed
    could produce it, and the collector has to be right either way.
    """

    def __init__(self, rows: tuple[CostRecord, ...], after: int) -> None:
        self._rows = rows
        self._after = after

    def latest_available_period(self) -> date:
        return self._rows[0].billing_period_start

    def read_period(self, _start: date, _end: date) -> Iterator[CostRecord]:
        # The window is ignored: this stub exists to fail part way through
        # a period, not to filter one.
        for index, row in enumerate(self._rows):
            if index >= self._after:
                raise errors.Throttled(
                    scope_key="billing",
                    collector="cost_focus",
                    detail="the provider stopped answering half way through the period",
                )
            yield row


def ingest(
    engine: Engine,
    tenant: UUID,
    export: object | None = None,
    run_id: UUID | None = None,
) -> tuple[int, int]:
    """One run, in its own transaction, as the worker does it."""
    with engine.begin() as connection:
        for month in (OLDEST_PERIOD, CLOSED_PERIOD, OPEN_PERIOD):
            ensure_partition(connection, "cost_focus_daily", month)
        collector = CostFocusCollector(export or FakeCostExport(rows=CLOSED), clock=lambda: NOW)
        outcome = collector(
            CollectorContext(
                unit=Unit(tenant_id=tenant), connection=connection, run_id=run_id or uuid4()
            )
        )
    return int(outcome.items_written), int(outcome.items_removed)


def prints_for(engine: Engine, tenant: UUID, period: date | None = None) -> set[str]:
    sql = "SELECT source_fingerprint FROM cost_focus_daily WHERE tenant_id = :t"
    params: dict[str, object] = {"t": tenant}
    if period is not None:
        sql += " AND billing_period_start = :p"
        params["p"] = period
    with engine.connect() as connection:
        return set(connection.execute(text(sql), params).scalars())


class TestARestatedPeriodDropsWhatWasWithdrawn:
    def test_the_retracted_row_is_gone_and_the_rest_are_not(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        ingest(engine, tenant_id)
        before = prints_for(engine, tenant_id)
        assert RETRACTED_FINGERPRINT in before

        ingest(engine, tenant_id, export=FakeCostExport(rows=restate(CLOSED)))
        after = prints_for(engine, tenant_id)

        assert RETRACTED_FINGERPRINT not in after
        assert after == before - {RETRACTED_FINGERPRINT}, "something else went with it"

    def test_the_run_reports_what_it_removed(self, engine: Engine, tenant_id: UUID) -> None:
        """A destructive operation nobody can count is one nobody notices going
        wrong. The first run removes nothing, the restated one removes one."""
        _, removed_first = ingest(engine, tenant_id)
        assert removed_first == 0

        _, removed_second = ingest(engine, tenant_id, export=FakeCostExport(rows=restate(CLOSED)))
        assert removed_second == 1


class TestAReadThatFailedHalfWayRemovesNothing:
    def test_the_previous_runs_rows_all_survive(self, engine: Engine, tenant_id: UUID) -> None:
        """The property this whole task exists for.

        A period read half way is indistinguishable from a period where half the
        charges were withdrawn, unless the removal sits downstream of finishing
        the read. Two things protect it and this exercises both as deployed: the
        collector never reaches the removal, and the worker's transaction rolls
        the unit back.
        """
        ingest(engine, tenant_id)
        before = prints_for(engine, tenant_id)
        assert len(before) > 10, "the estate is too small for a half read to mean anything"

        with pytest.raises(errors.Throttled):
            ingest(engine, tenant_id, export=HalfARead(CLOSED, after=5))

        assert prints_for(engine, tenant_id) == before

    def test_the_collector_alone_removes_nothing_on_a_half_read(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """The ordering guard, isolated from the transaction that hides it.

        The two tests above pass even with `_retract` moved ahead of `_write`,
        because the rollback undoes the removal along with everything else. That
        makes them a test of the worker's transaction rather than of this
        collector, which is worth knowing and not worth relying on.

        This one looks at the rows inside the transaction, before the rollback,
        so it sees what the collector actually did. Swap the two lines in
        `__call__` and this is the test that goes red.
        """
        ingest(engine, tenant_id)
        before = prints_for(engine, tenant_id)

        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                collector = CostFocusCollector(HalfARead(CLOSED, after=5), clock=lambda: NOW)
                with pytest.raises(errors.Throttled):
                    collector(
                        CollectorContext(
                            unit=Unit(tenant_id=tenant_id),
                            connection=connection,
                            run_id=uuid4(),
                        )
                    )
                still_there = set(
                    connection.execute(
                        text(
                            "SELECT source_fingerprint FROM cost_focus_daily WHERE tenant_id = :t"
                        ),
                        {"t": tenant_id},
                    ).scalars()
                )
            finally:
                transaction.rollback()

        assert still_there == before, "the removal ran before the read had finished"

    def test_it_holds_when_the_failure_lands_after_a_whole_batch(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # The collector writes in batches of 500, so failing at a batch boundary
        # is the case where rows have certainly reached the database already.
        # That is where an ordering mistake would show.
        ingest(engine, tenant_id)
        before = prints_for(engine, tenant_id)

        with pytest.raises(errors.Throttled):
            ingest(engine, tenant_id, export=HalfARead(CLOSED, after=500))

        assert prints_for(engine, tenant_id) == before


class TestTheRemovalIsKeyedOnTheRunAndNotTheClock:
    def test_two_runs_at_the_same_instant_are_still_told_apart(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """Every run here uses the same frozen clock, so `collected_at` is
        identical on both. A removal keyed on a timestamp would remove nothing
        or remove everything, depending which way its comparison leaned. Keyed
        on the run id, exactly the withdrawn row goes.
        """
        first, second = uuid4(), uuid4()
        ingest(engine, tenant_id, run_id=first)
        before = prints_for(engine, tenant_id)

        _, removed = ingest(
            engine, tenant_id, export=FakeCostExport(rows=restate(CLOSED)), run_id=second
        )

        assert removed == 1
        assert prints_for(engine, tenant_id) == before - {RETRACTED_FINGERPRINT}


class TestItRemovesNothingItWasNotAskedTo:
    def test_another_billing_period_is_untouched(self, engine: Engine, tenant_id: UUID) -> None:
        """Without the period predicate, ingesting one month removes every other
        month in a single statement. That is the worst outcome available to this
        collector and the easiest one to write."""
        ingest(engine, tenant_id, export=FakeCostExport(rows=OLDEST))
        oldest = prints_for(engine, tenant_id, OLDEST_PERIOD)
        assert oldest

        ingest(engine, tenant_id, export=FakeCostExport(rows=CLOSED))

        assert prints_for(engine, tenant_id, OLDEST_PERIOD) == oldest

    def test_another_tenant_is_untouched(self, engine: Engine, tenant_id: UUID) -> None:
        neighbour = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO tenant (tenant_id, name) VALUES (:id, :name)"),
                {"id": neighbour, "name": f"tenant-{neighbour}"},
            )
        ingest(engine, neighbour)
        theirs = prints_for(engine, neighbour)
        assert theirs

        ingest(engine, tenant_id)
        ingest(engine, tenant_id, export=FakeCostExport(rows=restate(CLOSED)))

        assert prints_for(engine, neighbour) == theirs


class TestTheMoneyFollowsTheInvoiceDown:
    def test_the_total_loses_exactly_the_withdrawn_charge(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """The point of retracting at all. An estate's total has to follow the
        invoice down as well as up, or the drift is one way and permanent."""

        def total() -> Decimal:
            with engine.connect() as connection:
                summed = connection.execute(
                    text(
                        "SELECT COALESCE(SUM(effective_cost), 0) FROM cost_focus_daily "
                        "WHERE tenant_id = :t"
                    ),
                    {"t": tenant_id},
                ).scalar_one()
            assert isinstance(summed, Decimal)
            return summed

        ingest(engine, tenant_id)
        before = total()

        corrected = restate(CLOSED)
        expected = sum((row.effective_cost for row in corrected), Decimal(0))

        ingest(engine, tenant_id, export=FakeCostExport(rows=corrected))

        assert total() == expected
        assert total() < before, "the estate did not follow the invoice down"
