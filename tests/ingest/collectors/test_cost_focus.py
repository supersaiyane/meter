"""Writing the bill, twice, and getting the same bill.

AWS restates a billing period continuously and can restate a closed one. So the
question this collector has to answer is not whether it can write rows. It is
whether writing the same period again leaves the same rows, and whether writing
a corrected row lands on the row it corrects rather than beside it.

One day of data hides all of it. That is how ISS-175 and ISS-177 both survived,
and it is why these tests ingest twice rather than once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core import errors
from finops_fakes import containers
from finops_fakes.cur import (
    CLOSED_PERIOD,
    CORRECTED_FINGERPRINT,
    ESTATE,
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


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


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

        # No new fingerprint appeared, which is the claim this test makes. The
        # one row missing afterwards is the retraction, and that has its own
        # file, because removing a row is a different operation from correcting
        # one and deserves its own review.
        assert set(after) == set(before) - {RETRACTED_FINGERPRINT}
        assert after[CORRECTED_FINGERPRINT] != before[CORRECTED_FINGERPRINT]
        changed = [key for key in after if before[key] != after[key]]
        assert changed == [CORRECTED_FINGERPRINT], f"more than the correction moved: {changed}"

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


class TestTheCadenceIsData:
    """ADR-0012 and constraint 9. A cadence in code is a cadence nobody can
    change without a deploy, and the first thing anyone does with an
    unexplained interval under cost pressure is double it."""

    def test_the_collector_has_a_row_and_not_a_constant(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        from finops_ingest.registry import install_default_schedule

        with engine.begin() as connection:
            install_default_schedule(connection, tenant_id, updated_by="test")
            row = connection.execute(
                text(
                    "SELECT cadence_seconds, reason, est_cost_per_run FROM collector_schedule "
                    "WHERE tenant_id = :t AND collector = 'cost_focus'"
                ),
                {"t": tenant_id},
            ).one()

        cadence, reason, cost = row
        assert cadence == 21600, "six hourly, which is four reads of the open period a day"
        assert len(reason) > 80, "a cadence nobody can explain is one nobody can safely change"
        assert Decimal(cost) > 0, "each run is an Athena query and the estimate should say so"

    def test_an_operators_change_survives_a_reinstall(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """The table is the source, so onboarding must not overwrite it.

        An operator who slowed this down to save money, and found it back at
        six hourly after the next tenant was onboarded, would stop trusting the
        table and put the number back in code.
        """
        from finops_ingest.registry import install_default_schedule

        with engine.begin() as connection:
            install_default_schedule(connection, tenant_id, updated_by="test")
            connection.execute(
                text(
                    "UPDATE collector_schedule SET cadence_seconds = 86400 "
                    "WHERE tenant_id = :t AND collector = 'cost_focus'"
                ),
                {"t": tenant_id},
            )
            install_default_schedule(connection, tenant_id, updated_by="test-again")
            after = connection.execute(
                text(
                    "SELECT cadence_seconds FROM collector_schedule "
                    "WHERE tenant_id = :t AND collector = 'cost_focus'"
                ),
                {"t": tenant_id},
            ).scalar_one()

        assert after == 86400


class TestSplitCostAllocation:
    """TASK-P6-002. Pod cost is measured, and it is money already on the bill.

    The defect these guard against is the one a cost product cannot ship: counting
    a clustered charge twice, once on the node and again on the pod. A split line
    carries no money of its own, so the period total has to be identical whether
    the container grain is present or absent, and the first test asserts exactly
    that rather than trusting the fake to have been built correctly.
    """

    def test_the_container_grain_reaches_the_table(self, engine: Engine, tenant_id: UUID) -> None:
        ingest(engine, tenant_id)
        with engine.connect() as connection:
            clusters = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT DISTINCT eks_cluster_name FROM cost_focus_daily "
                        "WHERE tenant_id = :t AND eks_cluster_name IS NOT NULL"
                    ),
                    {"t": tenant_id},
                )
            }
        assert clusters, "no charge was attributed to a cluster"
        # Both EKS clusters, including the one without enhanced observability: that
        # cluster's cost is readable even though its requests are not, and conflating
        # the two gaps would hide a cluster that does have a cost.
        assert clusters == {"platform-eks", "batch-eks"}

    def test_a_split_line_adds_no_money_to_the_period(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """The whole reason split cost is a breakdown rather than a charge."""
        ingest(engine, tenant_id)
        with engine.connect() as connection:
            total, split_money = connection.execute(
                text(
                    "SELECT COALESCE(SUM(effective_cost), 0), "
                    "COALESCE(SUM(effective_cost) FILTER "
                    "(WHERE eks_cluster_name IS NOT NULL), 0) "
                    "FROM cost_focus_daily WHERE tenant_id = :t"
                ),
                {"t": tenant_id},
            ).one()
        assert total > 0, "the fixture wrote no money at all, so this proves nothing"
        assert split_money == 0, (
            "split lines carry money of their own, which double counts every "
            "clustered charge against the node line that already holds it"
        )

    def test_a_cluster_reconciles_to_the_charge_it_is_splitting(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """A split that does not reconcile is a split that invented money."""
        ingest(engine, tenant_id)
        groups = {
            cluster.name: [group.resource_id for group in cluster.node_groups]
            for cluster in containers.CLUSTERS
            if cluster.platform == "EKS"
        }
        with engine.connect() as connection:
            for name, resources in groups.items():
                parent = connection.execute(
                    text(
                        "SELECT COALESCE(SUM(effective_cost), 0) FROM cost_focus_daily "
                        "WHERE tenant_id = :t AND resource_id = ANY(:r)"
                    ),
                    {"t": tenant_id, "r": resources},
                ).scalar_one()
                attributed = connection.execute(
                    text(
                        "SELECT COALESCE(SUM(split_cost), 0) + COALESCE(SUM(unused_cost), 0) "
                        "FROM cost_focus_daily WHERE tenant_id = :t AND eks_cluster_name = :c"
                    ),
                    {"t": tenant_id, "c": name},
                ).scalar_one()
                assert parent > 0, f"{name} has no node charge to split"
                assert attributed == parent, (
                    f"{name} attributes {attributed} of a {parent} node charge. The "
                    f"difference is money the breakdown either invented or lost."
                )

    def test_an_export_without_split_data_names_the_gap(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """ISS-003. A configuration fault, never a cluster costing nothing."""
        ingest(engine, tenant_id, export=FakeCostExport(split=False))
        with engine.connect() as connection:
            clusters = connection.execute(
                text(
                    "SELECT COUNT(*) FROM cost_focus_daily "
                    "WHERE tenant_id = :t AND eks_cluster_name IS NOT NULL"
                ),
                {"t": tenant_id},
            ).scalar_one()
            gaps = [
                (row[0], row[1], row[2])
                for row in connection.execute(
                    text(
                        "SELECT error_type, detail, remediation FROM sync_error "
                        "WHERE tenant_id = :t AND collector = 'cost_focus'"
                    ),
                    {"t": tenant_id},
                )
            ]
        # No cluster rows at all, which is the honest state: nothing was measured.
        assert clusters == 0
        assert len(gaps) == 1, f"expected one named gap, got {gaps}"
        error_type, detail, remediation = gaps[0]
        # Misconfigured, per ADR-0026: somebody fixes this by editing a setting.
        # NoData is the one cause that renders as zero and would be exactly wrong.
        assert error_type == "Misconfigured"
        assert "split cost allocation" in detail
        assert "ISS-003" in remediation

    def test_enabling_split_data_clears_the_gap(self, engine: Engine, tenant_id: UUID) -> None:
        """A corrected setting stops complaining without anybody tidying a row."""
        ingest(engine, tenant_id, export=FakeCostExport(split=False))
        ingest(engine, tenant_id)
        with engine.connect() as connection:
            remaining = connection.execute(
                text(
                    "SELECT COUNT(*) FROM sync_error WHERE tenant_id = :t "
                    "AND collector = 'cost_focus'"
                ),
                {"t": tenant_id},
            ).scalar_one()
        assert remaining == 0

    def test_a_successful_run_does_not_wipe_its_own_gap(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """The gap is reported by a run that succeeded, which is the trap here.

        The worker clears every error row for a collector and scope when a unit
        succeeds. Written under the unit's own scope key this gap would be deleted a
        moment after it was written, by the very thing proving the read worked, and
        the screen would show clusters costing nothing with nothing explaining why.
        """
        from finops_fakes.fixtures import ORGANIZATION_SCOPE
        from finops_ingest.collectors.cost_focus import SCOPE, SPLIT_GAP_SCOPE

        ingest(engine, tenant_id, export=FakeCostExport(split=False))
        with engine.connect() as connection:
            scope = connection.execute(
                text(
                    "SELECT scope_key FROM sync_error WHERE tenant_id = :t "
                    "AND collector = 'cost_focus'"
                ),
                {"t": tenant_id},
            ).scalar_one()
        # The row is still there after the run that wrote it, and it is under a key
        # that is neither the collector's own scope nor the organization scope the
        # worker would clear for an organization scoped unit.
        assert scope == SPLIT_GAP_SCOPE
        assert scope not in {SCOPE, ORGANIZATION_SCOPE}
