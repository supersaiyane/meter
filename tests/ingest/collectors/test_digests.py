"""The weekly digests, composed from the bill the screens read. TASK-P7-012.

The figures are checked against the fake bill's own rows, summed here independently of the
SQL that composed them, so a digest agreeing with itself proves nothing and a digest
agreeing with the bill proves the claim: composed from the same rows the screens show.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.insight import Answer
from finops_core.domain.platform import UNALLOCATED
from finops_ingest.collectors.digests import COLLECTOR, UNSENT, DigestCollector
from finops_ingest.registry import DEFAULT_SCHEDULE, WEEKLY, CollectorContext, CollectorOutcome
from finops_query.digest import WeekOfSpend, compose
from tests.query.insight.harness import CLOSED, seed_bill

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("clear_split_gap")]

#: A Monday in the fake bill's closed month, so the last complete week is inside it.
CLOCK = datetime(2026, 7, 20, 6, 0, tzinfo=UTC)
WEEK = (date(2026, 7, 13), date(2026, 7, 19))
WEEK_BEFORE = (date(2026, 7, 6), date(2026, 7, 12))


@dataclass(frozen=True)
class _Unit:
    tenant_id: UUID


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module seeds the fake bill's month, so it gives it back."""


def run(engine: Engine, tenant: UUID, composer: Any = compose) -> CollectorOutcome:
    with engine.begin() as connection:
        collector = DigestCollector(clock=lambda: CLOCK, composer=composer)
        return collector(
            CollectorContext(unit=_Unit(tenant_id=tenant), connection=connection, run_id=uuid4())
        )


def stored(engine: Engine, tenant: UUID) -> dict[str, dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT * FROM team_digest WHERE tenant_id = :t"), {"t": tenant}
        ).all()
    return {str(row.team or "organization"): dict(row._mapping) for row in rows}


def billed(start: date, end: date) -> dict[str, Decimal]:
    """The bill's own rows for a week, summed by team tag, independently of the SQL."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for row in CLOSED:
        if start <= row.charge_period_start.astimezone(UTC).date() <= end:
            totals[row.tags.get("team", UNALLOCATED)] += row.effective_cost
    return dict(totals)


def figure(digest: dict[str, Any], placeholder: str) -> Decimal | str:
    (value,) = [c["value"] for c in digest["citations"] if c["placeholder"] == placeholder]
    return Decimal(value) if placeholder in {"spend", "previous", "service_spend"} else value


def test_every_team_the_bill_names_gets_a_digest_and_the_organization_one(
    engine: Engine, tenant_id: UUID
) -> None:
    seed_bill(engine, tenant_id, split=False)

    outcome = run(engine, tenant_id)

    digests = stored(engine, tenant_id)
    assert set(digests) == {*billed(*WEEK), "organization"}
    assert outcome.items_written == len(digests)


def test_each_digests_figures_are_the_bills_own(engine: Engine, tenant_id: UUID) -> None:
    seed_bill(engine, tenant_id, split=False)
    run(engine, tenant_id)
    digests = stored(engine, tenant_id)

    this_week, week_before = billed(*WEEK), billed(*WEEK_BEFORE)
    for team, spend in this_week.items():
        assert figure(digests[team], "spend") == spend, team
        assert figure(digests[team], "previous") == week_before[team], team
    organization = digests["organization"]
    assert figure(organization, "spend") == sum(this_week.values())
    assert figure(organization, "previous") == sum(week_before.values())
    assert (organization["period_start"], organization["period_end"]) == WEEK


def test_a_digest_is_composed_and_kept_with_the_reason_it_was_not_sent(
    engine: Engine, tenant_id: UUID
) -> None:
    seed_bill(engine, tenant_id, split=False)
    run(engine, tenant_id)

    for digest in stored(engine, tenant_id).values():
        assert digest["sent_at"] is None
        assert digest["unsent_reason"] == UNSENT
        assert "OPEN-11" in digest["unsent_reason"]


def test_one_team_failing_does_not_fail_the_run(engine: Engine, tenant_id: UUID) -> None:
    seed_bill(engine, tenant_id, split=False)
    unlucky = sorted(billed(*WEEK))[0]

    def composer(week: WeekOfSpend) -> Answer:
        if week.team == unlucky:
            raise ValueError("this team's rows could not be composed")
        return compose(week)

    outcome = run(engine, tenant_id, composer)

    digests = stored(engine, tenant_id)
    assert unlucky not in digests
    assert outcome.items_written == len(digests) == len(billed(*WEEK))
    with engine.connect() as connection:
        failure = connection.execute(
            text(
                "SELECT error_type, scope_key FROM sync_error "
                "WHERE tenant_id = :t AND collector = :c"
            ),
            {"t": tenant_id, "c": COLLECTOR},
        ).one()
    assert failure.error_type == "SchemaDrift"
    assert failure.scope_key == f"digests:team:{unlucky}"


def test_a_team_that_composes_on_the_next_run_clears_its_own_failure(
    engine: Engine, tenant_id: UUID
) -> None:
    seed_bill(engine, tenant_id, split=False)
    unlucky = sorted(billed(*WEEK))[0]

    def failing(week: WeekOfSpend) -> Answer:
        if week.team == unlucky:
            raise ValueError("this team's rows could not be composed")
        return compose(week)

    run(engine, tenant_id, failing)
    run(engine, tenant_id)

    with engine.connect() as connection:
        left = connection.execute(
            text("SELECT count(*) FROM sync_error WHERE tenant_id = :t AND collector = :c"),
            {"t": tenant_id, "c": COLLECTOR},
        ).scalar_one()
    assert left == 0
    assert unlucky in stored(engine, tenant_id)


def test_running_the_same_week_again_replaces_rather_than_duplicates(
    engine: Engine, tenant_id: UUID
) -> None:
    seed_bill(engine, tenant_id, split=False)
    run(engine, tenant_id)
    first = len(stored(engine, tenant_id))

    run(engine, tenant_id)

    with engine.connect() as connection:
        total = connection.execute(
            text("SELECT count(*) FROM team_digest WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar_one()
    assert total == first


def test_a_week_with_no_billed_spend_has_no_digest(engine: Engine, tenant_id: UUID) -> None:
    """Nothing collected is not a quiet week."""
    assert run(engine, tenant_id).items_written == 0
    assert stored(engine, tenant_id) == {}


def test_digests_are_weekly_in_the_schedule_with_a_reason_and_a_cost() -> None:
    (entry,) = [e for e in DEFAULT_SCHEDULE if e.collector == COLLECTOR]
    assert entry.cadence_seconds == WEEKLY
    assert "week" in entry.reason
    assert entry.est_cost_per_run == "0"
