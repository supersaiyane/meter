"""P14's exit criteria, read through the API over the seeded demo. TASK-P14-010, spec section 13.

The local stack is seeded by `scripts/demo/seed_demo.py`, so the demo is what a person running it
meets. Each criterion is read here through the commitment endpoints a person's screen reads, as the
whole estate's reader, rather than from the tables the collectors wrote.

Criterion 1, that the Cost Explorer commitment reads are made as the payer and the Terraform grants
them, is held by the Terraform itself in
`tests/contract/test_no_commitment_purchases.py::test_the_payer_is_granted_exactly_the_commitment_reads`
and by the bindings in `tests/ingest/test_aws_bindings.py`. That a month with no List Cost says so
is held by `tests/api/test_commitments_routes.py` and the screen's own tests; the demo's bill
carries a List Cost on its usage lines, so here its rate is measured.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_core.domain.tenant import Scope
from finops_fakes.commitments import HOLDINGS
from finops_ingest.collectors.purchase_plan import PRINCIPAL, PurchasePlanCollector
from tests.api.test_query_routes import auth, client_for
from tests.api.test_waste_routes import everything, get, only
from tests.ingest.collectors.test_purchase_plan import run
from tests.scripts.test_seed_demo import DEMO_TENANT, _now, seed_demo

pytestmark = pytest.mark.integration

INVENTORY = "/api/v1/commitments/inventory"
CALENDAR = "/api/v1/commitments/calendar"
RATE = "/api/v1/commitments/savings-rate"
PLANS = "/api/v1/commitments/plans"
OWNER = "owner@example.local"


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """The seed bills months into partitions, so this module gives them back. ISS-268."""


@pytest.fixture
def demo(engine: Engine, settings: Settings) -> Iterator[Callable[[str], Any]]:
    seed_demo.seed(engine, settings, _now())
    client, token = client_for(engine, everything(DEMO_TENANT), settings)
    try:
        yield lambda path: get(client, token, path)
    finally:
        seed_demo.remove(engine)


def test_2_every_commitment_lands_with_its_term_and_end_and_a_refusal_is_its_cause(
    engine: Engine, demo: Callable[[str], Any]
) -> None:
    held = {one["commitment_id"]: one for one in demo(INVENTORY)["data"]["commitments"]}
    assert {holding.commitment_id for holding in HOLDINGS} <= set(held)
    for one in held.values():
        assert one["term_months"] > 0
        assert one["ends_at"] > one["starts_at"]
    with engine.connect() as connection:
        refused = set(
            connection.execute(
                text(
                    "SELECT error_type FROM ingest_run WHERE tenant_id = :t "
                    "AND collector = 'commitment_inventory' AND status = 'FAILED'"
                ),
                {"t": DEMO_TENANT},
            ).scalars()
        )
    assert refused == {"AccessDenied"}, "the refusing account reads as its cause, never as none"


def test_3_the_savings_rate_is_measured_from_the_bill(demo: Callable[[str], Any]) -> None:
    months = demo(f"{RATE}?months=12")["data"]["months"]
    assert months
    latest = months[-1]
    assert latest["rate_basis"] == "measured"
    assert latest["rate"] is not None
    assert Decimal(0) < Decimal(latest["rate"]) < Decimal(1)


def test_4_the_calendar_flags_the_month_whose_share_passes_the_ladder(
    demo: Callable[[str], Any],
) -> None:
    calendar = demo(CALENDAR)["data"]
    (ending,) = [
        month for month in calendar["months"] if "sp-fake-compute-0001" in month["commitments"]
    ]
    assert ending["over_limit"] is True
    assert Decimal(ending["share"]) > Decimal(calendar["ladder_limit"])


def test_5_meters_plan_and_aws_show_side_by_side_and_a_family_with_no_rate_is_unpriced(
    demo: Callable[[str], Any],
) -> None:
    data = demo(PLANS)["data"]
    assert data["plan"]["status"] == "DRAFT"
    assert data["lines"], "the demo's plan buys something"
    assert {line["basis"] for line in data["lines"]} == {"modelled"}
    assert {one["program"] for one in data["provider"] if one["kind"] == "savings_plan"} == {
        "Compute",
        "EC2Instance",
    }
    assert len(data["difference"]) >= 3
    unpriced = {one["instance_family"]: one for one in data["plan"]["unpriced"]}
    # The GPU instances' usage type is one the fake catalog does not price.
    assert {"g5", "p4d"} <= set(unpriced)
    assert all(Decimal(one["steady_hourly"]) > 0 for one in unpriced.values())


def hold_each_line(engine: Engine, lines: list[dict[str, Any]], plan_month: str) -> None:
    """A Savings Plan in the inventory for each line bought this month, a minute after now."""
    start = datetime.now(UTC) + timedelta(minutes=1)
    with engine.begin() as connection:
        for line in lines:
            if line["tranche_month"] != plan_month:
                continue
            connection.execute(
                text(
                    "INSERT INTO commitment_inventory (tenant_id, ingest_run_id, kind, "
                    "commitment_id, program, account_id, region_id, applies_to, quantity, "
                    "hourly_commitment, term_months, payment_option, upfront_amount, "
                    "recurring_hourly, currency, starts_at, ends_at, state, as_of, collected_at) "
                    "VALUES (:t, :run, 'savings_plan', :id, :program, 'fake-platform-a', "
                    ":region, :family, NULL, :hourly, 12, 'No Upfront', 0, :hourly, 'USD', "
                    ":start, :end, 'active', :start, :start)"
                ),
                {
                    "t": DEMO_TENANT,
                    "run": uuid4(),
                    "id": f"sp-exit-{line['line_no']}",
                    "program": line["program"],
                    "region": line["region_id"],
                    "family": line["instance_family"],
                    "hourly": line["hourly_commitment"],
                    "start": start,
                    "end": start + timedelta(days=365),
                },
            )


def test_6_a_plan_approved_bought_and_matched_is_verified_each_step_named(
    engine: Engine, settings: Settings, demo: Callable[[str], Any]
) -> None:
    plan = demo(PLANS)["data"]
    plan_id = plan["plan"]["plan_id"]
    note = {"note": "Within the ladder"}

    narrowed = only(DEMO_TENANT, "fake-platform-a")
    scope = Scope(
        tenant_id=DEMO_TENANT, is_global=False, accounts=narrowed.accounts, principal_id=OWNER
    )
    client, token = client_for(engine, scope, settings)
    refused = client.post(f"{PLANS}/{plan_id}/approve", json=note, headers=auth(token))
    assert refused.status_code == 403, "a narrowed principal cannot approve"

    owner = Scope(tenant_id=DEMO_TENANT, is_global=True, accounts=frozenset(), principal_id=OWNER)
    client, token = client_for(engine, owner, settings)
    for step in ("approve", "bought"):
        response = client.post(f"{PLANS}/{plan_id}/{step}", json=note, headers=auth(token))
        assert response.status_code == 200, response.text

    hold_each_line(engine, plan["lines"], plan["plan"]["plan_month"])
    run(engine, DEMO_TENANT, PurchasePlanCollector(clock=lambda: datetime.now(UTC)))

    after = demo(PLANS)["data"]
    assert after["plan"]["status"] == "VERIFIED"
    steps = {(one["from_status"], one["to_status"]): one["principal"] for one in after["events"]}
    assert steps[("BOUGHT", "VERIFIED")] == PRINCIPAL
    person = steps[("DRAFT", "APPROVED")]
    assert person != PRINCIPAL and steps[("APPROVED", "BOUGHT")] == person
