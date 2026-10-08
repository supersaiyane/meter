"""What the catalog holds for a Region, as the collectors that price a recommendation read it.

TASK-P9-007. One definition of the comparable price, shared by the recommendation collector,
which prices Compute Optimizer's options, TASK-P9-006, and `waste_compute`, which names Meter's own
target: the newest EC2 version for the Region, on demand, by the hour, the operating system asked
for, shared tenancy, used capacity, nothing preinstalled, no licence, and not an Extended Support
surcharge, FEAT-071. Two copies of that filter are how two screens quote two prices for one type.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Final

from sqlalchemy import text

from finops_query.targets import TypeOffer

EC2: Final = "AmazonEC2"
#: The operating system a price is quoted for when the source names none.
LINUX: Final = "Linux"

#: The newest EC2 price list version the catalog holds for a Region.
LATEST_VERSION = text(
    "SELECT version FROM price_list_version WHERE tenant_id = :t AND service_code = :s "
    "AND region = :r ORDER BY as_of DESC LIMIT 1"
)

_COMPARABLE = (
    "p.tenant_id = :t AND p.service_code = :s AND p.region = :r AND p.version = :v "
    "AND p.pricing_category = 'Standard' AND p.pricing_unit = 'Hrs' "
    "AND p.sku_price_details ->> 'operatingSystem' = :os "
    "AND coalesce(p.sku_price_details ->> 'tenancy', 'Shared') = 'Shared' "
    "AND coalesce(p.sku_price_details ->> 'capacitystatus', 'Used') = 'Used' "
    "AND coalesce(p.sku_price_details ->> 'preInstalledSw', 'NA') = 'NA' "
    "AND coalesce(p.sku_price_details ->> 'licenseModel', 'No License required') "
    "= 'No License required' "
    "AND (p.sku_price_details ->> 'extendedSupport') IS NULL"
)

PRICE_OF = text(
    "SELECT p.sku_price_id, p.recurring_unit_price FROM price p WHERE "
    + _COMPARABLE
    + " AND p.sku_price_details ->> 'instanceType' = :type ORDER BY p.sku_price_id LIMIT 1"
)

#: Every type described as offered in the Region, with its comparable price where one is held.
OFFERS = text(
    "SELECT s.instance_type, s.vcpus, s.memory_mib, s.architectures, s.burstable, "
    "s.network_baseline_gbps, s.ebs_baseline_mbps, price.sku_price_id, "
    "price.recurring_unit_price "
    "FROM instance_type_spec s LEFT JOIN LATERAL ("
    "  SELECT p.sku_price_id, p.recurring_unit_price FROM price p WHERE "
    + _COMPARABLE
    + "  AND p.sku_price_details ->> 'instanceType' = s.instance_type "
    "  ORDER BY p.sku_price_id LIMIT 1"
    ") price ON true "
    "WHERE s.tenant_id = :t AND s.service_code = :s AND s.region = :r AND s.offered"
)


def latest_version(connection: Any, tenant: object, region: str) -> str | None:
    found = connection.execute(LATEST_VERSION, {"t": tenant, "s": EC2, "r": region}).scalar()
    return None if found is None else str(found)


def price_of(
    connection: Any,
    tenant: object,
    region: str,
    version: str,
    instance_type: str,
    operating_system: str = LINUX,
) -> tuple[str, Decimal] | None:
    """A type's comparable price in one version, as its price id and hourly figure."""
    row = connection.execute(
        PRICE_OF,
        {
            "t": tenant,
            "s": EC2,
            "r": region,
            "v": version,
            "type": instance_type,
            "os": operating_system,
        },
    ).first()
    return None if row is None else (str(row[0]), Decimal(row[1]))


def offers(
    connection: Any, tenant: object, region: str, version: str, operating_system: str = LINUX
) -> dict[str, TypeOffer]:
    """Every type offered in the Region, by name, priced from `version` where it can be."""
    rows = connection.execute(
        OFFERS, {"t": tenant, "s": EC2, "r": region, "v": version, "os": operating_system}
    )
    return {
        row.instance_type: TypeOffer(
            instance_type=row.instance_type,
            vcpus=int(row.vcpus),
            memory_mib=int(row.memory_mib),
            architectures=tuple(row.architectures),
            burstable=bool(row.burstable),
            hourly_price=(
                None if row.recurring_unit_price is None else Decimal(row.recurring_unit_price)
            ),
            sku_price_id=row.sku_price_id,
            network_baseline_gbps=row.network_baseline_gbps,
            ebs_baseline_mbps=row.ebs_baseline_mbps,
        )
        for row in rows
    }
