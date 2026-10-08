"""What a rightsizing was compared with, called through the client. TASK-P9-010.

Compute Optimizer's fake finding on `i-oversized` moves an m5.xlarge and ranks m6i.large, then
m6g.large, which the fake catalog neither prices nor describes, then m5.large. Meter's own planted
m5.2xlarge, with no agent, may only step once in its family, to m5.xlarge.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from finops_core.config import Settings
from finops_fakes.catalog import VERSION, on_demand_hourly
from finops_query.targets import HOURS_PER_MONTH
from tests.api.test_query_routes import auth, client_for
from tests.api.test_waste_routes import LIST_PATH, everything, get, only, seed
from tests.ingest.collectors.test_waste_targets import OVERSIZED, candidates, catalogued, collect

pytestmark = pytest.mark.integration

CENT = Decimal("0.01")


def monthly(hourly: Decimal) -> Decimal:
    return (hourly * HOURS_PER_MONTH).quantize(CENT)


def finding(client: TestClient, token: str, resource: str) -> dict[str, Any]:
    rows = get(client, token)["data"]["recommendations"]
    found = next(row for row in rows if row["resource_id"] == resource)
    assert isinstance(found, dict)
    return found


def alternatives_of(client: TestClient, token: str, recommendation_id: str) -> dict[str, Any]:
    data = get(client, token, f"{LIST_PATH}/{recommendation_id}/alternatives")["data"]
    assert isinstance(data, dict)
    return data


class TestComputeOptimizersOptions:
    def test_the_finding_carries_its_target_and_both_list_prices(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        catalogued(engine, tenant_id)
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        found = finding(client, token, "i-oversized")
        assert (found["current_instance_type"], found["target_instance_type"]) == (
            "m5.xlarge",
            "m6i.large",
        )
        assert Decimal(found["current_hourly_price"]) == on_demand_hourly("m5.xlarge")
        assert Decimal(found["target_hourly_price"]) == on_demand_hourly("m6i.large")
        assert found["price_version"] == VERSION
        assert found["added_monthly_cost"] is None

    def test_the_chosen_type_leads_and_every_option_is_priced_or_says_why(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        catalogued(engine, tenant_id)
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        data = alternatives_of(
            client, token, finding(client, token, "i-oversized")["recommendation_id"]
        )
        assert data["current_instance_type"] == "m5.xlarge"
        assert data["price_version"] == VERSION
        names = [row["instance_type"] for row in data["alternatives"]]
        assert names == ["m6i.large", "m6g.large", "m5.large"]
        chosen, graviton, older = data["alternatives"]
        assert [row["chosen"] for row in data["alternatives"]] == [True, False, False]
        assert (chosen["vcpus"], chosen["memory_mib"]) == (2, 8192)
        hourly = on_demand_hourly("m6i.large")
        assert Decimal(chosen["hourly_price"]) == hourly
        assert Decimal(chosen["monthly_price"]) == monthly(hourly)
        assert Decimal(chosen["monthly_saving"]) == monthly(
            on_demand_hourly("m5.xlarge")
        ) - monthly(hourly)
        assert Decimal(chosen["performance_risk"]) == Decimal("1.0")
        # Neither priced nor described, and kept with the reason rather than dropped.
        assert graviton["hourly_price"] is None
        assert graviton["monthly_saving"] is None
        assert graviton["unpriced_reason"]
        assert graviton["vcpus"] is None
        assert graviton["platform_differences"] == ["Architecture"]
        assert Decimal(older["hourly_price"]) == on_demand_hourly("m5.large")

    def test_the_alternatives_export_as_a_file(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        catalogued(engine, tenant_id)
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        recommendation = finding(client, token, "i-oversized")["recommendation_id"]
        response = client.get(
            f"{LIST_PATH}/{recommendation}/alternatives?format=csv", headers=auth(token)
        )
        assert response.status_code == 200, response.text
        assert "m6i.large" in response.text
        assert "m5.large" in response.text


class TestMetersOwn:
    def test_the_types_the_rule_found_to_fit_carry_no_risk_score(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        catalogued(engine, tenant_id)
        collect(engine, tenant_id, settings, candidates())
        client, token = client_for(engine, everything(tenant_id), settings)
        found = finding(client, token, OVERSIZED)
        assert (found["current_instance_type"], found["target_instance_type"]) == (
            "m5.2xlarge",
            "m5.xlarge",
        )
        (only_type,) = alternatives_of(client, token, found["recommendation_id"])["alternatives"]
        assert (only_type["instance_type"], only_type["chosen"], only_type["rank"]) == (
            "m5.xlarge",
            True,
            1,
        )
        assert only_type["performance_risk"] is None
        assert Decimal(only_type["monthly_saving"]) > 0


class TestWhatItWillNotSay:
    def test_a_reader_who_cannot_see_the_finding_cannot_see_what_it_was_compared_with(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        catalogued(engine, tenant_id)
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        recommendation = finding(client, token, "i-oversized")["recommendation_id"]
        narrowed, narrowed_token = client_for(engine, only(tenant_id, "fake-platform-b"), settings)
        response = narrowed.get(
            f"{LIST_PATH}/{recommendation}/alternatives", headers=auth(narrowed_token)
        )
        assert response.status_code == 404

    def test_a_finding_that_names_no_target_has_no_alternatives(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        catalogued(engine, tenant_id)
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        rows = get(client, token)["data"]["recommendations"]
        untargeted = next(row for row in rows if row["waste_class"] != "RIGHTSIZE_INSTANCE")
        assert untargeted["target_instance_type"] is None
        data = alternatives_of(client, token, untargeted["recommendation_id"])
        assert data["alternatives"] == []


def test_one_recommendation_shown_whole_is_not_a_partial_view(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    catalogued(engine, tenant_id)
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    recommendation = finding(client, token, "i-oversized")["recommendation_id"]
    meta = get(client, token, f"{LIST_PATH}/{recommendation}/alternatives")["meta"]
    coverage = meta["scope_coverage"]
    assert (coverage["visible"], coverage["total"], coverage["unit"]) == (1, 1, "recommendations")
    assert coverage["is_partial"] is False
