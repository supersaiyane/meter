"""The price list adapter, held to AWS's own responses. TASK-P9-004, FEAT-071.

The extracts in `tests/providers/aws/extracts` are AWS's: the two sample responses in the Price
List API reference, and products from the real ElastiCache list for eu-west-1. The ElastiCache
products are in the offer file's form, and are rewritten into GetProducts' form here by the one
difference between the two, where the terms are keyed.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

from finops_core.domain.catalog import PriceListVersion, PricingCategory, PurchaseOption
from finops_core.errors import AccessDenied, NoData, SchemaDrift, Throttled
from finops_providers.aws.price_list import (
    COMPARABLE,
    AwsPriceCatalog,
    commercial,
    published,
)
from tests.providers.aws.pricing import StubPricing, price_list, volume

EXTRACTS = Path(__file__).resolve().parent / "extracts"
AT = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
EC2 = "AmazonEC2"
CACHE = "AmazonElastiCache"
#: A service read whole for its Region, so what the adapter filters itself reaches it unfiltered.
RDS = "AmazonRDS"


def extract(name: str) -> Any:
    return json.loads((EXTRACTS / name).read_text())


def as_get_products(offer: Any) -> list[str]:
    """An offer file's products as GetProducts items: the terms keyed by SKU and term alone."""
    return [
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


def version_of(service: str, region: str, version: str) -> PriceListVersion:
    return PriceListVersion(
        service_code=service,
        region=region,
        version=version,
        as_of=published(version),
        collected_at=AT,
    )


def catalog(
    *,
    lists: dict[str, list[dict[str, Any]]] | None = None,
    products: dict[str, list[str]] | None = None,
    failure: str | None = None,
) -> tuple[AwsPriceCatalog, StubPricing]:
    client = StubPricing(lists=lists or {}, products=products or {}, failure=failure)
    return AwsPriceCatalog(client=client, clock=lambda: AT), client


def product(
    sku: str = "AAAAAAAAAAAAAAAA",
    *,
    attributes: dict[str, str] | None = None,
    dimensions: dict[str, Any] | None = None,
    family: str = "Compute Instance",
) -> str:
    """One EC2 instance product with one on demand term, varied by the case under test."""
    fields = {
        "instanceType": "m5.large",
        "operatingSystem": "Linux",
        "regionCode": "eu-west-1",
        "usagetype": "EU-BoxUsage:m5.large",
        **COMPARABLE,
        **(attributes or {}),
    }
    priced = dimensions or {
        f"{sku}.JRTCKXETXF.6YS6EN2CT7": {"unit": "Hrs", "pricePerUnit": {"USD": "0.1070000000"}}
    }
    return json.dumps(
        {
            "product": {"productFamily": family, "sku": sku, "attributes": fields},
            "terms": {
                "OnDemand": {
                    f"{sku}.JRTCKXETXF": {
                        "offerTermCode": "JRTCKXETXF",
                        "sku": sku,
                        "effectiveDate": "2026-09-01T00:00:00Z",
                        "priceDimensions": priced,
                        "termAttributes": {},
                    }
                }
            },
        }
    )


def ec2_prices(*items: str, service: str = EC2) -> list[Any]:
    """The prices read from `items`. An EC2 Region also holds the volume every real one has,
    which is left out of what is returned."""
    extra = [volume("eu-west-1")] if service == EC2 and items else []
    found, _ = catalog(products={f"{service}:eu-west-1": [*items, *extra]})
    read = found.prices(version_of(service, "eu-west-1", "20260917190528"))
    return [p for p in read if p.pricing_unit != "GB-Mo"]


# --- versions -------------------------------------------------------------------------


def test_the_real_list_price_lists_sample_is_a_version_published_when_its_arn_says() -> None:
    sample = extract("list-price-lists-ec2.json")
    found, client = catalog(lists={EC2: sample["PriceLists"]})
    (version,) = found.versions(EC2)
    assert (version.region, version.version) == ("us-east-1", "20220603151047")
    assert version.as_of == datetime(2022, 6, 3, 15, 10, 47, tzinfo=UTC)
    assert version.collected_at == AT
    assert client.requests == [
        ("list_price_lists", {"ServiceCode": EC2, "EffectiveDate": AT, "CurrencyCode": "USD"})
    ]


def test_the_version_is_the_publication_time_as_the_real_list_pairs_them() -> None:
    # The ElastiCache list's own pair, and the GetProducts sample's.
    offer = extract("elasticache-eu-west-1-cache-m5-large.json")
    assert (
        published(offer["version"]).isoformat().replace("+00:00", "Z") == (offer["publicationDate"])
    )
    assert published("20170901182201") == datetime(2017, 9, 1, 18, 22, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    ("region", "kept"),
    [
        ("eu-west-1", True),
        ("ap-southeast-2", True),
        ("us-gov-west-1", False),
        ("cn-north-1", False),
        ("us-isob-east-1", False),
        ("us-east-1-bos-1", False),
        ("eusc-de-east-1", False),
        ("", False),
    ],
)
def test_only_a_commercial_region_is_kept_by_its_shape(region: str, kept: bool) -> None:
    assert commercial(region) is kept


def test_the_regions_are_the_price_lists_own_and_other_partitions_are_left_out() -> None:
    lists = [
        price_list(EC2, "20260917190528", region)
        for region in ("us-gov-west-1", "eu-west-1", "cn-north-1", "ap-south-2")
    ]
    found, _ = catalog(lists={EC2: lists})
    assert [v.region for v in found.versions(EC2)] == ["ap-south-2", "eu-west-1"]


def test_two_lists_for_one_region_keep_the_later() -> None:
    lists = [
        price_list(EC2, "20260917190528", "eu-west-1"),
        price_list(EC2, "20260920120000", "eu-west-1"),
        price_list(EC2, "20260901000000", "eu-west-1"),
    ]
    found, _ = catalog(lists={EC2: lists})
    assert [v.version for v in found.versions(EC2)] == ["20260920120000"]


@pytest.mark.parametrize(
    ("raw", "says"),
    [
        (
            {"PriceListArn": "arn:aws:pricing:::nothing", "RegionCode": "eu-west-1"},
            "unreadable ARN",
        ),
        (
            {
                "PriceListArn": "arn:aws:pricing:::price-list/aws/AmazonRDS/USD/1/eu-west-1",
                "RegionCode": "eu-west-1",
                "CurrencyCode": "USD",
            },
            "unreadable ARN",
        ),
        (
            {
                "PriceListArn": "arn:aws:pricing:::price-list/aws/AmazonEC2/CNY/1/eu-west-1",
                "RegionCode": "eu-west-1",
                "CurrencyCode": "CNY",
            },
            "not priced in USD",
        ),
        (
            {
                "PriceListArn": "arn:aws:pricing:::price-list/aws/AmazonEC2/USD/latest/eu-west-1",
                "RegionCode": "eu-west-1",
                "CurrencyCode": "USD",
            },
            "not a publication time",
        ),
    ],
)
def test_a_price_list_this_cannot_read_is_schema_drift(raw: dict[str, str], says: str) -> None:
    found, _ = catalog(lists={EC2: [raw]})
    with pytest.raises(SchemaDrift, match=says):
        found.versions(EC2)


# --- the real products ------------------------------------------------------------------


def test_the_real_get_products_sample_is_one_ebs_price() -> None:
    sample = extract("get-products-ec2-ebs-io1.json")
    instance = product(attributes={"regionCode": "ca-central-1"})
    found, client = catalog(products={f"{EC2}:ca-central-1": [instance, *sample["PriceList"]]})
    read = list(found.prices(version_of(EC2, "ca-central-1", "20170901182201")))
    (price,) = [p for p in read if p.sku == "WQGC34PB2AWS8R4U"]
    assert price.sku_price_id == "WQGC34PB2AWS8R4U.JRTCKXETXF"
    assert (price.pricing_unit, price.recurring_unit_price) == ("GB-Mo", Decimal("0.138"))
    assert price.sku_meter == "CAN1-EBS:VolumeUsage.piops"
    assert price.effective_date == date(2017, 8, 1)
    assert price.details == {
        "volumeType": "Provisioned IOPS",
        "storageMedia": "SSD-backed",
        "productFamily": "Storage",
    }
    assert price.as_of == datetime(2017, 9, 1, 18, 22, 1, tzinfo=UTC)
    asked = [request["Filters"] for _, request in client.requests]
    region = {"Type": "TERM_MATCH", "Field": "regionCode", "Value": "ca-central-1"}
    assert asked == [
        [region, *({"Type": "TERM_MATCH", "Field": f, "Value": v} for f, v in COMPARABLE.items())],
        *(
            [region, {"Type": "TERM_MATCH", "Field": "productFamily", "Value": family}]
            for family in ("Storage", "System Operation", "Provisioned Throughput")
        ),
    ]
    assert all(r["FormatVersion"] == "aws_v1" for _, r in client.requests)


def test_every_real_elasticache_term_is_a_price_and_all_upfront_is_its_fee() -> None:
    items = as_get_products(extract("elasticache-eu-west-1-cache-m5-large.json"))
    found, client = catalog(products={f"{CACHE}:eu-west-1": items})
    version = version_of(CACHE, "eu-west-1", "20260914063714")
    prices = {p.sku_price_id: p for p in found.prices(version)}
    assert len(prices) == 7
    three_years = prices["RPVSXBK67RKQZAHJ.NQ3QZPMQV9"]
    assert three_years.pricing_category is PricingCategory.COMMITTED
    assert (three_years.lease_years, three_years.purchase_option) == (
        3,
        PurchaseOption.ALL_UPFRONT,
    )
    assert three_years.recurring_unit_price == 0
    assert three_years.upfront_fee == Decimal("1631.2")
    assert prices["RPVSXBK67RKQZAHJ.JRTCKXETXF"].recurring_unit_price == Decimal("0.1376")
    # Read whole by Region: only EC2 is narrowed at the source.
    assert [r["Filters"] for _, r in client.requests] == [
        [{"Type": "TERM_MATCH", "Field": "regionCode", "Value": "eu-west-1"}]
    ]


def test_a_real_extended_support_product_is_named_not_read_as_the_types_price() -> None:
    items = as_get_products(extract("elasticache-eu-west-1-extended-support.json"))
    found, _ = catalog(products={f"{CACHE}:eu-west-1": items})
    surcharges = list(found.prices(version_of(CACHE, "eu-west-1", "20260914063714")))
    assert surcharges
    assert all(p.details["extendedSupport"] == "Yr3" for p in surcharges)
    assert all(p.details["instanceType"] == "cache.m5.xlarge" for p in surcharges)


# --- the comparable price -----------------------------------------------------------------


@pytest.mark.parametrize(
    "attributes",
    [
        {"tenancy": "Dedicated"},
        {"capacitystatus": "UnusedCapacityReservation"},
        {"preInstalledSw": "SQL Web"},
    ],
)
def test_a_price_that_is_not_the_comparable_one_is_left_out(attributes: dict[str, str]) -> None:
    # EC2 asks AWS for the comparable price; this is the filter every other service relies on.
    assert ec2_prices(product(attributes=attributes), service=RDS) == []


def test_a_product_that_is_neither_an_instance_nor_a_volume_is_left_out() -> None:
    transfer = json.loads(product())
    del transfer["product"]["attributes"]["instanceType"]
    transfer["product"]["productFamily"] = "Data Transfer"
    assert ec2_prices(json.dumps(transfer), service=RDS) == []


def test_the_operating_system_is_kept_rather_than_filtered() -> None:
    (windows,) = ec2_prices(product(attributes={"operatingSystem": "Windows"}))
    assert windows.details["operatingSystem"] == "Windows"
    assert windows.details["instanceType"] == "m5.large"


# --- refused, never stored ---------------------------------------------------------------

HOURLY = "AAAAAAAAAAAAAAAA.JRTCKXETXF.6YS6EN2CT7"


@pytest.mark.parametrize(
    ("item", "says"),
    [
        (product(dimensions={HOURLY: {"unit": "Hrs", "pricePerUnit": {"USD": "0"}}}), "nought"),
        (product(dimensions={HOURLY: {"unit": "Hrs", "pricePerUnit": {"CNY": "1"}}}), "CNY"),
        (product(dimensions={HOURLY: {"unit": "Hrs", "pricePerUnit": {}}}), "0 currencies"),
        (product(dimensions={HOURLY: {"unit": "Hrs", "pricePerUnit": {"USD": "x"}}}), "price 'x'"),
        (
            product(
                dimensions={
                    HOURLY: {"unit": "Hrs", "pricePerUnit": {"USD": "1"}},
                    f"{HOURLY}X": {"unit": "Hrs", "pricePerUnit": {"USD": "2"}},
                }
            ),
            "2 recurring prices",
        ),
        (
            product(dimensions={HOURLY: {"unit": "Quantity", "pricePerUnit": {"USD": "9"}}}),
            "0 recurring prices",
        ),
        (product(attributes={"regionCode": "us-east-1"}), "priced for us-east-1"),
        (product(attributes={"usagetype": ""}), "no usage type"),
        ("{not json", "cannot read"),
        (json.dumps({"product": {"attributes": {}}}), "no SKU"),
    ],
)
def test_a_price_this_cannot_read_is_refused_as_schema_drift(item: str, says: str) -> None:
    with pytest.raises(SchemaDrift, match=says):
        ec2_prices(item, service=RDS)


def test_a_product_with_no_price_is_refused() -> None:
    bare = json.loads(product())
    bare["terms"] = {}
    with pytest.raises(SchemaDrift, match="has no price"):
        ec2_prices(json.dumps(bare))


def test_a_reservation_with_no_length_is_refused() -> None:
    reserved = json.loads(product())
    term = reserved["terms"].pop("OnDemand")["AAAAAAAAAAAAAAAA.JRTCKXETXF"]
    term["termAttributes"] = {"PurchaseOption": "No Upfront"}
    reserved["terms"]["Reserved"] = {"AAAAAAAAAAAAAAAA.4NA7Y494T4": term}
    with pytest.raises(SchemaDrift, match="cannot read"):
        ec2_prices(json.dumps(reserved))


def test_a_region_the_list_holds_nothing_for_is_no_data() -> None:
    with pytest.raises(NoData):
        ec2_prices()


def test_an_ec2_region_with_volumes_and_no_instance_is_no_data_not_volumes_alone() -> None:
    # A wrong instance filter would look like this: EBS found, no instance. ISS-261.
    sample = extract("get-products-ec2-ebs-io1.json")
    found, _ = catalog(products={f"{EC2}:ca-central-1": sample["PriceList"]})
    with pytest.raises(NoData, match="tenancy Shared, capacitystatus Used"):
        list(found.prices(version_of(EC2, "ca-central-1", "20170901182201")))


def gp3_term(sku: str, family: str, unit: str, *, named: bool = True) -> str:
    """gp3's IOPS or throughput, a product of its own as the real list sells it. Price invented."""
    item = json.loads(
        product(
            sku,
            family=family,
            attributes={"usagetype": f"EBS:{family}.gp3", "volumeApiName": "gp3"},
            dimensions={
                f"{sku}.JRTCKXETXF.6YS6EN2CT7": {"unit": unit, "pricePerUnit": {"USD": "0.005"}}
            },
        )
    )
    fields = item["product"]["attributes"]
    for name in (
        "instanceType",
        "operatingSystem",
        *COMPARABLE,
        *(() if named else ("volumeApiName",)),
    ):
        del fields[name]
    return json.dumps(item)


def test_gp3_iops_and_throughput_are_read_from_their_own_families() -> None:
    items = [
        product(),
        volume("eu-west-1"),
        gp3_term("I" * 16, "System Operation", "IOPS-Mo"),
        gp3_term("T" * 16, "Provisioned Throughput", "MiBps-Mo"),
    ]
    found, _ = catalog(products={f"{EC2}:eu-west-1": items})
    read = list(found.prices(version_of(EC2, "eu-west-1", "20260917190528")))
    gp3 = {
        (p.details["productFamily"], p.pricing_unit)
        for p in read
        if p.details.get("volumeApiName") == "gp3"
    }
    assert gp3 == {
        ("Storage", "GB-Mo"),
        ("System Operation", "IOPS-Mo"),
        ("Provisioned Throughput", "MiBps-Mo"),
    }


def test_a_region_selling_no_gp3_iops_or_throughput_still_loads() -> None:
    # Only the gp2 to gp3 comparison needs them, and it says so when they are missing.
    found, _ = catalog(products={f"{EC2}:eu-west-1": [product(), volume("eu-west-1")]})
    read = list(found.prices(version_of(EC2, "eu-west-1", "20260917190528")))
    assert {p.pricing_unit for p in read} == {"Hrs", "GB-Mo"}


def test_an_operation_price_for_no_volume_type_is_left_out() -> None:
    nameless = gp3_term("N" * 16, "System Operation", "IOPS-Mo", named=False)
    found, _ = catalog(products={f"{EC2}:eu-west-1": [product(), volume("eu-west-1"), nameless]})
    read = list(found.prices(version_of(EC2, "eu-west-1", "20260917190528")))
    assert all(p.sku != "N" * 16 for p in read)


# --- how it reads ---------------------------------------------------------------------------


def test_prices_are_read_a_page_at_a_time_and_never_held_whole() -> None:
    items = [*(product(sku=chr(65 + n) * 16) for n in range(5)), volume("eu-west-1")]
    found, client = catalog(products={f"{EC2}:eu-west-1": items})
    version = version_of(EC2, "eu-west-1", "20260917190528")
    assert inspect.isgenerator(found.prices(version))
    reading = found.prices(version)
    assert client.requests == []
    first = next(reading)
    assert first.sku == "A" * 16
    assert len(client.requests) == 1
    assert len([first, *reading]) == 6


@pytest.mark.parametrize(
    ("code", "cause"), [("AccessDenied", AccessDenied), ("Throttled", Throttled)]
)
def test_a_refused_call_is_raised_by_its_cause(code: str, cause: type[Exception]) -> None:
    found, _ = catalog(failure=code)
    with pytest.raises(cause):
        found.versions(EC2)
    with pytest.raises(cause):
        list(found.prices(version_of(EC2, "eu-west-1", "20260917190528")))


def test_an_sdk_failure_mid_read_is_typed_too() -> None:
    class Failing:
        def get_paginator(self, _operation: str) -> Any:
            return self

        def paginate(self, **_request: Any) -> Iterator[dict[str, Any]]:
            yield {"PriceList": [product()]}
            raise ClientError({"Error": {"Code": "ThrottlingException"}}, "GetProducts")

    found = AwsPriceCatalog(client=Failing(), clock=lambda: AT)
    with pytest.raises(Throttled):
        list(found.prices(version_of(EC2, "eu-west-1", "20260917190528")))
