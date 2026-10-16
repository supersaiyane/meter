"""Each plan received, priced, its estimate written. TASK-P16-005, FEAT-095, spec 5.7 and 7.

The collector prices every plan `RECEIVED` from the tenant's own catalog and writes the estimate and
a line per change, the figures where it priced and the reason where it could not, then marks the
plan `PRICED`. A plan already priced, or refused, is not priced again.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_ingest.collectors.plan_estimates import COLLECTOR, PlanEstimatesCollector
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.plan_records import PlanTarget, record_plan
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.plan_pricing import LINUX, NO_REGION
from finops_query.plan_reading import PlannedChange, ReducedPlan, Unreadable

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
REGION = "eu-west-1"
VERSION = "20261001000000"


def shelve(engine: Engine, tenant: UUID) -> None:
    """An EC2 version holding m6i.large on demand as Linux and gp3's storage."""
    rows = [
        ({"instanceType": "m6i.large", "operatingSystem": "Linux"}, "Hrs", "0.107"),
        ({"volumeApiName": "gp3"}, "GB-Mo", "0.088"),
    ]
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO price_list_version (version_pk, tenant_id, ingest_run_id, "
                "service_code, region, version, row_count, as_of, collected_at) VALUES "
                "(:pk, :t, :run, 'AmazonEC2', :r, :v, 2, :at, :at)"
            ),
            {"pk": uuid4(), "t": tenant, "run": uuid4(), "r": REGION, "v": VERSION, "at": NOW},
        )
        for details, unit, amount in rows:
            sku = uuid4().hex[:16].upper()
            connection.execute(
                text(
                    "INSERT INTO price (price_pk, tenant_id, ingest_run_id, service_code, region, "
                    "sku, sku_price_id, sku_meter, pricing_unit, pricing_category, currency, "
                    "recurring_unit_price, upfront_fee, sku_price_details, effective_date, "
                    "version, as_of, collected_at) VALUES (:pk, :t, :run, 'AmazonEC2', :r, :sku, "
                    ":id, 'EU-Usage', :unit, 'Standard', 'USD', :amount, 0, "
                    "CAST(:details AS jsonb), :effective, :v, :at, :at)"
                ),
                {
                    "pk": uuid4(),
                    "t": tenant,
                    "run": uuid4(),
                    "r": REGION,
                    "sku": sku,
                    "id": f"{sku}.JRTCKXETXF",
                    "unit": unit,
                    "amount": Decimal(amount),
                    "details": json.dumps(details),
                    "effective": date(2026, 10, 1),
                    "v": VERSION,
                    "at": NOW,
                },
            )


def change(address: str, resource_type: str, **fields: Any) -> PlannedChange:
    return PlannedChange(
        address=address,
        resource_type=resource_type,
        actions=fields.pop("actions", ("create",)),
        region=fields.pop("region", REGION),
        before=fields.pop("before", {}),
        after=fields.pop("after", {}),
    )


WEB = {
    "instance_type": "m6i.large",
    "root_block_device": [{"volume_type": "gp3", "volume_size": 50}],
}
MIXED = (
    change("aws_instance.web", "aws_instance", after=WEB),
    change(
        "aws_ebs_volume.old",
        "aws_ebs_volume",
        actions=("delete",),
        before={"type": "gp3", "size": 100},
    ),
    change("aws_nat_gateway.out", "aws_nat_gateway"),
    change("aws_ebs_volume.lost", "aws_ebs_volume", region=None, after={"type": "gp3", "size": 10}),
)


def received(engine: Engine, tenant: UUID, found: Any, head: str = "abc1234def") -> UUID:
    target = PlanTarget("acme/infra", 7, head, "storage")
    with engine.begin() as connection:
        return record_plan(connection, tenant, target, found, route="test", now=NOW)


def run(engine: Engine, tenant: UUID) -> CollectorOutcome:
    work = WorkUnit(
        tenant_id=tenant,
        collector=COLLECTOR,
        window_start=NOW - timedelta(minutes=10),
        window_end=NOW,
    )
    collector = PlanEstimatesCollector(clock=lambda: NOW + timedelta(minutes=5))
    with engine.begin() as connection:
        return collector(CollectorContext(unit=work, connection=connection, run_id=uuid4()))


def read(engine: Engine, sql: str, plan_id: UUID) -> list[Any]:
    with engine.connect() as connection:
        return list(connection.execute(text(sql), {"p": plan_id}).all())


def test_each_plan_received_is_priced_line_by_line_and_marked_priced(
    engine: Engine, tenant_id: UUID
) -> None:
    shelve(engine, tenant_id)
    plan_id = received(engine, tenant_id, ReducedPlan("1.2", "1.9.8", None, MIXED))
    assert run(engine, tenant_id).items_written == 1
    (status,) = read(engine, "SELECT status FROM terraform_plan WHERE plan_id = :p", plan_id)
    assert status.status == "PRICED"
    (estimate,) = read(engine, "SELECT * FROM plan_estimate WHERE plan_id = :p", plan_id)
    assert (estimate.monthly_before, estimate.monthly_after, estimate.monthly_change) == (
        Decimal("8.8"),
        Decimal("82.51"),
        Decimal("73.71"),
    )
    assert (estimate.priced_lines, estimate.unpriced_lines, estimate.currency) == (2, 2, "USD")
    assert estimate.as_of == NOW
    assert estimate.priced_at == NOW + timedelta(minutes=5)
    lines = {
        one.address: one
        for one in read(engine, "SELECT * FROM plan_estimate_line WHERE plan_id = :p", plan_id)
    }
    web = lines["aws_instance.web"]
    assert (web.monthly_before, web.monthly_after, web.reason) == (None, Decimal("82.51"), None)
    assert web.notes == [LINUX]
    hours, storage = web.components
    # The catalog's own figure, kept to the places the catalog stores it.
    assert (hours["side"], Decimal(hours["unit_price"]), hours["quantity"], hours["version"]) == (
        "after",
        Decimal("0.107"),
        "730",
        VERSION,
    )
    assert Decimal(hours["monthly"]) == Decimal("78.11")
    assert storage["what"] == "gp3 storage, 50 GiB"
    old = lines["aws_ebs_volume.old"]
    assert (old.monthly_before, old.monthly_after) == (Decimal("8.8"), None)
    nat = lines["aws_nat_gateway.out"]
    assert (nat.monthly_before, nat.monthly_after, nat.components) == (None, None, [])
    assert nat.reason == "aws_nat_gateway is billed by use, which a plan does not say"
    assert lines["aws_ebs_volume.lost"].reason == NO_REGION


def test_a_plan_priced_or_refused_is_not_priced_again(engine: Engine, tenant_id: UUID) -> None:
    shelve(engine, tenant_id)
    received(engine, tenant_id, ReducedPlan("1.2", None, None, MIXED[:1]))
    received(engine, tenant_id, Unreadable("not JSON"), head="0f0f0f0f")
    assert run(engine, tenant_id).items_written == 1
    assert run(engine, tenant_id).items_written == 0
    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM plan_estimate WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar_one()
    assert count == 1


def test_a_plan_changing_nothing_billed_has_an_estimate_of_nothing(
    engine: Engine, tenant_id: UUID
) -> None:
    plan_id = received(engine, tenant_id, ReducedPlan("1.2", None, None, ()))
    assert run(engine, tenant_id).items_written == 1
    (estimate,) = read(engine, "SELECT * FROM plan_estimate WHERE plan_id = :p", plan_id)
    assert (estimate.monthly_change, estimate.priced_lines, estimate.unpriced_lines) == (
        Decimal("0"),
        0,
        0,
    )


def test_a_tenant_with_no_catalog_is_told_so_line_by_line(engine: Engine, tenant_id: UUID) -> None:
    plan_id = received(engine, tenant_id, ReducedPlan("1.2", None, None, MIXED[:1]))
    run(engine, tenant_id)
    (line,) = read(engine, "SELECT * FROM plan_estimate_line WHERE plan_id = :p", plan_id)
    assert line.reason == f"the catalog holds no AmazonEC2 prices for {REGION}"
    assert (line.monthly_before, line.monthly_after) == (None, None)
