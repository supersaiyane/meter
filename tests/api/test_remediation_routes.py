"""Where fixes go, through the API as a person sets it. TASK-P15-003, FEAT-091, OPEN-13, OPEN-42.

The connection and the mapping are the organization's: a narrowed reader is told so, a change
needs a person whose scope is the whole organization, and both refusals and changes are audited.
The database refuses a key outside a code host path and a folder that climbs out of a repository
on its own, constraint 11, as the API refuses them first.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from finops_core.config import Settings
from finops_core.domain.tenant import Scope
from tests.api.test_query_routes import auth, client_for
from tests.api.test_waste_routes import get, only

pytestmark = pytest.mark.integration

CONNECTION = "/api/v1/remediation/connection"
REPOSITORIES = "/api/v1/remediation/repositories"
OWNER = "owner@example.local"
#: Who the test client signs in as, whatever the scope it is given names.
SIGNED_IN = "p2"
ACCOUNT = "fake-platform-a"
STORAGE = "s3://state-bucket/storage/terraform.tfstate"
NETWORK = "s3://state-bucket/network/terraform.tfstate"


def person(tenant: UUID) -> Scope:
    return Scope(tenant_id=tenant, is_global=True, accounts=frozenset(), principal_id=OWNER)


def audited(engine: Engine, tenant: UUID, resource: str) -> list[str]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    "SELECT outcome FROM audit_event WHERE tenant_id = :t AND resource = :r "
                    "AND action = 'change' ORDER BY occurred_at"
                ),
                {"t": tenant, "r": resource},
            ).scalars()
        )


def app(settings: Settings, key: str = "github-app") -> dict[str, str]:
    return {
        "host": "github",
        "app_id": "1001",
        "key_secret_name": f"meter/{settings.env}/codehost/{key}",
    }


def mapping(state: str, folder: str, repository: str = "acme/infra") -> dict[str, str]:
    return {
        "state_reference": state,
        "repository": repository,
        "base_branch": "main",
        "folder": folder,
    }


def put(client: Any, token: str, path: str, body: Any) -> Any:
    response = client.put(path, json=body, headers=auth(token))
    assert response.status_code == 200, response.text
    return response.json()


# -- the connection --------------------------------------------------------------------------


def test_nothing_is_connected_until_a_person_connects_the_app(
    engine: Engine, settings: Settings, tenant_id: UUID
) -> None:
    client, token = client_for(engine, person(tenant_id), settings)
    before = get(client, token, CONNECTION)
    assert before["data"]["connected"] is False
    assert before["meta"]["scope_coverage"]["unit"] == "payer"
    made = put(client, token, CONNECTION, app(settings))
    found = get(client, token, CONNECTION)["data"]
    assert found == made["data"]
    assert (found["connected"], found["app_id"], found["connected_by"]) == (True, "1001", SIGNED_IN)
    assert found["key_secret_name"] == f"meter/{settings.env}/codehost/github-app"
    assert made["meta"]["as_of"] is not None
    assert audited(engine, tenant_id, "code_host_connection") == ["ALLOWED"]


def test_a_key_outside_this_environments_code_host_path_is_refused_and_nothing_kept(
    engine: Engine, settings: Settings, tenant_id: UUID
) -> None:
    client, token = client_for(engine, person(tenant_id), settings)
    for name in (f"meter/{settings.env}/ai/openai", "meter/other/codehost/github-app"):
        body = {**app(settings), "key_secret_name": name}
        response = client.put(CONNECTION, json=body, headers=auth(token))
        assert response.status_code == 422
        assert "codehost/" in response.text
    assert get(client, token, CONNECTION)["data"]["connected"] is False


def test_the_database_refuses_a_key_outside_any_code_host_path(
    engine: Engine, tenant_id: UUID
) -> None:
    with pytest.raises(IntegrityError, match="ck_code_host_connection__key"), engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO code_host_connection (tenant_id, host, app_id, key_secret_name, "
                "connected_by) VALUES (:t, 'github', '1001', 'meter/dev/database', 'x')"
            ),
            {"t": tenant_id},
        )


def test_a_narrowed_person_may_neither_read_nor_change_where_fixes_go(
    engine: Engine, settings: Settings, tenant_id: UUID
) -> None:
    narrowed = only(tenant_id, ACCOUNT)
    scope = Scope(
        tenant_id=tenant_id, is_global=False, accounts=narrowed.accounts, principal_id=OWNER
    )
    client, token = client_for(engine, scope, settings)
    for path in (CONNECTION, REPOSITORIES):
        refused = client.get(path, headers=auth(token))
        assert refused.status_code == 404
        assert "whole organization" in refused.text
    assert client.put(CONNECTION, json=app(settings), headers=auth(token)).status_code == 403
    body = {"mappings": [mapping(STORAGE, "storage")]}
    assert client.put(REPOSITORIES, json=body, headers=auth(token)).status_code == 403
    assert audited(engine, tenant_id, "code_host_connection") == ["DENIED"]
    assert audited(engine, tenant_id, "repository_mapping") == ["DENIED"]


# -- the mapping -----------------------------------------------------------------------------


def test_the_mapping_is_set_whole_and_an_unchanged_state_keeps_when_it_was_set(
    engine: Engine, settings: Settings, tenant_id: UUID
) -> None:
    client, token = client_for(engine, person(tenant_id), settings)
    first = put(
        client,
        token,
        REPOSITORIES,
        {"mappings": [mapping(STORAGE, "storage"), mapping(NETWORK, "network")]},
    )
    assert [one["state_reference"] for one in first["data"]["mappings"]] == [NETWORK, STORAGE]
    assert {one["set_by"] for one in first["data"]["mappings"]} == {SIGNED_IN}
    before = {one["state_reference"]: one["set_at"] for one in first["data"]["mappings"]}

    second = put(
        client,
        token,
        REPOSITORIES,
        {"mappings": [mapping(STORAGE, "storage"), mapping(NETWORK, "net")]},
    )
    by_state = {one["state_reference"]: one for one in second["data"]["mappings"]}
    assert by_state[STORAGE]["set_at"] == before[STORAGE], "unchanged, so not set again"
    assert by_state[NETWORK]["set_at"] > before[NETWORK], "changed, so set now"
    assert by_state[NETWORK]["folder"] == "net"

    third = put(client, token, REPOSITORIES, {"mappings": [mapping(STORAGE, "storage")]})
    assert [one["state_reference"] for one in third["data"]["mappings"]] == [STORAGE]
    assert audited(engine, tenant_id, "repository_mapping") == ["ALLOWED"] * 3


def test_states_terraform_was_read_from_with_no_mapping_are_named(
    engine: Engine, settings: Settings, tenant_id: UUID
) -> None:
    at = datetime.now(UTC)
    with engine.begin() as connection:
        for state, address in ((STORAGE, "aws_ebs_volume.data"), (NETWORK, "aws_vpc.main")):
            connection.execute(
                text(
                    "INSERT INTO resource_management (management_id, tenant_id, ingest_run_id, "
                    "sub_account_id, provider_id, address, state_reference, as_of, collected_at) "
                    "VALUES (:id, :t, :run, :account, :arn, :address, :state, :at, :at)"
                ),
                {
                    "id": uuid4(),
                    "t": tenant_id,
                    "run": uuid4(),
                    "account": ACCOUNT,
                    "arn": f"arn:aws:ec2:eu-west-1:{ACCOUNT}:{address}",
                    "address": address,
                    "state": state,
                    "at": at,
                },
            )
    client, token = client_for(engine, person(tenant_id), settings)
    assert get(client, token, REPOSITORIES)["data"]["unmapped"] == [NETWORK, STORAGE]
    found = put(client, token, REPOSITORIES, {"mappings": [mapping(STORAGE, "storage")]})
    assert found["data"]["unmapped"] == [NETWORK]


@pytest.mark.parametrize(
    "body",
    [
        {"mappings": [mapping(STORAGE, "../elsewhere")]},
        {"mappings": [mapping(STORAGE, "/storage")]},
        {"mappings": [mapping(STORAGE, "storage/")]},
        {"mappings": [mapping(STORAGE, "a//b")]},
        {"mappings": [mapping(STORAGE, "storage", repository="infra")]},
        {"mappings": [{**mapping(STORAGE, "storage"), "base_branch": "  "}]},
        {"mappings": [mapping(STORAGE, "storage"), mapping(STORAGE, "network")]},
    ],
)
def test_a_mapping_no_fix_could_follow_is_refused_before_it_is_stored(
    engine: Engine, settings: Settings, tenant_id: UUID, body: dict[str, Any]
) -> None:
    client, token = client_for(engine, person(tenant_id), settings)
    assert client.put(REPOSITORIES, json=body, headers=auth(token)).status_code == 422
    assert get(client, token, REPOSITORIES)["data"]["mappings"] == []


def test_the_database_refuses_a_folder_that_climbs_out_of_the_repository(
    engine: Engine, tenant_id: UUID
) -> None:
    with pytest.raises(IntegrityError, match="ck_repository_mapping__folder"), engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO repository_mapping (tenant_id, state_reference, repository, "
                "base_branch, folder, set_by) VALUES (:t, 's', 'acme/infra', 'main', "
                "'storage/../..', 'x')"
            ),
            {"t": tenant_id},
        )


# -- asking for a fix, TASK-P15-004 ----------------------------------------------------------

FIX = "/api/v1/waste/recommendations/{}/pull-request"


def recommendation(engine: Engine, tenant: UUID, lifecycle: str = "ACCEPTED") -> UUID:
    identifier = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, source, "
                "source_reference, waste_class, resource_id, region_id, "
                "estimated_monthly_saving, confidence, severity, observation_days, lifecycle, "
                "owner, rationale, as_of, collected_at) VALUES (:id, :t, :account, 'METER', :ref, "
                "'EBS_UNATTACHED', 'vol-0abc', 'eu-west-1', 41.20, 'HIGH', 'HIGH', 30, "
                ":lifecycle, 'team-storage', 'unattached for 30 days', :at, :at)"
            ),
            {
                "id": identifier,
                "t": tenant,
                "account": ACCOUNT,
                "ref": f"ref:{identifier}",
                "lifecycle": lifecycle,
                "at": datetime.now(UTC),
            },
        )
    return identifier


def test_a_person_asks_for_a_fix_once_and_the_ask_is_recorded(
    engine: Engine, settings: Settings, tenant_id: UUID
) -> None:
    asked_about = recommendation(engine, tenant_id)
    client, token = client_for(engine, person(tenant_id), settings)
    response = client.post(
        FIX.format(asked_about), json={"note": "  storage team agrees  "}, headers=auth(token)
    )
    assert response.status_code == 200, response.text
    found = response.json()["data"]
    assert (found["status"], found["note"], found["requested_by"]) == (
        "REQUESTED",
        "storage team agrees",
        SIGNED_IN,
    )
    assert found["number"] is None and found["url"] is None
    again = client.post(FIX.format(asked_about), json={}, headers=auth(token))
    assert again.status_code == 409
    assert "already asked" in again.text
    with engine.connect() as connection:
        steps = connection.execute(
            text("SELECT to_status, principal FROM fix_pull_request_event WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).all()
        audited_asks = connection.execute(
            text(
                "SELECT outcome FROM audit_event WHERE tenant_id = :t "
                "AND resource = 'fix_pull_request' AND action = 'request'"
            ),
            {"t": tenant_id},
        ).scalars()
        assert [tuple(one) for one in steps] == [("REQUESTED", SIGNED_IN)]
        assert list(audited_asks) == ["ALLOWED"]


@pytest.mark.parametrize("lifecycle", ["OPEN", "DISMISSED", "IN_PROGRESS"])
def test_a_fix_is_asked_for_only_once_the_recommendation_is_accepted(
    engine: Engine, settings: Settings, tenant_id: UUID, lifecycle: str
) -> None:
    asked_about = recommendation(engine, tenant_id, lifecycle)
    client, token = client_for(engine, person(tenant_id), settings)
    refused = client.post(FIX.format(asked_about), json={}, headers=auth(token))
    assert refused.status_code == 409
    assert "accepted with an owner" in refused.text and lifecycle in refused.text


def test_a_person_who_cannot_see_the_account_cannot_ask(
    engine: Engine, settings: Settings, tenant_id: UUID
) -> None:
    asked_about = recommendation(engine, tenant_id)
    elsewhere = only(tenant_id, "fake-product-a")
    scope = Scope(
        tenant_id=tenant_id, is_global=False, accounts=elsewhere.accounts, principal_id=OWNER
    )
    client, token = client_for(engine, scope, settings)
    assert client.post(FIX.format(asked_about), json={}, headers=auth(token)).status_code == 404
    with engine.connect() as connection:
        asked = connection.execute(
            text("SELECT count(*) FROM fix_pull_request WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar_one()
    assert asked == 0


def test_the_database_allows_one_live_fix_per_recommendation(
    engine: Engine, tenant_id: UUID
) -> None:
    asked_about = recommendation(engine, tenant_id)
    insert = text(
        "INSERT INTO fix_pull_request (fix_id, tenant_id, recommendation_id, sub_account_id, "
        "status, reason, failure_cause, requested_by, requested_at, as_of, collected_at) VALUES "
        "(:fix, :t, :id, :account, :status, :reason, :cause, 'x', now(), now(), now())"
    )
    values = {"t": tenant_id, "id": asked_about, "account": ACCOUNT}
    with engine.begin() as connection:
        # A failed fix is history, so it does not stop the next ask.
        failed = {"status": "FAILED", "reason": "refused", "cause": "AccessDenied"}
        connection.execute(insert, {**values, "fix": uuid4(), **failed})
        live = {"status": "REQUESTED", "reason": None, "cause": None}
        connection.execute(insert, {**values, "fix": uuid4(), **live})
    with pytest.raises(IntegrityError, match="ux_fix_pull_request__live"), engine.begin() as db:
        db.execute(insert, {**values, "fix": uuid4(), **live})


def test_every_fix_in_the_readers_scope_is_listed_with_its_steps(
    engine: Engine, settings: Settings, tenant_id: UUID
) -> None:
    asked_about = recommendation(engine, tenant_id)
    client, token = client_for(engine, person(tenant_id), settings)
    assert client.post(FIX.format(asked_about), json={}, headers=auth(token)).status_code == 200
    (fix,) = get(client, token, "/api/v1/remediation/pull-requests")["data"]["fixes"]
    assert (fix["recommendation_id"], fix["status"]) == (str(asked_about), "REQUESTED")
    assert [(one["to_status"], one["principal"]) for one in fix["steps"]] == [
        ("REQUESTED", SIGNED_IN)
    ]
    elsewhere = only(tenant_id, "fake-product-a")
    narrowed = Scope(
        tenant_id=tenant_id, is_global=False, accounts=elsewhere.accounts, principal_id=OWNER
    )
    client, token = client_for(engine, narrowed, settings)
    assert get(client, token, "/api/v1/remediation/pull-requests")["data"]["fixes"] == []
