"""Savings Plans rates for EC2, read through the relay outside the VPC. FEAT-071, TASK-P9-012.

P9 spec section 14, ADR-0035 and OPEN-17. Read only, constraint 6. **Unproved against a real
account**: the shapes are the botocore 1.43.108 model's, and proof waits on ISS-002 and ISS-263.

**Through the relay, a page at a time inside it.** `DescribeSavingsPlansOfferingRates` has no
botocore paginator; the relay follows its `nextToken` itself, and this adapter asks for each plan
type and payment option separately, six calls a Region, so no one answer holds a whole Region's
rates in the relay's 256 MB. About 13,000 rates a call (modelled).

**Narrowed to what Meter compares.** EC2 usage and shared tenancy, at the source. The operating
system is kept, in `productDescription`, as the price list's is.

**A version made from the rates.** The API publishes no version, so the sheet's version is a
digest of its rates, `sheet_version`, and `as_of` is the read: the same rates read again make the
same version, and the collector stores nothing.

**Refused, never stored.** A rate of nought, a length that is neither one nor three years, a
currency other than USD, a rate with no unit, or a rate for another Region is SchemaDrift, which
fails the Region's sheet and keeps the one held.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.domain.catalog import (
    SAVINGS_PLANS,
    Price,
    PriceListVersion,
    PriceSheet,
    PricingCategory,
    PurchaseOption,
    sheet_version,
)
from finops_core.errors import NoData, SchemaDrift
from finops_providers.aws.client import translate

COLLECTOR: Final = "savings_plan_rates"
CURRENCY: Final = "USD"
PLAN_TYPES: Final = ("Compute", "EC2Instance")
#: What Meter compares a Savings Plans rate against: EC2 instances in shared tenancy.
PRODUCTS: Final = ("EC2",)
TENANCY: Final = "shared"
PAGE: Final = 1000
#: A plan's length in seconds, as the API states it, to its length in years.
YEARS: Final[Mapping[int, int]] = {31536000: 1, 94608000: 3}


def _system_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class _Rate:
    """One rate as read, before the sheet it belongs to is known."""

    sku: str
    sku_price_id: str
    meter: str
    unit: str
    rate: Decimal
    years: int
    option: PurchaseOption
    plan: str
    details: Mapping[str, str]

    def price(self, version: PriceListVersion) -> Price:
        return Price(
            service_code=SAVINGS_PLANS,
            region=version.region,
            sku=self.sku,
            sku_price_id=self.sku_price_id,
            sku_meter=self.meter,
            pricing_unit=self.unit,
            pricing_category=PricingCategory.COMMITTED,
            currency=CURRENCY,
            recurring_unit_price=self.rate,
            lease_years=self.years,
            purchase_option=self.option,
            offering_class=self.plan,
            details=self.details,
            # The API names no effective date, so a rate is effective from the day it was read.
            effective_date=version.as_of.date(),
            version=version.version,
            as_of=version.as_of,
            collected_at=version.collected_at,
        )


class AwsSavingsPlansRates:
    """Compute and EC2 Instance Savings Plans rates for EC2, one Region at a time."""

    def __init__(self, *, client: Any, clock: Callable[[], datetime] = _system_clock) -> None:
        # A `RelayClient` for savingsplans, ADR-0035. The relay follows the token.
        self._client = client
        self._clock = clock

    def rates(self, region: str) -> PriceSheet:
        scope = f"{SAVINGS_PLANS}:{region}"
        at = self._clock()
        found: dict[str, _Rate] = {}
        try:
            for result in self._results(region):
                rate = _read(result, region, scope)
                found.setdefault(rate.sku_price_id, rate)
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=scope, collector=COLLECTOR) from failure
        if not found:
            raise NoData(
                scope_key=scope,
                collector=COLLECTOR,
                detail="no Savings Plans rate for shared tenancy EC2 in this Region",
            )
        version = PriceListVersion(
            service_code=SAVINGS_PLANS,
            region=region,
            version=sheet_version((r.sku_price_id, r.rate) for r in found.values()),
            as_of=at,
            collected_at=at,
        )
        return PriceSheet(
            version=version,
            prices=tuple(found[key].price(version) for key in sorted(found)),
        )

    def _results(self, region: str) -> Iterator[Any]:
        paginator = self._client.get_paginator("describe_savings_plans_offering_rates")
        for plan in PLAN_TYPES:
            for option in PurchaseOption:
                pages = paginator.paginate(
                    savingsPlanTypes=[plan],
                    savingsPlanPaymentOptions=[option.value],
                    products=list(PRODUCTS),
                    filters=[
                        {"name": "region", "values": [region]},
                        {"name": "tenancy", "values": [TENANCY]},
                    ],
                    maxResults=PAGE,
                )
                for page in pages:
                    yield from page.get("searchResults") or ()


def _read(result: Any, region: str, scope: str) -> _Rate:
    """One search result as a rate, or SchemaDrift saying what could not be read."""

    def drift(detail: str) -> SchemaDrift:
        return SchemaDrift(scope_key=scope, collector=COLLECTOR, detail=detail)

    offering = result.get("savingsPlanOffering") or {}
    offering_id = str(offering.get("offeringId") or "")
    usage = str(result.get("usageType") or "")
    operation = str(result.get("operation") or "")
    unit = str(result.get("unit") or "")
    if not (offering_id and usage and unit):
        raise drift("a rate with no offering, usage type or unit")
    name = f"{offering_id}.{usage}.{operation}"
    properties = {
        str(p.get("name")): str(p.get("value"))
        for p in result.get("properties") or ()
        if p.get("name") and p.get("value") is not None
    }
    if properties.get("region", region) != region:
        raise drift(f"{name} is a rate for {properties['region']}")
    if offering.get("currency") != CURRENCY:
        raise drift(f"{name} is priced in {offering.get('currency')!r}")
    try:
        years = YEARS.get(int(offering.get("durationSeconds") or 0))
        rate = Decimal(str(result.get("rate")))
        option = PurchaseOption(str(offering.get("paymentOption")))
    except (InvalidOperation, TypeError, ValueError) as failure:
        raise drift(f"{name} is a rate this cannot read") from failure
    if years is None:
        raise drift(f"{name} lasts {offering.get('durationSeconds')!r} seconds")
    if rate <= 0:
        raise drift(f"{name} is a rate of nought")
    details = {key: value for key, value in properties.items() if key != "region"}
    details["discountedServiceCode"] = str(result.get("serviceCode") or "")
    details["productType"] = str(result.get("productType") or "")
    return _Rate(
        sku=offering_id,
        sku_price_id=name,
        meter=usage,
        unit=unit,
        rate=rate,
        years=years,
        option=option,
        plan=str(offering.get("planType") or ""),
        details=details,
    )
