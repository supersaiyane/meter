"""AWS's own price list extracts, read through the real adapter, for tests. TASK-P16-004.

The extracts in `extracts` are offer files pruned to a few products; GetProducts keys their terms
by SKU and term alone, which is the one difference rewritten here.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from finops_core.domain.catalog import Price, PriceListVersion
from finops_providers.aws.price_list import AwsPriceCatalog, published
from tests.providers.aws.pricing import StubPricing

EXTRACTS = Path(__file__).resolve().parent / "extracts"
REGION = "eu-west-1"
AT = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


def offer_items(name: str) -> tuple[Any, list[str]]:
    """An extract, and its products as GetProducts items."""
    offer = json.loads((EXTRACTS / name).read_text())
    return offer, [
        json.dumps(
            {
                "product": product,
                "serviceCode": offer["offerCode"],
                "terms": {kind: by_sku[sku] for kind, by_sku in offer["terms"].items()},
                "version": offer["version"],
                "publicationDate": offer["publicationDate"],
            }
        )
        for sku, product in offer["products"].items()
    ]


def version_of(service: str, version: str) -> PriceListVersion:
    return PriceListVersion(
        service_code=service,
        region=REGION,
        version=version,
        as_of=published(version),
        collected_at=AT,
    )


def prices_of(service: str, version: str, items: Sequence[str]) -> list[Price]:
    """What the adapter keeps of `items`, read as one version of one service in eu-west-1."""
    client = StubPricing(lists={}, products={f"{service}:{REGION}": list(items)}, failure=None)
    adapter = AwsPriceCatalog(client=client, clock=lambda: AT)
    return list(adapter.prices(version_of(service, version)))


def real_prices(service: str, name: str) -> tuple[PriceListVersion, list[Price]]:
    """An extract's version and every price the adapter keeps from it."""
    offer, items = offer_items(name)
    return version_of(service, offer["version"]), prices_of(service, offer["version"], items)
