"""An export holds the screen's rows, never more than its reader may see, and is recorded.
FEAT-067, TASK-P8-009, P8 spec section 5.5 items 1 and 5.

Against a database, through the API's own client, so the scope dependency and the repository
guard under test are the ones the screens use. `test_export_responder.py` proves the responder
on a route of its own; this proves the routes, and that the database holds the record's
invariants rather than trusting the code that writes it.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError

from finops_api.db import models
from finops_core.config import Settings
from tests.api.test_cost_explore import seed_months
from tests.api.test_cost_routes import ONE_ACCOUNT, everything, only, seed
from tests.api.test_query_routes import auth, client_for
from tests.api.workbook import cells, column

# `seed` writes a bill with no split data, which leaves a split gap that migration 0018's
# downgrade refuses to delete, so every module that seeds gives it back. See conftest.
pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("clear_split_gap")]


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module seeds, and seeding creates partitions, so it gives them back. See conftest."""


def screen(client: TestClient, token: str, path: str, query: str = "") -> Any:
    response = client.get(f"{path}?{query}", headers=auth(token))
    assert response.status_code == 200, f"{path} returned {response.status_code}: {response.text}"
    return response.json()["data"]


def filed(client: TestClient, token: str, path: str, query: str = "") -> list[list[str]]:
    """The CSV of a view, heading row first."""
    response = client.get(f"{path}?format=csv&{query}", headers=auth(token))
    assert response.status_code == 200, f"{path} returned {response.status_code}: {response.text}"
    return list(csv.reader(StringIO(response.content.decode("utf-8-sig"))))


def runs(engine: Engine, tenant: UUID) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        found = connection.execute(
            select(models.report_run).where(models.report_run.c.tenant_id == tenant)
        )
        return [dict(row) for row in found.mappings()]


class TestTheFileIsTheScreen:
    def test_cost_by_service(self, engine: Engine, tenant_id: UUID, settings: Settings) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        shown = screen(client, token, "/api/v1/cost/by-service")
        rows = filed(client, token, "/api/v1/cost/by-service")
        assert rows[0][:2] == ["Service Name", "Effective Cost"]
        assert [(row[0], Decimal(row[1])) for row in rows[1:]] == [
            (row["name"], Decimal(row["effective_cost"])) for row in shown
        ]

    def test_the_explorer_s_table_grouped_two_ways(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed_months(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        query = "group_by=service&then_by=region"
        shown = screen(client, token, "/api/v1/cost/explore", query)["rows"]
        rows = filed(client, token, "/api/v1/cost/explore", query)
        assert rows[0][:2] == ["Service", "Region"]
        assert shown
        assert [(row[0], row[1], Decimal(row[2])) for row in rows[1:]] == [
            (row["first"], row["second"] or "", Decimal(row["this_period"])) for row in shown
        ]

    def test_a_workbook_holds_the_rows_the_csv_holds(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        path = "/api/v1/cost/by-account"
        body = client.get(f"{path}?format=xlsx", headers=auth(token)).content
        assert column(cells(body, 1), "A") == [row[0] for row in filed(client, token, path)]


class TestANarrowerReaderNeverSeesMore:
    @pytest.mark.parametrize(
        ("path", "query", "heading"),
        [
            ("/api/v1/cost/by-account", "", "Sub Account ID"),
            ("/api/v1/cost/showback", "", "Sub Account ID"),
            ("/api/v1/cost/explore", "group_by=account", "Account"),
        ],
    )
    def test_its_files_hold_only_its_accounts(
        self,
        engine: Engine,
        tenant_id: UUID,
        settings: Settings,
        path: str,
        query: str,
        heading: str,
    ) -> None:
        seed_months(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        rows = filed(client, token, path, query)
        where = rows[0].index(heading)
        assert rows[1:], f"{path} exported nothing, which proves nothing about scope"
        assert {row[where] for row in rows[1:]} == {ONE_ACCOUNT}

    def test_its_file_adds_up_to_less_than_the_whole(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)

        def total(client: TestClient, token: str) -> Decimal:
            rows = filed(client, token, "/api/v1/cost/by-service")
            return sum((Decimal(row[1]) for row in rows[1:]), Decimal(0))

        whole = total(*client_for(engine, everything(tenant_id), settings))
        part = total(*client_for(engine, only(tenant_id, ONE_ACCOUNT), settings))
        assert Decimal(0) < part < whole


class TestEveryFileIsRecorded:
    def test_once_with_who_what_which_scope_and_how_big(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        shown = screen(client, token, "/api/v1/cost/by-service")
        response = client.get("/api/v1/cost/by-service?format=xlsx", headers=auth(token))
        [run] = runs(engine, tenant_id)
        assert (run["principal_id"], run["view_path"], run["view_query"]) == (
            "p2",
            "/api/v1/cost/by-service",
            "",
        )
        assert (run["format"], run["scope_global"], run["scope_accounts"]) == ("xlsx", True, [])
        assert (run["row_count"], run["truncated"]) == (len(shown), False)
        assert run["byte_count"] == len(response.content)

    def test_a_narrow_file_records_the_accounts_it_could_see(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        filed(client, token, "/api/v1/cost/by-service")
        [run] = runs(engine, tenant_id)
        assert (run["scope_global"], run["scope_accounts"]) == (False, [ONE_ACCOUNT])

    def test_the_query_is_recorded_without_the_format(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed_months(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        filed(client, token, "/api/v1/cost/explore", "group_by=account")
        [run] = runs(engine, tenant_id)
        assert run["view_query"] == "group_by=account"

    def test_a_screen_read_records_nothing(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        screen(client, token, "/api/v1/cost/by-service")
        assert runs(engine, tenant_id) == []


def record(tenant: UUID, **changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "run_id": uuid4(),
        "tenant_id": tenant,
        "principal_id": "p2",
        "view_path": "/api/v1/cost/by-service",
        "view_query": "",
        "scope_global": True,
        "scope_accounts": [],
        "format": "xlsx",
        "row_count": 1,
        "byte_count": 10,
        "truncated": False,
        "made_at": datetime.now(UTC),
    }
    return {**row, **changes}


class TestTheDatabaseHoldsTheRecordsInvariants:
    def test_a_whole_record_is_accepted(self, engine: Engine, tenant_id: UUID) -> None:
        # So each refusal below is the constraint, and not a record that was wrong anyway.
        with engine.begin() as connection:
            connection.execute(models.report_run.insert().values(record(tenant_id)))
        assert len(runs(engine, tenant_id)) == 1

    @pytest.mark.parametrize(
        "changes",
        [
            {"format": "pdf"},
            {"row_count": -1},
            {"byte_count": -1},
            {"principal_id": "  "},
            {"view_path": "cost/by-service"},
            {"scope_accounts": [ONE_ACCOUNT]},
        ],
        ids=["format", "rows", "bytes", "nobody", "path", "global-with-accounts"],
    )
    def test_a_broken_record_is_refused(
        self, engine: Engine, tenant_id: UUID, changes: dict[str, object]
    ) -> None:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(models.report_run.insert().values(record(tenant_id, **changes)))
