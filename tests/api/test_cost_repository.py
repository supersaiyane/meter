"""Reading the bill, and being refused the parts of it that are not yours.

`cost_focus_daily` is the widest table in the schema and the most damaging to
leak. Until 2026-09-19 it sat in `SCOPED_TABLES` with the rule `None`, meaning
the tenant filter was the whole of its scoping, which was harmless only because
nothing read it. The first route over it would have served a whole
organization's bill to a viewer entitled to two accounts. ISS-184.

So the first question here is not what the arithmetic says. It is who is
allowed to see it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_api.db.repositories.base import AccessContext
from finops_api.db.repositories.cost import (
    CostRepository,
    MonthlyCostRepository,
    previous_month,
)
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.platform import UNALLOCATED
from finops_core.domain.tenant import Scope
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.registry import CollectorContext
from finops_providers.fake.cur import (
    CLOSED_PERIOD,
    ESTATE,
    OLDEST_PERIOD,
    OPEN_PERIOD,
    FakeCostExport,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
CLOSED = tuple(row for row in ESTATE if row.billing_period_start == CLOSED_PERIOD)
#: One of the five accounts the fake estate bills, so a narrow scope over it
#: sees strictly less than a global one.
ONE_ACCOUNT = "fake-platform-a"


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


@pytest.fixture
def seeded(engine: Engine, tenant_id: UUID) -> UUID:
    with engine.begin() as connection:
        for month in (OLDEST_PERIOD, CLOSED_PERIOD, OPEN_PERIOD):
            ensure_partition(connection, "cost_focus_daily", month)
        collector = CostFocusCollector(FakeCostExport(rows=CLOSED), clock=lambda: NOW)
        collector(
            CollectorContext(unit=Unit(tenant_id=tenant_id), connection=connection, run_id=uuid4())
        )
    return tenant_id


def everything(tenant: UUID) -> Scope:
    return Scope(tenant_id=tenant, is_global=True, accounts=frozenset())


def only(tenant: UUID, account: str) -> Scope:
    return Scope(
        tenant_id=tenant,
        is_global=False,
        accounts=frozenset({AccountKey(provider=Provider.AWS, account_id=account)}),
    )


def repo(connection: object) -> CostRepository:
    return CostRepository(connection, AccessContext(request_id="test"))  # type: ignore[arg-type]


class TestScopeIsEnforced:
    def test_a_narrow_scope_sees_less_than_a_global_one(self, engine: Engine, seeded: UUID) -> None:
        """The assertion that would have failed before the guard was corrected.

        With the rule at `None` these two numbers were identical, and the test
        that would have caught it did not exist, because nothing read the table.
        """
        with engine.connect() as connection:
            subject = repo(connection)
            whole = subject.period_total(everything(seeded), CLOSED_PERIOD)[0][0]
            mine = subject.period_total(only(seeded, ONE_ACCOUNT), CLOSED_PERIOD)[0][0]

        assert mine > 0, "the narrow scope sees nothing at all, which is the other failure"
        assert mine < whole

    def test_an_empty_scope_reads_nothing_rather_than_everything(
        self, engine: Engine, seeded: UUID
    ) -> None:
        """Fail closed. An entitlement that resolved to no accounts is not a
        licence to read the whole organization."""
        empty = Scope(tenant_id=seeded, is_global=False, accounts=frozenset())
        with engine.connect() as connection:
            total = repo(connection).period_total(empty, CLOSED_PERIOD)[0][0]
        assert total == 0

    def test_a_narrow_scope_sees_only_its_own_accounts_in_a_grouping(
        self, engine: Engine, seeded: UUID
    ) -> None:
        with engine.connect() as connection:
            rows = repo(connection).grouped(only(seeded, ONE_ACCOUNT), CLOSED_PERIOD, "account")
        assert {row[0] for row in rows} == {ONE_ACCOUNT}

    def test_every_read_is_audited(self, engine: Engine, seeded: UUID) -> None:
        """The audit is what makes the global viewer credential defensible.

        Who read the whole organization's bill, and when, has to have an answer.
        """
        with engine.connect() as connection:
            repo(connection).period_total(everything(seeded), CLOSED_PERIOD)
            audited = connection.execute(
                text(
                    "SELECT count(*) FROM audit_event WHERE tenant_id = :t "
                    "AND resource = 'cost_focus_daily'"
                ),
                {"t": seeded},
            ).scalar_one()
        assert audited >= 1


class TestTheArithmetic:
    def test_a_grouping_sums_to_the_period_total(self, engine: Engine, seeded: UUID) -> None:
        """Every grouping is the same money cut a different way.

        A grouping that does not sum back to the total is dropping rows, and on
        a screen that reads as an estate smaller than it is.
        """
        with engine.connect() as connection:
            subject = repo(connection)
            scope = everything(seeded)
            total = subject.period_total(scope, CLOSED_PERIOD)[0][0]
            for dimension in ("service", "account", "region"):
                grouped = sum(
                    (row[1] for row in subject.grouped(scope, CLOSED_PERIOD, dimension)),
                    Decimal(0),
                )
                assert grouped == total, f"{dimension} does not sum to the period"

    def test_the_groupings_are_worst_first(self, engine: Engine, seeded: UUID) -> None:
        with engine.connect() as connection:
            rows = repo(connection).grouped(everything(seeded), CLOSED_PERIOD, "service")
        costs = [row[1] for row in rows]
        assert costs == sorted(costs, reverse=True)
        assert len(set(costs)) == len(costs), "a ranking of equal numbers is a list"

    def test_effective_and_billed_are_different_numbers(self, engine: Engine, seeded: UUID) -> None:
        """Both come back so a reconciliation has something to reconcile with,
        and they differ here so a screen labelling one as the other is wrong
        rather than accidentally right."""
        with engine.connect() as connection:
            effective, billed, *_ = repo(connection).period_total(
                everything(seeded), CLOSED_PERIOD
            )[0]
        assert effective != billed

    def test_the_daily_series_is_oldest_first_and_sums_to_the_period(
        self, engine: Engine, seeded: UUID
    ) -> None:
        with engine.connect() as connection:
            subject = repo(connection)
            scope = everything(seeded)
            days = subject.daily(scope, CLOSED_PERIOD)
            total = subject.period_total(scope, CLOSED_PERIOD)[0][0]
        assert [row[0] for row in days] == sorted(row[0] for row in days)
        assert sum((row[1] for row in days), Decimal(0)) == total

    def test_both_timestamps_come_back(self, engine: Engine, seeded: UUID) -> None:
        # Constraint 10. A period is only as current as its least current line
        # item, so `as_of` is the oldest charge and `collected_at` the newest
        # fetch.
        with engine.connect() as connection:
            *_, as_of, collected_at = repo(connection).period_total(
                everything(seeded), CLOSED_PERIOD
            )[0]
        assert collected_at >= as_of


class TestAllocation:
    def test_what_nobody_tagged_is_a_row_and_not_a_silence(
        self, engine: Engine, seeded: UUID
    ) -> None:
        """The reason the allocation screen exists.

        An allocation view that quietly drops what it cannot attribute reports a
        smaller estate than exists, and the gap between it and the invoice is
        the first thing finance finds.
        """
        with engine.connect() as connection:
            rows = repo(connection).by_tag(everything(seeded), CLOSED_PERIOD, "team")
        buckets = {row[0]: row[1] for row in rows}
        assert UNALLOCATED in buckets
        assert buckets[UNALLOCATED] > 0

    def test_allocation_sums_to_the_period_total(self, engine: Engine, seeded: UUID) -> None:
        with engine.connect() as connection:
            subject = repo(connection)
            scope = everything(seeded)
            allocated = sum(
                (row[1] for row in subject.by_tag(scope, CLOSED_PERIOD, "team")), Decimal(0)
            )
            total = subject.period_total(scope, CLOSED_PERIOD)[0][0]
        assert allocated == total, "the unallocated bucket does not close the gap"

    def test_a_tag_key_nobody_uses_puts_everything_in_unallocated(
        self, engine: Engine, seeded: UUID
    ) -> None:
        # Not an error and not an empty page. Grouping by a key nothing carries
        # is a true answer about an estate that does not use that key.
        with engine.connect() as connection:
            rows = repo(connection).by_tag(everything(seeded), CLOSED_PERIOD, "cost-centre")
        assert [row[0] for row in rows] == [UNALLOCATED]


class TestPeriods:
    def test_the_latest_period_is_the_one_that_was_written(
        self, engine: Engine, seeded: UUID
    ) -> None:
        with engine.connect() as connection:
            assert repo(connection).latest_period(everything(seeded)) == CLOSED_PERIOD

    def test_a_tenant_with_no_cost_gets_none_rather_than_a_zero(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """A different answer from a period that totalled zero, and the route
        keeps them apart: one is an estate nobody has collected yet, the other
        is an estate that spent nothing."""
        with engine.connect() as connection:
            assert repo(connection).latest_period(everything(tenant_id)) is None

    def test_the_month_before_january_is_december_of_the_year_before(self) -> None:
        # The case a route gets wrong once and is then wrong about every January.
        assert previous_month(date(2027, 1, 1)) == date(2026, 12, 1)

    def test_the_monthly_view_agrees_with_the_daily_one(self, engine: Engine, seeded: UUID) -> None:
        """The two tables are one number at two grains. If they disagree, one of
        the screens reading them is lying and nobody can tell which."""
        with engine.connect() as connection:
            daily_total = repo(connection).period_total(everything(seeded), CLOSED_PERIOD)[0][0]
            monthly = MonthlyCostRepository(connection, AccessContext(request_id="test"))  # type: ignore[arg-type]
            months = monthly.months(everything(seeded))
        matching = [row for row in months if row[0] == CLOSED_PERIOD]
        assert matching, "the month was never rolled up"
        assert matching[0][1] == daily_total
