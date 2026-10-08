"""Every invariant of the price catalog is a constraint the database enforces. TASK-P9-003.

Constraint 11: if application code is the only thing preventing a bad row, the bad row will
eventually exist. Each test writes a row that breaks one rule and expects the database to refuse
it by that rule's name, beside a row that keeps every rule and is admitted. The All Upfront case
is the one AWS's own price list taught, spec section 5.3 as corrected on 2026-10-08: nought an hour
beside an upfront fee is a real price and is kept.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError

from finops_api.db import models

pytestmark = pytest.mark.integration

PUBLISHED = datetime(2026, 8, 20, 0, 0, tzinfo=UTC)
AT = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
VERSION = "20260820000000"
REGION = "eu-west-1"


def insert(engine: Engine, table: str, values: dict[str, Any]) -> None:
    """One row, its columns checked against the model so a typo fails here and not in SQL."""
    columns = models.metadata.tables[table].c
    assert set(values) <= set(columns.keys()), set(values) - set(columns.keys())
    marks = [
        f"CAST(:{name} AS jsonb)" if isinstance(columns[name].type, JSONB) else f":{name}"
        for name in values
    ]
    statement = f"INSERT INTO {table} ({', '.join(values)}) VALUES ({', '.join(marks)})"
    with engine.begin() as connection:
        connection.execute(text(statement), values)


def refused(engine: Engine, table: str, values: dict[str, Any], constraint: str) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        insert(engine, table, values)


def version(tenant: UUID, **overrides: Any) -> dict[str, Any]:
    return {
        "version_pk": uuid4(),
        "tenant_id": tenant,
        "ingest_run_id": uuid4(),
        "service_code": "AmazonEC2",
        "region": REGION,
        "version": VERSION,
        "row_count": 7,
        "as_of": PUBLISHED,
        "collected_at": AT,
        **overrides,
    }


def a_version(engine: Engine, tenant: UUID) -> None:
    insert(engine, "price_list_version", version(tenant))


def price(tenant: UUID, **overrides: Any) -> dict[str, Any]:
    return {
        "price_pk": uuid4(),
        "tenant_id": tenant,
        "ingest_run_id": uuid4(),
        "service_code": "AmazonEC2",
        "region": REGION,
        "sku": "ABCDEFGHIJKLMNOP",
        "sku_price_id": f"ABCDEFGHIJKLMNOP.{uuid4().hex[:10].upper()}",
        "sku_meter": "EU-BoxUsage:m5.xlarge",
        "pricing_unit": "Hrs",
        "pricing_category": "Standard",
        "currency": "USD",
        "recurring_unit_price": Decimal("0.1947"),
        "upfront_fee": Decimal(0),
        "lease_years": None,
        "purchase_option": None,
        "offering_class": None,
        "sku_price_details": json.dumps({"instanceType": "m5.xlarge"}),
        "effective_date": date(2026, 8, 1),
        "version": VERSION,
        "as_of": PUBLISHED,
        "collected_at": AT,
        **overrides,
    }


ALL_UPFRONT = {
    "pricing_category": "Committed",
    "recurring_unit_price": Decimal(0),
    "upfront_fee": Decimal("1631.2"),
    "lease_years": 3,
    "purchase_option": "All Upfront",
    "offering_class": "standard",
}


# --- versions --------------------------------------------------------------------------


def test_a_version_is_admitted(engine: Engine, tenant_id: UUID) -> None:
    a_version(engine, tenant_id)


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"row_count": -1}, "ck_price_list_version__rows"),
        ({"collected_at": datetime(2026, 8, 1, tzinfo=UTC)}, "collected_after_true"),
        ({"version": ""}, "ck_price_list_version__named"),
    ],
)
def test_a_version_that_breaks_a_rule_is_refused(
    engine: Engine, tenant_id: UUID, overrides: dict[str, Any], constraint: str
) -> None:
    refused(engine, "price_list_version", version(tenant_id, **overrides), constraint)


# --- prices ----------------------------------------------------------------------------


def test_an_on_demand_price_and_an_all_upfront_one_are_admitted(
    engine: Engine, tenant_id: UUID
) -> None:
    a_version(engine, tenant_id)
    insert(engine, "price", price(tenant_id))
    # Nought an hour beside its fee, as AWS's own price list sells it.
    insert(engine, "price", price(tenant_id, **ALL_UPFRONT))


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"recurring_unit_price": Decimal(0)}, "ck_price__not_both_nought"),
        ({"recurring_unit_price": Decimal("-0.1")}, "ck_price__never_negative"),
        ({"currency": "usd"}, "ck_price__currency_iso"),
        ({"pricing_category": "Committed"}, "ck_price__reservation_named"),
        ({"upfront_fee": Decimal("10")}, "ck_price__on_demand_nothing_up_front"),
        ({**ALL_UPFRONT, "lease_years": 2}, "ck_price__lease"),
        ({**ALL_UPFRONT, "purchase_option": "Some Upfront"}, "ck_price__purchase_option"),
        ({"pricing_category": "Spot"}, "ck_price__category"),
        ({"sku_price_details": "[]"}, "ck_price__details_object"),
        ({"collected_at": datetime(2026, 8, 1, tzinfo=UTC)}, "ck_price__collected_after_true"),
        ({"version": "19990101000000"}, "fk_price__version"),
    ],
)
def test_a_price_that_breaks_a_rule_is_refused(
    engine: Engine, tenant_id: UUID, overrides: dict[str, Any], constraint: str
) -> None:
    a_version(engine, tenant_id)
    refused(engine, "price", price(tenant_id, **overrides), constraint)


def test_one_price_appears_once_in_a_version(engine: Engine, tenant_id: UUID) -> None:
    a_version(engine, tenant_id)
    first = price(tenant_id)
    insert(engine, "price", first)
    refused(engine, "price", {**first, "price_pk": uuid4()}, "uq_price__identity")


# --- instance types --------------------------------------------------------------------


def instance(tenant: UUID, **overrides: Any) -> dict[str, Any]:
    return {
        "spec_pk": uuid4(),
        "tenant_id": tenant,
        "ingest_run_id": uuid4(),
        "service_code": "AmazonEC2",
        "region": REGION,
        "instance_type": f"m5.{uuid4().hex[:6]}",
        "family": "m5",
        "current_generation": True,
        "architectures": ["x86_64"],
        "burstable": False,
        "vcpus": 4,
        "memory_mib": 16384,
        "network_performance": "Up to 10 Gigabit",
        "gpu_count": 0,
        "offered": True,
        "as_of": PUBLISHED,
        "collected_at": AT,
        **overrides,
    }


def test_an_instance_type_and_a_burstable_one_with_its_baseline_are_admitted(
    engine: Engine, tenant_id: UUID
) -> None:
    insert(engine, "instance_type_spec", instance(tenant_id))
    insert(
        engine,
        "instance_type_spec",
        instance(
            tenant_id,
            burstable=True,
            baseline_cpu=Decimal("0.2"),
            maximum_credits=Decimal("576"),
            baseline_source="EC2 guide, burstable baselines",
        ),
    )


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"vcpus": 0}, "ck_instance_type_spec__sized"),
        ({"memory_mib": 0}, "ck_instance_type_spec__sized"),
        ({"gpu_count": -1}, "ck_instance_type_spec__gpus"),
        ({"architectures": []}, "ck_instance_type_spec__architecture"),
        ({"burstable": True}, "ck_instance_type_spec__burstable_has_baseline"),
        (
            {"baseline_cpu": Decimal("1.5"), "baseline_source": "x"},
            "ck_instance_type_spec__baseline_a_share",
        ),
        (
            {"network_baseline_gbps": Decimal("10"), "network_peak_gbps": Decimal("5")},
            "ck_instance_type_spec__network_peak",
        ),
        (
            {"ebs_baseline_mbps": 4750, "ebs_maximum_mbps": 1000},
            "ck_instance_type_spec__ebs_maximum",
        ),
    ],
)
def test_an_instance_type_that_breaks_a_rule_is_refused(
    engine: Engine, tenant_id: UUID, overrides: dict[str, Any], constraint: str
) -> None:
    refused(engine, "instance_type_spec", instance(tenant_id, **overrides), constraint)


# --- volume types --------------------------------------------------------------------


def volume(tenant: UUID, **overrides: Any) -> dict[str, Any]:
    return {
        "volume_pk": uuid4(),
        "tenant_id": tenant,
        "volume_type": f"gp3-{uuid4().hex[:6]}",
        "baseline_iops": 3000,
        "baseline_throughput_mibps": 125,
        "maximum_iops": 16000,
        "maximum_throughput_mibps": 1000,
        "iops_per_gib": None,
        "source": "EBS volume types, the EBS user guide",
        "as_of": PUBLISHED,
        "collected_at": AT,
        **overrides,
    }


def test_a_volume_type_is_admitted(engine: Engine, tenant_id: UUID) -> None:
    insert(engine, "volume_type_spec", volume(tenant_id))


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        # Without a baseline, so the maximum is the one rule broken.
        ({"maximum_iops": 0, "baseline_iops": None}, "ck_volume_type_spec__maxima"),
        ({"baseline_iops": 20000}, "ck_volume_type_spec__baseline_within_maximum"),
        ({"source": "  "}, "ck_volume_type_spec__sourced"),
    ],
)
def test_a_volume_type_that_breaks_a_rule_is_refused(
    engine: Engine, tenant_id: UUID, overrides: dict[str, Any], constraint: str
) -> None:
    refused(engine, "volume_type_spec", volume(tenant_id, **overrides), constraint)


# --- spot --------------------------------------------------------------------------------


def pool(tenant: UUID) -> dict[str, Any]:
    return {
        "tenant_id": tenant,
        "ingest_run_id": uuid4(),
        "region": REGION,
        "availability_zone": "eu-west-1a",
        "instance_type": "m5.xlarge",
        "product_description": "Linux/UNIX",
        "as_of": AT,
        "collected_at": AT,
    }


def test_a_pool_holds_one_latest_price(engine: Engine, tenant_id: UUID) -> None:
    first = {**pool(tenant_id), "spot_pk": uuid4(), "price": Decimal("0.0712")}
    insert(engine, "spot_price", first)
    refused(engine, "spot_price", {**first, "spot_pk": uuid4()}, "uq_spot_price__pool")
    refused(
        engine,
        "spot_price",
        {**pool(tenant_id), "spot_pk": uuid4(), "price": Decimal(0), "instance_type": "c5.large"},
        "ck_spot_price__positive",
    )


@pytest.mark.parametrize(
    ("low", "high", "readings", "constraint"),
    [
        ("0.08", "0.07", 3, "ck_spot_price_daily__low_not_above_high"),
        ("0", "0.07", 3, "ck_spot_price_daily__positive"),
        ("0.07", "0.08", 0, "ck_spot_price_daily__read"),
    ],
)
def test_a_spot_day_that_breaks_a_rule_is_refused(
    engine: Engine, tenant_id: UUID, low: str, high: str, readings: int, constraint: str
) -> None:
    day = {
        **pool(tenant_id),
        "spot_day_pk": uuid4(),
        "day": date(2026, 8, 24),
        "low": Decimal(low),
        "high": Decimal(high),
        "readings": readings,
    }
    refused(engine, "spot_price_daily", day, constraint)


# --- the recommendation's target ---------------------------------------------------------


def recommendation(engine: Engine, tenant: UUID) -> UUID:
    identifier = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, "
                "source, source_reference, waste_class, resource_id, region_id, "
                "estimated_monthly_saving, confidence, severity, observation_days, "
                "lifecycle, rationale, as_of, collected_at) "
                "VALUES (:id, :t, '111122223333', 'METER', :ref, 'IDLE_INSTANCE', :res, "
                ":region, 42, 'HIGH', 'HIGH', 30, 'OPEN', 'because', :at, :at)"
            ),
            {
                "id": identifier,
                "t": tenant,
                "ref": f"ref:{identifier}",
                "res": f"i-{identifier.hex[:8]}",
                "region": REGION,
                "at": AT,
            },
        )
    return identifier


def target(engine: Engine, recommendation_id: UUID, **columns: Any) -> None:
    assignments = ", ".join(f"{name} = :{name}" for name in columns)
    with engine.begin() as connection:
        connection.execute(
            text(f"UPDATE recommendation SET {assignments} WHERE recommendation_id = :id"),
            {**columns, "id": recommendation_id},
        )


def test_a_target_named_by_a_recorded_price_of_one_version_is_admitted(
    engine: Engine, tenant_id: UUID
) -> None:
    a_version(engine, tenant_id)
    current, smaller = price(tenant_id), price(tenant_id, recurring_unit_price=Decimal("0.0974"))
    insert(engine, "price", current)
    insert(engine, "price", smaller)
    target(
        engine,
        recommendation(engine, tenant_id),
        current_sku_price_id=current["sku_price_id"],
        target_instance_type="m5.large",
        target_sku_price_id=smaller["sku_price_id"],
        price_version=VERSION,
    )


@pytest.mark.parametrize(
    ("columns", "constraint"),
    [
        ({"target_instance_type": "m5.large"}, "ck_recommendation__target_priced"),
        (
            {"target_instance_type": "m5.large", "target_sku_price_id": "X.Y"},
            "ck_recommendation__target_priced",
        ),
        ({"current_sku_price_id": "X.Y"}, "ck_recommendation__target_priced"),
        (
            {
                "target_instance_type": "m5.large",
                "target_sku_price_id": "NOTINTHECATALOG.Y",
                "price_version": VERSION,
            },
            "fk_recommendation__target_price",
        ),
    ],
)
def test_a_target_that_names_no_recorded_price_is_refused(
    engine: Engine, tenant_id: UUID, columns: dict[str, Any], constraint: str
) -> None:
    a_version(engine, tenant_id)
    identifier = recommendation(engine, tenant_id)
    with pytest.raises(IntegrityError, match=constraint):
        target(engine, identifier, **columns)
