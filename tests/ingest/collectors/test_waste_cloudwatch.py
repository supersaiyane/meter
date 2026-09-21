"""The module that bills for watching, over a real database.

Four of the fake's ten resources are findings and six are not. The six are the
tests worth reading: a group somebody chose a retention for, a group too young for
a policy to have saved anything, a tiny group under the floor, an alarm quiet for
two hours rather than seven months, and two alarms doing their job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_ingest.collectors.waste_cloudwatch import WasteCloudWatchCollector
from finops_ingest.registry import CollectorContext
from finops_providers.fake.cloudwatch_estate import FakeCloudWatchEstate

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


def collect(engine: Engine, tenant: UUID, settings: Settings, estate: object | None = None) -> int:
    with engine.begin() as connection:
        outcome = WasteCloudWatchCollector(
            estate or FakeCloudWatchEstate(at=NOW), clock=lambda: NOW
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
                    "SELECT resource_id, waste_class, estimated_monthly_saving, rationale "
                    "FROM recommendation WHERE tenant_id = :t"
                ),
                {"t": tenant},
            )
        }


class TestRetention:
    def test_a_group_nobody_chose_a_retention_for_is_a_finding(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        collect(engine, tenant_id, settings)
        assert "/aws/lambda/fake-ingest" in found(engine, tenant_id)

    def test_a_group_somebody_chose_for_is_left_alone(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """However large it is. A retention policy is a decision, and this product
        does not second guess a decision somebody made."""
        collect(engine, tenant_id, settings)
        assert "/aws/eks/fake-cluster/cluster" not in found(engine, tenant_id)

    def test_a_group_too_young_to_have_expired_anything_is_left_alone(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # Asking for work with no payoff is how a recommendation list loses its
        # reader.
        collect(engine, tenant_id, settings)
        assert "/aws/lambda/fake-new" not in found(engine, tenant_id)

    def test_a_tiny_group_is_under_the_floor(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        collect(engine, tenant_id, settings)
        assert "/aws/lambda/fake-quiet" not in found(engine, tenant_id)

    def test_the_rationale_names_the_assumption_the_saving_rests_on(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The straight line assumption is doing real work in this figure.

        A reader who cannot see it cannot judge whether it holds for their group,
        and a group whose ingest tripled last month will not save what we said.
        """
        collect(engine, tenant_id, settings)
        rationale = found(engine, tenant_id)["/aws/lambda/fake-ingest"][2]
        assert "even ingest rate" in rationale
        assert "30 day retention" in rationale


class TestAnUnknownPriceIsNotAZeroPrice:
    def test_the_retention_check_is_skipped_rather_than_priced_at_nothing(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """A saving computed from an invented price is worse than no saving.

        Somebody would act on it, and the number they were promised would not
        appear.
        """
        collect(engine, tenant_id, settings, FakeCloudWatchEstate(at=NOW, price_known=False))
        assert "/aws/lambda/fake-ingest" not in found(engine, tenant_id)

    def test_the_alarms_are_still_checked(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # One check failing does not take the other with it.
        collect(engine, tenant_id, settings, FakeCloudWatchEstate(at=NOW, price_known=False))
        assert "fake-orphaned-queue-depth" in found(engine, tenant_id)


class TestAlarms:
    def test_an_alarm_quiet_for_seven_months_is_a_finding(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        collect(engine, tenant_id, settings)
        assert "fake-orphaned-queue-depth" in found(engine, tenant_id)

    def test_an_alarm_quiet_for_two_hours_is_not(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # Normal during a deploy. Flagging it would teach a reader to skim.
        collect(engine, tenant_id, settings)
        assert "fake-deploying-service" not in found(engine, tenant_id)

    def test_alarms_doing_their_job_are_not_findings(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        collect(engine, tenant_id, settings)
        rows = found(engine, tenant_id)
        assert "fake-healthy" not in rows
        assert "fake-firing" not in rows

    def test_the_finding_is_about_assurance_rather_than_money(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """An alarm costs almost nothing, so the saving is zero and the rationale
        carries the actual cost: coverage that is not there."""
        collect(engine, tenant_id, settings)
        _, saving, rationale = found(engine, tenant_id)["fake-orphaned-queue-depth"]
        assert saving == Decimal("0E-10")
        assert "coverage it appears to give is not there" in rationale


class TestItRefusesWithoutSettings:
    def test_severity_boundaries_are_configuration(self, engine: Engine, tenant_id: UUID) -> None:
        with engine.begin() as connection, pytest.raises(ValueError, match="settings"):
            WasteCloudWatchCollector(FakeCloudWatchEstate(at=NOW), clock=lambda: NOW)(
                CollectorContext(
                    unit=Unit(tenant_id=tenant_id), connection=connection, run_id=uuid4()
                )
            )
