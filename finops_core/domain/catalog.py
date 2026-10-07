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

import re
from collections.abc import Mapping
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

    def __post_init__(self) -> None:
        if self.vcpus <= 0 or self.memory_mib <= 0:
            raise ValueError(f"{self.instance_type} has no vCPUs or no memory")
        if self.gpu_count < 0:
            raise ValueError(f"{self.instance_type} has a negative GPU count")
