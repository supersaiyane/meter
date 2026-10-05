"""The one export responder, on a route of its own. FEAT-067, TASK-P8-009.

A route built here rather than borrowed from the API, so what is proved is the responder: the
JSON a screen reads is untouched, a file holds the same rows, a route that returns early is
exported too, and every file is recorded once. The API's routes are held to it in
`test_export_routes.py`, and against a database in `test_export_parity.py`.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import APIRouter, FastAPI, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel

from finops_api.deps import get_connection, get_scope, get_settings
from finops_api.exports import (
    EFFECTIVE_COST,
    ExportSpec,
    billing_period,
    exportable,
    listed,
    responder,
)
from finops_api.schemas import CoverageOut, Envelope, FailureOut, Meta
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.tenant import Scope
from tests.api.workbook import cells, column, pairs, sheet_names

TENANT = uuid4()
AS_OF = datetime(2026, 10, 4, 6, 0, tzinfo=UTC)
COLLECTED = datetime(2026, 10, 4, 6, 5, tzinfo=UTC)
HOSTILE_NAME = '=HYPERLINK("http://example.invalid","open")'


class Item(BaseModel):
    name: str
    effective_cost: Decimal


ITEMS = (
    Item(name=HOSTILE_NAME, effective_cost=Decimal("5.00")),
    Item(name="Amazon EC2", effective_cost=Decimal("12.50")),
    Item(name="Amazon S3", effective_cost=Decimal("-1.25")),
)

FAILURE = FailureOut(
    scope_key="aws:fake-platform-b",
    collector="account_health",
    cause="AccessDenied",
    remediation="Grant the reader role in fake-platform-b.",
    occurrences=2,
    last_seen_at=AS_OF,
)


def meta(*failures: FailureOut) -> Meta:
    return Meta(
        as_of=AS_OF,
        collected_at=COLLECTED,
        scope_coverage=CoverageOut(visible=1, total=2),
        failures=failures,
    )


router = APIRouter()


@router.get("/things", response_model=Envelope[list[Item]])
@exportable(
    ExportSpec(
        title="Things by name",
        row_model=Item,
        rows=listed,
        grouping="Name",
        period=billing_period,
        metric=EFFECTIVE_COST,
    )
)
def things(
    empty: bool = Query(default=False),
    limit: int = Query(default=3, ge=1, le=3),
) -> Envelope[list[Item]]:
    """A screen of things. An empty one returns early, the way an uncollected period does."""
    if empty:
        return Envelope(data=[], meta=meta())
    return Envelope(data=list(ITEMS[:limit]), meta=meta(FAILURE))


def narrow(principal: str | None = "p2") -> Scope:
    return Scope(
        tenant_id=TENANT,
        is_global=False,
        accounts=frozenset({AccountKey(provider=Provider.AWS, account_id="fake-platform-a")}),
        principal_id=principal,
    )


def whole() -> Scope:
    return Scope(tenant_id=TENANT, is_global=True, accounts=frozenset(), principal_id="p2")


def client(scope: Scope | None = None, limit: int = 100) -> TestClient:
    app = FastAPI()
    app.include_router(router)

    def no_connection() -> Iterator[None]:
        yield None

    app.dependency_overrides[get_connection] = no_connection
    app.dependency_overrides[get_scope] = lambda: scope or narrow()
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(export_row_limit=limit)
    return TestClient(app)


@pytest.fixture(autouse=True)
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """What each export would have written to `report_run`. Every test, so none reaches for a
    connection the route here does not have."""
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(responder, "record_run", lambda _connection, **row: calls.append(row))
    return calls


def csv_rows(body: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(body.decode("utf-8-sig"))))


class TestTheScreenIsUntouched:
    def test_without_a_format_the_screen_gets_its_envelope(
        self, recorded: list[dict[str, Any]]
    ) -> None:
        response = client().get("/things")
        assert response.status_code == 200
        assert [row["name"] for row in response.json()["data"]] == [item.name for item in ITEMS]
        assert recorded == []

    def test_format_json_is_the_same_answer(self, recorded: list[dict[str, Any]]) -> None:
        assert client().get("/things?format=json").json() == client().get("/things").json()
        assert recorded == []

    def test_called_directly_a_route_returns_its_envelope(self) -> None:
        found = things(empty=False, limit=3)
        assert isinstance(found, Envelope)
        assert len(found.data) == 3


class TestTheFile:
    def test_a_workbook_is_an_attachment_named_for_the_view_and_the_day(self) -> None:
        response = client().get("/things?format=xlsx")
        today = datetime.now(UTC).date().isoformat()
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(responder.MEDIA_TYPES["xlsx"])
        assert response.headers["content-disposition"] == (
            f'attachment; filename="meter-things-by-name-{today}.xlsx"'
        )
        assert response.headers["cache-control"] == "no-store"
        assert sheet_names(response.content) == ["Data", "About this export"]

    def test_the_csv_holds_the_screen_s_rows_in_the_screen_s_order(self) -> None:
        screen = client().get("/things").json()["data"]
        rows = csv_rows(client().get("/things?format=csv").content)
        assert rows[0] == ["Name", "Effective Cost"]
        assert [Decimal(row[1]) for row in rows[1:]] == [
            Decimal(row["effective_cost"]) for row in screen
        ]
        assert [row[0].removeprefix("'") for row in rows[1:]] == [row["name"] for row in screen]

    def test_an_early_return_is_a_file_rather_than_json(self) -> None:
        response = client().get("/things?empty=true&format=csv")
        assert response.headers["content-type"].startswith("text/csv")
        assert csv_rows(response.content) == [["Name", "Effective Cost"]]

    def test_a_hostile_value_from_the_route_arrives_as_text(self) -> None:
        workbook = cells(client().get("/things?format=xlsx").content, 1)
        assert workbook["A2"].kind == "inlineStr"
        assert not workbook["A2"].is_formula
        assert csv_rows(client().get("/things?format=csv").content)[1][0] == f"'{HOSTILE_NAME}"

    def test_a_workbook_past_the_row_limit_stops_and_says_so(
        self, recorded: list[dict[str, Any]]
    ) -> None:
        body = client(limit=2).get("/things?format=xlsx").content
        assert column(cells(body, 1), "B") == ["Effective Cost", "5", "12.5"]
        assert pairs(cells(body, 2))["Rows"] == "2 of 3. The CSV of the same view holds all 3."
        assert (recorded[0]["rows"], recorded[0]["truncated"]) == (2, True)

    def test_the_csv_holds_every_row_whatever_the_limit(self) -> None:
        assert len(csv_rows(client(limit=2).get("/things?format=csv").content)) == 4


class TestTheAboutSheet:
    def test_it_holds_every_field_spec_section_5_5_item_2_names(self) -> None:
        about = pairs(cells(client().get("/things?format=xlsx").content, 2))
        required = {
            "Scope",
            "Coverage",
            "Filters",
            "Grouping",
            "Period",
            "Currency",
            "Cost metric",
            "As of",
            "Collected at",
            "Failures",
            "Made at",
            "Made by",
            "Row limit",
        }
        assert required <= set(about)
        assert about["Scope"] == "1 account: fake-platform-a"
        assert about["Coverage"] == "1 of 2 accounts, so this is part of the estate"
        assert about["Period"] == "The newest billing period collected"
        assert about["Cost metric"] == EFFECTIVE_COST
        assert about["As of"] == "2026-10-04 06:00:00 UTC"
        assert about["Collected at"] == "2026-10-04 06:05:00 UTC"
        assert about["Made by"] == "p2"
        assert about["Failures"] == "1, listed below"

    def test_a_failed_collector_is_a_row_there_and_never_a_zero(self) -> None:
        notes = cells(client().get("/things?format=xlsx").content, 2)
        # Named as the screens name it, never by its code. ISS-246.
        assert "Account health" in column(notes, "A")
        assert "account_health" not in column(notes, "A")
        assert "AccessDenied" in column(notes, "B")

    def test_the_filters_are_the_query_without_the_format(self) -> None:
        about = pairs(cells(client().get("/things?limit=2&format=xlsx").content, 2))
        assert about["Filters"] == "limit=2"


class TestEveryFileIsRecorded:
    def test_once_with_its_view_and_its_scope(self, recorded: list[dict[str, Any]]) -> None:
        response = client().get("/things?limit=2&format=csv")
        assert len(recorded) == 1
        row = recorded[0]
        assert row["tenant_id"] == TENANT
        assert row["principal_id"] == "p2"
        assert (row["view_path"], row["view_query"]) == ("/things", "limit=2")
        assert row["scope_accounts"] == ["fake-platform-a"]
        assert (row["file_format"], row["rows"], row["truncated"]) == ("csv", 2, False)
        assert row["size"] == len(response.content)

    def test_a_global_scope_is_recorded_as_global(self, recorded: list[dict[str, Any]]) -> None:
        client(whole()).get("/things?format=xlsx")
        assert recorded[0]["scope_accounts"] is None


class TestRefusals:
    def test_an_unknown_format_is_refused(self) -> None:
        assert client().get("/things?format=pdf").status_code == 422

    def test_a_file_for_nobody_is_refused_and_the_screen_still_answers(
        self, recorded: list[dict[str, Any]]
    ) -> None:
        refused = client(narrow(None)).get("/things?format=xlsx")
        assert refused.status_code == 403
        assert refused.json()["detail"] == responder.NOBODY
        assert client(narrow(None)).get("/things").status_code == 200
        assert recorded == []

    def test_the_route_s_own_parameters_are_still_validated(self) -> None:
        assert client().get("/things?limit=9&format=csv").status_code == 422

    def test_an_async_route_is_refused_when_it_is_marked(self) -> None:
        async def later() -> Envelope[list[Item]]:
            return Envelope(data=[], meta=meta())

        mark = exportable(ExportSpec(title="Later", row_model=Item, rows=listed))
        with pytest.raises(TypeError, match="async"):
            mark(later)  # type: ignore[arg-type]

    def test_a_route_with_a_parameter_of_the_responder_s_name_is_refused(self) -> None:
        def clash(exporter: int = 0) -> Envelope[list[Item]]:
            return Envelope(
                data=[Item(name="clash", effective_cost=Decimal(exporter))], meta=meta()
            )

        with pytest.raises(TypeError, match="exporter"):
            exportable(ExportSpec(title="Clash", row_model=Item, rows=listed))(clash)
