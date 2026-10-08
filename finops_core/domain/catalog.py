"""What AWS charges for a product, and what an instance type is. P9, TASK-P9-002.

P9 spec sections 5.3 and 5.4. Every price comes from AWS's price list and every specification
from EC2's own description of itself, so these hold what was read and nothing Meter worked out.

**A price is one offer term.** On demand, or a reservation of one length, payment option and
class. A reservation can carry two prices, an hourly rate and an upfront fee, and an All Upfront
one carries an hourly rate of exactly nought beside the whole cost up front: the real ElastiCache
price list of 2026-09-14 lists `cache.m5.large` for three years at 0.00 an hour and 1631.20
upfront. So the refusal the spec asks for, a price of nought, is a term whose every price is
nought, and a nought hourly rate beside a fee is a real price and is kept. `sku_price_id` is the
SKU and the term, `RPVSXBK67RKQZAHJ.NQ3QZPMQV9`, because the term has a rate code per price and
the term is what a recommendation names.

**Shape, not judgement.** An instance type is held as AWS describes it. Which type is smaller,
newer or cheaper is decided elsewhere, from these and the prices.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Final

from finops_core.domain.fact import Fact

#: An ISO 4217 code, as every price list states its currency.
_CURRENCY: Final = re.compile(r"[A-Z]{3}")
#: Hours in a year of a reservation, as AWS counts them for an effective hourly rate.
HOURS_PER_YEAR: Final = 8760
#: The service a Savings Plans rate is listed under, as AWS's Savings Plans price list names it.
#: One code for Compute and EC2 Instance plans alike; the plan type is the offering class.
SAVINGS_PLANS: Final = "ComputeSavingsPlans"
#: Hex digits of a sheet's digest kept as its version: 80 bits, far past any collision a few
#: thousand versions could meet.
_DIGEST_DIGITS: Final = 20


class PricingCategory(StrEnum):
    """FOCUS's words for how a price is paid."""

    #: On demand.
    STANDARD = "Standard"
    #: A reservation.
    COMMITTED = "Committed"


class PurchaseOption(StrEnum):
    """How much of a reservation is paid when it is bought, in the price list's own words."""

    NO_UPFRONT = "No Upfront"
    PARTIAL_UPFRONT = "Partial Upfront"
    ALL_UPFRONT = "All Upfront"


@dataclass(frozen=True, kw_only=True)
class PriceListVersion(Fact):
    """One publication of one service's prices in one Region. `as_of` is its publication."""

    service_code: str
    region: str
    version: str


@dataclass(frozen=True, kw_only=True)
class Price(Fact):
    """One offer term for one product in one Region, as the price list states it."""

    service_code: str
    region: str
    sku: str
    #: The SKU and the offer term, FOCUS's SkuPriceId.
    sku_price_id: str
    #: The usage type the product is billed under, FOCUS's SkuMeter.
    sku_meter: str
    pricing_unit: str
    pricing_category: PricingCategory
    currency: str
    #: Per pricing unit. Nought only beside a positive upfront fee.
    recurring_unit_price: Decimal
    upfront_fee: Decimal = Decimal(0)
    lease_years: int | None = None
    purchase_option: PurchaseOption | None = None
    #: standard or convertible, in the price list's own words.
    offering_class: str | None = None
    #: The product's attributes that tell one price from another for the same type: operating
    #: system, tenancy, capacity status, preinstalled software, licence, engine.
    details: Mapping[str, str] = field(default_factory=dict)
    effective_date: date
    version: str

    def __post_init__(self) -> None:
        if not _CURRENCY.fullmatch(self.currency):
            raise ValueError(f"{self.currency!r} is not an ISO 4217 currency")
        if self.recurring_unit_price < 0 or self.upfront_fee < 0:
            raise ValueError("a price is never negative")
        if self.recurring_unit_price == 0 and self.upfront_fee == 0:
            raise ValueError("a term whose every price is nought is not a price")
        committed = self.pricing_category is PricingCategory.COMMITTED
        if committed and (self.lease_years is None or self.purchase_option is None):
            raise ValueError("a reservation names its length and how it is paid")
        if not committed and (self.lease_years is not None or self.upfront_fee != 0):
            raise ValueError("an on demand price has no lease and nothing up front")

    @property
    def effective_hourly(self) -> Decimal | None:
        """An hourly price with any upfront fee spread over the lease, for comparing terms.

        Derived, never stored: both inputs are. None for a price not charged by the hour.
        """
        if self.pricing_unit != "Hrs":
            return None
        if self.lease_years is None or self.upfront_fee == 0:
            return self.recurring_unit_price
        return self.recurring_unit_price + self.upfront_fee / (self.lease_years * HOURS_PER_YEAR)


@dataclass(frozen=True, kw_only=True)
class InstanceTypeSpec(Fact):
    """One instance type as AWS describes it in one Region.

    For EC2 the source is `DescribeInstanceTypes`; for RDS, ElastiCache, Redshift and OpenSearch,
    the price list's own product attributes, P9 spec section 14.3. A figure the source does not
    publish is None, never a guess.
    """

    service_code: str
    region: str
    instance_type: str
    family: str
    current_generation: bool
    architectures: tuple[str, ...]
    burstable: bool
    vcpus: int
    memory_mib: int
    #: As AWS words it, "Up to 10 Gigabit", where no figures are published.
    network_performance: str
    network_baseline_gbps: Decimal | None = None
    network_peak_gbps: Decimal | None = None
    ebs_baseline_mbps: int | None = None
    ebs_maximum_mbps: int | None = None
    gpu_count: int = 0
    #: A burstable type's baseline, the share of each vCPU it may use and earn back its credits,
    #: from the EC2 guide's credit table, TASK-P9-005. 0.30 for a t3.large. None for any other
    #: type, and for a burstable type the table does not list, which is never stored.
    baseline_cpu: Decimal | None = None
    #: The most credits it can accrue, the same table's figure.
    maximum_credits: Decimal | None = None
    #: Where the baseline was read, so a figure copied from a document says which one.
    baseline_source: str | None = None

    def __post_init__(self) -> None:
        if self.vcpus <= 0 or self.memory_mib <= 0:
            raise ValueError(f"{self.instance_type} has no vCPUs or no memory")
        if self.gpu_count < 0:
            raise ValueError(f"{self.instance_type} has a negative GPU count")
        if not self.architectures:
            raise ValueError(f"{self.instance_type} names no architecture")
        if self.baseline_cpu is not None and not 0 < self.baseline_cpu <= 1:
            raise ValueError(f"{self.instance_type}'s baseline is not a share of a vCPU")
        if (self.baseline_cpu is None) != (self.baseline_source is None):
            raise ValueError(f"{self.instance_type}'s baseline and its source go together")
        if self.maximum_credits is not None and self.maximum_credits < 0:
            raise ValueError(f"{self.instance_type} has a negative credit limit")
        peak, base = self.network_peak_gbps, self.network_baseline_gbps
        if peak is not None and base is not None and peak < base:
            raise ValueError(f"{self.instance_type}'s network peak is below its baseline")
        ebs_max, ebs_base = self.ebs_maximum_mbps, self.ebs_baseline_mbps
        if ebs_max is not None and ebs_base is not None and ebs_max < ebs_base:
            raise ValueError(f"{self.instance_type}'s EBS maximum is below its baseline")


def sheet_version(rates: Iterable[tuple[str, Decimal]]) -> str:
    """A version for prices read through an API that publishes none, from the prices themselves.

    TASK-P9-012. The same rates in any order make the same version, so a run that reads them
    unchanged finds the version held and stores nothing; one rate moving makes a new one.
    """
    lines = sorted(f"{sku_price_id}={rate.normalize()}" for sku_price_id, rate in rates)
    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    return digest[:_DIGEST_DIGITS]


@dataclass(frozen=True, kw_only=True)
class PriceSheet:
    """Every price of one version of one service in one Region, read together. TASK-P9-012."""

    version: PriceListVersion
    prices: tuple[Price, ...]

    def __post_init__(self) -> None:
        version = self.version
        for price in self.prices:
            if (price.service_code, price.region, price.version) != (
                version.service_code,
                version.region,
                version.version,
            ):
                raise ValueError(f"{price.sku_price_id} does not belong to the sheet's version")


@dataclass(frozen=True, kw_only=True)
class SpotPrice(Fact):
    """One spot price reading for one pool, as EC2 recorded it. TASK-P9-013.

    A pool is an instance type and a product description in one Availability Zone. `as_of` is
    the reading's own time, when EC2 set the price, and `collected_at` is when Meter read it,
    constraint 10.
    """

    region: str
    availability_zone: str
    instance_type: str
    product_description: str
    price: Decimal

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError(
                f"a spot price of {self.price} for {self.instance_type} is not a price"
            )
        if not self.availability_zone.startswith(self.region):
            raise ValueError(f"{self.availability_zone} is not a zone of {self.region}")

    @property
    def pool(self) -> tuple[str, str, str]:
        return (self.availability_zone, self.instance_type, self.product_description)
