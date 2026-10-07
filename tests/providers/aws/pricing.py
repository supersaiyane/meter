"""A stubbed Pricing client, answering as the Price List Query API does. TASK-P9-004.

Shared by the adapter's tests and the catalog contract. The documents it serves are the fake
catalog's prices written back into the GetProducts shape the API reference's own sample shows,
`tests/providers/aws/extracts/get-products-ec2-ebs-io1.json`: a JSON string per product, its terms
keyed by SKU and term. So the adapter is held to the contract by reading the same prices the fake
returns, through the shape AWS sends them in.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from botocore.exceptions import ClientError

from finops_core.domain.catalog import Price, PricingCategory
from finops_core.errors import CollectionError
from finops_fakes import fixtures
from finops_fakes.catalog import (
    EC2,
    HOURLY_RATE,
    UPFRONT_RATE,
    VERSION,
    FakePriceCatalog,
)
from finops_providers.aws.price_list import AwsPriceCatalog

#: The code AWS answers each cause with, so a planned failure reaches `translate` as AWS's would.
CODES: dict[str, str] = {
    "AccessDenied": "AccessDeniedException",
    "Throttled": "ThrottlingException",
}


def arn(service: str, version: str, region: str) -> str:
    return f"arn:aws:pricing:::price-list/aws/{service}/USD/{version}/{region}"


def price_list(service: str, version: str, region: str) -> dict[str, Any]:
    return {
        "PriceListArn": arn(service, version, region),
        "RegionCode": region,
        "CurrencyCode": "USD",
        "FileFormats": ["json", "csv"],
    }


def document(prices: Iterable[Price], family: str = "Compute Instance") -> str:
    """One GetProducts item for one product, from the prices of its terms."""
    terms: dict[str, dict[str, Any]] = {"OnDemand": {}, "Reserved": {}}
    first: Price | None = None
    for price in prices:
        first = first or price
        kind = "OnDemand" if price.pricing_category is PricingCategory.STANDARD else "Reserved"
        dimensions = {
            f"{price.sku_price_id}.{HOURLY_RATE}": {
                "unit": price.pricing_unit,
                "pricePerUnit": {price.currency: str(price.recurring_unit_price)},
                "rateCode": f"{price.sku_price_id}.{HOURLY_RATE}",
            }
        }
        if price.upfront_fee:
            dimensions[f"{price.sku_price_id}.{UPFRONT_RATE}"] = {
                "unit": "Quantity",
                "pricePerUnit": {price.currency: str(price.upfront_fee)},
                "rateCode": f"{price.sku_price_id}.{UPFRONT_RATE}",
            }
        attributes: dict[str, str] = {}
        if price.lease_years is not None and price.purchase_option is not None:
            attributes = {
                "LeaseContractLength": f"{price.lease_years}yr",
                "OfferingClass": price.offering_class or "standard",
                "PurchaseOption": price.purchase_option.value,
            }
        terms[kind][price.sku_price_id] = {
            "offerTermCode": price.sku_price_id.split(".")[1],
            "sku": price.sku,
            "effectiveDate": f"{price.effective_date.isoformat()}T00:00:00Z",
            "priceDimensions": dimensions,
            "termAttributes": attributes,
        }
    assert first is not None, "a product is written from at least one price"
    product = {
        "productFamily": family,
        "sku": first.sku,
        "attributes": {
            **first.details,
            "usagetype": first.sku_meter,
            "regionCode": first.region,
            "servicecode": first.service_code,
        },
    }
    return json.dumps(
        {
            "product": product,
            "serviceCode": first.service_code,
            "terms": terms,
            "version": first.version,
        }
    )


def volume(region: str) -> str:
    """One EBS gp3 product, as every real EC2 list holds beside its instances. Price invented."""
    sku = f"GP3{region.upper().replace('-', '')}".ljust(16, "X")[:16]
    return json.dumps(
        {
            "product": {
                "productFamily": "Storage",
                "sku": sku,
                "attributes": {
                    "volumeApiName": "gp3",
                    "storageMedia": "SSD-backed",
                    "usagetype": "EBS:VolumeUsage.gp3",
                    "regionCode": region,
                },
            },
            "terms": {
                "OnDemand": {
                    f"{sku}.JRTCKXETXF": {
                        "offerTermCode": "JRTCKXETXF",
                        "sku": sku,
                        "effectiveDate": "2026-08-01T00:00:00Z",
                        "priceDimensions": {
                            f"{sku}.JRTCKXETXF.{HOURLY_RATE}": {
                                "unit": "GB-Mo",
                                "pricePerUnit": {"USD": "0.0800000000"},
                            }
                        },
                        "termAttributes": {},
                    }
                }
            },
        }
    )


def fake_documents() -> dict[str, list[str]]:
    """The fake catalog's EC2 prices as GetProducts items, by Region, with one volume each."""
    catalog = FakePriceCatalog()
    by_region: dict[str, list[str]] = {}
    for version in catalog.versions(EC2):
        by_sku: dict[str, list[Price]] = defaultdict(list)
        for price in catalog.prices(version):
            by_sku[price.sku].append(price)
        by_region[version.region] = [
            *(document(terms) for _, terms in sorted(by_sku.items())),
            volume(version.region),
        ]
    return by_region


def _matches(item: str, filters: list[Mapping[str, str]]) -> bool:
    if not filters:
        return True
    product = json.loads(item)["product"]
    fields = {**product["attributes"], "productFamily": product.get("productFamily", "")}
    return all(fields.get(f["Field"]) == f["Value"] for f in filters)


class StubPricing:
    """Answers `get_paginator(...).paginate(...)` from literals, a page at a time."""

    def __init__(
        self,
        *,
        lists: Mapping[str, list[dict[str, Any]]],
        products: Mapping[str, list[str]],
        failure: str | None = None,
        page_size: int = 2,
    ) -> None:
        #: Price lists by service code, and GetProducts items by service code and Region.
        self._lists = lists
        self._products = products
        self._failure = failure
        self._page_size = page_size
        #: Every request, operation then its parameters, for the tests that check what was asked.
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def get_paginator(self, operation: str) -> _Paginator:
        return _Paginator(self, operation)

    def answer(self, operation: str, request: dict[str, Any]) -> Iterator[dict[str, Any]]:
        self.requests.append((operation, request))
        if self._failure is not None:
            code = CODES[self._failure]
            raise ClientError({"Error": {"Code": code, "Message": "stubbed"}}, operation)
        if operation == "list_price_lists":
            yield from self._pages("PriceLists", self._lists.get(request["ServiceCode"], []))
            return
        filters = request["Filters"]
        region = next(f["Value"] for f in filters if f["Field"] == "regionCode")
        rest = [f for f in filters if f["Field"] != "regionCode"]
        held = self._products.get(f"{request['ServiceCode']}:{region}", [])
        yield from self._pages("PriceList", [item for item in held if _matches(item, rest)])

    def _pages(self, key: str, items: list[Any]) -> Iterator[dict[str, Any]]:
        if not items:
            yield {key: []}
            return
        for start in range(0, len(items), self._page_size):
            yield {key: items[start : start + self._page_size]}


class _Paginator:
    def __init__(self, client: StubPricing, operation: str) -> None:
        self._client = client
        self._operation = operation

    def paginate(self, **request: Any) -> Iterator[dict[str, Any]]:
        return self._client.answer(self._operation, request)


def fake_backed(*, failure: type[CollectionError] | None = None) -> AwsPriceCatalog:
    """The AWS adapter over a stub serving the fake estate's EC2 prices, for the contract."""
    documents = fake_documents()
    client = StubPricing(
        lists={EC2: [price_list(EC2, VERSION, region) for region in sorted(documents)]},
        products={f"{EC2}:{region}": items for region, items in documents.items()},
        failure=failure.cause if failure is not None else None,
    )
    return AwsPriceCatalog(client=client, clock=lambda: fixtures.COLLECTED_AT)
