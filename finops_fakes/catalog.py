"""AWS's price list and instance types, for the fake estate. TASK-P9-002, ADR-0022.

**Shaped by AWS's own, priced by the estate's.** The structure is the real one: the on demand
term code, the six standard reservation codes and the rate codes are copied from the ElastiCache
price list in `tests/providers/aws/extracts`, and an All Upfront reservation has an hourly price
of nought beside its fee, as the real one does. The prices are not AWS's. Each type's on demand
rate is its monthly figure in `finops_fakes/prices.py` over that module's 720 hours, so a
rightsizing saving worked out from this catalog equals the difference in the bill the estate
generates, and a demo cannot show a saving and a bill that disagree for a reason the fixture made.
The reservation discounts are invented too, and round on purpose.

**The planted cases' types.** Every type the estate prices is described, at the vCPUs and memory
the EC2 documentation gives for it, so a downsizing candidate always has a target to name. EC2's
product attribute names, `operatingSystem` and the rest, are the price list documentation's;
TASK-P9-004 holds them to a real EC2 extract when it reads one.

Only EC2 is faked. Another service's versions are none, and its prices are NoData.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Final

from finops_core.domain.catalog import (
    HOURS_PER_YEAR,
    InstanceTypeSpec,
    Price,
    PriceListVersion,
    PricingCategory,
    PurchaseOption,
)
from finops_core.errors import CollectionError, NoData, NotOptedIn
from finops_fakes import fixtures, prices
from finops_fakes.estate_shape import REGIONS

EC2: Final = "AmazonEC2"
COLLECTOR: Final = "price_catalog"
VERSION: Final = "20260820000000"
#: Before the estate's own clock, so every price was published before it was read.
PUBLISHED: Final = datetime(2026, 8, 20, 0, 0, tzinfo=UTC)
EFFECTIVE: Final = date(2026, 8, 1)
CURRENCY: Final = "USD"

#: The real codes, from the ElastiCache extract. An offer term, and the rate of each price in it.
ON_DEMAND_TERM: Final = "JRTCKXETXF"
HOURLY_RATE: Final = "6YS6EN2CT7"
UPFRONT_RATE: Final = "2TG2D8R56U"
RESERVED_TERMS: Final[dict[tuple[int, PurchaseOption], str]] = {
    (1, PurchaseOption.NO_UPFRONT): "4NA7Y494T4",
    (1, PurchaseOption.PARTIAL_UPFRONT): "HU7G6KETJZ",
    (1, PurchaseOption.ALL_UPFRONT): "6QCMYABX3D",
    (3, PurchaseOption.NO_UPFRONT): "BPH4J8HBKS",
    (3, PurchaseOption.PARTIAL_UPFRONT): "38NPMPTW36",
    (3, PurchaseOption.ALL_UPFRONT): "NQ3QZPMQV9",
}
#: Invented. A reservation's discount off on demand, by its length in years.
DISCOUNT: Final = {1: Decimal("0.35"), 3: Decimal("0.55")}

#: What makes one EC2 price another's: the price list's attribute names.
LINUX_SHARED: Final = {
    "operatingSystem": "Linux",
    "tenancy": "Shared",
    "capacitystatus": "Used",
    "preInstalledSw": "NA",
    "licenseModel": "No License required",
}

#: Each priced type's family, vCPUs, memory in MiB, whether it is burstable, its architecture,
#: GPUs and network, as the EC2 documentation gives them.
SPECS: Final[dict[str, tuple[str, int, int, bool, str, int, str]]] = {
    "t3.micro": ("t3", 2, 1024, True, "x86_64", 0, "Up to 5 Gigabit"),
    "t3.small": ("t3", 2, 2048, True, "x86_64", 0, "Up to 5 Gigabit"),
    "t3.medium": ("t3", 2, 4096, True, "x86_64", 0, "Up to 5 Gigabit"),
    "t3.large": ("t3", 2, 8192, True, "x86_64", 0, "Up to 5 Gigabit"),
    "m5.large": ("m5", 2, 8192, False, "x86_64", 0, "Up to 10 Gigabit"),
    "m5.xlarge": ("m5", 4, 16384, False, "x86_64", 0, "Up to 10 Gigabit"),
    "m5.2xlarge": ("m5", 8, 32768, False, "x86_64", 0, "Up to 10 Gigabit"),
    "m5.4xlarge": ("m5", 16, 65536, False, "x86_64", 0, "Up to 10 Gigabit"),
    "m6g.xlarge": ("m6g", 4, 16384, False, "arm64", 0, "Up to 10 Gigabit"),
    "m6i.large": ("m6i", 2, 8192, False, "x86_64", 0, "Up to 12.5 Gigabit"),
    "m6i.xlarge": ("m6i", 4, 16384, False, "x86_64", 0, "Up to 12.5 Gigabit"),
    "m6i.2xlarge": ("m6i", 8, 32768, False, "x86_64", 0, "Up to 12.5 Gigabit"),
    "m6i.4xlarge": ("m6i", 16, 65536, False, "x86_64", 0, "Up to 12.5 Gigabit"),
    "c5.2xlarge": ("c5", 8, 16384, False, "x86_64", 0, "Up to 10 Gigabit"),
    "c5.4xlarge": ("c5", 16, 32768, False, "x86_64", 0, "Up to 10 Gigabit"),
    "c6i.2xlarge": ("c6i", 8, 16384, False, "x86_64", 0, "Up to 12.5 Gigabit"),
    "c6i.4xlarge": ("c6i", 16, 32768, False, "x86_64", 0, "Up to 12.5 Gigabit"),
    "r5.xlarge": ("r5", 4, 32768, False, "x86_64", 0, "Up to 10 Gigabit"),
    "r5.2xlarge": ("r5", 8, 65536, False, "x86_64", 0, "Up to 10 Gigabit"),
    "r6i.xlarge": ("r6i", 4, 32768, False, "x86_64", 0, "Up to 12.5 Gigabit"),
    "g4dn.xlarge": ("g4dn", 4, 16384, False, "x86_64", 1, "Up to 25 Gigabit"),
}

_HOURLY = Decimal("0.0001")
_CENT = Decimal("0.01")


def on_demand_hourly(instance_type: str) -> Decimal:
    """The estate's monthly figure over its own month, to the price list's four places."""
    monthly = prices.INSTANCE_USD[instance_type]
    return (monthly / prices.HOURS_PER_MONTH).quantize(_HOURLY)


def sku_for(region: str, instance_type: str) -> str:
    """A SKU in the price list's form, sixteen capitals, the same every time for one product."""
    digest = hashlib.sha256(f"{region}:{instance_type}".encode()).hexdigest().upper()
    return "".join(ch for ch in digest if ch.isalpha())[:16].ljust(16, "X")


class FakePriceCatalog:
    """EC2's on demand and standard reserved prices in every fake Region."""

    def __init__(
        self,
        *,
        regions: Iterable[str] = REGIONS,
        failure: type[CollectionError] | None = None,
    ) -> None:
        self._regions = tuple(regions)
        self._failure = failure

    def versions(self, service_code: str) -> Iterable[PriceListVersion]:
        self._fail()
        if service_code != EC2:
            return ()
        return tuple(
            PriceListVersion(
                service_code=EC2,
                region=region,
                version=VERSION,
                as_of=PUBLISHED,
                collected_at=fixtures.COLLECTED_AT,
            )
            for region in self._regions
        )

    def prices(self, version: PriceListVersion) -> Iterable[Price]:
        self._fail()
        if version.service_code != EC2 or version.region not in self._regions:
            raise NoData(
                scope_key=f"{version.service_code}:{version.region}",
                collector=COLLECTOR,
                detail="the fake price list holds EC2 in the fake Regions only",
            )
        found: list[Price] = []
        for instance_type in sorted(prices.INSTANCE_USD):
            found.extend(self._terms(version.region, instance_type))
        return tuple(found)

    def _terms(self, region: str, instance_type: str) -> list[Price]:
        sku = sku_for(region, instance_type)
        hourly = on_demand_hourly(instance_type)
        details = {"instanceType": instance_type, **LINUX_SHARED}
        common: dict[str, Any] = {
            "service_code": EC2,
            "region": region,
            "sku": sku,
            "sku_meter": f"BoxUsage:{instance_type}",
            "pricing_unit": "Hrs",
            "currency": CURRENCY,
            "details": details,
            "effective_date": EFFECTIVE,
            "version": VERSION,
            "as_of": PUBLISHED,
            "collected_at": fixtures.COLLECTED_AT,
        }
        terms = [
            Price(
                sku_price_id=f"{sku}.{ON_DEMAND_TERM}",
                pricing_category=PricingCategory.STANDARD,
                recurring_unit_price=hourly,
                **common,
            )
        ]
        for (years, option), code in RESERVED_TERMS.items():
            reserved = hourly * (1 - DISCOUNT[years])
            whole = reserved * HOURS_PER_YEAR * years
            if option is PurchaseOption.NO_UPFRONT:
                recurring, upfront = reserved, Decimal(0)
            elif option is PurchaseOption.PARTIAL_UPFRONT:
                recurring, upfront = reserved / 2, whole / 2
            else:
                recurring, upfront = Decimal(0), whole
            terms.append(
                Price(
                    sku_price_id=f"{sku}.{code}",
                    pricing_category=PricingCategory.COMMITTED,
                    recurring_unit_price=recurring.quantize(_HOURLY),
                    upfront_fee=upfront.quantize(_CENT),
                    lease_years=years,
                    purchase_option=option,
                    offering_class="standard",
                    **common,
                )
            )
        return terms

    def _fail(self) -> None:
        if self._failure is not None:
            raise self._failure(
                scope_key=fixtures.ORGANIZATION_SCOPE,
                collector=COLLECTOR,
                detail="planned by the fake price catalog",
            )


class FakeInstanceCatalog:
    """EC2's description of every type the estate prices, in any Region opted into."""

    def __init__(
        self,
        *,
        not_opted_in: Iterable[str] = (),
        failure: type[CollectionError] | None = None,
    ) -> None:
        self._not_opted_in = frozenset(not_opted_in)
        self._failure = failure

    def instance_types(self, region: str) -> Iterable[InstanceTypeSpec]:
        if self._failure is not None:
            raise self._failure(
                scope_key=region,
                collector="instance_catalog",
                detail="planned by the fake instance catalog",
            )
        if region in self._not_opted_in:
            raise NotOptedIn(
                scope_key=region,
                collector="instance_catalog",
                detail="the Region is not enabled for the account",
            )
        return tuple(
            InstanceTypeSpec(
                service_code=EC2,
                region=region,
                instance_type=instance_type,
                family=family,
                current_generation=True,
                architectures=(architecture,),
                burstable=burstable,
                vcpus=vcpus,
                memory_mib=memory,
                network_performance=network,
                gpu_count=gpus,
                as_of=PUBLISHED,
                collected_at=fixtures.COLLECTED_AT,
            )
            for instance_type, (
                family,
                vcpus,
                memory,
                burstable,
                architecture,
                gpus,
                network,
            ) in sorted(SPECS.items())
        )
