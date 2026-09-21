"""The AWS recommendation collector, over a real database.

The contract suite checks the port. What this asks is whether a human's work
survives a re read, which is the only thing this collector can really get wrong.

A provider re read happens every day. If it resets an accepted recommendation, or
deletes a withdrawn one, or writes a second row for a finding it already has, the
lifecycle is decoration and nobody will use it twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.waste import Source
from finops_core.errors import AccessDenied
from finops_fakes.recommendations import FakeRecommendationSource, findings
from finops_ingest.collectors.recommendations import RecommendationCollector
from finops_ingest.registry import CollectorContext

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


def collect(engine: Engine, tenant: UUID, provider: object | None = None) -> int:
    with engine.begin() as connection:
        outcome = RecommendationCollector(
            provider or FakeRecommendationSource(), clock=lambda: NOW
        )(CollectorContext(unit=Unit(tenant_id=tenant), connection=connection, run_id=uuid4()))
    return int(outcome.items_written)


def rows(engine: Engine, tenant: UUID) -> list[tuple[str, str, str, Decimal]]:
    with engine.connect() as connection:
        return [
            (row[0], row[1], row[2], row[3])
            for row in connection.execute(
                text(
                    "SELECT source_reference, lifecycle, confidence, estimated_monthly_saving "
                    "FROM recommendation WHERE tenant_id = :t ORDER BY source_reference"
                ),
                {"t": tenant},
            )
        ]


def events(engine: Engine, tenant: UUID) -> list[tuple[str | None, str, str | None]]:
    with engine.connect() as connection:
        return [
            (row[0], row[1], row[2])
            for row in connection.execute(
                text(
                    "SELECT from_lifecycle, to_lifecycle, reason FROM recommendation_event "
                    "WHERE tenant_id = :t ORDER BY occurred_at, to_lifecycle"
                ),
                {"t": tenant},
            )
        ]


def move(engine: Engine, tenant: UUID, reference: str, lifecycle: str) -> None:
    """A human doing something, so the next re read has something to preserve."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE recommendation SET lifecycle = :l "
                "WHERE tenant_id = :t AND source_reference = :r"
            ),
            {"l": lifecycle, "t": tenant, "r": reference},
        )


class NoLongerReporting:
    """A provider that has stopped reporting everything except the hub.

    Written as a class rather than a flag on the fake, because the fake's job is to
    describe an estate and this is a description of a provider changing its mind.
    """

    def compute_optimizer(self) -> tuple[()]:
        return ()

    def cost_optimization_hub(self):  # type: ignore[no-untyped-def]
        return FakeRecommendationSource().cost_optimization_hub()

    def trusted_advisor(self) -> tuple[()]:
        return ()


class TestItWrites:
    def test_every_finding_lands_once(self, engine: Engine, tenant_id: UUID) -> None:
        assert collect(engine, tenant_id) == 4
        assert len(rows(engine, tenant_id)) == 4

    def test_a_second_run_updates_rather_than_duplicating(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        collect(engine, tenant_id)
        collect(engine, tenant_id)
        assert len(rows(engine, tenant_id)) == 4

    def test_the_first_event_records_that_it_was_found(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # Exactly one null from_lifecycle per recommendation, which the schema
        # enforces and which lets the log be replayed rather than merely listed.
        collect(engine, tenant_id)
        firsts = [event for event in events(engine, tenant_id) if event[0] is None]
        assert len(firsts) == 4
        assert {event[1] for event in firsts} == {"OPEN"}

    def test_a_second_run_writes_no_second_first_event(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        collect(engine, tenant_id)
        collect(engine, tenant_id)
        assert len([event for event in events(engine, tenant_id) if event[0] is None]) == 4


class TestAHumansWorkSurvivesAReRead:
    def test_an_accepted_recommendation_is_not_reopened(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """The provider owns the finding. We own the lifecycle.

        A re read resetting this every six hours would make the acceptance
        meaningless and the screen useless.
        """
        collect(engine, tenant_id)
        reference = "hub-graviton-0001"
        move(engine, tenant_id, reference, "ACCEPTED")
        collect(engine, tenant_id)
        found = {row[0]: row[1] for row in rows(engine, tenant_id)}
        assert found[reference] == "ACCEPTED"

    def test_an_untouched_recommendation_is_refreshed(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # The other half. A row nobody has moved should take the provider's newest
        # money and working, or the screen goes stale silently.
        collect(engine, tenant_id)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE recommendation SET estimated_monthly_saving = 1, rationale = 'stale' "
                    "WHERE tenant_id = :t"
                ),
                {"t": tenant_id},
            )
        collect(engine, tenant_id)
        assert all(row[3] > Decimal("1") for row in rows(engine, tenant_id))


class TestWithdrawal:
    def test_a_finding_aws_stopped_reporting_is_dismissed_not_deleted(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """Removing the row would take its event log with it.

        The log is the only record that somebody accepted it in March and nothing
        happened, which is the failure ISS-028 exists for.
        """
        collect(engine, tenant_id)
        collect(engine, tenant_id, NoLongerReporting())
        found = {row[0]: row[1] for row in rows(engine, tenant_id)}
        assert len(found) == 4, "a withdrawn recommendation must keep its row"
        # Derived from the fake rather than written out, because the fake builds
        # its ARNs from `fixtures.REGION` and a literal here would go stale the
        # first time that moved.
        withdrawn = next(
            item.source_reference for item in findings() if item.resource_id == "i-oversized"
        )
        assert found[withdrawn] == "DISMISSED"

    def test_the_withdrawal_event_names_where_it_came_from(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """The bug this test was written for.

        Postgres RETURNING on an UPDATE yields the new row, so a naive
        `RETURNING lifecycle` writes "DISMISSED to DISMISSED" for every withdrawal
        and the log says nothing. The collector captures the prior state in a CTE
        before the write.
        """
        collect(engine, tenant_id)
        collect(engine, tenant_id, NoLongerReporting())
        withdrawals = [event for event in events(engine, tenant_id) if event[1] == "DISMISSED"]
        assert withdrawals
        for came_from, _, reason in withdrawals:
            assert came_from == "OPEN", f"withdrawal recorded as coming from {came_from}"
            assert reason and "no longer reports" in reason

    def test_a_service_that_was_never_enabled_withdraws_nothing(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # A service that was never on has not stopped reporting anything, and
        # dismissing its findings would be a claim nobody made.
        collect(engine, tenant_id)
        collect(
            engine,
            tenant_id,
            FakeRecommendationSource(not_opted_in=frozenset({Source.COMPUTE_OPTIMIZER})),
        )
        alive = [row for row in rows(engine, tenant_id) if row[1] == "OPEN"]
        assert len(alive) == 4


class TestFailure:
    def test_not_opted_in_is_absorbed_and_the_others_still_run(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        written = collect(
            engine,
            tenant_id,
            FakeRecommendationSource(not_opted_in=frozenset({Source.COMPUTE_OPTIMIZER})),
        )
        # The two Compute Optimizer findings are absent; the other two are not.
        assert written == 2

    def test_a_real_failure_is_not_swallowed(self, engine: Engine, tenant_id: UUID) -> None:
        # Withdrawing on a timeout would dismiss every finding from a service that
        # merely failed to answer.
        with pytest.raises(AccessDenied):
            collect(engine, tenant_id, FakeRecommendationSource(AccessDenied))


class TestScope:
    def test_one_tenant_does_not_see_another(self, engine: Engine, tenant_id: UUID) -> None:
        neighbour = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO tenant (tenant_id, name) VALUES (:id, :name)"),
                {"id": neighbour, "name": f"tenant-{neighbour}"},
            )
        collect(engine, neighbour)
        assert rows(engine, tenant_id) == []
        assert len(rows(engine, neighbour)) == 4
