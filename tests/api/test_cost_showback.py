"""The showback file finance opens. FEAT-045, TASK-P1-018, delivered through FEAT-067.

The route that replaced `/cost/export`. Since TASK-P8-009 the showback rows are a screen like
any other and the file comes through the one export responder, so these tests read the CSV the
responder writes for `format=csv` and hold it to everything FEAT-045 promised of the file that
used to be written by hand: it sums to the screen, it drops nothing it cannot attribute, every
money column names its measure, and every row carries its period, both timestamps and the
coverage.

One question matters more than the rest, and it is the first class. A file that disagrees with
what a reader was shown is worse than no file, because the disagreement is found later, by
somebody reconciling against an invoice, and it discredits both numbers. So these tests do not
assert a total written down here. They sum the file's columns and compare against
`/cost/summary`, which is the figure the screen shows.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from finops_core.config import Settings
from finops_core.domain.platform import UNALLOCATED
from tests.api.test_cost_routes import ONE_ACCOUNT, everything, only, seed
from tests.api.test_query_routes import auth, client_for
from tests.api.workbook import cells, column, pairs

# `seed` writes a bill with no split data, which leaves a split gap that migration 0018's
# downgrade refuses to delete, so every module that seeds gives it back. See conftest.
pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("clear_split_gap")]

PATH = "/api/v1/cost/showback"
EFFECTIVE = "Effective Cost"
BILLED = "Billed Cost"
TAG = "Tag value, team"


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module seeds, and seeding creates partitions, so it gives them back. See conftest."""


def download(client: TestClient, token: str, query: str = "") -> str:
    response = client.get(f"{PATH}?format=csv&{query}", headers=auth(token))
    assert response.status_code == 200, f"{PATH} returned {response.status_code}: {response.text}"
    assert response.headers["content-type"].startswith("text/csv")
    return response.content.decode("utf-8-sig")


def parsed(body: str) -> list[dict[str, str]]:
    return list(csv.DictReader(StringIO(body)))


def summed(body: str, column_name: str) -> Decimal:
    return sum((Decimal(row[column_name]) for row in parsed(body)), Decimal("0"))


def screen(client: TestClient, token: str) -> list[dict[str, Any]]:
    response = client.get(PATH, headers=auth(token))
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert isinstance(rows, list)
    return rows


def total_on_screen(client: TestClient, token: str, field: str) -> Decimal:
    summary = client.get("/api/v1/cost/summary", headers=auth(token)).json()
    return Decimal(str(summary["data"]["current"][field]))


class TestTheFileAgreesWithTheScreen:
    def test_the_effective_cost_column_sums_to_the_period_total(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The assertion this file exists to pass, against the figure the screen shows."""
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        assert summed(download(client, token), EFFECTIVE) == total_on_screen(
            client, token, "effective_cost"
        )

    def test_the_billed_column_sums_to_the_period_total_too(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        assert summed(download(client, token), BILLED) == total_on_screen(
            client, token, "billed_cost"
        )

    def test_the_line_items_sum_to_the_period_count(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # A grouped export loses rows silently when a group key is null and the grouping
        # drops it, and the count is what notices.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        assert summed(download(client, token), "Line items") == total_on_screen(
            client, token, "line_items"
        )

    def test_the_file_holds_the_screen_s_rows_in_the_screen_s_order(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        shown = [
            (row["account_id"], row["service_name"], row["tag_value"], row["effective_cost"])
            for row in screen(client, token)
        ]
        filed = [
            (row["Sub Account ID"], row["Service Name"], row[TAG], row[EFFECTIVE])
            for row in parsed(download(client, token))
        ]
        assert shown
        assert [(a, s, t, Decimal(c)) for a, s, t, c in filed] == [
            (a, s, t, Decimal(c)) for a, s, t, c in shown
        ]


class TestNothingIsQuietlyDropped:
    def test_the_unallocated_bucket_is_a_named_row(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """`fake-product-b` is untagged throughout the fake estate on purpose, so the bucket
        is never empty and the row is never absent for want of data."""
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        assert UNALLOCATED in {row[TAG] for row in parsed(download(client, token))}

    def test_the_unallocated_money_is_not_zero(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # A present row with a zero in it would pass the test above and still have lost the
        # money.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        unallocated = [row for row in parsed(download(client, token)) if row[TAG] == UNALLOCATED]
        assert sum((Decimal(row[EFFECTIVE]) for row in unallocated), Decimal("0")) > 0


class TestEveryFigureSaysWhatItIs:
    def test_the_money_headings_name_their_measure(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """A column headed "cost" is a column somebody will argue about. Amortized and billed
        differ by exactly the commitment discount, and the FOCUS names say which is which."""
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        headings = next(csv.reader(StringIO(download(client, token))))
        assert {EFFECTIVE, BILLED} <= set(headings)
        assert "Cost" not in headings

    def test_both_timestamps_are_on_every_row(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """A CSV has no About sheet, and a spreadsheet outlives the moment it was made, so the
        freshness travels in the cells. Two columns, per constraint 10."""
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        rows = parsed(download(client, token))
        assert rows
        for row in rows:
            assert row["As of"]
            assert row["Collected at"]
            assert row["As of"] != row["Collected at"]

    def test_the_scope_coverage_is_on_every_row(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """FEAT-045 promises it: a reader who pastes one row into a deck takes the coverage
        with them."""
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        rows = parsed(download(client, token))
        assert rows
        for row in rows:
            assert int(row["Accounts in file"]) == 1
            assert int(row["Accounts in organization"]) >= 1

    def test_a_narrow_file_reports_a_smaller_coverage_than_a_whole_one(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        whole_client, whole_token = client_for(engine, everything(tenant_id), settings)
        narrow_client, narrow_token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        whole = parsed(download(whole_client, whole_token))[0]
        narrow = parsed(download(narrow_client, narrow_token))[0]
        assert int(narrow["Accounts in file"]) < int(whole["Accounts in file"])

    def test_the_period_is_on_every_row(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # A file whose period is only in its name has lost it the moment somebody pastes two
        # of them into one sheet.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        assert len({row["Billing period"] for row in parsed(download(client, token))}) == 1


class TestScope:
    def test_a_narrow_scope_exports_less(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The same predicate as every other read, not a second one. An export is the easiest
        place to leak an estate, because nobody reads it on screen before saving it."""
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        whole = summed(download(client, token), EFFECTIVE)
        narrow_client, narrow_token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        part = summed(download(narrow_client, narrow_token), EFFECTIVE)
        assert Decimal("0") < part < whole

    def test_a_narrow_scope_exports_only_its_own_accounts(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        accounts = {row["Sub Account ID"] for row in parsed(download(client, token))}
        assert accounts == {ONE_ACCOUNT}

    def test_a_narrow_scopes_file_still_agrees_with_its_own_screen(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        assert summed(download(client, token), EFFECTIVE) == total_on_screen(
            client, token, "effective_cost"
        )


class TestTheFileItself:
    def test_it_is_offered_as_a_download_named_for_the_view_and_the_day(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        response = client.get(f"{PATH}?format=csv", headers=auth(token))
        today = datetime.now(UTC).date().isoformat()
        assert response.headers["content-disposition"] == (
            f'attachment; filename="meter-showback-{today}.csv"'
        )

    def test_the_workbook_says_which_tag_it_grouped_by(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        body = client.get(f"{PATH}?format=xlsx", headers=auth(token)).content
        assert column(cells(body, 1), "D")[0] == TAG
        assert pairs(cells(body, 2))["Grouping"] == "Account, service and the tag team"

    def test_a_tenant_with_no_cost_is_told_so_rather_than_sent_an_empty_file(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # An empty file with a heading row says the estate spent nothing. A 404 says nothing
        # has been collected, which is the true statement. Constraint 5.
        client, token = client_for(engine, everything(tenant_id), settings)
        assert client.get(f"{PATH}?format=csv", headers=auth(token)).status_code == 404
        assert client.get(PATH, headers=auth(token)).status_code == 404

    def test_a_tag_key_nobody_used_still_exports_the_whole_period(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # Every row lands in the unallocated bucket rather than the file being empty, which
        # would look like an estate with no spend.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        body = download(client, token, "tag=nobody-uses-this")
        assert {row["Tag value, nobody-uses-this"] for row in parsed(body)} == {UNALLOCATED}
        assert summed(body, EFFECTIVE) == total_on_screen(client, token, "effective_cost")
