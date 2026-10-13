"""The commitment routes, read through the API as a person reads them. P14, FEAT-086 to 090.

TASK-P14-004 first: the effective savings rate by billing month, measured from the bill. The fake
estate's bill is collected for two months, one of them with every List Cost removed, and read by a
reader of the whole estate and by one narrowed to an account.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from functools import partial
from operator import add
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine

from finops_core.config import Settings
from finops_core.domain.cost import CostRecord
from finops_fakes.cur import CLOSED_PERIOD, ESTATE, FakeCostExport
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext
from finops_query.savings_rate import NO_LIST_COST
from tests.api.test_query_routes import client_for
from tests.api.test_waste_routes import everything, get, only

pytestmark = pytest.mark.integration

RATE = "/api/v1/commitments/savings-rate"
EARLIER = CLOSED_PERIOD.replace(month=CLOSED_PERIOD.month - 1)
ACCOUNT = "fake-platform-a"


def month(period: Any) -> tuple[CostRecord, ...]:
    return tuple(row for row in ESTATE if row.billing_period_start == period)


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


@pytest.fixture
def billed(engine: Engine, tenant_id: UUID) -> UUID:
    unlisted = tuple(replace(row, list_cost=None) for row in month(EARLIER))
    for rows in (unlisted, month(CLOSED_PERIOD)):
        last = max(row.charge_period_start for row in rows)
        work = WorkUnit(
            tenant_id=tenant_id,
            collector="cost_focus",
            window_start=last,
            window_end=last + timedelta(days=1),
        )
        collector = CostFocusCollector(
            FakeCostExport(rows=rows), clock=partial(add, last, timedelta(days=2))
        )
        with engine.begin() as connection:
            ensure_partition(connection, "cost_focus_daily", rows[0].billing_period_start)
            collector(CollectorContext(unit=work, connection=connection, run_id=uuid4()))
    return tenant_id


def expected(rows: tuple[CostRecord, ...]) -> Decimal:
    listed = [row for row in rows if row.list_cost is not None and row.charge_category == "Usage"]
    effective = sum((row.effective_cost for row in listed), Decimal(0))
    return (
        Decimal(1) - effective / sum((row.list_cost or 0 for row in listed), Decimal(0))
    ).quantize(Decimal("0.0001"))


def read(engine: Engine, settings: Settings, tenant: UUID, account: str = "") -> Any:
    scope = only(tenant, account) if account else everything(tenant)
    client, token = client_for(engine, scope, settings)
    return get(client, token, RATE)


def test_the_rate_is_measured_from_the_bills_own_sums(
    engine: Engine, settings: Settings, billed: UUID
) -> None:
    found = read(engine, settings, billed)
    by_period = {one["period"]: one for one in found["data"]["months"]}
    closed = by_period[CLOSED_PERIOD.isoformat()]
    assert Decimal(closed["rate"]) == expected(month(CLOSED_PERIOD))
    assert (closed["rate_basis"], closed["reason"], closed["lines_without_list_cost"]) == (
        "measured",
        None,
        0,
    )
    assert found["meta"]["as_of"] is not None and found["meta"]["collected_at"] is not None


def test_a_month_whose_lines_carry_no_list_cost_has_no_rate_never_nought(
    engine: Engine, settings: Settings, billed: UUID
) -> None:
    by_period = {one["period"]: one for one in read(engine, settings, billed)["data"]["months"]}
    earlier = by_period[EARLIER.isoformat()]
    assert (earlier["rate"], earlier["reason"]) == (None, NO_LIST_COST)
    assert earlier["lines"] == earlier["lines_without_list_cost"] > 0
    assert Decimal(earlier["effective_cost_without_list_cost"]) > 0


def test_a_narrowed_reader_reads_the_rate_of_their_own_accounts(
    engine: Engine, settings: Settings, billed: UUID
) -> None:
    found = read(engine, settings, billed, account=ACCOUNT)
    by_period = {one["period"]: one for one in found["data"]["months"]}
    own = tuple(row for row in month(CLOSED_PERIOD) if row.sub_account_id == ACCOUNT)
    assert Decimal(by_period[CLOSED_PERIOD.isoformat()]["rate"]) == expected(own)


def test_a_tenant_with_no_bill_has_no_months_rather_than_rates_of_nought(
    engine: Engine, settings: Settings, tenant_id: UUID
) -> None:
    assert read(engine, settings, tenant_id)["data"]["months"] == []


# --- TASK-P14-005: the inventory, the calendar and the policy ------------------------------

INVENTORY = "/api/v1/commitments/inventory"
CALENDAR = "/api/v1/commitments/calendar"
POLICY = "/api/v1/commitments/policy"
OWNER = "owner@example.local"


@pytest.fixture
def held(engine: Engine, tenant_id: UUID) -> UUID:
    from datetime import UTC, datetime

    from finops_core.domain.account import AccountKey, Provider
    from finops_fakes import fixtures
    from finops_fakes.commitments import FakeCommitmentHoldings
    from finops_ingest.collectors.commitment_inventory import CommitmentInventoryCollector
    from finops_ingest.commitment_policy import install_default_policy

    now = datetime.now(UTC)
    collector = CommitmentInventoryCollector(
        FakeCommitmentHoldings(at=now), first_region=fixtures.REGION
    )
    for account in ("fake-platform-a", "fake-product-a"):
        work = WorkUnit(
            tenant_id=tenant_id,
            collector="commitment_inventory",
            window_start=now - timedelta(days=1),
            window_end=now,
            account=AccountKey(provider=Provider.AWS, account_id=account),
            region=fixtures.REGION,
        )
        with engine.begin() as connection:
            collector(CollectorContext(unit=work, connection=connection, run_id=uuid4()))
    with engine.begin() as connection:
        install_default_policy(connection, tenant_id, updated_by="test")
    return tenant_id


def as_owner(tenant: UUID) -> Any:
    from finops_core.domain.tenant import Scope

    return Scope(tenant_id=tenant, is_global=True, accounts=frozenset(), principal_id=OWNER)


def test_the_inventory_lists_every_commitment_soonest_ending_first_and_names_the_unreadable(
    engine: Engine, settings: Settings, held: UUID
) -> None:
    client, token = client_for(engine, everything(held), settings)
    found = get(client, token, INVENTORY)
    ids = [one["commitment_id"] for one in found["data"]["commitments"]]
    assert ids[0] == "sp-fake-compute-0001", "the plan ending in three weeks is first"
    assert {"ri-fake-ec2-0001", "ri-fake-rds-0001", "ri-fake-cache-0001"} <= set(ids)
    assert found["data"]["unreadable"] == ["DynamoDB"]
    assert found["meta"]["scope_coverage"]["unit"] == "payer"


def test_the_calendar_flags_the_month_the_plan_ends_in(
    engine: Engine, settings: Settings, held: UUID
) -> None:
    client, token = client_for(engine, everything(held), settings)
    data = get(client, token, CALENDAR)["data"]
    assert len(data["months"]) == 12
    (ending,) = [one for one in data["months"] if "sp-fake-compute-0001" in one["commitments"]]
    assert ending["over_limit"] is True and ending["basis"] == "measured"
    assert Decimal(data["ladder_limit"]) == Decimal("0.0833")
    assert data["total_basis"] == "modelled", "reservations are held, so the total is modelled"


def test_a_narrowed_reader_is_told_commitments_need_the_payer(
    engine: Engine, settings: Settings, held: UUID
) -> None:
    from tests.api.test_query_routes import auth

    client, token = client_for(engine, only(held, ACCOUNT), settings)
    for path in (INVENTORY, CALENDAR, POLICY):
        response = client.get(path, headers=auth(token))
        assert response.status_code == 404, path
        assert "payer" in response.json()["detail"], path


def test_the_policy_starts_as_the_cautious_default(
    engine: Engine, settings: Settings, held: UUID
) -> None:
    client, token = client_for(engine, everything(held), settings)
    policy = get(client, token, POLICY)["data"]
    assert (policy["term_years"], policy["payment_option"], Decimal(policy["target_coverage"])) == (
        1,
        "No Upfront",
        Decimal("0.800"),
    )


def test_a_person_with_the_whole_organization_changes_the_policy_with_a_reason_audited(
    engine: Engine, settings: Settings, held: UUID
) -> None:
    from sqlalchemy import text

    from tests.api.test_query_routes import auth

    client, token = client_for(engine, as_owner(held), settings)
    change = {
        "target_coverage": "0.9",
        "term_years": 3,
        "payment_option": "Partial Upfront",
        "ladder_limit": "0.1",
        "reason": "Usage has been steady for two years",
    }
    response = client.put(POLICY, json=change, headers=auth(token))
    assert response.status_code == 200, response.text
    policy = response.json()["data"]
    assert (policy["term_years"], policy["is_default"], policy["reason"]) == (
        3,
        False,
        change["reason"],
    )
    with engine.connect() as connection:
        audited = connection.execute(
            text(
                "SELECT outcome FROM audit_event WHERE tenant_id = :t "
                "AND resource = 'commitment_policy' AND action = 'change'"
            ),
            {"t": held},
        ).scalars()
        assert list(audited) == ["ALLOWED"]
    # The person who made the change is on the policy, so a reader can ask them why.
    assert policy["updated_by"]


def test_a_narrowed_person_cannot_change_the_policy_and_the_refusal_is_audited(
    engine: Engine, settings: Settings, held: UUID
) -> None:
    from sqlalchemy import text

    from finops_core.domain.tenant import Scope
    from tests.api.test_query_routes import auth

    narrowed = only(held, ACCOUNT)
    scope = Scope(tenant_id=held, is_global=False, accounts=narrowed.accounts, principal_id=OWNER)
    client, token = client_for(engine, scope, settings)
    change = {
        "target_coverage": "0.9",
        "term_years": 1,
        "payment_option": "No Upfront",
        "ladder_limit": "0.1",
        "reason": "Trying from a narrowed scope",
    }
    assert client.put(POLICY, json=change, headers=auth(token)).status_code == 403
    with engine.connect() as connection:
        audited = connection.execute(
            text(
                "SELECT outcome FROM audit_event WHERE tenant_id = :t "
                "AND resource = 'commitment_policy' AND action = 'change'"
            ),
            {"t": held},
        ).scalars()
        assert list(audited) == ["DENIED"]


def test_a_policy_no_plan_could_follow_is_refused_before_it_is_stored(
    engine: Engine, settings: Settings, held: UUID
) -> None:
    from tests.api.test_query_routes import auth

    client, token = client_for(engine, as_owner(held), settings)
    bad = {
        "target_coverage": "0.9",
        "term_years": 2,
        "payment_option": "No Upfront",
        "ladder_limit": "0.1",
        "reason": "Two years is not a term AWS sells",
    }
    assert client.put(POLICY, json=bad, headers=auth(token)).status_code == 422
