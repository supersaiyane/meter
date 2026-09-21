"""The verification collector over real tables.

The verdict arithmetic has its own suite on numbers. What this asks is whether the
right days reach it, which is where a windowed comparison actually goes wrong: an
off by one on a half open bound, a settling period counted from the wrong end, a
recommendation judged before its after window has finished accruing.

So the estate is built rather than the verdicts inserted. Every case lays down daily
charges for a resource, marks a recommendation done on a chosen date, and asks what
the collector concludes. A test that wrote a row into `realized_saving` and then
checked it was there would be testing an insert.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.waste import Lifecycle
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.collectors.realized_savings import (
    MATURITY_DAYS,
    SETTLE_DAYS,
    WINDOW_DAYS,
    RealizedSavingsCollector,
)
from finops_ingest.registry import CollectorContext

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)

#: Done exactly long enough ago that its after window closed yesterday.
MATURE_ON = NOW.date() - timedelta(days=MATURITY_DAYS)

ACCOUNT = "111122223333"


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


def charge(
    engine: Engine,
    tenant: UUID,
    *,
    resource: str,
    day: date,
    cost: Decimal,
    quantity: Decimal | None,
) -> None:
    """One day of charge for one resource.

    `quantity` of None leaves `consumed_quantity` null, which is what a real export
    does for the services that publish no usage figure. It is the case the whole
    unobserved control path exists for.
    """
    period = date(day.year, day.month, 1)
    with engine.begin() as connection:
        ensure_partition(connection, "cost_focus_daily", period)
        start = datetime(day.year, day.month, day.day, tzinfo=UTC)
        connection.execute(
            text(
                "INSERT INTO cost_focus_daily (tenant_id, ingest_run_id, "
                "source_fingerprint, as_of, collected_at, billing_account_id, "
                "sub_account_id, billing_period_start, billing_period_end, "
                "charge_period_start, charge_period_end, provider_name, service_name, "
                "resource_id, charge_category, billed_cost, effective_cost, "
                "consumed_quantity, tags) "
                "VALUES (:t, :run, :fp, :at, :at, 'payer', :account, :period, :period_end, "
                ":start, :end, 'Fake', 'AmazonEC2', :resource, 'Usage', :cost, :cost, "
                ":quantity, '{}'::jsonb)"
            ),
            {
                "t": tenant,
                "run": uuid4(),
                "fp": f"{resource}:{day}",
                "at": NOW,
                "account": ACCOUNT,
                "period": period,
                "period_end": date(period.year + (period.month // 12), (period.month % 12) + 1, 1),
                "start": start,
                "end": start + timedelta(days=1),
                "resource": resource,
                "cost": cost,
                "quantity": quantity,
            },
        )


def lay_down(
    engine: Engine,
    tenant: UUID,
    *,
    resource: str,
    done_on: date,
    cost_before: Decimal,
    cost_after: Decimal,
    quantity_before: Decimal | None = Decimal("24"),
    quantity_after: Decimal | None = Decimal("24"),
) -> None:
    """A flat daily charge through both windows, at two different levels.

    Flat on purpose. A shape inside a window is the business of the arithmetic
    suite; what this fixture has to get right is which days land on which side.
    """
    for offset in range(WINDOW_DAYS):
        charge(
            engine,
            tenant,
            resource=resource,
            day=done_on - timedelta(days=offset + 1),
            cost=cost_before,
            quantity=quantity_before,
        )
        charge(
            engine,
            tenant,
            resource=resource,
            day=done_on + timedelta(days=SETTLE_DAYS + offset),
            cost=cost_after,
            quantity=quantity_after,
        )


def a_recommendation(
    engine: Engine,
    tenant: UUID,
    *,
    resource: str,
    done_on: date,
    lifecycle: Lifecycle = Lifecycle.DONE,
) -> UUID:
    """One recommendation in `lifecycle`, with a DONE event on `done_on`.

    The event is what the collector reads, and it is written directly here because
    driving a recommendation through four route calls to set up a cost comparison
    would make this a test of the routes.
    """
    identifier = uuid4()
    done_at = datetime(done_on.year, done_on.month, done_on.day, 12, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, "
                "source, source_reference, waste_class, resource_id, region_id, "
                "estimated_monthly_saving, confidence, severity, observation_days, "
                "lifecycle, rationale, as_of, collected_at) "
                "VALUES (:id, :t, :account, 'METER', :ref, 'RIGHTSIZE_INSTANCE', :resource, "
                "'eu-west-1', 999, 'HIGH', 'HIGH', 30, :lifecycle, 'test fixture', :at, :at)"
            ),
            {
                "id": identifier,
                "t": tenant,
                "account": ACCOUNT,
                "ref": f"ref:{identifier}",
                "resource": resource,
                "lifecycle": lifecycle.value,
                "at": NOW,
            },
        )
        for target, occurred in (
            (Lifecycle.OPEN, done_at - timedelta(days=7)),
            (Lifecycle.ACCEPTED, done_at - timedelta(days=6)),
            (Lifecycle.IN_PROGRESS, done_at - timedelta(days=5)),
            (Lifecycle.DONE, done_at),
        ):
            connection.execute(
                text(
                    "INSERT INTO recommendation_event (event_id, recommendation_id, tenant_id, "
                    "from_lifecycle, to_lifecycle, actor, reason, occurred_at, as_of, "
                    "collected_at) VALUES (:e, :id, :t, :from, :to, 'test', NULL, :at, :at, :at)"
                ),
                {
                    "e": uuid4(),
                    "id": identifier,
                    "t": tenant,
                    "from": None if target is Lifecycle.OPEN else "PREVIOUS",
                    "to": target.value,
                    "at": occurred,
                },
            )
    return identifier


def verify(engine: Engine, tenant: UUID) -> int:
    with engine.begin() as connection:
        outcome = RealizedSavingsCollector(clock=lambda: NOW)(
            CollectorContext(unit=Unit(tenant_id=tenant), connection=connection, run_id=uuid4())
        )
    return int(outcome.items_written)


def verdicts(engine: Engine, tenant: UUID) -> dict[UUID, tuple[str, Decimal, Decimal, str]]:
    with engine.connect() as connection:
        return {
            row[0]: (row[1], Decimal(row[2]), Decimal(row[3]), row[4])
            for row in connection.execute(
                text(
                    "SELECT recommendation_id, verdict, cost_before, cost_after, why "
                    "FROM realized_saving WHERE tenant_id = :t"
                ),
                {"t": tenant},
            ).all()
        }


def lifecycle_of(engine: Engine, tenant: UUID, identifier: UUID) -> str:
    with engine.connect() as connection:
        found = connection.execute(
            text(
                "SELECT lifecycle FROM recommendation "
                "WHERE tenant_id = :t AND recommendation_id = :id"
            ),
            {"t": tenant, "id": identifier},
        ).scalar_one()
    assert isinstance(found, str)
    return found


class TestTheThreeVerdicts:
    def test_a_cost_fall_with_flat_usage_is_verified(self, engine: Engine, tenant_id: UUID) -> None:
        resource = "i-verified"
        identifier = a_recommendation(engine, tenant_id, resource=resource, done_on=MATURE_ON)
        lay_down(
            engine,
            tenant_id,
            resource=resource,
            done_on=MATURE_ON,
            cost_before=Decimal("10.00"),
            cost_after=Decimal("6.00"),
        )
        assert verify(engine, tenant_id) == 1
        verdict, before, after, _ = verdicts(engine, tenant_id)[identifier]
        assert verdict == "VERIFIED"
        assert before == Decimal("300.0000000000")
        assert after == Decimal("180.0000000000")

    def test_a_cost_that_did_not_move_is_regressed(self, engine: Engine, tenant_id: UUID) -> None:
        """The direction that matters, and the one a vanity metric hides.

        A recommendation somebody marked done whose bill never changed is the most
        important row on the savings screen, because it is the one that says the
        work did not land.
        """
        resource = "i-regressed"
        identifier = a_recommendation(engine, tenant_id, resource=resource, done_on=MATURE_ON)
        lay_down(
            engine,
            tenant_id,
            resource=resource,
            done_on=MATURE_ON,
            cost_before=Decimal("10.00"),
            cost_after=Decimal("10.00"),
        )
        verify(engine, tenant_id)
        assert verdicts(engine, tenant_id)[identifier][0] == "REGRESSED"

    def test_usage_falling_faster_than_cost_is_inconclusive(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # Cost down 40 percent, usage down 75. The bill fell because the workload
        # shrank, and this collector refuses to take the credit.
        resource = "i-shrank"
        identifier = a_recommendation(engine, tenant_id, resource=resource, done_on=MATURE_ON)
        lay_down(
            engine,
            tenant_id,
            resource=resource,
            done_on=MATURE_ON,
            cost_before=Decimal("10.00"),
            cost_after=Decimal("6.00"),
            quantity_before=Decimal("24"),
            quantity_after=Decimal("6"),
        )
        verify(engine, tenant_id)
        verdict, _, _, why = verdicts(engine, tenant_id)[identifier]
        assert verdict == "INCONCLUSIVE"
        assert "smaller workload" in why

    def test_an_unpublished_usage_quantity_is_inconclusive_and_stays_null(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """Constraint 5, carried from the billing rows to the column.

        `consumed_quantity` is nullable in the export and a null sum is unobserved,
        not zero. Migration `0012` widened the column so the null survives, and the
        database refuses a verified saving with no control behind it.
        """
        resource = "i-nousage"
        identifier = a_recommendation(engine, tenant_id, resource=resource, done_on=MATURE_ON)
        lay_down(
            engine,
            tenant_id,
            resource=resource,
            done_on=MATURE_ON,
            cost_before=Decimal("10.00"),
            cost_after=Decimal("6.00"),
            quantity_before=None,
            quantity_after=None,
        )
        verify(engine, tenant_id)
        assert verdicts(engine, tenant_id)[identifier][0] == "INCONCLUSIVE"
        with engine.connect() as connection:
            stored = connection.execute(
                text(
                    "SELECT usage_before, usage_after FROM realized_saving "
                    "WHERE recommendation_id = :id"
                ),
                {"id": identifier},
            ).one()
        assert stored.usage_before is None
        assert stored.usage_after is None


class TestWhichDaysReachIt:
    def test_a_recommendation_done_yesterday_is_not_judged(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """Its after window has not started, let alone finished.

        Judging it would compare the thirty days before the change against a window
        largely in the future, which is thirty days of nothing and reads as a
        hundred percent saving.
        """
        resource = "i-tooearly"
        done_on = NOW.date() - timedelta(days=1)
        a_recommendation(engine, tenant_id, resource=resource, done_on=done_on)
        lay_down(
            engine,
            tenant_id,
            resource=resource,
            done_on=done_on,
            cost_before=Decimal("10.00"),
            cost_after=Decimal("6.00"),
        )
        assert verify(engine, tenant_id) == 0
        assert verdicts(engine, tenant_id) == {}

    def test_one_day_short_of_maturity_is_still_not_judged(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # The boundary, so that moving the settling period is a deliberate act
        # rather than something a refactor does quietly.
        resource = "i-almost"
        done_on = NOW.date() - timedelta(days=MATURITY_DAYS - 1)
        a_recommendation(engine, tenant_id, resource=resource, done_on=done_on)
        lay_down(
            engine,
            tenant_id,
            resource=resource,
            done_on=done_on,
            cost_before=Decimal("10.00"),
            cost_after=Decimal("6.00"),
        )
        assert verify(engine, tenant_id) == 0

    def test_the_settling_period_is_excluded_from_both_windows(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """The thirty days after the change are deliberately not looked at.

        A resize bills at both sizes for an hour and an amortized discount
        redistributes over the following weeks, so the days immediately after the
        work are the least trustworthy ones. Here they are made absurd, and the
        verdict must not notice.
        """
        resource = "i-settling"
        identifier = a_recommendation(engine, tenant_id, resource=resource, done_on=MATURE_ON)
        lay_down(
            engine,
            tenant_id,
            resource=resource,
            done_on=MATURE_ON,
            cost_before=Decimal("10.00"),
            cost_after=Decimal("6.00"),
        )
        for offset in range(SETTLE_DAYS):
            charge(
                engine,
                tenant_id,
                resource=resource,
                day=MATURE_ON + timedelta(days=offset),
                cost=Decimal("500.00"),
                quantity=Decimal("24"),
            )
        verify(engine, tenant_id)
        verdict, before, after, _ = verdicts(engine, tenant_id)[identifier]
        assert verdict == "VERIFIED"
        assert before == Decimal("300.0000000000")
        assert after == Decimal("180.0000000000")

    def test_the_day_of_the_change_belongs_to_neither_window(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # Both windows are half open. The before window ends on the change date and
        # excludes it, because that day contains charges at both sizes.
        resource = "i-boundary"
        identifier = a_recommendation(engine, tenant_id, resource=resource, done_on=MATURE_ON)
        lay_down(
            engine,
            tenant_id,
            resource=resource,
            done_on=MATURE_ON,
            cost_before=Decimal("10.00"),
            cost_after=Decimal("6.00"),
        )
        charge(
            engine,
            tenant_id,
            resource=resource,
            day=MATURE_ON,
            cost=Decimal("999.00"),
            quantity=Decimal("24"),
        )
        verify(engine, tenant_id)
        _, before, after, _ = verdicts(engine, tenant_id)[identifier]
        assert before == Decimal("300.0000000000")
        assert after == Decimal("180.0000000000")


class TestTheLifecycleItMoves:
    def test_a_verified_saving_moves_the_recommendation_to_verified(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        resource = "i-moves"
        identifier = a_recommendation(engine, tenant_id, resource=resource, done_on=MATURE_ON)
        lay_down(
            engine,
            tenant_id,
            resource=resource,
            done_on=MATURE_ON,
            cost_before=Decimal("10.00"),
            cost_after=Decimal("6.00"),
        )
        verify(engine, tenant_id)
        assert lifecycle_of(engine, tenant_id, identifier) == "VERIFIED"

    def test_the_move_is_recorded_with_the_working(self, engine: Engine, tenant_id: UUID) -> None:
        # The same append only log the routes write to, and the actor is the
        # collector, because nobody decided this: a measurement did.
        resource = "i-logged"
        identifier = a_recommendation(engine, tenant_id, resource=resource, done_on=MATURE_ON)
        lay_down(
            engine,
            tenant_id,
            resource=resource,
            done_on=MATURE_ON,
            cost_before=Decimal("10.00"),
            cost_after=Decimal("6.00"),
        )
        verify(engine, tenant_id)
        with engine.connect() as connection:
            event = connection.execute(
                text(
                    "SELECT from_lifecycle, actor, reason FROM recommendation_event "
                    "WHERE recommendation_id = :id AND to_lifecycle = 'VERIFIED'"
                ),
                {"id": identifier},
            ).one()
        assert event.from_lifecycle == "DONE"
        assert event.actor == "realized_savings"
        assert "cost" in event.reason

    def test_an_inconclusive_verdict_leaves_it_at_done(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """There is no inconclusive lifecycle, and that is the design.

        A measurement nobody can read either way is not a reason to close a
        recommendation, so it stays open work with a row explaining why the bill
        cannot settle the question.
        """
        resource = "i-stuck"
        identifier = a_recommendation(engine, tenant_id, resource=resource, done_on=MATURE_ON)
        lay_down(
            engine,
            tenant_id,
            resource=resource,
            done_on=MATURE_ON,
            cost_before=Decimal("10.00"),
            cost_after=Decimal("6.00"),
            quantity_after=Decimal("2"),
        )
        verify(engine, tenant_id)
        assert lifecycle_of(engine, tenant_id, identifier) == "DONE"

    def test_a_second_run_leaves_one_row_and_one_event(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """Idempotent, because the verdict is a function of two fixed windows.

        The second run finds the recommendation already VERIFIED and writes no
        second event, which is what stops a terminal state being moved from.
        """
        resource = "i-twice"
        identifier = a_recommendation(engine, tenant_id, resource=resource, done_on=MATURE_ON)
        lay_down(
            engine,
            tenant_id,
            resource=resource,
            done_on=MATURE_ON,
            cost_before=Decimal("10.00"),
            cost_after=Decimal("6.00"),
        )
        verify(engine, tenant_id)
        verify(engine, tenant_id)
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT COUNT(*) FROM realized_saving WHERE recommendation_id = :id"),
                {"id": identifier},
            ).scalar_one()
            events = connection.execute(
                text(
                    "SELECT COUNT(*) FROM recommendation_event "
                    "WHERE recommendation_id = :id AND to_lifecycle = 'VERIFIED'"
                ),
                {"id": identifier},
            ).scalar_one()
        assert rows == 1
        assert events == 1


class TestWhatItRefusesToGuess:
    def test_a_resource_with_no_charges_is_a_named_gap(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """Not a verdict of inconclusive, because the reason would be ours.

        A recommendation naming a resource that appears nowhere in the bill means
        the two identifiers do not line up, and an estate where that happens
        everywhere would otherwise read as an estate where nothing can be proved.
        """
        a_recommendation(engine, tenant_id, resource="i-unbilled", done_on=MATURE_ON)
        assert verify(engine, tenant_id) == 0
        assert verdicts(engine, tenant_id) == {}
        with engine.connect() as connection:
            detail = connection.execute(
                text(
                    "SELECT detail FROM sync_error WHERE tenant_id = :t "
                    "AND collector = 'realized_savings'"
                ),
                {"t": tenant_id},
            ).scalar_one()
        assert "no billing rows" in detail
        assert "i-unbilled" in detail

    def test_it_never_reads_the_estimated_saving(self) -> None:
        """Asserted against the source, because the point is independence.

        The fixture puts an estimate of 999 on every recommendation. A collector
        that could see that number is one that could be tuned until the measured
        and the modelled figures agree, which is the failure FEAT-029 exists to
        prevent.
        """
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[3]
            / "finops_ingest"
            / "collectors"
            / "realized_savings.py"
        )
        assert "estimated_monthly_saving" not in source.read_text()
