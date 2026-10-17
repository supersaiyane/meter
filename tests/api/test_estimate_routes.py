"""The estimate routes, read through the API as a person reads them. P16, TASK-P16-008.

Spec section 8. The plans newest first, each with its estimate, comment and pull request's state;
one plan's lines, the unpriced first, with what each left unknown and what the bill said; and the
accuracy by type from the judged alone. All of it is the organization's, so a reader narrowed to
an account is answered 404 with the reason, never with an empty list.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_api.routes.estimates import NEEDS_THE_ORGANIZATION, NO_SUCH_PLAN
from finops_core.config import Settings
from tests.api.test_query_routes import auth, client_for
from tests.api.test_waste_routes import everything, get, only
from tests.ingest.collectors.test_estimate_comparison import (
    ADDRESS,
    MERGED,
    WINDOW,
    a_comparison,
    a_plan,
    pull_request_is,
)

pytestmark = pytest.mark.integration

PLANS = "/api/v1/estimates"
ACCURACY = "/api/v1/estimates/accuracy"
UNPRICED = "aws_nat_gateway.out"
PART = {
    "side": "after",
    "what": "m7g.large, Linux, shared tenancy",
    "quantity": "730",
    "unit": "Hrs",
    "unit_price": "0.1000000000",
    "monthly": "73.000000",
    "sku_price_id": "sku-1",
    "version": "20261001",
}


def written(connection: Any, plan_id: UUID) -> None:
    """The estimate's totals and its comment, as the two collectors leave them."""
    connection.execute(
        text(
            "UPDATE plan_estimate SET monthly_after = 73, monthly_change = 73, priced_lines = 1, "
            "unpriced_lines = 1, comment_status = 'WRITTEN', comment_id = '1', "
            "comment_url = 'https://code.example/acme/infra/pull/7#issuecomment-1', "
            "commented_at = priced_at WHERE plan_id = :p"
        ),
        {"p": plan_id},
    )
    connection.execute(
        text(
            "UPDATE plan_estimate_line SET components = CAST(:parts AS jsonb) "
            "WHERE plan_id = :p AND address = :a"
        ),
        {"p": plan_id, "a": ADDRESS, "parts": json.dumps([PART])},
    )
    connection.execute(
        text(
            "UPDATE planned_change SET unknown = ARRAY['ami'] WHERE plan_id = :p AND address = :a"
        ),
        {"p": plan_id, "a": ADDRESS},
    )


@pytest.fixture
def plans(engine: Engine, tenant_id: UUID) -> tuple[UUID, UUID]:
    """An older plan for pull request 7, priced and commented, and a newer one for 8."""
    with engine.begin() as connection:
        older = a_plan(
            connection,
            tenant_id,
            lines=((ADDRESS, ("create",), "73"), (UNPRICED, ("create",), None)),
        )
        written(connection, older)
        a_comparison(
            connection,
            tenant_id,
            older,
            verdict="WITHIN",
            reason=None,
            provider="i-0123456789abcdef0",
            seen=MERGED + timedelta(hours=3),
            start=WINDOW[0],
            end=WINDOW[1],
            list=Decimal("80.3"),
            effective=Decimal("58.4"),
            variance=Decimal("10.0"),
        )
        pull_request_is(connection, tenant_id, "MERGED")
        newer = a_plan(connection, tenant_id, pull_request=8, received=MERGED + timedelta(days=1))
    return older, newer


def test_the_plans_come_newest_first_with_their_estimate_comment_and_state(
    engine: Engine, settings: Settings, tenant_id: UUID, plans: tuple[UUID, UUID]
) -> None:
    older, newer = plans
    client, token = client_for(engine, everything(tenant_id), settings)
    found = get(client, token, PLANS)
    listed = found["data"]["plans"]
    assert [one["plan_id"] for one in listed] == [str(newer), str(older)]
    assert found["data"]["more"] is False
    first = listed[1]
    assert (first["pull_request"], first["folder"], first["status"]) == (7, "storage", "PRICED")
    assert (Decimal(first["monthly_change"]), first["priced_lines"], first["unpriced_lines"]) == (
        Decimal(73),
        1,
        1,
    )
    assert (first["comment_status"], first["pull_request_state"], first["basis"]) == (
        "WRITTEN",
        "MERGED",
        "modelled",
    )
    assert listed[0]["pull_request_state"] is None, "pull request 8 has not been read yet"
    assert found["meta"]["as_of"] is not None and found["meta"]["collected_at"] is not None

    fewer = get(client, token, f"{PLANS}?limit=1")["data"]
    assert ([one["plan_id"] for one in fewer["plans"]], fewer["more"]) == ([str(newer)], True)


def test_one_plan_opens_on_its_unpriced_change_and_carries_what_the_bill_said(
    engine: Engine, settings: Settings, tenant_id: UUID, plans: tuple[UUID, UUID]
) -> None:
    older, _ = plans
    client, token = client_for(engine, everything(tenant_id), settings)
    found = get(client, token, f"{PLANS}/{older}")["data"]
    unpriced, priced = found["lines"]
    assert (unpriced["address"], unpriced["monthly_after"], unpriced["comparison"]) == (
        UNPRICED,
        None,
        None,
    )
    assert unpriced["reason"]
    assert (priced["address"], priced["unknown"], priced["components"][0]["sku_price_id"]) == (
        ADDRESS,
        ["ami"],
        "sku-1",
    )
    comparison = priced["comparison"]
    assert (comparison["verdict"], comparison["basis"]) == ("WITHIN", "measured")
    assert Decimal(comparison["list_monthly"]) == Decimal("80.3")
    assert "730 hours" in found["assumptions"]


def test_a_plan_nobody_received_is_404_with_the_reason(
    engine: Engine, settings: Settings, tenant_id: UUID
) -> None:
    client, token = client_for(engine, everything(tenant_id), settings)
    missing = client.get(f"{PLANS}/{uuid4()}", headers=auth(token))
    assert (missing.status_code, missing.json()["detail"]) == (404, NO_SUCH_PLAN)


def test_accuracy_is_by_type_from_the_judged_alone(
    engine: Engine, settings: Settings, tenant_id: UUID
) -> None:
    judged = {
        "provider": "i-0123456789abcdef0",
        "seen": MERGED,
        "start": WINDOW[0],
        "end": WINDOW[1],
        "list": Decimal(80),
        "effective": Decimal(60),
        "reason": None,
    }
    waiting = {"verdict": "PENDING", "reason": None, "seen": MERGED, "start": WINDOW[0]}
    compare: dict[str, dict[str, Any]] = {
        "aws_instance.n0": {**judged, "verdict": "WITHIN", "variance": Decimal(2)},
        "aws_instance.n1": {**judged, "verdict": "ABOVE", "variance": Decimal(20)},
        "aws_instance.n2": {**waiting, "end": WINDOW[1]},
        "aws_instance.n3": {},
    }
    with engine.begin() as connection:
        plan_id = a_plan(
            connection, tenant_id, lines=tuple((one, ("create",), "73") for one in compare)
        )
        for address, changed in compare.items():
            a_comparison(connection, tenant_id, plan_id, address=address, **changed)

    client, token = client_for(engine, everything(tenant_id), settings)
    found = get(client, token, ACCURACY)
    data = found["data"]
    assert [
        (one["resource_type"], one["compared"], one["within"], Decimal(one["median_error_percent"]))
        for one in data["types"]
    ] == [("aws_instance", 2, 1, Decimal(11)), ("all", 2, 1, Decimal(11))]
    assert (data["pending"], data["not_compared"], data["window_days"]) == (1, 1, 30)
    assert Decimal(data["within_percent"]) == Decimal(10)
    assert found["meta"]["as_of"] is not None


def test_a_reader_narrowed_to_an_account_is_told_estimates_are_the_organizations(
    engine: Engine, settings: Settings, tenant_id: UUID, plans: tuple[UUID, UUID]
) -> None:
    older, _ = plans
    client, token = client_for(engine, only(tenant_id, "111111111111"), settings)
    for path in (PLANS, ACCURACY, f"{PLANS}/{older}"):
        response = client.get(path, headers=auth(token))
        assert (response.status_code, response.json()["detail"]) == (
            404,
            NEEDS_THE_ORGANIZATION,
        ), path


@pytest.mark.usefixtures("plans")
def test_the_plans_export_as_the_screen_reads_them(
    engine: Engine, settings: Settings, tenant_id: UUID
) -> None:
    client, token = client_for(engine, everything(tenant_id), settings)
    response = client.get(f"{PLANS}?format=csv", headers=auth(token))
    assert response.status_code == 200
    assert "acme/infra" in response.text
