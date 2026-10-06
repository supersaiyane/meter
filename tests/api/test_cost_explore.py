"""Cost Explorer's query, called through the client. FEAT-065, TASK-P8-007.

Every figure asserted here is recomputed in Python from the seeded line items, so a test fails
when the query adds up differently from the estate rather than when it differs from a number
somebody once copied down.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from finops_api.db.repositories.explore import NAMED_SERIES
from finops_api.routes import explore as explore_route
from finops_core.config import Settings
from finops_core.domain.cost import CostRecord
from finops_core.domain.explore import Preset, Window, previous, window_for
from finops_core.domain.geography import geography_of
from finops_core.domain.platform import UNALLOCATED
from tests.api.test_cost_routes import CURRENT, ONE_ACCOUNT, everything, only, seed
from tests.api.test_query_routes import auth, client_for

pytestmark = pytest.mark.integration

PATH = "/api/v1/cost/explore"


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


def explore(client: TestClient, token: str, query: str = "") -> dict[str, Any]:
    response = client.get(f"{PATH}?{query}", headers=auth(token))
    assert response.status_code == 200, f"{query} returned {response.status_code}: {response.text}"
    data = response.json()["data"]
    assert isinstance(data, dict)
    return data


def windows(preset: Preset) -> tuple[Window, Window]:
    current = window_for(preset, datetime.now(UTC).date())
    return current, previous(current, preset)


def charged_in(window: Window, rows: Iterable[CostRecord] = CURRENT) -> list[CostRecord]:
    return [
        row
        for row in rows
        if window.start <= row.charge_period_start.astimezone(UTC).date() <= window.end
    ]


def total(rows: Iterable[CostRecord], measure: str = "effective_cost") -> Decimal:
    return sum((Decimal(getattr(row, measure)) for row in rows), Decimal(0))


def money(value: str | None) -> Decimal:
    assert value is not None
    return Decimal(value)


def reconciles(data: dict[str, Any]) -> None:
    """The rows and the omissions add up to the total, whatever the limit left out."""
    shown = sum((Decimal(row["this_period"]) for row in data["rows"]), Decimal(0))
    assert shown + Decimal(data["omitted_this_period"]) == money(data["total_this_period"])


def seed_months(engine: Engine, tenant: UUID) -> None:
    """One collector run per billing month, oldest first, the way a backfill arrives.

    One run over the whole estate collects only its newest month, which left the comparison
    with nothing to compare against and every test of it asserting about an empty month.
    """
    for month in sorted({row.billing_period_start for row in CURRENT}):
        seed(engine, tenant, tuple(row for row in CURRENT if row.billing_period_start == month))


@pytest.fixture
def seeded(engine: Engine, tenant_id: UUID, settings: Settings) -> tuple[TestClient, str]:
    seed_months(engine, tenant_id)
    return client_for(engine, everything(tenant_id), settings)


class TestTheDefaultView:
    def test_it_is_effective_cost_month_to_date_by_day_and_by_service(
        self, seeded: tuple[TestClient, str]
    ) -> None:
        data = explore(*seeded)
        assert (data["metric"], data["period"], data["granularity"]) == (
            "effective_cost",
            "mtd",
            "daily",
        )
        assert data["group_by"] == {"dimension": "service", "tag_key": None}
        assert data["then_by"] is None

    def test_a_period_ending_today_says_it_is_still_open(
        self, seeded: tuple[TestClient, str]
    ) -> None:
        assert explore(*seeded)["is_open"] is True
        yesterday = datetime.now(UTC).date() - timedelta(days=1)
        closed = explore(*seeded, f"period=custom&start={yesterday}&end={yesterday}")
        assert closed["is_open"] is False

    def test_the_total_is_the_line_items_charged_in_the_window(
        self, seeded: tuple[TestClient, str]
    ) -> None:
        current, before = windows("mtd")
        data = explore(*seeded)
        assert money(data["total_this_period"]) == total(charged_in(current))
        assert data["previous_collected"] is True
        assert money(data["total_previous_period"]) == total(charged_in(before))
        reconciles(data)

    def test_the_chart_adds_up_to_the_same_total(self, seeded: tuple[TestClient, str]) -> None:
        current, _ = windows("mtd")
        data = explore(*seeded)
        plotted = sum((Decimal(point["cost"]) for point in data["points"]), Decimal(0))
        assert plotted == money(data["total_this_period"])
        assert len(data["series"]) <= NAMED_SERIES
        assert all(
            current.start.isoformat() <= point["bucket"] <= current.end.isoformat()
            for point in data["points"]
        )

    def test_a_month_is_one_bucket_on_its_first_day(self, seeded: tuple[TestClient, str]) -> None:
        data = explore(*seeded, "period=3m&granularity=monthly")
        assert {point["bucket"][-2:] for point in data["points"]} == {"01"}


class TestGrouping:
    def test_two_groupings_add_up_to_the_total(self, seeded: tuple[TestClient, str]) -> None:
        current, _ = windows("mtd")
        data = explore(*seeded, "group_by=service&then_by=region")
        services = {row.service_name for row in charged_in(current)}
        assert {row["first"] for row in data["rows"]} <= services
        assert all(row["second"] is not None for row in data["rows"])
        reconciles(data)

    def test_unallocated_is_a_row_and_the_limit_never_drops_it(
        self, seeded: tuple[TestClient, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        current, _ = windows("mtd")
        untagged = [row for row in charged_in(current) if "team" not in row.tags]
        assert untagged, "the estate is meant to have cost nobody tagged"
        monkeypatch.setattr(explore_route, "ROW_LIMIT", 1)
        data = explore(*seeded, "group_by=tag&group_by_tag=team")
        unallocated = [row for row in data["rows"] if row["first"] == UNALLOCATED]
        assert len(unallocated) == 1
        assert money(unallocated[0]["this_period"]) == total(untagged)
        assert data["rows_omitted"] > 0
        reconciles(data)

    def test_the_tag_keys_offered_are_the_period_s_own(
        self, seeded: tuple[TestClient, str]
    ) -> None:
        data = explore(*seeded)
        assert {"team", "finops:module"} <= set(data["tag_keys"])


class TestTheMeasures:
    def test_an_optional_measure_is_offered_only_where_every_line_carries_it(
        self, seeded: tuple[TestClient, str]
    ) -> None:
        current, before = windows("mtd")
        lines = charged_in(current) + charged_in(before)
        data = explore(*seeded)
        offered = set(data["metrics_available"])
        assert {"effective_cost", "billed_cost"} <= offered
        assert ("list_cost" in offered) == all(row.list_cost is not None for row in lines)
        assert ("contracted_cost" in offered) == all(
            row.contracted_cost is not None for row in lines
        )

    def test_billed_cost_sums_the_billed_column(self, seeded: tuple[TestClient, str]) -> None:
        current, _ = windows("mtd")
        data = explore(*seeded, "metric=billed_cost")
        assert money(data["total_this_period"]) == total(charged_in(current), "billed_cost")

    def test_a_measure_some_lines_lack_is_refused_and_says_why(
        self, seeded: tuple[TestClient, str]
    ) -> None:
        client, token = seeded
        response = client.get(f"{PATH}?metric=contracted_cost", headers=auth(token))
        assert response.status_code == 422
        assert "Contracted Cost is not on every line item" in response.text


class TestTheComparison:
    def test_a_previous_period_nobody_collected_is_null_and_never_zero(
        self, seeded: tuple[TestClient, str]
    ) -> None:
        data = explore(*seeded, "period=12m")
        assert data["previous_collected"] is False
        assert data["total_previous_period"] is None
        assert data["omitted_previous_period"] is None
        assert all(row["previous_period"] is None for row in data["rows"])


class TestScopeAndFilters:
    def test_a_narrow_scope_is_served_only_its_own_accounts(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed_months(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, ONE_ACCOUNT), settings)
        current, _ = windows("mtd")
        mine = [row for row in charged_in(current) if row.sub_account_id == ONE_ACCOUNT]
        data = explore(client, token, "group_by=account")
        assert money(data["total_this_period"]) == total(mine)
        assert {row["first"] for row in data["rows"]} == {ONE_ACCOUNT}

    def test_a_column_filter_holds_the_rows_to_its_values(
        self, seeded: tuple[TestClient, str]
    ) -> None:
        current, _ = windows("mtd")
        data = explore(*seeded, "service=AmazonEC2&then_by=region")
        assert {row["first"] for row in data["rows"]} == {"AmazonEC2"}
        ec2 = [row for row in charged_in(current) if row.service_name == "AmazonEC2"]
        assert money(data["total_this_period"]) == total(ec2)

    def test_a_tag_filter_holds_the_rows_to_its_values(
        self, seeded: tuple[TestClient, str]
    ) -> None:
        current, _ = windows("mtd")
        owner = next(row.tags["team"] for row in charged_in(current) if "team" in row.tags)
        data = explore(*seeded, f"tag_key=team&tag_value={owner}")
        theirs = [row for row in charged_in(current) if row.tags.get("team") == owner]
        assert money(data["total_this_period"]) == total(theirs)


class TestRefusals:
    @pytest.mark.parametrize(
        ("query", "said"),
        [
            ("group_by=service&then_by=service", "two different things"),
            ("group_by=resource_id", "not a column"),
            ("group_by=tag", "needs the tag key"),
            ("group_by=tag&group_by_tag=not-a-key-anyone-uses", "most used"),
            ("group_by=service&group_by_tag=team", "goes with a tag grouping"),
            ("period=custom", "needs both a start and an end"),
            ("period=mtd&start=2026-01-01", "go with a custom period"),
            ("tag_key=team", "needs a tag key and at least one value"),
        ],
    )
    def test_a_view_that_cannot_be_drawn_is_refused_and_says_why(
        self, seeded: tuple[TestClient, str], query: str, said: str
    ) -> None:
        client, token = seeded
        response = client.get(f"{PATH}?{query}", headers=auth(token))
        assert response.status_code == 422, response.text
        assert said in response.text

    def test_a_tenant_with_no_cost_is_told_so_rather_than_shown_zero(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        client, token = client_for(engine, everything(tenant_id), settings)
        assert client.get(PATH, headers=auth(token)).status_code == 404


class TestRegionGeographies:
    """TASK-P8-017. A view by region says which geography each region is in, by the one rule."""

    def test_a_view_by_region_places_each_region_by_the_prefix_rule(
        self, seeded: tuple[TestClient, str]
    ) -> None:
        data = explore(*seeded, "group_by=region")
        expected = {}
        for row in data["rows"]:
            placed = geography_of(row["first"])
            if placed is not None:
                expected[row["first"]] = {"key": placed.key, "name": placed.name}
        assert expected, "the estate is meant to bill in a region the table places"
        assert data["region_geographies"] == expected

    def test_any_other_view_places_nothing(self, seeded: tuple[TestClient, str]) -> None:
        # Region as the second grouping included: the placements describe `first`, and a second
        # grouping's regions would have no row of their own to belong to.
        assert explore(*seeded, "group_by=service")["region_geographies"] == {}
        assert explore(*seeded, "group_by=service&then_by=region")["region_geographies"] == {}
