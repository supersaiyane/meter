"""Our own findings, over a real database.

The arithmetic has its own suite against lists. What this asks is whether the
right instances reach it, and the tests that matter are the ones asserting
**nothing** was written: the burstable instance running on credits, the batch
worker, the one that is nine days old, and the one that published no metrics at
all.

A detector that finds waste everywhere is worthless, and each of those four is a
different way to find it everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_fakes.waste import FakeWasteMetrics, instances
from finops_ingest.collectors.waste_compute import Candidate, WasteComputeCollector
from finops_ingest.registry import CollectorContext

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


def estate() -> list[Candidate]:
    """Every instance in the fake, as the collector is asked to see them."""
    return [
        Candidate(
            resource_id=shape.instance_id,
            account_id="fake-platform-a",
            region_id="eu-west-1",
            observation_days=shape.days,
            monthly_cost=shape.monthly_cost,
            credit_balance=shape.credit_balance,
        )
        for shape in instances()
    ]


def collect(
    engine: Engine, tenant: UUID, settings: Settings, candidates: list[Candidate] | None = None
) -> int:
    chosen = candidates if candidates is not None else estate()
    with engine.begin() as connection:
        outcome = WasteComputeCollector(
            FakeWasteMetrics(), lambda _context: chosen, clock=lambda: NOW
        )(
            CollectorContext(
                unit=Unit(tenant_id=tenant),
                connection=connection,
                run_id=uuid4(),
                settings=settings,
            )
        )
    return int(outcome.items_written)


def found(engine: Engine, tenant: UUID) -> dict[str, tuple[str, Decimal, str]]:
    with engine.connect() as connection:
        return {
            row[0]: (row[1], row[2], row[3])
            for row in connection.execute(
                text(
                    "SELECT resource_id, waste_class, estimated_monthly_saving, severity "
                    "FROM recommendation WHERE tenant_id = :t AND source = 'METER'"
                ),
                {"t": tenant},
            )
        }


def refusals(engine: Engine, tenant: UUID) -> dict[str, tuple[str, str, int]]:
    with engine.connect() as connection:
        return {
            row[0]: (row[1], row[2], row[3])
            for row in connection.execute(
                text(
                    "SELECT resource_id, waste_class, reason, observation_days "
                    "FROM sizing_refusal WHERE tenant_id = :t"
                ),
                {"t": tenant},
            )
        }


class TestWhatItRecordsAboutRefusing:
    """FEAT-062. The four false positives above are now visible rather than only absent.

    Until 2026-09-28 the collector ended `_judge` with
    `return smaller if smaller.is_worth_acting_on else None`, so a resource examined and
    cleared and a resource nobody looked at produced the same thing: nothing. Those are
    different facts, and rendering them identically is the same defect as rendering a
    collection failure as the number zero. ADR-0027.
    """

    def test_a_resource_it_declines_is_recorded_with_its_reason(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        collect(engine, tenant_id, settings)
        written = refusals(engine, tenant_id)
        assert written, "the collector examined the estate and recorded nothing it declined"
        for resource, (waste_class, reason, days) in written.items():
            assert waste_class, resource
            # The sentence is the feature, and the database refuses a short one. This asserts
            # the stronger property: it names a measurement rather than giving a verdict.
            assert any(char.isdigit() for char in reason), f"{resource}: {reason!r}"
            assert days >= 0

    def test_nothing_it_recommends_is_also_recorded_as_refused(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """A resource cannot be both. One appearing in each list would make the two disagree,
        and a reader who spots that stops trusting whichever is less convenient."""
        collect(engine, tenant_id, settings)
        assert set(found(engine, tenant_id)) & set(refusals(engine, tenant_id)) == set()

    def test_a_second_run_replaces_a_refusal_rather_than_repeating_it(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """A refusal is a statement about the current measurement.

        Keyed on the resource and the rule, so a collector running every six hours leaves one
        row rather than a history nobody asked for, and last week's p99 is not a fact about
        today.
        """
        collect(engine, tenant_id, settings)
        first = refusals(engine, tenant_id)
        collect(engine, tenant_id, settings)
        assert refusals(engine, tenant_id) == first


class TestWhatItRefusesToFlag:
    """The four false positives, each with its own name."""

    def test_a_burstable_instance_on_credits_is_left_alone(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # The single most common false positive in this category. Recommending it
        # down is what teaches a platform team to distrust the screen.
        collect(engine, tenant_id, settings)
        assert "i-burstable" not in found(engine, tenant_id)

    def test_a_batch_worker_is_not_idle(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        collect(engine, tenant_id, settings)
        assert "i-batch" not in found(engine, tenant_id)

    def test_a_diurnal_workload_is_not_oversized(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        collect(engine, tenant_id, settings)
        assert "i-diurnal" not in found(engine, tenant_id)

    def test_an_instance_under_the_floor_is_not_judged(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        collect(engine, tenant_id, settings)
        assert "i-new" not in found(engine, tenant_id)


class TestAnUnobservedResourceIsNotAnIdleOne:
    def test_it_is_not_flagged(self, engine: Engine, tenant_id: UUID, settings: Settings) -> None:
        """The most expensive possible failure in this collector.

        An instance publishing no metrics may be perfectly busy. Reading the
        absence as zero would recommend terminating a running system.
        """
        collect(engine, tenant_id, settings)
        assert "i-unobserved" not in found(engine, tenant_id)

    def test_the_gap_is_recorded_rather_than_silent(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # An estate where half the instances publish nothing is a configuration
        # problem, and a run reporting "no waste found" would hide it.
        collect(engine, tenant_id, settings)
        with engine.connect() as connection:
            detail = connection.execute(
                text(
                    "SELECT detail FROM sync_error WHERE tenant_id = :t AND collector = "
                    "'waste_compute'"
                ),
                {"t": tenant_id},
            ).scalar_one()
        assert "published no metrics" in detail

    def test_a_persistent_gap_is_one_row_with_a_rising_count(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        collect(engine, tenant_id, settings)
        collect(engine, tenant_id, settings)
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT occurrences FROM sync_error WHERE tenant_id = :t "
                    "AND collector = 'waste_compute'"
                ),
                {"t": tenant_id},
            ).all()
        assert len(rows) == 1
        assert rows[0][0] == 2


class TestWhatItDoesFlag:
    def test_the_oversized_instance_is_a_rightsizing(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        collect(engine, tenant_id, settings)
        assert found(engine, tenant_id)["i-oversized"][0] == "RIGHTSIZE_INSTANCE"

    def test_a_dead_instance_reads_as_idle_not_as_oversized(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The ordering decision.

        Rightsizing would also report this one, truthfully and uselessly: nobody
        shrinks a machine they could delete. Asking idle first is what stops the
        screen filling with rightsizings for dead instances.
        """
        collect(engine, tenant_id, settings)
        assert found(engine, tenant_id)["i-idle"][0] == "IDLE_INSTANCE"

    def test_severity_comes_from_the_money(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        collect(engine, tenant_id, settings)
        rows = found(engine, tenant_id)
        assert rows["i-oversized"][2] in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}

    def test_a_second_run_updates_rather_than_duplicating(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        collect(engine, tenant_id, settings)
        collect(engine, tenant_id, settings)
        assert len(found(engine, tenant_id)) == 2


class TestScalingGroups:
    def test_twenty_instances_in_one_group_produce_one_recommendation(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """FEAT-026's binding rule.

        Twenty rows telling somebody the same thing is how a screen gets ignored.
        """
        group = [
            Candidate(
                resource_id="i-oversized",
                account_id="fake-platform-a",
                region_id="eu-west-1",
                observation_days=45,
                monthly_cost=Decimal("420.00"),
                scaling_group="asg-web",
            )
            for _ in range(20)
        ]
        assert collect(engine, tenant_id, settings, group) == 1
        assert list(found(engine, tenant_id)) == ["asg-web"]


class TestWhatItRefusesToRun:
    def test_it_refuses_without_settings(self, engine: Engine, tenant_id: UUID) -> None:
        # Severity comes from the money, and the boundaries are settings.
        # Defaulting them would put a severity nobody chose onto a screen.
        with engine.begin() as connection, pytest.raises(ValueError, match="settings"):
            WasteComputeCollector(FakeWasteMetrics(), lambda _c: estate(), clock=lambda: NOW)(
                CollectorContext(
                    unit=Unit(tenant_id=tenant_id), connection=connection, run_id=uuid4()
                )
            )
