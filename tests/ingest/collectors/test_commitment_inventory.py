"""What each account holds, written per account and Region. TASK-P14-002, FEAT-086.

The collector reads a unit's reservations, and its account's Savings Plans only in the first
collection Region's unit, so a plan is never counted once per Region. A rerun removes what the
source no longer lists from the scope it read and from nothing else, and an account that refuses
keeps its last good rows rather than reading as holding nothing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.commitments import RESERVATION, SAVINGS_PLAN, HeldCommitment
from finops_core.errors import AccessDenied, SchemaDrift
from finops_fakes import fixtures
from finops_fakes.commitments import FakeCommitmentHoldings
from finops_ingest.collectors.commitment_inventory import CommitmentInventoryCollector
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext, CollectorOutcome

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 13, 6, tzinfo=UTC)
OTHER_REGION = "us-fake-2"


@dataclass
class Spy:
    """The fake holdings, recording what was asked and dropping what a test names."""

    asked: list[str] = field(default_factory=list)
    without: frozenset[str] = frozenset()
    refuse: bool = False

    def savings_plans(self, account: AccountKey) -> Iterable[HeldCommitment]:
        self.asked.append("savings_plans")
        self._refuse(account)
        found = FakeCommitmentHoldings(at=NOW).savings_plans(account)
        return [one for one in found if one.commitment_id not in self.without]

    def reservations(self, account: AccountKey, region: str) -> Iterable[HeldCommitment]:
        self.asked.append(f"reservations:{region}")
        self._refuse(account)
        found = FakeCommitmentHoldings(at=NOW).reservations(account, region)
        return [one for one in found if one.commitment_id not in self.without]

    def _refuse(self, account: AccountKey) -> None:
        if self.refuse:
            raise AccessDenied(scope_key=str(account), collector="commitment_inventory")


def unit(tenant: UUID, account: str = "fake-platform-a", region: str = fixtures.REGION) -> WorkUnit:
    return WorkUnit(
        tenant_id=tenant,
        collector="commitment_inventory",
        window_start=NOW - timedelta(days=1),
        window_end=NOW,
        account=AccountKey(provider=Provider.AWS, account_id=account),
        region=region,
    )


def run(engine: Engine, spy: Spy, work: WorkUnit) -> CollectorOutcome:
    collector = CommitmentInventoryCollector(spy, first_region=fixtures.REGION)
    with engine.begin() as connection:
        return collector(CollectorContext(unit=work, connection=connection, run_id=uuid4()))


def held(engine: Engine, tenant: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT commitment_id, kind, account_id, region_id, quantity, hourly_commitment, "
                "term_months, ends_at FROM commitment_inventory WHERE tenant_id = :t"
            ),
            {"t": tenant},
        ).mappings()
        return {row["commitment_id"]: dict(row) for row in rows}


def test_the_first_regions_unit_reads_reservations_and_savings_plans(
    engine: Engine, tenant_id: UUID
) -> None:
    spy = Spy()
    outcome = run(engine, spy, unit(tenant_id))
    assert spy.asked == [f"reservations:{fixtures.REGION}", "savings_plans"]
    found = held(engine, tenant_id)
    assert set(found) == {"sp-fake-compute-0001", "sp-fake-ec2-0001", "ri-fake-ec2-0001"}
    assert outcome.items_written == 3
    reservation = found["ri-fake-ec2-0001"]
    assert (reservation["kind"], reservation["quantity"], reservation["hourly_commitment"]) == (
        RESERVATION,
        4,
        None,
    )
    plan = found["sp-fake-compute-0001"]
    assert (plan["kind"], plan["region_id"], plan["term_months"]) == (SAVINGS_PLAN, None, 12)


def test_another_regions_unit_never_reads_the_savings_plans_again(
    engine: Engine, tenant_id: UUID
) -> None:
    spy = Spy()
    run(engine, spy, unit(tenant_id, region=OTHER_REGION))
    assert spy.asked == [f"reservations:{OTHER_REGION}"]
    assert held(engine, tenant_id) == {}


def test_a_rerun_removes_what_the_source_no_longer_lists_and_nothing_else(
    engine: Engine, tenant_id: UUID
) -> None:
    run(engine, Spy(), unit(tenant_id))
    run(engine, Spy(), unit(tenant_id, account="fake-product-a"))
    outcome = run(engine, Spy(without=frozenset({"ri-fake-ec2-0001"})), unit(tenant_id))
    found = held(engine, tenant_id)
    assert "ri-fake-ec2-0001" not in found
    # Another account's reservation, read by another unit, is untouched.
    assert "ri-fake-rds-0001" in found
    assert outcome.items_removed == 1


def test_an_account_that_refuses_keeps_its_last_good_rows(engine: Engine, tenant_id: UUID) -> None:
    run(engine, Spy(), unit(tenant_id))
    before = held(engine, tenant_id)
    with pytest.raises(AccessDenied):
        run(engine, Spy(refuse=True), unit(tenant_id))
    assert held(engine, tenant_id) == before


def test_a_unit_without_an_account_is_drift(engine: Engine, tenant_id: UUID) -> None:
    work = WorkUnit(
        tenant_id=tenant_id,
        collector="commitment_inventory",
        window_start=NOW - timedelta(days=1),
        window_end=NOW,
    )
    with pytest.raises(SchemaDrift, match="without an account"):
        run(engine, Spy(), work)


def test_the_fake_estate_refuses_the_account_it_refuses_everywhere() -> None:
    fake = FakeCommitmentHoldings(at=NOW)
    with pytest.raises(AccessDenied):
        list(fake.reservations(fixtures.DENIED_ACCOUNT_KEY, fixtures.REGION))
    platform_b = AccountKey(provider=Provider.AWS, account_id="fake-platform-b")
    retired = [one for one in fake.savings_plans(platform_b) if one.state == "retired"]
    assert retired and retired[0].ends_at < NOW
