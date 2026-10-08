"""The catalog's two routes, called through the client. TASK-P9-010, P9 spec section 8.

The fake catalog sells every estate type in three Regions, on demand and in six reservations,
at version 20260820000000, and describes each type as the EC2 documentation does.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from finops_core.config import Settings
from finops_fakes.catalog import PUBLISHED, VERSION, on_demand_hourly
from finops_fakes.estate_shape import REGIONS
from tests.api.test_query_routes import auth, client_for
from tests.api.test_waste_routes import everything, get, only
from tests.ingest.collectors.test_waste_targets import catalogued

pytestmark = pytest.mark.integration

TYPES = "/api/v1/catalog/instance-types"
PRICES = "/api/v1/catalog/prices"
HERE = REGIONS[0]


def reader(engine: Engine, tenant: UUID, settings: Settings) -> tuple[TestClient, str]:
    catalogued(engine, tenant)
    return client_for(engine, everything(tenant), settings)


def names(payload: dict[str, Any], key: str = "instance_types") -> set[str]:
    return {row["instance_type"] for row in payload["data"][key]}


class TestInstanceTypes:
    def test_a_type_is_described_as_the_documentation_gives_it(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        client, token = reader(engine, tenant_id, settings)
        payload = get(client, token, f"{TYPES}?region={HERE}")
        m5 = next(r for r in payload["data"]["instance_types"] if r["instance_type"] == "m5.xlarge")
        assert (m5["vcpus"], m5["memory_mib"], m5["architectures"]) == (4, 16384, ["x86_64"])
        assert {row["region"] for row in payload["data"]["instance_types"]} == {HERE}
        # One Region of the three the catalog holds: partial, and counted in Regions.
        assert payload["meta"]["scope_coverage"] == {
            **payload["meta"]["scope_coverage"],
            "visible": 1,
            "total": len(REGIONS),
            "unit": "Regions",
        }

    def test_family_architecture_vcpus_and_memory_each_narrow_the_list(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        client, token = reader(engine, tenant_id, settings)
        family = get(client, token, f"{TYPES}?region={HERE}&family=m5")
        assert names(family) == {"m5.large", "m5.xlarge", "m5.2xlarge", "m5.4xlarge"}
        graviton = get(client, token, f"{TYPES}?region={HERE}&architecture=arm64")
        assert names(graviton) == {"m6g.xlarge"}
        sized = get(client, token, f"{TYPES}?region={HERE}&vcpus=4&memory_mib=16384")
        assert names(sized) == {"m5.xlarge", "m6g.xlarge", "m6i.xlarge", "g4dn.xlarge"}

    def test_a_limit_that_cuts_the_list_says_so(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        client, token = reader(engine, tenant_id, settings)
        payload = get(client, token, f"{TYPES}?region={HERE}&limit=2")
        assert len(payload["data"]["instance_types"]) == 2
        assert payload["data"]["limit_reached"] is True


class TestPrices:
    def test_a_price_says_which_list_it_is_from_and_when_that_was_true(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        client, token = reader(engine, tenant_id, settings)
        payload = get(
            client,
            token,
            f"{PRICES}?region={HERE}&instance_type=m5.xlarge&pricing_category=Standard",
        )
        (price,) = payload["data"]["prices"]
        assert Decimal(price["recurring_unit_price"]) == on_demand_hourly("m5.xlarge")
        assert (price["version"], price["pricing_unit"]) == (VERSION, "Hrs")
        assert price["details"]["instanceType"] == "m5.xlarge"
        assert datetime.fromisoformat(price["as_of"]) == PUBLISHED
        assert payload["meta"]["as_of"]

    def test_the_six_reservations_are_committed_prices(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        client, token = reader(engine, tenant_id, settings)
        payload = get(
            client,
            token,
            f"{PRICES}?region={HERE}&instance_type=m5.xlarge&pricing_category=Committed",
        )
        found = payload["data"]["prices"]
        assert len(found) == 6
        assert {(p["lease_years"], p["purchase_option"]) for p in found} == {
            (years, option)
            for years in (1, 3)
            for option in ("No Upfront", "Partial Upfront", "All Upfront")
        }

    def test_a_version_the_catalog_does_not_hold_has_no_prices(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        client, token = reader(engine, tenant_id, settings)
        assert get(client, token, f"{PRICES}?version=19990101000000")["data"]["prices"] == []

    def test_a_pricing_category_outside_focus_is_refused(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        client, token = reader(engine, tenant_id, settings)
        response = client.get(f"{PRICES}?pricing_category=Cheap", headers=auth(token))
        assert response.status_code == 422

    def test_a_reader_narrowed_to_one_account_sees_the_same_price_list(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        client, token = reader(engine, tenant_id, settings)
        narrowed, narrowed_token = client_for(engine, only(tenant_id, "fake-platform-b"), settings)
        path = f"{PRICES}?region={HERE}&instance_type=m5.xlarge"
        assert get(client, token, path)["data"] == get(narrowed, narrowed_token, path)["data"]

    def test_the_prices_export_as_a_file(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        client, token = reader(engine, tenant_id, settings)
        response = client.get(
            f"{PRICES}?region={HERE}&instance_type=m5.xlarge&format=csv", headers=auth(token)
        )
        assert response.status_code == 200, response.text
        assert VERSION in response.text
