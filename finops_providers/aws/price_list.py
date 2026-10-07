"""AWS's published prices, read through the Price List Query API. FEAT-071, TASK-P9-004.

P9 spec sections 5.2, 5.3 and 14. Read only, constraint 6.

**Unproved against a real account**, like every adapter in this package. The shapes are read from
the Pricing service model botocore 1.43.108 installs and from the two sample responses in the API
reference, saved in `tests/providers/aws/extracts`. Proof waits on ISS-002.

**Versions from ListPriceLists, prices from GetProducts.** A price list's ARN ends in its version
and its Region, and the version is its publication time, so `as_of` is read from the ARN rather
than from a second call. `GetProducts` takes no version and answers from the current list, so a
version published between the two calls is read under the earlier label until the next run finds
it, one cadence later at most. The Regions are the price list's own codes, kept when they have
the shape of a commercial Region, `eu-west-1`: GovCloud, China, the isolated partitions and Local
Zones are left out by their shape, and no Region is named here, P9 spec section 14.2.

**One page at a time.** `prices` is a generator over GetProducts pages, so no offer file and no
whole Region's list is held in memory. EC2 is narrowed at the source to the comparable instance
price and to EBS storage, because most of its list is products no rightsizing compares, such as
data transfer and addresses. The other four services are read by Region and filtered here; the
ElastiCache list for eu-west-1 holds 506 products (measured on 2026-10-08).

**The comparable price.** Shared tenancy, used capacity and no preinstalled software, wherever a
product carries the attribute. The operating system is not filtered: it is kept in `details`,
because a Windows instance's smaller size is priced at Windows rates. An Extended Support product
is a surcharge on a type rather than its price, so it is kept and named, `extendedSupport` in
`details` holding its year, and is never read as a second price for the same type.

**Refused, never stored.** A term whose every price is nought, a product with no price, a currency
that is not ISO 4217, or a term with more than one recurring price is SchemaDrift. That fails one
service in one Region, and the collector keeps the version it already holds. Each query that finds
no product is NoData, so an EC2 instance filter that matched nothing fails the Region rather than
storing its volumes alone.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.domain.catalog import Price, PriceListVersion, PricingCategory, PurchaseOption
from finops_core.errors import NoData, SchemaDrift
from finops_providers.aws.client import translate

COLLECTOR: Final = "price_catalog"
CURRENCY: Final = "USD"
FORMAT_VERSION: Final = "aws_v1"
#: A commercial Region's code: two letters, words, a number.
_REGION: Final = re.compile(r"[a-z]{2}(-[a-z]+)+-\d+")
#: Partitions whose codes have that shape but whose prices no commercial estate pays.
_OTHER_PARTITIONS: Final = ("us-gov-", "cn-", "us-iso")
#: The version's form, which is its publication time: `20170901182201` is 2017-09-01T18:22:01Z.
_VERSION: Final = "%Y%m%d%H%M%S"
#: The values that make a price the comparable one, where a product carries the attribute.
COMPARABLE: Final[Mapping[str, str]] = {
    "tenancy": "Shared",
    "capacitystatus": "Used",
    "preInstalledSw": "NA",
}
#: The attributes kept on a price, the ones that tell two prices for one type apart.
DETAILS: Final = (
    "instanceType",
    "operatingSystem",
    "tenancy",
    "capacitystatus",
    "preInstalledSw",
    "licenseModel",
    "databaseEngine",
    "databaseEdition",
    "deploymentOption",
    "cacheEngine",
    "volumeApiName",
    "volumeType",
    "storageMedia",
)
#: The usage type marker of an Extended Support surcharge, `EU-ExtendedSupportYr3-NodeUsage:...`.
EXTENDED_SUPPORT: Final = "ExtendedSupport"
#: The unit of an upfront fee, as the real ElastiCache list prices it.
UPFRONT_UNIT: Final = "Quantity"
TERM_KINDS: Final = {"OnDemand": PricingCategory.STANDARD, "Reserved": PricingCategory.COMMITTED}

#: What is asked of GetProducts beyond the Region, per service: one query per tuple. EC2 asks
#: twice, for instances at the comparable price and for EBS storage. Any other service is read
#: whole for its Region.
QUERIES: Final[Mapping[str, tuple[tuple[tuple[str, str], ...], ...]]] = {
    "AmazonEC2": (tuple(COMPARABLE.items()), (("productFamily", "Storage"),)),
}
_WHOLE_REGION: Final[tuple[tuple[tuple[str, str], ...], ...]] = ((),)


def _system_clock() -> datetime:
    return datetime.now(UTC)


def commercial(region: str) -> bool:
    """Whether a price list's Region code is a commercial Region's."""
    return bool(_REGION.fullmatch(region)) and not region.startswith(_OTHER_PARTITIONS)


def published(version: str) -> datetime:
    """The publication time a version names. ValueError for a version not in that form."""
    return datetime.strptime(version, _VERSION).replace(tzinfo=UTC)


def _match(field: str, value: str) -> dict[str, str]:
    return {"Type": "TERM_MATCH", "Field": field, "Value": value}


class AwsPriceCatalog:
    """AWS's on demand and reserved prices for one service in one Region at a time."""

    def __init__(self, *, client: Any, clock: Callable[[], datetime] = _system_clock) -> None:
        # A Pricing client in us-east-1, reached through the hub's endpoint, ADR-0035.
        self._client = client
        self._clock = clock

    def versions(self, service_code: str) -> Iterable[PriceListVersion]:
        at = self._clock()
        latest: dict[str, PriceListVersion] = {}
        try:
            pages = self._client.get_paginator("list_price_lists").paginate(
                ServiceCode=service_code, EffectiveDate=at, CurrencyCode=CURRENCY
            )
            for page in pages:
                for raw in page.get("PriceLists") or ():
                    found = self._version(service_code, raw, at)
                    held = latest.get(found.region) if found else None
                    if found and (held is None or found.version > held.version):
                        latest[found.region] = found
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=service_code, collector=COLLECTOR) from failure
        return tuple(latest[region] for region in sorted(latest))

    def prices(self, version: PriceListVersion) -> Iterator[Price]:
        scope = f"{version.service_code}:{version.region}"
        at = self._clock()
        try:
            for query in QUERIES.get(version.service_code, _WHOLE_REGION):
                filters = [_match("regionCode", version.region)]
                filters.extend(_match(field, value) for field, value in query)
                pages = self._client.get_paginator("get_products").paginate(
                    ServiceCode=version.service_code,
                    FormatVersion=FORMAT_VERSION,
                    Filters=filters,
                )
                products = 0
                for page in pages:
                    for document in page.get("PriceList") or ():
                        products += 1
                        yield from _Product(document, version, at, scope).prices()
                # Each query, not the Region: an EC2 filter that matched no instance would
                # otherwise store the Region's volumes and quietly no instance at all.
                if products == 0:
                    asked = ", ".join(f"{field} {value}" for field, value in query)
                    raise NoData(
                        scope_key=scope,
                        collector=COLLECTOR,
                        detail="the price list holds no product for this service in this Region"
                        + (f" with {asked}" if asked else ""),
                    )
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=scope, collector=COLLECTOR) from failure

    def _version(self, service_code: str, raw: Any, at: datetime) -> PriceListVersion | None:
        region = str(raw.get("RegionCode") or "")
        if not commercial(region):
            return None
        arn = str(raw.get("PriceListArn") or "")
        # arn:aws:pricing:::price-list/aws/AmazonEC2/USD/20220603151047/us-east-1
        parts = arn.partition("price-list/")[2].split("/")
        if len(parts) != 5 or parts[1] != service_code or parts[4] != region:
            raise SchemaDrift(
                scope_key=service_code, collector=COLLECTOR, detail=f"unreadable ARN {arn!r}"
            )
        if raw.get("CurrencyCode") != CURRENCY or parts[2] != CURRENCY:
            raise SchemaDrift(
                scope_key=service_code,
                collector=COLLECTOR,
                detail=f"{arn} is not priced in {CURRENCY}, which was asked for",
            )
        try:
            when = published(parts[3])
        except ValueError as failure:
            raise SchemaDrift(
                scope_key=service_code,
                collector=COLLECTOR,
                detail=f"version {parts[3]!r} is not a publication time",
            ) from failure
        return PriceListVersion(
            service_code=service_code,
            region=region,
            version=parts[3],
            as_of=when,
            # A clock behind AWS's would otherwise read the list before it was published.
            collected_at=max(at, when),
        )


class _Product:
    """One GetProducts document: a product and its terms, read into prices or refused."""

    def __init__(self, document: Any, version: PriceListVersion, at: datetime, scope: str) -> None:
        self._version = version
        self._at = at
        self._scope = scope
        try:
            item = json.loads(document) if isinstance(document, str) else document
            self._product = dict(item["product"])
            self._attributes = dict(self._product.get("attributes") or {})
            self._terms = dict(item.get("terms") or {})
        except (ValueError, KeyError, TypeError) as failure:
            raise self._drift("a product this cannot read") from failure
        self._sku = str(self._product.get("sku") or "")
        if not self._sku:
            raise self._drift("a product with no SKU")

    def prices(self) -> list[Price]:
        if not self._compared():
            return []
        region = self._attributes.get("regionCode")
        if region is not None and region != self._version.region:
            raise self._drift(f"{self._sku} is priced for {region}, not the Region asked for")
        meter = str(self._attributes.get("usagetype") or "")
        if not meter:
            raise self._drift(f"{self._sku} has no usage type")
        found = [
            self._price(kind, meter, term)
            for kind in TERM_KINDS
            for term in (self._terms.get(kind) or {}).values()
        ]
        if not found:
            raise self._drift(f"{self._sku} has no price")
        return found

    def _compared(self) -> bool:
        """An instance or an EBS volume, at the comparable price."""
        kept = bool(self._attributes.get("instanceType")) or (
            self._product.get("productFamily") == "Storage"
        )
        return kept and all(
            self._attributes.get(name, wanted) == wanted for name, wanted in COMPARABLE.items()
        )

    def _details(self, meter: str) -> dict[str, str]:
        attributes = self._attributes
        details = {name: str(attributes[name]) for name in DETAILS if attributes.get(name)}
        if EXTENDED_SUPPORT in meter:
            details["extendedSupport"] = str(self._attributes.get("year_number") or meter)
        return details

    def _price(self, kind: str, meter: str, term: Any) -> Price:
        code = str(term.get("offerTermCode") or "")
        if not code or term.get("sku", self._sku) != self._sku:
            raise self._drift(f"{self._sku} has a term this cannot read")
        recurring: list[tuple[str, Decimal]] = []
        upfront = Decimal(0)
        currencies: set[str] = set()
        for dimension in (term.get("priceDimensions") or {}).values():
            currency, amount = self._amount(dimension, code)
            currencies.add(currency)
            if dimension.get("unit") == UPFRONT_UNIT:
                upfront += amount
            else:
                recurring.append((str(dimension.get("unit") or ""), amount))
        if len(recurring) != 1 or not recurring[0][0]:
            raise self._drift(
                f"{self._sku}.{code} has {len(recurring)} recurring prices, and one is read"
            )
        if currencies != {CURRENCY}:
            raise self._drift(f"{self._sku}.{code} is priced in {sorted(currencies)}")
        unit, rate = recurring[0]
        if rate == 0 and upfront == 0:
            raise self._drift(f"{self._sku}.{code} is a term whose every price is nought")
        committed = TERM_KINDS[kind] is PricingCategory.COMMITTED
        options = term.get("termAttributes") or {}
        try:
            return Price(
                service_code=self._version.service_code,
                region=self._version.region,
                sku=self._sku,
                sku_price_id=f"{self._sku}.{code}",
                sku_meter=meter,
                pricing_unit=unit,
                pricing_category=TERM_KINDS[kind],
                currency=CURRENCY,
                recurring_unit_price=rate,
                upfront_fee=upfront,
                lease_years=_years(options["LeaseContractLength"]) if committed else None,
                purchase_option=PurchaseOption(options["PurchaseOption"]) if committed else None,
                offering_class=options.get("OfferingClass") if committed else None,
                details=self._details(meter),
                effective_date=_effective(term["effectiveDate"]),
                version=self._version.version,
                as_of=self._version.as_of,
                collected_at=max(self._at, self._version.as_of),
            )
        except (KeyError, TypeError, ValueError) as failure:
            raise self._drift(f"{self._sku}.{code} is a term this cannot read") from failure

    def _amount(self, dimension: Any, code: str) -> tuple[str, Decimal]:
        priced = dict(dimension.get("pricePerUnit") or {})
        if len(priced) != 1:
            raise self._drift(f"{self._sku}.{code} has a price in {len(priced)} currencies")
        ((currency, value),) = priced.items()
        try:
            return str(currency), Decimal(str(value))
        except InvalidOperation as failure:
            raise self._drift(f"{self._sku}.{code} has a price {value!r}") from failure

    def _drift(self, detail: str) -> SchemaDrift:
        return SchemaDrift(scope_key=self._scope, collector=COLLECTOR, detail=detail)


def _years(length: Any) -> int:
    """`1yr` or `3yr`, the price list's words for a reservation's length."""
    return int(str(length).removesuffix("yr"))


def _effective(value: Any) -> date:
    """The day a term took effect, from `2017-08-01T00:00:00Z`."""
    return date.fromisoformat(str(value)[:10])
