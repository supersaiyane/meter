"""The score collector over real tables, and the history it has to make explainable.

The arithmetic has its own suite on numbers. What this asks is whether the right rows
reach it and whether what it stores is enough to explain a change: an account that was
never judged getting no row at all, a component's null surviving the write, and the
difference between two runs resolving to a list of findings rather than to two
numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.collectors.score import JUDGING_COLLECTORS, ScoreCollector
from finops_ingest.registry import CollectorContext

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)
WATCHED = "111122223333"
BLIND = "444455556666"


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


def an_account(engine: Engine, tenant: UUID, account: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO cloud_account (account_pk, tenant_id, provider, account_id, name, "
                "status, as_of, collected_at) "
                "VALUES (:pk, :t, 'aws', :a, :a, 'ACTIVE', :at, :at) ON CONFLICT DO NOTHING"
            ),
            {"pk": uuid4(), "t": tenant, "a": account, "at": NOW},
        )


def a_judging_run(engine: Engine, tenant: UUID, account: str, *, ago_days: int = 0) -> None:
    """A successful waste collection for one account.

    This is what makes an account count as judged, and the scope key format is the
    documented `provider:account:region`, which the collector reads the second field
    of. A test that wrote a different shape would pass while production returned
    nothing.
    """
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, "
                "idempotency_key, started_at, finished_at, status, as_of_window_start, "
                "as_of_window_end) VALUES (:r, :t, :c, :k, :idem, :at, :at, 'SUCCEEDED', "
                ":at, :at)"
            ),
            {
                "r": uuid4(),
                "t": tenant,
                "c": JUDGING_COLLECTORS[0],
                "k": f"aws:{account}:eu-west-1",
                "idem": str(uuid4()),
                "at": NOW - timedelta(days=ago_days),
            },
        )


def spend(engine: Engine, tenant: UUID, account: str, daily: str = "100") -> None:
    day = NOW.date() - timedelta(days=1)
    period = date(day.year, day.month, 1)
    with engine.begin() as connection:
        ensure_partition(connection, "cost_focus_daily", period)
        start = datetime(day.year, day.month, day.day, tzinfo=UTC)
        connection.execute(
            text(
                "INSERT INTO cost_focus_daily (tenant_id, ingest_run_id, source_fingerprint, "
                "as_of, collected_at, billing_account_id, sub_account_id, "
                "billing_period_start, billing_period_end, charge_period_start, "
                "charge_period_end, provider_name, service_name, charge_category, "
                "billed_cost, effective_cost, tags) "
                "VALUES (:t, :run, :fp, :at, :at, 'payer', :a, :period, :period_end, "
                ":start, :end, 'Fake', 'AmazonEC2', 'Usage', :cost, :cost, '{}'::jsonb)"
            ),
            {
                "t": tenant,
                "run": uuid4(),
                "fp": f"{account}:{day}",
                "at": NOW,
                "a": account,
                "period": period,
                "period_end": date(period.year + (period.month // 12), (period.month % 12) + 1, 1),
                "start": start,
                "end": start + timedelta(days=1),
                "cost": Decimal(daily),
            },
        )


def a_finding(
    engine: Engine,
    tenant: UUID,
    account: str,
    *,
    saving: str = "500",
    lifecycle: str = "OPEN",
    owner: str | None = None,
) -> UUID:
    identifier = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, "
                "source, source_reference, waste_class, resource_id, region_id, "
                "estimated_monthly_saving, confidence, severity, observation_days, "
                "lifecycle, owner, rationale, as_of, collected_at) "
                "VALUES (:id, :t, :a, 'METER', :ref, 'IDLE_INSTANCE', :res, 'eu-west-1', "
                ":saving, 'HIGH', 'HIGH', 30, :lifecycle, :owner, 'because', :at, :at)"
            ),
            {
                "id": identifier,
                "t": tenant,
                "a": account,
                "ref": f"ref:{identifier}",
                "res": f"i-{identifier}",
                "saving": Decimal(saving),
                "lifecycle": lifecycle,
                "owner": owner,
                "at": NOW,
            },
        )
    return identifier


def run(engine: Engine, tenant: UUID, at: datetime = NOW) -> int:
    with engine.begin() as connection:
        outcome = ScoreCollector(clock=lambda: at)(
            CollectorContext(unit=Unit(tenant_id=tenant), connection=connection, run_id=uuid4())
        )
    return int(outcome.items_written)


def scores(engine: Engine, tenant: UUID) -> dict[str, tuple[int, int, UUID]]:
    with engine.connect() as connection:
        return {
            row[0]: (int(row[1]), int(row[2]), row[3])
            for row in connection.execute(
                text(
                    # Ascending, and it matters: the comprehension below keeps the
                    # last value it sees for a key, so descending would leave the
                    # oldest score per account and every history test would compare
                    # the first run with itself.
                    "SELECT sub_account_id, total, available_weight, score_id "
                    "FROM finops_score WHERE tenant_id = :t ORDER BY as_of ASC"
                ),
                {"t": tenant},
            ).all()
        }


def components(engine: Engine, score_id: UUID) -> dict[str, tuple[Decimal | None, int, list[UUID]]]:
    with engine.connect() as connection:
        return {
            row[0]: (None if row[1] is None else Decimal(row[1]), int(row[2]), list(row[3]))
            for row in connection.execute(
                text(
                    "SELECT name, points, weight, finding_ids FROM finops_score_component "
                    "WHERE score_id = :s"
                ),
                {"s": score_id},
            ).all()
        }


class TestWhatGetsAScore:
    def test_a_judged_account_is_scored_with_its_components(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        an_account(engine, tenant_id, WATCHED)
        a_judging_run(engine, tenant_id, WATCHED)
        spend(engine, tenant_id, WATCHED, daily="1000")
        finding_id = a_finding(engine, tenant_id, WATCHED, saving="100")

        assert run(engine, tenant_id) == 1
        total, weight, score_id = scores(engine, tenant_id)[WATCHED]
        assert 0 <= total <= 100
        assert weight > 0
        parts = components(engine, score_id)
        assert set(parts) == {"waste", "coverage", "responsiveness", "verification"}
        assert finding_id in parts["waste"][2]

    def test_an_account_no_collector_reached_gets_no_row_at_all(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """Not a zero, and not a hundred.

        An account nobody assessed must not appear in a league table, in either
        direction. A zero would put a collection failure at the bottom, and the
        absence of findings would otherwise put it at the top.
        """
        an_account(engine, tenant_id, BLIND)
        spend(engine, tenant_id, BLIND, daily="1000")

        assert run(engine, tenant_id) == 0
        assert scores(engine, tenant_id) == {}

    def test_the_unscored_accounts_are_recorded_rather_than_simply_absent(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # A shorter list is not something anybody notices, so the gap gets a row of
        # its own with the count and the remediation.
        an_account(engine, tenant_id, BLIND)
        run(engine, tenant_id)
        with engine.connect() as connection:
            detail = connection.execute(
                text(
                    "SELECT detail FROM sync_error WHERE tenant_id = :t "
                    "AND collector = 'finops_score'"
                ),
                {"t": tenant_id},
            ).scalar_one()
        assert "could not be scored" in detail
        assert BLIND in detail

    def test_a_stale_judging_run_does_not_count(self, engine: Engine, tenant_id: UUID) -> None:
        """A waste collection from a fortnight ago is not evidence about today.

        The window is deliberately two days rather than one, so a single failed run
        does not blank an account's score, and this asserts it is not unbounded.
        """
        an_account(engine, tenant_id, WATCHED)
        a_judging_run(engine, tenant_id, WATCHED, ago_days=14)
        spend(engine, tenant_id, WATCHED)

        assert run(engine, tenant_id) == 0

    def test_a_run_from_yesterday_does_count(self, engine: Engine, tenant_id: UUID) -> None:
        # The other side of the window, so the test above is about the boundary and
        # not about the lookup never matching anything.
        an_account(engine, tenant_id, WATCHED)
        a_judging_run(engine, tenant_id, WATCHED, ago_days=1)
        spend(engine, tenant_id, WATCHED)

        assert run(engine, tenant_id) == 1


class TestWhatItStoresForLater:
    def test_a_component_that_could_not_be_computed_stores_null_not_zero(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """The null has to survive the write or the whole rule is cosmetic.

        Here there are no verifications and no findings, so two components are
        uncomputable. A zero in either would put them back into the denominator as
        the worst possible value.
        """
        an_account(engine, tenant_id, WATCHED)
        a_judging_run(engine, tenant_id, WATCHED)
        spend(engine, tenant_id, WATCHED)

        run(engine, tenant_id)
        _, weight, score_id = scores(engine, tenant_id)[WATCHED]
        parts = components(engine, score_id)
        assert parts["verification"][0] is None
        assert parts["responsiveness"][0] is None
        # And the stored weight is what the total is actually out of, so a reader of
        # an old row can tell sixty out of sixty from sixty out of a hundred.
        assert weight == parts["waste"][1] + parts["coverage"][1]

    def test_two_runs_leave_two_rows_so_the_history_exists(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        an_account(engine, tenant_id, WATCHED)
        a_judging_run(engine, tenant_id, WATCHED)
        spend(engine, tenant_id, WATCHED)

        run(engine, tenant_id)
        run(engine, tenant_id, at=NOW + timedelta(hours=6))
        with engine.connect() as connection:
            count = connection.execute(
                text("SELECT COUNT(*) FROM finops_score WHERE tenant_id = :t"),
                {"t": tenant_id},
            ).scalar_one()
        assert count == 2

    def test_a_repeated_run_at_the_same_instant_replaces_rather_than_failing(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # A retry is not an error, and the verdict is identical either way, so the
        # unique index must not turn a repeat into a failed collection.
        an_account(engine, tenant_id, WATCHED)
        a_judging_run(engine, tenant_id, WATCHED)
        spend(engine, tenant_id, WATCHED)

        run(engine, tenant_id)
        run(engine, tenant_id)
        with engine.connect() as connection:
            count = connection.execute(
                text("SELECT COUNT(*) FROM finops_score WHERE tenant_id = :t"),
                {"t": tenant_id},
            ).scalar_one()
        assert count == 1

    def test_a_change_between_two_runs_resolves_to_a_finding(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """The criterion FEAT-043 ships on, asserted against stored rows.

        Two runs either side of one finding being dismissed. The difference between
        the two scores is not merely visible, it resolves to the identifier of the
        finding that left, which is only possible because each run stored its own
        components.
        """
        an_account(engine, tenant_id, WATCHED)
        a_judging_run(engine, tenant_id, WATCHED)
        spend(engine, tenant_id, WATCHED, daily="1000")
        staying = a_finding(engine, tenant_id, WATCHED, saving="100")
        leaving = a_finding(engine, tenant_id, WATCHED, saving="100")

        run(engine, tenant_id)
        first = scores(engine, tenant_id)[WATCHED]
        before = components(engine, first[2])["waste"][2]

        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE recommendation SET lifecycle = 'DISMISSED' "
                    "WHERE recommendation_id = :id"
                ),
                {"id": leaving},
            )
        run(engine, tenant_id, at=NOW + timedelta(hours=6))
        second = scores(engine, tenant_id)[WATCHED]
        after = components(engine, second[2])["waste"][2]

        assert set(before) == {staying, leaving}
        assert set(after) == {staying}
        assert set(before) - set(after) == {leaving}
        # And the score improved, because the money on the bill went down.
        assert second[0] > first[0]
