"""The savings ledger's routes: teams by the savings they hold, and their credits. TASK-P11-008.

P11 spec sections 5.6 and 8, read through the routes as every route test reads. Four credits are
planted as the ledger collector leaves them: two for platform in one account, one held two months
and one that regressed in its second; one for payments in another account; and one no source named
a team for, verified with no month closed yet. Teams are ranked and people never are, a narrowed
reader sees only its account's credits, and both routes export.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from tests.api.test_query_routes import auth, client_for
from tests.api.test_waste_routes import everything, get, only
from tests.ingest.collectors.test_savings_ledger import ACCOUNT, finished

pytestmark = pytest.mark.integration

LEDGER = "/api/v1/savings/ledger"
CREDITS = f"{LEDGER}/credits"
OTHER = "999988887777"
CLOSED = datetime(2026, 12, 2, 6, 0, tzinfo=UTC)
OCTOBER, NOVEMBER = date(2026, 10, 1), date(2026, 11, 1)

INSERT_CREDIT = text(
    "INSERT INTO savings_credit (credit_id, tenant_id, ingest_run_id, sub_account_id, "
    "recommendation_id, realized_id, owner, team, closed_by, verified_monthly_saving, "
    "verified_on, as_of, collected_at) VALUES (:id, :t, :run, :account, :recommendation, "
    ":realized, 'platform@example.local', :team, 'alice', 40, '2026-09-20', :at, :at)"
)
INSERT_MONTH = text(
    "INSERT INTO savings_credit_month (month_pk, tenant_id, ingest_run_id, sub_account_id, "
    "credit_id, month, state, cost, saving, as_of, collected_at) VALUES (:pk, :t, :run, "
    ":account, :credit, :month, :state, :cost, :saving, :at, :at)"
)

Month = tuple[date, str, Decimal | None, Decimal | None]


def credited(
    engine: Engine,
    tenant: UUID,
    resource: str,
    team: str | None,
    months: tuple[Month, ...] = (),
    account: str = ACCOUNT,
) -> None:
    """One credit as the ledger collector leaves it, with the months it judged."""
    recommendation = finished(engine, tenant, resource)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE recommendation SET sub_account_id = :a WHERE recommendation_id = :id"),
            {"a": account, "id": recommendation},
        )
        realized = connection.execute(
            text("SELECT realized_id FROM realized_saving WHERE recommendation_id = :id"),
            {"id": recommendation},
        ).scalar_one()
        credit = uuid4()
        connection.execute(
            INSERT_CREDIT,
            {
                "id": credit,
                "t": tenant,
                "run": uuid4(),
                "account": account,
                "recommendation": recommendation,
                "realized": realized,
                "team": team,
                "at": CLOSED,
            },
        )
        for month, state, cost, saving in months:
            connection.execute(
                INSERT_MONTH,
                {
                    "pk": uuid4(),
                    "t": tenant,
                    "run": uuid4(),
                    "account": account,
                    "credit": credit,
                    "month": month,
                    "state": state,
                    "cost": cost,
                    "saving": saving,
                    "at": CLOSED,
                },
            )


@pytest.fixture
def planted(engine: Engine, tenant_id: UUID) -> None:
    held: tuple[Month, ...] = (
        (OCTOBER, "HELD", Decimal("40"), Decimal("53")),
        (NOVEMBER, "HELD", Decimal("0"), Decimal("90")),
    )
    back: tuple[Month, ...] = (
        (OCTOBER, "HELD", Decimal("60"), Decimal("33")),
        (NOVEMBER, "REGRESSED", Decimal("120"), Decimal("-30")),
    )
    credited(engine, tenant_id, "i-held", "platform", held)
    credited(engine, tenant_id, "i-back", "platform", back)
    credited(
        engine,
        tenant_id,
        "i-pay",
        "payments",
        ((OCTOBER, "UNOBSERVED", None, None),),
        account=OTHER,
    )
    credited(engine, tenant_id, "i-none", None)


def read(engine: Engine, settings: Settings, tenant: UUID, path: str, account: str = "") -> Any:
    scope = only(tenant, account) if account else everything(tenant)
    client, token = client_for(engine, scope, settings)
    return get(client, token, path)


@pytest.mark.usefixtures("planted")
def test_teams_are_ranked_by_the_saving_their_months_held(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    teams = read(engine, settings, tenant_id, LEDGER)["data"]["teams"]
    assert [
        (one["team"], one["credits"], Decimal(one["saving_held"]), one["months_held"])
        for one in teams
    ] == [
        # 53 and 90 held, and 33 before the regression; the regressed month adds nothing.
        ("platform", 2, Decimal("176"), 3),
        # An unobserved month is never a zero saving, and nothing yet is not one either.
        ("payments", 1, Decimal("0"), 0),
        (None, 1, Decimal("0"), 0),
    ]
    platform = teams[0]
    assert (platform["regressed"], platform["latest_month"]) == (1, "2026-11-01")


@pytest.mark.usefixtures("planted")
def test_the_ledger_ranks_teams_and_never_names_a_person(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    teams = read(engine, settings, tenant_id, LEDGER)["data"]["teams"]
    for one in teams:
        assert not {"owner", "closed_by"} & set(one)


@pytest.mark.usefixtures("planted")
def test_a_teams_credits_carry_their_owner_closer_and_months(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    found = read(engine, settings, tenant_id, f"{CREDITS}?team=platform")["data"]
    assert (found["team"], found["every_team"]) == ("platform", False)
    by_resource = {one["resource_id"]: one for one in found["credits"]}
    held = by_resource["i-held"]
    assert (held["owner"], held["closed_by"], Decimal(held["saving_held"])) == (
        "platform@example.local",
        "alice",
        Decimal("143"),
    )
    assert [(one["month"], one["state"]) for one in held["months"]] == [
        ("2026-10-01", "HELD"),
        ("2026-11-01", "HELD"),
    ]
    assert by_resource["i-back"]["regressed"] is True
    # The most held saving first.
    assert [one["resource_id"] for one in found["credits"]] == ["i-held", "i-back"]


@pytest.mark.usefixtures("planted")
def test_an_unobserved_month_carries_no_figure(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    found = read(engine, settings, tenant_id, f"{CREDITS}?team=payments")["data"]["credits"]
    assert [(one["state"], one["cost"], one["saving"]) for one in found[0]["months"]] == [
        ("UNOBSERVED", None, None)
    ]


@pytest.mark.usefixtures("planted")
def test_an_empty_team_asks_for_the_credits_no_team_was_named_for(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    found = read(engine, settings, tenant_id, f"{CREDITS}?team=")["data"]
    assert [one["resource_id"] for one in found["credits"]] == ["i-none"]
    assert found["credits"][0]["months"] == []


@pytest.mark.usefixtures("planted")
def test_no_team_asks_for_every_credit(engine: Engine, tenant_id: UUID, settings: Settings) -> None:
    found = read(engine, settings, tenant_id, CREDITS)["data"]
    assert found["every_team"] is True
    assert len(found["credits"]) == 4


@pytest.mark.usefixtures("planted")
def test_a_reader_narrowed_to_one_account_sees_only_its_credits(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    teams = read(engine, settings, tenant_id, LEDGER, account=ACCOUNT)["data"]["teams"]
    assert [one["team"] for one in teams] == ["platform", None]
    credits_seen = read(engine, settings, tenant_id, CREDITS, account=OTHER)["data"]["credits"]
    assert [one["resource_id"] for one in credits_seen] == ["i-pay"]


@pytest.mark.usefixtures("planted")
@pytest.mark.parametrize("path", [LEDGER, CREDITS])
def test_both_routes_export(engine: Engine, tenant_id: UUID, settings: Settings, path: str) -> None:
    client, token = client_for(engine, everything(tenant_id), settings)
    response = client.get(f"{path}?format=csv", headers=auth(token))
    assert response.status_code == 200, response.text
    assert "Saving held" in response.text
