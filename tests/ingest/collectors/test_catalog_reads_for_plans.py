"""The catalog as a plan is priced from it. TASK-P16-003, FEAT-095, spec section 5.4.

`StoredCatalogue` reads the newest version held for a service and Region, the comparable instance
price every other collector reads, and each term of an EBS volume type, refusing two prices for
one term rather than choosing between tiers.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_ingest.collectors.catalog_reads import StoredCatalogue
from finops_query.plan_pricing import Quote, price_change
from finops_query.plan_reading import PlannedChange

pytestmark = pytest.mark.integration

REGION = "eu-west-1"
VERSION = "20261001000000"
OLDER = "20260901000000"
AT = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


def shelve(engine: Engine, tenant: UUID, version: str, published: datetime) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO price_list_version (version_pk, tenant_id, ingest_run_id, "
                "service_code, region, version, row_count, as_of, collected_at) VALUES "
                "(:pk, :t, :run, 'AmazonEC2', :r, :v, 1, :as_of, :at)"
            ),
            {
                "pk": uuid4(),
                "t": tenant,
                "run": uuid4(),
                "r": REGION,
                "v": version,
                "as_of": published,
                "at": AT,
            },
        )


def price(
    engine: Engine,
    tenant: UUID,
    details: dict[str, Any],
    unit: str,
    amount: str,
    *,
    version: str = VERSION,
) -> str:
    sku = uuid4().hex[:16].upper()
    sku_price_id = f"{sku}.{uuid4().hex[:10].upper()}"
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO price (price_pk, tenant_id, ingest_run_id, service_code, region, sku, "
                "sku_price_id, sku_meter, pricing_unit, pricing_category, currency, "
                "recurring_unit_price, upfront_fee, sku_price_details, effective_date, version, "
                "as_of, collected_at) VALUES (:pk, :t, :run, 'AmazonEC2', :r, :sku, :id, :meter, "
                ":unit, 'Standard', 'USD', :amount, 0, CAST(:details AS jsonb), :effective, :v, "
                ":at, :at)"
            ),
            {
                "pk": uuid4(),
                "t": tenant,
                "run": uuid4(),
                "r": REGION,
                "sku": sku,
                "id": sku_price_id,
                "meter": "EU-Usage",
                "unit": unit,
                "amount": Decimal(amount),
                "details": json.dumps(details),
                "effective": date(2026, 10, 1),
                "v": version,
                "at": AT,
            },
        )
    return sku_price_id


def linux(instance_type: str, **more: str) -> dict[str, str]:
    return {"instanceType": instance_type, "operatingSystem": "Linux", **more}


def catalogue(engine: Engine, tenant: UUID) -> tuple[Any, StoredCatalogue]:
    connection = engine.connect()
    return connection, StoredCatalogue(connection, tenant)


def test_an_instance_hour_is_the_comparable_price_at_the_newest_version(
    engine: Engine, tenant_id: UUID
) -> None:
    shelve(engine, tenant_id, OLDER, datetime(2026, 9, 1, tzinfo=UTC))
    shelve(engine, tenant_id, VERSION, datetime(2026, 10, 1, tzinfo=UTC))
    price(engine, tenant_id, linux("m6i.large"), "Hrs", "0.120", version=OLDER)
    wanted = price(engine, tenant_id, linux("m6i.large", tenancy="Shared"), "Hrs", "0.107")
    windows = {"instanceType": "m6i.large", "operatingSystem": "Windows"}
    price(engine, tenant_id, windows, "Hrs", "0.199")
    price(engine, tenant_id, linux("m6i.large", extendedSupport="true"), "Hrs", "0.050")
    connection, shelf = catalogue(engine, tenant_id)
    with connection:
        assert shelf.instance_hour(REGION, "m6i.large") == Quote(
            sku_price_id=wanted, unit_price=Decimal("0.107"), unit="Hrs", version=VERSION
        )
        assert shelf.instance_hour(REGION, "x9z.huge") == (
            f"the catalog holds no on demand Linux price for x9z.huge in {REGION}, "
            f"version {VERSION}"
        )
        assert shelf.instance_hour("ap-east-9", "m6i.large") == (
            "the catalog holds no AmazonEC2 prices for ap-east-9"
        )


def test_each_volume_term_is_read_by_its_unit_and_tiers_are_refused(
    engine: Engine, tenant_id: UUID
) -> None:
    shelve(engine, tenant_id, VERSION, datetime(2026, 10, 1, tzinfo=UTC))
    storage = price(engine, tenant_id, {"volumeApiName": "gp3"}, "GB-Mo", "0.088")
    price(engine, tenant_id, {"volumeApiName": "gp3"}, "IOPS-Mo", "0.0055")
    throughput = price(engine, tenant_id, {"volumeApiName": "gp3"}, "GiBps-mo", "0.044")
    price(engine, tenant_id, {"volumeApiName": "io2"}, "IOPS-Mo", "0.072")
    price(engine, tenant_id, {"volumeApiName": "io2"}, "IOPS-Mo", "0.050")
    connection, shelf = catalogue(engine, tenant_id)
    with connection:
        assert shelf.volume_month(REGION, "gp3", "storage") == Quote(
            sku_price_id=storage, unit_price=Decimal("0.088"), unit="GB-Mo", version=VERSION
        )
        read = shelf.volume_month(REGION, "gp3", "throughput")
        assert isinstance(read, Quote)
        assert (read.sku_price_id, read.unit_price) == (throughput, Decimal("0.044"))
        assert shelf.volume_month(REGION, "io2", "iops") == (
            f"the catalog holds 2 io2 iops prices in {REGION}, tiers it does not tell apart"
        )
        assert shelf.volume_month(REGION, "sc1", "storage") == (
            f"the catalog holds no sc1 storage price in {REGION}, version {VERSION}"
        )
        assert shelf.volume_month("ap-east-9", "gp3", "storage") == (
            "the catalog holds no AmazonEC2 prices for ap-east-9"
        )


def test_a_planned_instance_is_priced_from_what_is_stored(engine: Engine, tenant_id: UUID) -> None:
    shelve(engine, tenant_id, VERSION, datetime(2026, 10, 1, tzinfo=UTC))
    price(engine, tenant_id, linux("m6i.large"), "Hrs", "0.107")
    price(engine, tenant_id, {"volumeApiName": "gp3"}, "GB-Mo", "0.088")
    change = PlannedChange(
        address="aws_instance.web",
        resource_type="aws_instance",
        actions=("create",),
        region=REGION,
        before={},
        after={
            "instance_type": "m6i.large",
            "root_block_device": [{"volume_type": "gp3", "volume_size": 50}],
        },
    )
    connection, shelf = catalogue(engine, tenant_id)
    with connection:
        line = price_change(change, shelf)
    assert line.monthly_after == Decimal("82.51")
