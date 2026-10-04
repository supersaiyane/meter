"""The container collector, and the cluster it must not quietly drop.

Four of these tests are about a cluster nothing can measure. It has no usage rows,
so every obvious implementation leaves it out of the product altogether, and a
platform team looking at nine of their ten clusters learns nothing about the tenth.
The tenth is the one worth asking about.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_api.db import models
from finops_core import errors
from finops_core.domain.account import AccountKey, Provider
from finops_fakes import fixtures
from finops_fakes.containers import FakeContainerSource
from finops_fakes.cur import ESTATE, FakeCostExport
from finops_ingest.collectors.container_usage import ContainerUsageCollector
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.registry import CollectorContext
from finops_query.containers import KIND, NO_COST, NO_REQUEST

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)
ENHANCED = AccountKey(provider=Provider.AWS, account_id="fake-platform-a")
PLAIN = AccountKey(provider=Provider.AWS, account_id="fake-platform-b")


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID
    account: AccountKey | None = ENHANCED
    region: str | None = fixtures.REGION

    @property
    def scope_key(self) -> str:
        return f"{self.account}:{self.region}"


def run(
    engine: Engine,
    tenant: UUID,
    *,
    account: AccountKey = ENHANCED,
    source: Any = None,
    run_id: UUID | None = None,
) -> int:
    with engine.begin() as connection:
        collector = ContainerUsageCollector(
            source or FakeContainerSource(at=NOW), clock=lambda: NOW
        )
        outcome = collector(
            CollectorContext(
                unit=Unit(tenant_id=tenant, account=account),
                connection=connection,
                run_id=run_id or uuid4(),
            )
        )
    return int(outcome.items_written)


def clusters_in(engine: Engine, tenant: UUID) -> list[tuple[str, bool, str | None]]:
    with engine.connect() as connection:
        return [
            (row[0], row[1], row[2])
            for row in connection.execute(
                text(
                    "SELECT cluster_name, enhanced_observability, request_unavailable_reason "
                    "FROM container_cluster WHERE tenant_id = :t ORDER BY cluster_name"
                ),
                {"t": tenant},
            )
        ]


class TestTheClusterNothingCanMeasure:
    def test_a_cluster_without_requests_is_recorded_rather_than_omitted(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        run(engine, tenant_id, account=PLAIN)
        found = clusters_in(engine, tenant_id)
        assert found, "the unmeasurable account produced no cluster row at all"
        for name, enhanced, reason in found:
            assert enhanced is False, name
            # And it says why, at length. A blank reason teaches a reader that the
            # explanations here are empty.
            assert reason and len(reason.strip()) >= 12, name

    def test_its_workloads_have_no_request_rather_than_a_request_of_zero(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """The pair the check constraint forbids, asserted from the read side too."""
        run(engine, tenant_id, account=PLAIN)
        with engine.connect() as connection:
            rows = [
                (row[0], row[1], row[2])
                for row in connection.execute(
                    text(
                        "SELECT workload, cpu_requested_millicores, cpu_used_p99_millicores "
                        "FROM container_usage WHERE tenant_id = :t"
                    ),
                    {"t": tenant_id},
                )
            ]
        assert rows, "no usage rows, so this asserted nothing"
        for workload, requested, used in rows:
            assert requested is None, f"{workload} has a request it could not have read"
            assert used is not None and used > 0, f"{workload} has no use either"

    def test_an_unobserved_oom_is_stored_as_null_and_never_as_false(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        run(engine, tenant_id, account=PLAIN)
        with engine.connect() as connection:
            states = {
                row[0]
                for row in connection.execute(
                    text("SELECT was_oom_killed FROM container_usage WHERE tenant_id = :t"),
                    {"t": tenant_id},
                )
            }
        assert states == {None}, (
            f"got {states}. False here would send the smaller memory margin to "
            f"workloads nobody checked."
        )


class TestTheMeasurableCluster:
    def test_requests_and_use_both_land(self, engine: Engine, tenant_id: UUID) -> None:
        run(engine, tenant_id)
        with engine.connect() as connection:
            rows = [
                (row[0], row[1], row[2], row[3])
                for row in connection.execute(
                    text(
                        "SELECT workload, cpu_requested_millicores, cpu_used_p99_millicores, "
                        "observation_days FROM container_usage WHERE tenant_id = :t"
                    ),
                    {"t": tenant_id},
                )
            ]
        assert rows
        for workload, requested, used, days in rows:
            assert requested is not None and requested > 0, workload
            assert used is not None, workload
            # The window the aggregate covers travels with it, which is what stops a
            # percentile over a fortnight being read as a figure for one day.
            assert days >= 14, workload

    def test_the_fleet_ratios_are_fractions(self, engine: Engine, tenant_id: UUID) -> None:
        run(engine, tenant_id)
        with engine.connect() as connection:
            rows = [
                (row[0], row[1], row[2])
                for row in connection.execute(
                    text(
                        "SELECT cluster_name, spot_ratio, packing_efficiency "
                        "FROM container_cluster WHERE tenant_id = :t"
                    ),
                    {"t": tenant_id},
                )
            ]
        assert rows
        for name, spot, packing in rows:
            for value in (spot, packing):
                if value is not None:
                    assert Decimal(0) <= value <= Decimal(1), name


class TestRunningTwice:
    def test_the_second_run_leaves_the_same_rows(self, engine: Engine, tenant_id: UUID) -> None:
        first = run(engine, tenant_id)
        before = clusters_in(engine, tenant_id)
        second = run(engine, tenant_id)
        assert first == second
        assert clusters_in(engine, tenant_id) == before

    def test_a_run_for_one_slice_does_not_retract_another(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """The defect the quota collector shipped and had to be fixed for.

        A retraction scoped only to the tenant and the run would have one account's
        run delete the rows the other account's run had just written, leaving
        whichever ran last as the whole estate.
        """
        run(engine, tenant_id, account=ENHANCED)
        run(engine, tenant_id, account=PLAIN)

        names = {name for name, _, _ in clusters_in(engine, tenant_id)}
        assert len(names) > 1, f"only {names} survived. One slice's run removed another's rows."


class TestFailuresAreTypedAndNeverZero:
    def test_a_unit_without_an_account_is_schema_drift(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        with engine.begin() as connection:
            collector = ContainerUsageCollector(FakeContainerSource(at=NOW))
            with pytest.raises(errors.SchemaDrift):
                collector(
                    CollectorContext(
                        unit=Unit(tenant_id=tenant_id, account=None),
                        connection=connection,
                        run_id=uuid4(),
                    )
                )

    def test_a_missing_run_id_is_a_caller_bug_and_not_a_collection_failure(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """A typed failure here would be recorded against the scope and send
        somebody to look at AWS for a mistake made in this process."""
        with engine.begin() as connection:
            collector = ContainerUsageCollector(FakeContainerSource(at=NOW))
            with pytest.raises(ValueError, match="run id"):
                collector(
                    CollectorContext(
                        unit=Unit(tenant_id=tenant_id), connection=connection, run_id=None
                    )
                )

    def test_a_planned_provider_failure_is_raised_as_itself(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        with engine.begin() as connection:
            collector = ContainerUsageCollector(
                FakeContainerSource(at=NOW, failure=errors.AccessDenied)
            )
            with pytest.raises(errors.AccessDenied):
                collector(
                    CollectorContext(
                        unit=Unit(tenant_id=tenant_id), connection=connection, run_id=uuid4()
                    )
                )


# --- TASK-P6-007: sizing into P3's table ----------------------------------------


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates cost partitions for the bill, so it gives them back."""


def bill(engine: Engine, tenant: UUID) -> None:
    """The fake bill with its container grain, so workloads have a measured cost."""
    with engine.begin() as connection:
        for month in {row.billing_period_start for row in ESTATE}:
            ensure_partition(connection, "cost_focus_daily", month)
        CostFocusCollector(FakeCostExport(split=True), clock=lambda: NOW)(
            CollectorContext(unit=Unit(tenant_id=tenant), connection=connection, run_id=uuid4())
        )


def recommendations(engine: Engine, tenant: UUID) -> list[Any]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    "SELECT resource_id, waste_class, lifecycle, source, severity, "
                    "estimated_monthly_saving, rationale FROM recommendation "
                    "WHERE tenant_id = :t ORDER BY resource_id"
                ),
                {"t": tenant},
            )
        )


def refusals(engine: Engine, tenant: UUID) -> list[Any]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    "SELECT resource_id, reason FROM sizing_refusal "
                    "WHERE tenant_id = :t ORDER BY resource_id"
                ),
                {"t": tenant},
            )
        )


class TestSizingIntoP3sTable:
    def test_the_over_requested_namespace_gets_a_recommendation(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """The finding the waste screen exists for, written where P3's are."""
        bill(engine, tenant_id)
        run(engine, tenant_id)
        ledger = [row for row in recommendations(engine, tenant_id) if "/ledger/" in row[0]]
        assert ledger, "the namespace requesting five times its use produced nothing"
        for resource, waste_class, lifecycle, source, severity, saving, rationale in ledger:
            assert waste_class == KIND.value, resource
            # P3's lifecycle and P3's severity, inherited rather than restated.
            assert lifecycle == "OPEN", resource
            assert source == "METER", resource
            assert severity in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}, resource
            assert saving > 0, resource
            assert "modelled" in rationale, resource

    def test_a_correctly_sized_namespace_is_not_recommended(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """A detector that flags everything would pass the test above and fail this."""
        bill(engine, tenant_id)
        run(engine, tenant_id)
        flagged = {row[0] for row in recommendations(engine, tenant_id)}
        assert not any("/channels/" in resource for resource in flagged), flagged

    def test_a_cluster_without_requests_is_refused_rather_than_recommended(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        bill(engine, tenant_id)
        run(engine, tenant_id, account=PLAIN)
        assert recommendations(engine, tenant_id) == []
        reasons = {row[1] for row in refusals(engine, tenant_id)}
        assert reasons == {NO_REQUEST}, reasons

    def test_without_a_bill_every_workload_is_refused_for_want_of_a_cost(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """No split cost, so no saving can be stated: a refusal naming ISS-003.

        Not a recommendation with a saving of zero, which would rank as the least
        valuable action rather than as the absence of one.
        """
        run(engine, tenant_id)
        assert recommendations(engine, tenant_id) == []
        reasons = {row[1] for row in refusals(engine, tenant_id)}
        assert reasons == {NO_COST}, reasons

    def test_running_twice_leaves_one_recommendation_and_one_birth(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        bill(engine, tenant_id)
        run(engine, tenant_id)
        first = recommendations(engine, tenant_id)
        run(engine, tenant_id)
        assert recommendations(engine, tenant_id) == first
        with engine.connect() as connection:
            births = connection.execute(
                text(
                    "SELECT COUNT(*) FROM recommendation_event e JOIN recommendation r "
                    "ON r.recommendation_id = e.recommendation_id "
                    "WHERE r.tenant_id = :t AND e.from_lifecycle IS NULL"
                ),
                {"t": tenant_id},
            ).scalar_one()
        assert births == len(first)


def test_there_is_no_second_recommendation_table() -> None:
    """The plan's own criterion. Container recommendations are P3 recommendations.

    Counted rather than described: a task that found itself creating a second list
    would have found a disagreement with the spec, and this is where it would show.
    """
    names = {name for name in models.metadata.tables if "recommendation" in name}
    assert names == {"recommendation", "recommendation_event"}, names
