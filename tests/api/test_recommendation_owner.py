"""A recommendation's suggested owner, from its resource's team tag. ISS-021, priority 1 item 4.

The suggestion is read through the route, as every P3 route test reads, and the three ways it
must stay empty are held beside the one way it is filled: an empty tag, a node in another
account that happens to share the identifier, and a resource no node names at all. Assigning
an owner stays a person's act, so the stored owner is asserted untouched.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_core.constants import TEAM_TAG
from tests.api.test_query_routes import auth, client_for
from tests.api.test_waste_routes import LIST_PATH, everything, get, only, seed

pytestmark = pytest.mark.integration

AT = datetime(2026, 9, 21, 5, 0, tzinfo=UTC)

INSERT_RUN = text(
    "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, idempotency_key, "
    "status, as_of_window_start, as_of_window_end) "
    "VALUES (:run, :t, 'inventory', 'scope', :key, 'SUCCEEDED', :at, :at)"
)

INSERT_NODE = text(
    "INSERT INTO topology_node (node_id, tenant_id, ingest_run_id, sub_account_id, "
    "provider_id, node_kind, resource_type, region_id, availability_zone, name, tags, as_of, "
    "collected_at) VALUES (:node, :t, :run, :account, :provider, 'INSTANCE', "
    "'AWS::EC2::Instance', 'eu-west-1', NULL, :provider, CAST(:tags AS jsonb), :at, :at)"
)

FINDINGS = text(
    "SELECT resource_id, sub_account_id FROM recommendation WHERE tenant_id = :t "
    "ORDER BY resource_id"
)


def by_resource(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["resource_id"]: row for row in payload["data"]["recommendations"]}


@pytest.fixture
def tagged(engine: Engine, tenant_id: UUID) -> dict[str, str]:
    """The fake's findings, three of their resources given nodes, one left without."""
    seed(engine, tenant_id)
    with engine.begin() as connection:
        found = connection.execute(FINDINGS, {"t": tenant_id}).all()
        assert len(found) >= 4, "the fake recommendation source changed shape"
        run = uuid4()
        connection.execute(INSERT_RUN, {"run": run, "t": tenant_id, "key": str(run), "at": AT})
        owned, empty, elsewhere, untouched = found[0], found[1], found[2], found[3]

        def node(provider: str, account: str, tags: dict[str, str]) -> None:
            connection.execute(
                INSERT_NODE,
                {
                    "node": uuid4(),
                    "t": tenant_id,
                    "run": run,
                    "account": account,
                    "provider": provider,
                    "tags": json.dumps(tags),
                    "at": AT,
                },
            )

        node(owned.resource_id, owned.sub_account_id, {TEAM_TAG: "platform", "env": "prod"})
        node(empty.resource_id, empty.sub_account_id, {TEAM_TAG: ""})
        node(elsewhere.resource_id, "999988887777", {TEAM_TAG: "intruder"})
    return {
        "owned": owned.resource_id,
        "owned_account": owned.sub_account_id,
        "empty": empty.resource_id,
        "elsewhere": elsewhere.resource_id,
        "untouched": untouched.resource_id,
    }


def test_a_tagged_resource_suggests_its_team_and_owns_nothing(
    engine: Engine, tenant_id: UUID, settings: Settings, tagged: dict[str, str]
) -> None:
    client, token = client_for(engine, everything(tenant_id), settings)
    row = by_resource(get(client, token))[tagged["owned"]]
    assert row["suggested_owner"] == "platform"
    assert row["owner"] is None


def test_an_empty_tag_a_node_in_another_account_and_no_node_suggest_nobody(
    engine: Engine, tenant_id: UUID, settings: Settings, tagged: dict[str, str]
) -> None:
    client, token = client_for(engine, everything(tenant_id), settings)
    rows = by_resource(get(client, token))
    assert {
        name: rows[tagged[name]]["suggested_owner"] for name in ("empty", "elsewhere", "untouched")
    } == {"empty": None, "elsewhere": None, "untouched": None}


def test_one_recommendation_read_alone_carries_its_suggestion(
    engine: Engine, tenant_id: UUID, settings: Settings, tagged: dict[str, str]
) -> None:
    client, token = client_for(engine, everything(tenant_id), settings)
    identifier = by_resource(get(client, token))[tagged["owned"]]["recommendation_id"]
    response = client.get(f"{LIST_PATH}/{identifier}", headers=auth(token))
    assert response.status_code == 200, response.text
    assert response.json()["data"]["recommendation"]["suggested_owner"] == "platform"


def test_a_reader_narrowed_to_the_account_still_sees_the_suggestion(
    engine: Engine, tenant_id: UUID, settings: Settings, tagged: dict[str, str]
) -> None:
    client, token = client_for(engine, only(tenant_id, tagged["owned_account"]), settings)
    rows = by_resource(get(client, token))
    assert rows[tagged["owned"]]["suggested_owner"] == "platform"
