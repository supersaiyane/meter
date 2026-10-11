"""Every source's owner suggestion on a recommendation, strongest first. TASK-P11-005.

P11 spec sections 5.1 and 8, read through the route as `test_recommendation_owner` reads the team
tag. A catalogue owner, a tag and a creator planted for one resource come back strongest first,
each with its source, detail and both dates; the strongest team is the suggested owner and a
creator never is; a resource older than CloudTrail's history says where the history began; and a
row in another account sharing the identifier suggests nothing. The stored owner stays untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from tests.api.test_query_routes import auth, client_for
from tests.api.test_recommendation_owner import FINDINGS, by_resource
from tests.api.test_waste_routes import LIST_PATH, everything, get, only, seed

pytestmark = pytest.mark.integration

AT = datetime(2026, 9, 21, 5, 0, tzinfo=UTC)
NOW = AT + timedelta(hours=1)
STARTS = NOW - timedelta(days=90)

INSERT_OWNER = text(
    "INSERT INTO resource_owner (owner_pk, tenant_id, ingest_run_id, sub_account_id, region_id, "
    "resource_id, source, owner, owner_kind, detail, as_of, collected_at) VALUES (:pk, :t, :run, "
    ":account, 'eu-west-1', :resource, :source, :owner, :kind, :detail, :at, :now)"
)
INSERT_LOOKUP = text(
    "INSERT INTO creator_lookup (lookup_pk, tenant_id, ingest_run_id, sub_account_id, region_id, "
    "resource_id, outcome, history_starts, as_of, collected_at) VALUES (:pk, :t, :run, :account, "
    "'eu-west-1', :resource, :outcome, :starts, :now, :now)"
)
OWNERS = text("SELECT owner FROM recommendation WHERE tenant_id = :t")


@pytest.fixture
def planted(engine: Engine, tenant_id: UUID) -> dict[str, str]:
    """Three sources for one finding's resource, a pipeline for a second, an older third."""
    seed(engine, tenant_id)
    with engine.begin() as connection:
        found = connection.execute(FINDINGS, {"t": tenant_id}).all()
        assert len(found) >= 4, "the fake recommendation source changed shape"
        owned, made, older, elsewhere = found[0], found[1], found[2], found[3]

        def owner(row: Any, source: str, name: str, kind: str, detail: str, **where: str) -> None:
            connection.execute(
                INSERT_OWNER,
                {
                    "pk": uuid4(),
                    "t": tenant_id,
                    "run": uuid4(),
                    "account": where.get("account", row.sub_account_id),
                    "resource": row.resource_id,
                    "source": source,
                    "owner": name,
                    "kind": kind,
                    "detail": detail,
                    "at": AT,
                    "now": NOW,
                },
            )

        def lookup(row: Any, outcome: str, starts: datetime | None) -> None:
            connection.execute(
                INSERT_LOOKUP,
                {
                    "pk": uuid4(),
                    "t": tenant_id,
                    "run": uuid4(),
                    "account": row.sub_account_id,
                    "resource": row.resource_id,
                    "outcome": outcome,
                    "starts": starts,
                    "now": NOW,
                },
            )

        # Planted weakest first, so the order read back is the route's and not the insert's.
        owner(owned, "CREATOR", "dev.lead@fake.example", "PERSON", "evt-0003")
        owner(owned, "TAG", "platform", "TEAM", "team")
        owner(owned, "CATALOGUE", "payments", "TEAM", "checkout")
        owner(made, "CREATOR", "deploy-pipeline", "AUTOMATION", "evt-0001")
        lookup(made, "FOUND", None)
        lookup(older, "BEFORE_HISTORY", STARTS)
        owner(elsewhere, "TAG", "intruder", "TEAM", "team", account="999988887777")
    return {
        "owned": owned.resource_id,
        "owned_account": owned.sub_account_id,
        "made": made.resource_id,
        "older": older.resource_id,
        "elsewhere": elsewhere.resource_id,
    }


def rows(engine: Engine, tenant_id: UUID, settings: Settings) -> dict[str, dict[str, Any]]:
    client, token = client_for(engine, everything(tenant_id), settings)
    return by_resource(get(client, token))


def test_every_source_is_listed_strongest_first_with_what_to_check_it_by(
    engine: Engine, tenant_id: UUID, settings: Settings, planted: dict[str, str]
) -> None:
    row = rows(engine, tenant_id, settings)[planted["owned"]]
    listed = row["owner_suggestions"]
    assert [(one["source"], one["owner"], one["kind"], one["detail"]) for one in listed] == [
        ("CATALOGUE", "payments", "TEAM", "checkout"),
        ("TAG", "platform", "TEAM", "team"),
        ("CREATOR", "dev.lead@fake.example", "PERSON", "evt-0003"),
    ]
    for one in listed:
        assert datetime.fromisoformat(one["as_of"]) == AT
        assert datetime.fromisoformat(one["collected_at"]) == NOW
    assert row["owner"] is None


def test_the_strongest_team_is_the_suggested_owner_and_a_creator_never_is(
    engine: Engine, tenant_id: UUID, settings: Settings, planted: dict[str, str]
) -> None:
    found = rows(engine, tenant_id, settings)
    assert found[planted["owned"]]["suggested_owner"] == "payments"
    made = found[planted["made"]]
    assert [one["kind"] for one in made["owner_suggestions"]] == ["AUTOMATION"]
    assert made["suggested_owner"] is None


def test_a_resource_older_than_the_history_says_where_it_began(
    engine: Engine, tenant_id: UUID, settings: Settings, planted: dict[str, str]
) -> None:
    found = rows(engine, tenant_id, settings)
    assert datetime.fromisoformat(found[planted["older"]]["created_before"]) == STARTS
    assert found[planted["older"]]["owner_suggestions"] == []
    # Found, or never asked: nothing to say about the history.
    assert found[planted["made"]]["created_before"] is None
    assert found[planted["owned"]]["created_before"] is None


def test_a_suggestion_in_another_account_sharing_the_identifier_is_never_shown(
    engine: Engine, tenant_id: UUID, settings: Settings, planted: dict[str, str]
) -> None:
    row = rows(engine, tenant_id, settings)[planted["elsewhere"]]
    assert (row["owner_suggestions"], row["suggested_owner"]) == ([], None)


def test_one_recommendation_read_alone_carries_its_suggestions(
    engine: Engine, tenant_id: UUID, settings: Settings, planted: dict[str, str]
) -> None:
    client, token = client_for(engine, everything(tenant_id), settings)
    identifier = by_resource(get(client, token))[planted["owned"]]["recommendation_id"]
    response = client.get(f"{LIST_PATH}/{identifier}", headers=auth(token))
    assert response.status_code == 200, response.text
    one = response.json()["data"]["recommendation"]
    assert [row["source"] for row in one["owner_suggestions"]] == ["CATALOGUE", "TAG", "CREATOR"]


def test_a_reader_narrowed_to_the_account_still_sees_them(
    engine: Engine, tenant_id: UUID, settings: Settings, planted: dict[str, str]
) -> None:
    client, token = client_for(engine, only(tenant_id, planted["owned_account"]), settings)
    row = by_resource(get(client, token))[planted["owned"]]
    assert len(row["owner_suggestions"]) == 3


@pytest.mark.usefixtures("planted")
def test_reading_the_suggestions_writes_no_owner(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    rows(engine, tenant_id, settings)
    with engine.connect() as connection:
        assert {row.owner for row in connection.execute(OWNERS, {"t": tenant_id})} == {None}
