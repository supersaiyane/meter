"""The file finance opens. FEAT-045, TASK-P1-018.

Named for the route rather than the port, because `tests/contract/test_cost_export.py`
already holds the `CostExport` contract and the two are different subjects: that one
asks whether an adapter reads a billing export, this one asks whether the CSV we hand
somebody agrees with the screen they were looking at.

One question matters more than the rest, and it is the first class. A CSV that
disagrees with what a reader was shown is worse than no CSV, because the disagreement
is found later, by somebody reconciling against an invoice, and it discredits both
numbers.

So these tests do not assert a total written down here. They sum the file's columns
and compare against `/cost/summary`, which is the figure the screen shows. A different
grouping, a dropped unallocated bucket, or a scope predicate applied in one place and
not the other all fail here.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from io import StringIO
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from finops_core.config import Settings
from finops_core.domain.platform import UNALLOCATED
from tests.api.test_cost_routes import ONE_ACCOUNT, everything, only, seed
from tests.api.test_query_routes import auth, client_for

pytestmark = pytest.mark.integration

PATH = "/api/v1/cost/export"


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module seeds, and seeding creates partitions, so it gives them back.

    Inherited by importing `seed` rather than by writing rows directly, which is
    exactly how it was missed: the tests passed alone and failed in the full run,
    where `tests/db/test_schema.py` compares the models against the live database and
    found partitions no module owned. See conftest.
    """


def download(client: TestClient, token: str, query: str = "") -> str:
    response = client.get(f"{PATH}{query}", headers=auth(token))
    assert response.status_code == 200, f"{PATH} returned {response.status_code}: {response.text}"
    assert response.headers["content-type"].startswith("text/csv")
    return response.text


def parsed(body: str) -> list[dict[str, str]]:
    return list(csv.DictReader(StringIO(body)))


def summed(body: str, column: str) -> Decimal:
    return sum((Decimal(row[column]) for row in parsed(body)), Decimal("0"))


def total_on_screen(client: TestClient, token: str, field: str) -> Decimal:
    summary = client.get("/api/v1/cost/summary", headers=auth(token)).json()
    return Decimal(str(summary["data"]["current"][field]))


class TestTheFileAgreesWithTheScreen:
    def test_the_amortized_column_sums_to_the_period_total(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The assertion this endpoint exists to pass.

        Not a number written down here. The summary route is what the screen shows,
        so the comparison is against that, and anything making the two drift fails.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        body = download(client, token)
        assert summed(body, "effective_cost_amortized_usd") == total_on_screen(
            client, token, "effective_cost"
        )

    def test_the_billed_column_sums_to_the_period_total_too(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        body = download(client, token)
        assert summed(body, "billed_cost_usd") == total_on_screen(client, token, "billed_cost")

    def test_the_line_items_sum_to_the_period_count(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # A grouped export loses rows silently when a group key is null and the
        # grouping drops it, and the count is what notices.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        body = download(client, token)
        assert summed(body, "line_items") == total_on_screen(client, token, "line_items")


class TestNothingIsQuietlyDropped:
    def test_the_unallocated_bucket_is_a_named_row(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """An export that loses what it cannot attribute reports a smaller estate.

        `fake-product-b` is untagged throughout the fake estate on purpose, so the
        bucket is never empty and the row is never absent for want of data.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        values = {row["tag_value"] for row in parsed(download(client, token))}
        assert UNALLOCATED in values

    def test_the_unallocated_money_is_not_zero(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # A present row with a zero in it would pass the test above and still have
        # lost the money.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        unallocated = [
            row for row in parsed(download(client, token)) if row["tag_value"] == UNALLOCATED
        ]
        assert sum(
            (Decimal(row["effective_cost_amortized_usd"]) for row in unallocated), Decimal("0")
        ) > Decimal("0")


class TestEveryFigureSaysWhichMeasureItIs:
    def test_the_money_headers_name_their_measure(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """A column headed "cost" is a column somebody will argue about.

        Amortized and billed differ by exactly the commitment discount, and nothing
        in a bare number in a spreadsheet cell says which one is in it.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        header = download(client, token).splitlines()[0]
        assert "effective_cost_amortized_usd" in header
        assert "billed_cost_usd" in header
        assert ",cost," not in f",{header},"

    def test_both_timestamps_are_on_every_row(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The reason this route may skip the meta envelope.

        A CSV cannot carry the envelope, and the envelope exists so a reader can tell
        stale from fresh. A spreadsheet outlives the moment it was downloaded: it gets
        mailed on and pasted into a deck, so the freshness has to be in the cells. Two
        columns, not one, per constraint 10: `as_of` is when the charge was true at
        the source and `collected_at` is when Meter fetched it.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        rows = parsed(download(client, token))
        assert rows
        for row in rows:
            assert row["as_of"]
            assert row["collected_at"]
            assert row["as_of"] != row["collected_at"]

    def test_the_scope_coverage_is_on_every_row(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """FEAT-045 promises it, and a partial file is the reason.

        A file drawn from two of three hundred accounts is not the estate. Once it is
        a spreadsheet nobody can ask the product what scope produced it, and a reader
        who pastes one row into a deck has taken the coverage with them.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        rows = parsed(download(client, token))
        assert rows
        for row in rows:
            assert int(row["accounts_in_file"]) == 1
            assert int(row["accounts_in_organization"]) >= 1

    def test_a_narrow_file_reports_a_smaller_coverage_than_a_whole_one(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # The assertion above would pass with the number hardcoded to one. This one
        # requires the two scopes to differ.
        seed(engine, tenant_id)
        whole_client, whole_token = client_for(engine, everything(tenant_id), settings)
        narrow_client, narrow_token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        whole = parsed(download(whole_client, whole_token))[0]
        narrow = parsed(download(narrow_client, narrow_token))[0]
        assert int(narrow["accounts_in_file"]) < int(whole["accounts_in_file"])

    def test_the_period_is_on_every_row(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # A file whose period is only in its filename has lost its period the moment
        # somebody pastes two of them into one sheet.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        periods = {row["billing_period"] for row in parsed(download(client, token))}
        assert len(periods) == 1


class TestScope:
    def test_a_narrow_scope_exports_less(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The same predicate as every other read, not a second one.

        An export is the easiest place to leak an estate, because it is the one
        response nobody reads on screen before saving it.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        whole = summed(download(client, token), "effective_cost_amortized_usd")

        narrow_client, narrow_token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        part = summed(download(narrow_client, narrow_token), "effective_cost_amortized_usd")

        assert part < whole
        assert part > Decimal("0")

    def test_a_narrow_scope_exports_only_its_own_accounts(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        accounts = {row["account_id"] for row in parsed(download(client, token))}
        assert accounts == {ONE_ACCOUNT}

    def test_a_narrow_scopes_file_still_agrees_with_its_own_screen(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # The stronger form of the first class. The file and the screen have to agree
        # for every scope, not only the global one, or a reader with two accounts gets
        # a file that reconciles against nothing.
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        body = download(client, token)
        assert summed(body, "effective_cost_amortized_usd") == total_on_screen(
            client, token, "effective_cost"
        )


class TestTheFileItself:
    def test_it_is_offered_as_a_download_named_for_its_period(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        response = client.get(PATH, headers=auth(token))
        disposition = response.headers["content-disposition"]
        assert "attachment" in disposition
        assert parsed(response.text)[0]["billing_period"] in disposition

    def test_a_tenant_with_no_cost_is_told_so_rather_than_sent_an_empty_file(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # An empty CSV with a header row says the estate spent nothing. A 404 says
        # nothing has been collected, which is the true statement. Constraint 5.
        client, token = client_for(engine, everything(tenant_id), settings)
        assert client.get(PATH, headers=auth(token)).status_code == 404

    def test_a_tag_key_nobody_used_still_exports_the_whole_period(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # Every row lands in the unallocated bucket rather than the file being empty.
        # An export returning nothing because a tag key was misspelled would look like
        # an estate with no spend.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        body = download(client, token, "?tag=nobody-uses-this")
        assert {row["tag_value"] for row in parsed(body)} == {UNALLOCATED}
        assert summed(body, "effective_cost_amortized_usd") == total_on_screen(
            client, token, "effective_cost"
        )
