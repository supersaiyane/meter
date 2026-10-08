"""AWS's price list and instance types, as Meter holds them. FEAT-071, FEAT-072, TASK-P9-010.

Two routes, P9 spec section 8, both reads of what the catalog collectors stored and neither a
call to AWS. Every row says which price list version it is from and when it was true at the
source, constraint 10, and the envelope counts coverage in Regions, because the catalog is about
Regions and not about accounts: one Region shown of thirty held is a partial view, and saying
`1 of 1 accounts` over it would be a claim about the wrong thing.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.catalog import (
    InstanceTypeRepository,
    PriceListVersionRepository,
    PriceRepository,
)
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.exports import ExportSpec, exportable, rows_in
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import (
    Envelope,
    InstanceTypeOut,
    InstanceTypesOut,
    PriceOut,
    PricesOut,
)
from finops_core.domain.catalog import PricingCategory
from finops_core.domain.tenant import Scope

router = APIRouter(prefix=API_PREFIX, tags=["catalog"])

#: The service a filter names when it names none: EC2 is what a rightsizing is priced from.
EC2 = "AmazonEC2"
REGIONS = "Regions"


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(value)


def _regions(rows: Any) -> int:
    return len({row.region for row in rows})


@router.get("/catalog/instance-types", response_model=Envelope[InstanceTypesOut])
@exportable(
    ExportSpec(title="Instance types", row_model=InstanceTypeOut, rows=rows_in("instance_types"))
)
def instance_types(
    service: str = EC2,
    region: str | None = None,
    family: str | None = None,
    architecture: str | None = None,
    vcpus: int | None = Query(default=None, ge=1),
    memory_mib: int | None = Query(default=None, ge=1),
    offered: bool = True,
    limit: int = Query(default=500, ge=1, le=5000),
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[InstanceTypesOut]:
    """The types that match, filtered by family, architecture, vCPUs and memory."""
    rows = InstanceTypeRepository(connection, context).matching(
        scope,
        service=service,
        region=region,
        family=family,
        architecture=architecture,
        vcpus=vcpus,
        memory_mib=memory_mib,
        offered=offered,
        limit=limit,
    )
    data = InstanceTypesOut(
        instance_types=[
            InstanceTypeOut(
                service_code=row.service_code,
                region=row.region,
                instance_type=row.instance_type,
                family=row.family,
                current_generation=row.current_generation,
                architectures=list(row.architectures),
                burstable=row.burstable,
                baseline_cpu=_decimal(row.baseline_cpu),
                vcpus=row.vcpus,
                memory_mib=row.memory_mib,
                network_performance=row.network_performance,
                network_baseline_gbps=_decimal(row.network_baseline_gbps),
                ebs_baseline_mbps=row.ebs_baseline_mbps,
                gpu_count=row.gpu_count,
                offered=row.offered,
                as_of=row.as_of,
                collected_at=row.collected_at,
            )
            for row in rows
        ],
        limit_reached=len(rows) == limit,
    )
    held = PriceListVersionRepository(connection, context).regions_held(scope, service)
    meta = build_meta(
        connection,
        scope,
        context,
        visible=_regions(rows),
        rows=rows,
        coverage=(_regions(rows), held),
        coverage_unit=REGIONS,
    )
    return Envelope(data=data, meta=meta)


@router.get("/catalog/prices", response_model=Envelope[PricesOut])
@exportable(ExportSpec(title="Prices", row_model=PriceOut, rows=rows_in("prices")))
def prices(
    service: str = EC2,
    region: str | None = None,
    sku: str | None = None,
    instance_type: str | None = None,
    pricing_category: PricingCategory | None = None,
    version: str | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[PricesOut]:
    """The prices that match, from the version named or each Region's newest."""
    rows = PriceRepository(connection, context).matching(
        scope,
        service=service,
        region=region,
        sku=sku,
        instance_type=instance_type,
        pricing_category=None if pricing_category is None else pricing_category.value,
        version=version,
        limit=limit,
    )
    data = PricesOut(
        prices=[
            PriceOut(
                sku_price_id=row.sku_price_id,
                sku=row.sku,
                service_code=row.service_code,
                region=row.region,
                version=row.version,
                pricing_category=row.pricing_category,
                pricing_unit=row.pricing_unit,
                currency=row.currency,
                recurring_unit_price=Decimal(row.recurring_unit_price),
                upfront_fee=Decimal(row.upfront_fee),
                lease_years=row.lease_years,
                purchase_option=row.purchase_option,
                offering_class=row.offering_class,
                details={str(k): str(v) for k, v in (row.sku_price_details or {}).items()},
                effective_date=row.effective_date,
                as_of=row.as_of,
                collected_at=row.collected_at,
            )
            for row in rows
        ],
        limit_reached=len(rows) == limit,
    )
    held = PriceListVersionRepository(connection, context).regions_held(scope, service)
    meta = build_meta(
        connection,
        scope,
        context,
        visible=_regions(rows),
        rows=rows,
        coverage=(_regions(rows), held),
        coverage_unit=REGIONS,
    )
    return Envelope(data=data, meta=meta)
