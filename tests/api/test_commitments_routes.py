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


# --- TASK-P14-007: Meter's plan beside the provider's ------------------------------------------

PLANS = "/api/v1/commitments/plans"


@pytest.fixture
def planned(engine: Engine, tenant_id: UUID) -> UUID:
    """A month of steady m6i usage priced by P9's fake rates, the provider's advice, and a plan."""
    from finops_fakes.commitments import FakePurchaseRecommendations
    from finops_ingest.collectors.purchase_plan import PurchasePlanCollector
    from finops_ingest.collectors.purchase_recommendation import PurchaseRecommendationCollector
    from tests.ingest.collectors.test_purchase_plan import NOW, billed, priced, run

    priced(engine, tenant_id)
    billed(engine, tenant_id)
    advice = PurchaseRecommendationCollector(
        FakePurchaseRecommendations(tenant_id, at=NOW),
        services=("Amazon Elastic Compute Cloud - Compute", "Amazon Redshift"),
        clock=lambda: NOW,
    )
    run(engine, tenant_id, advice, "purchase_recommendation")
    run(engine, tenant_id, PurchasePlanCollector(clock=lambda: NOW))
    return tenant_id


def test_meters_plan_shows_beside_the_providers_with_the_difference_in_words(
    engine: Engine, settings: Settings, planned: UUID
) -> None:
    client, token = client_for(engine, everything(planned), settings)
    found = get(client, token, PLANS)
    data = found["data"]
    assert data["plan"]["status"] == "DRAFT"
    assert data["no_plan_reason"] is None
    assert {line["program"] for line in data["lines"]} == {"EC2Instance"}
    assert all(line["basis"] == "modelled" for line in data["lines"])
    assert {(one["kind"], one["program"]) for one in data["provider"]} == {
        ("savings_plan", "Compute"),
        ("savings_plan", "EC2Instance"),
        ("reservation", "Amazon Elastic Compute Cloud - Compute"),
        ("reservation", "Amazon Redshift"),
    }
    assert any("looked back 30 days" in sentence for sentence in data["difference"])
    assert any("applies the ladder" in sentence for sentence in data["difference"])
    assert found["meta"]["scope_coverage"]["unit"] == "payer"


def test_before_a_plan_is_drafted_the_route_says_so(
    engine: Engine, settings: Settings, tenant_id: UUID
) -> None:
    from finops_api.routes.commitments import NO_PLAN_YET

    client, token = client_for(engine, everything(tenant_id), settings)
    data = get(client, token, PLANS)["data"]
    assert (data["plan"], data["no_plan_reason"]) == (None, NO_PLAN_YET)
    assert (data["lines"], data["difference"]) == ([], [])


def test_a_narrowed_reader_cannot_read_the_plans(
    engine: Engine, settings: Settings, planned: UUID
) -> None:
    from tests.api.test_query_routes import auth

    client, token = client_for(engine, only(planned, ACCOUNT), settings)
    response = client.get(PLANS, headers=auth(token))
    assert response.status_code == 404
    assert "payer" in response.json()["detail"]


def test_the_plans_lines_export_as_a_file(
    engine: Engine, settings: Settings, planned: UUID
) -> None:
    from tests.api.test_query_routes import auth

    client, token = client_for(engine, everything(planned), settings)
    response = client.get(f"{PLANS}?format=csv", headers=auth(token))
    assert response.status_code == 200
    assert "EC2Instance" in response.text


# --- TASK-P14-008: approval, the purchase recorded, and verification ----------------------------


def plan_of(engine: Engine, tenant: UUID) -> UUID:
    from sqlalchemy import text

    with engine.connect() as connection:
        plan: UUID = connection.execute(
            text("SELECT plan_id FROM purchase_plan WHERE tenant_id = :t"), {"t": tenant}
        ).scalar_one()
        return plan


def step(client: Any, token: str, plan: UUID, action: str, note: str = "Within the ladder") -> Any:
    from tests.api.test_query_routes import auth

    return client.post(f"{PLANS}/{plan}/{action}", json={"note": note}, headers=auth(token))


def audited(engine: Engine, tenant: UUID) -> list[tuple[str, str]]:
    from sqlalchemy import text

    with engine.connect() as connection:
        return [
            (row.action, row.outcome)
            for row in connection.execute(
                text(
                    "SELECT action, outcome FROM audit_event WHERE tenant_id = :t "
                    "AND resource = 'purchase_plan' AND action LIKE 'plan.%' ORDER BY action"
                ),
                {"t": tenant},
            )
        ]


def test_a_person_approves_and_records_a_plan_bought_each_step_named(
    engine: Engine, settings: Settings, planned: UUID
) -> None:
    client, token = client_for(engine, as_owner(planned), settings)
    plan = plan_of(engine, planned)
    approved = step(client, token, plan, "approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["plan"]["status"] == "APPROVED"
    bought = step(client, token, plan, "bought", "Bought in the console by the payer")
    assert bought.status_code == 200, bought.text
    data = bought.json()["data"]
    assert data["plan"]["status"] == "BOUGHT"
    assert [(one["from_status"], one["to_status"]) for one in data["events"]] == [
        (None, "DRAFT"),
        ("DRAFT", "APPROVED"),
        ("APPROVED", "BOUGHT"),
    ]
    # Both steps carry the person who signed in, never the collector that drafted the plan.
    people = {one["principal"] for one in data["events"][1:]}
    assert len(people) == 1 and data["events"][0]["principal"] not in people
    assert data["events"][-1]["note"] == "Bought in the console by the payer"
    assert audited(engine, planned) == [("plan.approved", "ALLOWED"), ("plan.bought", "ALLOWED")]


def test_a_step_out_of_order_is_refused_and_says_why(
    engine: Engine, settings: Settings, planned: UUID
) -> None:
    client, token = client_for(engine, as_owner(planned), settings)
    response = step(client, token, plan_of(engine, planned), "bought")
    assert response.status_code == 409
    assert response.json()["detail"] == "This plan is draft, so it cannot be recorded as bought."


def test_a_withdrawn_plan_cannot_be_approved(
    engine: Engine, settings: Settings, planned: UUID
) -> None:
    client, token = client_for(engine, as_owner(planned), settings)
    plan = plan_of(engine, planned)
    withdrawn = step(client, token, plan, "withdraw", "Usage is moving to containers")
    assert withdrawn.json()["data"]["plan"]["status"] == "WITHDRAWN"
    assert step(client, token, plan, "approve").status_code == 409


def test_a_narrowed_person_cannot_approve_and_the_refusal_is_audited(
    engine: Engine, settings: Settings, planned: UUID
) -> None:
    from finops_core.domain.tenant import Scope

    narrowed = only(planned, ACCOUNT)
    scope = Scope(
        tenant_id=planned, is_global=False, accounts=narrowed.accounts, principal_id=OWNER
    )
    client, token = client_for(engine, scope, settings)
    assert step(client, token, plan_of(engine, planned), "approve").status_code == 403
    assert audited(engine, planned) == [("plan.approved", "DENIED")]


def test_an_unknown_plan_is_not_found_and_a_note_is_required(
    engine: Engine, settings: Settings, planned: UUID
) -> None:
    from finops_api.routes.commitments import NO_SUCH_PLAN

    client, token = client_for(engine, as_owner(planned), settings)
    missing = step(client, token, uuid4(), "approve")
    assert (missing.status_code, missing.json()["detail"]) == (404, NO_SUCH_PLAN)
    assert step(client, token, plan_of(engine, planned), "approve", note="").status_code == 422


def hold(engine: Engine, tenant: UUID, commitment: str, hourly: Decimal, family: str) -> None:
    """A Savings Plan the inventory holds, bought a minute after now."""
    from datetime import UTC, datetime

    from sqlalchemy import text

    from tests.ingest.collectors.test_purchase_plan import REGION

    start = datetime.now(UTC) + timedelta(minutes=1)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO commitment_inventory (tenant_id, ingest_run_id, kind, commitment_id, "
                "program, account_id, region_id, applies_to, quantity, hourly_commitment, "
                "term_months, payment_option, upfront_amount, recurring_hourly, currency, "
                "starts_at, ends_at, state, as_of, collected_at) VALUES (:t, :run, "
                "'savings_plan', :id, 'EC2Instance', 'fake-platform-a', :region, :family, NULL, "
                ":hourly, 12, 'No Upfront', 0, :hourly, 'USD', :start, :end, 'active', :start, "
                ":start)"
            ),
            {
                "t": tenant,
                "run": uuid4(),
                "id": commitment,
                "region": REGION,
                "family": family,
                "hourly": hourly,
                "start": start,
                "end": start + timedelta(days=365),
            },
        )


def this_months_lines(engine: Engine, plan: UUID) -> list[Any]:
    from sqlalchemy import text

    with engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    "SELECT l.line_no, l.hourly_commitment, l.matched_commitment_id "
                    "FROM purchase_plan_line l JOIN purchase_plan p ON p.plan_id = l.plan_id "
                    "WHERE l.plan_id = :plan AND l.tranche_month = p.plan_month"
                ),
                {"plan": plan},
            )
        )


def settle(engine: Engine, tenant: UUID) -> None:
    from finops_ingest.collectors.purchase_plan import PurchasePlanCollector
    from tests.ingest.collectors.test_purchase_plan import NOW, run

    run(engine, tenant, PurchasePlanCollector(clock=lambda: NOW))


def test_a_bought_plan_is_verified_once_the_inventory_holds_its_purchase(
    engine: Engine, settings: Settings, planned: UUID
) -> None:
    from finops_ingest.collectors.purchase_plan import PRINCIPAL

    client, token = client_for(engine, as_owner(planned), settings)
    plan = plan_of(engine, planned)
    step(client, token, plan, "approve")
    step(client, token, plan, "bought")
    for line in this_months_lines(engine, plan):
        hold(engine, planned, f"sp-bought-{line.line_no}", line.hourly_commitment, "m6i")
    settle(engine, planned)
    data = get(client, token, PLANS)["data"]
    assert data["plan"]["status"] == "VERIFIED"
    steps = [(one["from_status"], one["to_status"], one["principal"]) for one in data["events"]]
    assert ("BOUGHT", "VERIFIED", PRINCIPAL) in steps
    assert all(line.matched_commitment_id for line in this_months_lines(engine, plan))


def test_a_bought_line_nothing_matches_stays_bought_and_unseen(
    engine: Engine, settings: Settings, planned: UUID
) -> None:
    client, token = client_for(engine, as_owner(planned), settings)
    plan = plan_of(engine, planned)
    step(client, token, plan, "approve")
    step(client, token, plan, "bought")
    # Bought in the wrong family, so it is not this plan's purchase.
    for line in this_months_lines(engine, plan):
        hold(engine, planned, f"sp-other-{line.line_no}", line.hourly_commitment, "c6i")
    settle(engine, planned)
    assert get(client, token, PLANS)["data"]["plan"]["status"] == "BOUGHT"
    assert not any(line.matched_commitment_id for line in this_months_lines(engine, plan))
