"""What the catalog holds for a Region, as the collectors that price a recommendation read it.

TASK-P9-007. One definition of the comparable price, shared by the recommendation collector,
which prices Compute Optimizer's options, TASK-P9-006, and `waste_compute`, which names Meter's own
target: the newest EC2 version for the Region, on demand, by the hour, the operating system asked
for, shared tenancy, used capacity, nothing preinstalled, no licence, and not an Extended Support
surcharge, FEAT-071. Two copies of that filter are how two screens quote two prices for one type.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import text

from finops_query.plan_quotes import Quote
from finops_query.targets import TypeOffer
from finops_query.volumes import VolumePrices

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


#: gp2's and gp3's EBS prices in one version, TASK-P9-009.
VOLUME_PRICES = text(
    "SELECT p.sku_price_details ->> 'volumeApiName' AS volume, p.pricing_unit, "
    "p.recurring_unit_price FROM price p WHERE p.tenant_id = :t AND p.service_code = :s "
    "AND p.region = :r AND p.version = :v AND p.pricing_category = 'Standard' "
    "AND p.sku_price_details ->> 'volumeApiName' IN ('gp2', 'gp3') ORDER BY p.sku_price_id"
)
#: Which term of a volume a price is, by the unit it is sold in. A throughput price is read as per
#: MiB/s whichever unit labels it and is never divided by 1,024: dividing a price that was per MiB/s
#: all along would make gp3 look 1,024 times cheaper than it is, where not dividing one that was per
#: GiB/s can only understate a saving. ISS-265.
_TERMS: Final = {
    "gb-mo": "storage",
    "iops-mo": "iops",
    "mibps-mo": "throughput",
    "gibps-mo": "throughput",
}
#: In the order `VolumePrices` takes them.
_WANTED: Final = (("gp2", "storage"), ("gp3", "storage"), ("gp3", "iops"), ("gp3", "throughput"))

#: One EBS volume type's on demand prices in one version, every term, TASK-P16-003.
VOLUME_TERM_PRICES = text(
    "SELECT p.sku_price_id, p.pricing_unit, p.recurring_unit_price FROM price p "
    "WHERE p.tenant_id = :t AND p.service_code = :s AND p.region = :r AND p.version = :v "
    "AND p.pricing_category = 'Standard' AND p.sku_price_details ->> 'volumeApiName' = :name "
    "ORDER BY p.sku_price_id"
)
#: A managed service's on demand prices in one version holding every attribute asked, never an
#: Extended Support surcharge, TASK-P16-004.
SERVICE_PRICES = text(
    "SELECT p.sku_price_id, p.pricing_unit, p.recurring_unit_price FROM price p "
    "WHERE p.tenant_id = :t AND p.service_code = :s AND p.region = :r AND p.version = :v "
    "AND p.pricing_category = 'Standard' AND p.sku_price_details @> CAST(:asked AS jsonb) "
    "AND (p.sku_price_details ->> 'extendedSupport') IS NULL ORDER BY p.sku_price_id"
)
#: Which term a managed service's price is, by its unit, as AWS's RDS, ElastiCache, Redshift and
#: OpenSearch lists spell them: RDS sells throughput per MBPS-Mo, OpenSearch gp3 IOPS per PIOPS-Mo.
_SERVICE_TERMS: Final = {
    "hrs": "hours",
    "gb-mo": "storage",
    "iops-mo": "iops",
    "piops-mo": "iops",
    "mbps-mo": "throughput",
    "mibps-mo": "throughput",
    "gibps-mo": "throughput",
}


def latest_version(connection: Any, tenant: object, region: str, service: str = EC2) -> str | None:
    found = connection.execute(LATEST_VERSION, {"t": tenant, "s": service, "r": region}).scalar()
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


def volume_prices(connection: Any, tenant: object, region: str, version: str) -> VolumePrices | str:
    """The four prices gp2 to gp3 is worked out from, or which of them the catalog lacks."""
    found: dict[tuple[str, str], Decimal] = {}
    rows = connection.execute(VOLUME_PRICES, {"t": tenant, "s": EC2, "r": region, "v": version})
    for row in rows:
        term = _TERMS.get(str(row.pricing_unit).lower())
        if term is not None:
            found.setdefault((row.volume, term), Decimal(row.recurring_unit_price))
    missing = [f"{volume} {term}" for volume, term in _WANTED if (volume, term) not in found]
    if missing:
        return f"the catalog holds no {', '.join(missing)} price in version {version}"
    return VolumePrices(*(found[wanted] for wanted in _WANTED))


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


class StoredCatalogue:
    """The catalog as a plan is priced from it, TASK-P16-003, FEAT-095: for each service and
    Region the newest version held, and from it the comparable price that every other collector
    reads, so an estimate and a recommendation quote one price for one type."""

    def __init__(self, connection: Any, tenant: object) -> None:
        self._connection = connection
        self._tenant = tenant
        self._versions: dict[tuple[str, str], str | None] = {}

    def _version(self, service: str, region: str) -> str | None:
        if (service, region) not in self._versions:
            found = latest_version(self._connection, self._tenant, region, service)
            self._versions[(service, region)] = found
        return self._versions[(service, region)]

    def instance_hour(self, region: str, instance_type: str) -> Quote | str:
        version = self._version(EC2, region)
        if version is None:
            return f"the catalog holds no {EC2} prices for {region}"
        found = price_of(self._connection, self._tenant, region, version, instance_type)
        if found is None:
            return (
                f"the catalog holds no on demand Linux price for {instance_type} in {region}, "
                f"version {version}"
            )
        return Quote(sku_price_id=found[0], unit_price=found[1], unit="Hrs", version=version)

    def volume_month(self, region: str, volume_type: str, term: str) -> Quote | str:
        """One term of a volume type. Two prices for one term are tiers this cannot tell apart,
        such as io2's IOPS, and are refused rather than one of them chosen."""
        version = self._version(EC2, region)
        if version is None:
            return f"the catalog holds no {EC2} prices for {region}"
        rows = self._connection.execute(
            VOLUME_TERM_PRICES,
            {"t": self._tenant, "s": EC2, "r": region, "v": version, "name": volume_type},
        )
        matching = [row for row in rows if _TERMS.get(str(row.pricing_unit).lower()) == term]
        if not matching:
            return f"the catalog holds no {volume_type} {term} price in {region}, version {version}"
        prices = {Decimal(row.recurring_unit_price) for row in matching}
        if len(prices) > 1:
            return (
                f"the catalog holds {len(prices)} {volume_type} {term} prices in {region}, "
                "tiers it does not tell apart"
            )
        first = matching[0]
        return Quote(
            sku_price_id=str(first.sku_price_id),
            unit_price=Decimal(first.recurring_unit_price),
            unit=str(first.pricing_unit),
            version=version,
        )

    def service_price(
        self, service: str, region: str, attributes: Mapping[str, str], term: str
    ) -> Quote | str:
        """The one on demand price holding every attribute asked, for a term. Two prices are
        refused rather than one chosen: they differ by something the plan does not say."""
        version = self._version(service, region)
        if version is None:
            return f"the catalog holds no {service} prices for {region}"
        asked = json.dumps(dict(attributes), sort_keys=True)
        rows = self._connection.execute(
            SERVICE_PRICES,
            {"t": self._tenant, "s": service, "r": region, "v": version, "asked": asked},
        )
        matching = [
            row for row in rows if _SERVICE_TERMS.get(str(row.pricing_unit).lower()) == term
        ]
        named = ", ".join(f"{key} {value}" for key, value in sorted(attributes.items()))
        if not matching:
            return (
                f"the catalog holds no {service} {term} price for {named} in {region}, "
                f"version {version}"
            )
        prices = {Decimal(row.recurring_unit_price) for row in matching}
        if len(prices) > 1:
            return (
                f"the catalog holds {len(prices)} {service} {term} prices for {named} in "
                f"{region}, which it does not tell apart"
            )
        first = matching[0]
        return Quote(
            sku_price_id=str(first.sku_price_id),
            unit_price=Decimal(first.recurring_unit_price),
            unit=str(first.pricing_unit),
            version=version,
        )
