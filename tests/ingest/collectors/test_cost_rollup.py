"""The monthly aggregate, which is derived and must stay that way.

Two callers write `cost_focus_monthly` for different reasons, and the danger is
not that either is wrong on its own. It is that they drift apart, and the way
that shows up is a person reading two screens which disagree about one month.

So the arithmetic is one function, and this asks the only questions that matter
about it: does a month equal its days, does it follow a retraction down, and
does the retention caller keep the archive it exists to create.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.cost import CostRecord
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.cost_rollup import roll_up_before
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.registry import CollectorContext
from finops_providers.fake.cur import (
    CLOSED_PERIOD,
    ESTATE,
    OLDEST_PERIOD,
    OPEN_PERIOD,
    RETRACTED_FINGERPRINT,
    FakeCostExport,
    restate,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
CLOSED = tuple(row for row in ESTATE if row.billing_period_start == CLOSED_PERIOD)


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


def ingest(engine: Engine, tenant: UUID, rows: tuple[CostRecord, ...] = CLOSED) -> None:
    with engine.begin() as connection:
        for month in (OLDEST_PERIOD, CLOSED_PERIOD, OPEN_PERIOD):
            ensure_partition(connection, "cost_focus_daily", month)
        collector = CostFocusCollector(FakeCostExport(rows=rows), clock=lambda: NOW)
        collector(
            CollectorContext(unit=Unit(tenant_id=tenant), connection=connection, run_id=uuid4())
        )


def monthly(engine: Engine, tenant: UUID) -> dict[tuple[str, str, str], tuple[Decimal, int]]:
    with engine.connect() as connection:
        return {
            (row[0], row[1], row[2]): (row[3], row[4])
            for row in connection.execute(
                text(
                    "SELECT sub_account_id, service_name, region_id, effective_cost, "
                    "line_items FROM cost_focus_monthly WHERE tenant_id = :t"
                ),
                {"t": tenant},
            )
        }


def daily_total(engine: Engine, tenant: UUID) -> Decimal:
    with engine.connect() as connection:
        total = connection.execute(
            text(
                "SELECT COALESCE(SUM(effective_cost), 0) FROM cost_focus_daily WHERE tenant_id = :t"
            ),
            {"t": tenant},
        ).scalar_one()
    assert isinstance(total, Decimal)
    return total


class TestTheMonthEqualsItsDays:
    def test_the_totals_agree(self, engine: Engine, tenant_id: UUID) -> None:
        """Summed both ways and compared, which is the only way to know.

        Reading the SQL back and agreeing with it is not evidence that the
        grouping is right.
        """
        ingest(engine, tenant_id)
        rolled = sum((cost for cost, _ in monthly(engine, tenant_id).values()), Decimal(0))
        assert rolled == daily_total(engine, tenant_id)

    def test_the_line_item_counts_agree(self, engine: Engine, tenant_id: UUID) -> None:
        ingest(engine, tenant_id)
        counted = sum(count for _, count in monthly(engine, tenant_id).values())
        assert counted == len(CLOSED)

    def test_rolling_up_twice_changes_nothing(self, engine: Engine, tenant_id: UUID) -> None:
        ingest(engine, tenant_id)
        first = monthly(engine, tenant_id)
        ingest(engine, tenant_id)
        assert monthly(engine, tenant_id) == first


class TestItFollowsARetractionDown:
    def test_the_month_loses_what_the_provider_withdrew(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """The aggregate has to move with the detail, in the same transaction.

        A monthly table that only ever went up would be the drift this whole
        sub project exists to prevent, one level removed and harder to see.
        """
        ingest(engine, tenant_id)
        before = sum((cost for cost, _ in monthly(engine, tenant_id).values()), Decimal(0))

        ingest(engine, tenant_id, rows=restate(CLOSED))
        after = sum((cost for cost, _ in monthly(engine, tenant_id).values()), Decimal(0))

        assert after < before
        assert after == daily_total(engine, tenant_id)

    def test_a_group_whose_every_row_was_withdrawn_is_removed(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """The upsert alone cannot do this.

        It only ever replaces groups it can still see, so a group with nothing
        left behind it would keep its last known total forever. Small, but
        permanent, and it only ever points one way.
        """
        victim = next(row for row in CLOSED if row.source_fingerprint == RETRACTED_FINGERPRINT)
        group = (victim.sub_account_id, victim.service_name, victim.region_id)

        ingest(engine, tenant_id, rows=(victim,))
        assert group in monthly(engine, tenant_id)

        survivors = tuple(row for row in CLOSED if row.service_name != victim.service_name)
        ingest(engine, tenant_id, rows=survivors)
        assert group not in monthly(engine, tenant_id), "a group with no line items survived"


class TestRetentionKeepsItsArchive:
    def test_aggregating_before_a_boundary_does_not_prune(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """Retention aggregates the months whose detail it is about to drop.

        If that pass pruned monthly rows with nothing behind them, the second
        time it ran it would delete everything it had archived. The two callers
        differ in exactly this, which is why they are two functions rather than
        one with a flag.
        """
        ingest(engine, tenant_id)
        with engine.begin() as connection:
            roll_up_before(connection, tenant=tenant_id, before=OPEN_PERIOD, at=NOW)
            archived = monthly(engine, tenant_id)
            assert archived

            connection.execute(
                text("DELETE FROM cost_focus_daily WHERE tenant_id = :t"), {"t": tenant_id}
            )
            roll_up_before(connection, tenant=tenant_id, before=OPEN_PERIOD, at=NOW)

        assert monthly(engine, tenant_id) == archived, "the archive was deleted by its own pass"
