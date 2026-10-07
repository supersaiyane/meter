"""A price and an instance type as the domain holds them, held to AWS's real data. TASK-P9-002.

The extracts in `tests/providers/aws/extracts` are AWS's own, so the strongest test here builds
the domain's records from them: if the model could not hold a real price list term, the refusal
the spec first asked for, every nought price, would have refused every All Upfront reservation
AWS sells.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from finops_core.domain.catalog import (
    HOURS_PER_YEAR,
    InstanceTypeSpec,
    Price,
    PricingCategory,
    PurchaseOption,
)

EXTRACTS = Path(__file__).resolve().parents[1] / "providers" / "aws" / "extracts"
AT = datetime(2026, 9, 14, 6, 37, 14, tzinfo=UTC)


def extract(name: str) -> Any:
    return json.loads((EXTRACTS / name).read_text())


def terms_of(document: Any) -> list[Price]:
    """The domain's prices for every term in a real price list extract, as an adapter would."""
    found: list[Price] = []
    for kind, by_sku in document["terms"].items():
        for sku, terms in by_sku.items():
            product = document["products"][sku]
            attributes = product["attributes"]
            for term in terms.values():
                recurring, upfront, unit = Decimal(0), Decimal(0), "Hrs"
                for dimension in term["priceDimensions"].values():
                    amount = Decimal(dimension["pricePerUnit"]["USD"])
                    if dimension["unit"] == "Quantity":
                        upfront += amount
                    else:
                        recurring, unit = amount, dimension["unit"]
                options = term["termAttributes"]
                committed = kind == "Reserved"
                found.append(
                    Price(
                        service_code=document["offerCode"],
                        region=attributes["regionCode"],
                        sku=sku,
                        sku_price_id=f"{sku}.{term['offerTermCode']}",
                        sku_meter=attributes["usagetype"],
                        pricing_unit=unit,
                        pricing_category=(
                            PricingCategory.COMMITTED if committed else PricingCategory.STANDARD
                        ),
                        currency="USD",
                        recurring_unit_price=recurring,
                        upfront_fee=upfront,
                        lease_years=int(options["LeaseContractLength"][0]) if committed else None,
                        purchase_option=(
                            PurchaseOption(options["PurchaseOption"]) if committed else None
                        ),
                        offering_class=options.get("OfferingClass"),
                        details={"instanceType": attributes["instanceType"]},
                        effective_date=date.fromisoformat(term["effectiveDate"][:10]),
                        version=document["version"],
                        as_of=AT,
                        collected_at=AT,
                    )
                )
    return found


# --- the real price list --------------------------------------------------------


def test_every_term_of_a_real_price_list_is_a_price() -> None:
    found = terms_of(extract("elasticache-eu-west-1-cache-m5-large.json"))
    assert len(found) == 7
    assert {price.pricing_category for price in found} == set(PricingCategory)


def test_a_real_all_upfront_reservation_is_nought_an_hour_beside_its_fee() -> None:
    found = {
        p.sku_price_id: p for p in terms_of(extract("elasticache-eu-west-1-cache-m5-large.json"))
    }
    three_years = found["RPVSXBK67RKQZAHJ.NQ3QZPMQV9"]
    assert three_years.recurring_unit_price == 0
    assert three_years.upfront_fee == Decimal("1631.2")
    assert three_years.purchase_option is PurchaseOption.ALL_UPFRONT
    assert three_years.effective_hourly == Decimal("1631.2") / (3 * HOURS_PER_YEAR)


def test_a_real_on_demand_price_is_its_hourly_rate() -> None:
    found = {
        p.sku_price_id: p for p in terms_of(extract("elasticache-eu-west-1-cache-m5-large.json"))
    }
    on_demand = found["RPVSXBK67RKQZAHJ.JRTCKXETXF"]
    assert on_demand.effective_hourly == Decimal("0.1376")
    assert on_demand.lease_years is None


# --- what is refused -------------------------------------------------------------


def price(**overrides: Any) -> Price:
    fields: dict[str, Any] = {
        "service_code": "AmazonEC2",
        "region": "eu-west-1",
        "sku": "ABCDEFGHIJKLMNOP",
        "sku_price_id": "ABCDEFGHIJKLMNOP.JRTCKXETXF",
        "sku_meter": "EU-BoxUsage:m5.large",
        "pricing_unit": "Hrs",
        "pricing_category": PricingCategory.STANDARD,
        "currency": "USD",
        "recurring_unit_price": Decimal("0.107"),
        "effective_date": date(2026, 9, 1),
        "version": "20260917190528",
        "as_of": AT,
        "collected_at": AT,
    }
    return Price(**{**fields, **overrides})


@pytest.mark.parametrize(
    ("overrides", "says"),
    [
        ({"recurring_unit_price": Decimal(0)}, "every price is nought"),
        ({"recurring_unit_price": Decimal("-1")}, "never negative"),
        ({"currency": "usd"}, "ISO 4217"),
        ({"pricing_category": PricingCategory.COMMITTED}, "names its length"),
        ({"upfront_fee": Decimal("10")}, "nothing up front"),
        ({"lease_years": 1}, "nothing up front"),
    ],
)
def test_a_price_that_is_not_one_is_refused(overrides: dict[str, Any], says: str) -> None:
    with pytest.raises(ValueError, match=says):
        price(**overrides)


def test_a_price_not_charged_by_the_hour_has_no_hourly_figure() -> None:
    assert price(pricing_unit="GB-Mo").effective_hourly is None


# --- the real instance description -------------------------------------------------


def test_a_real_instance_description_is_an_instance_type() -> None:
    (described,) = extract("describe-instance-types-t2-micro.json")["InstanceTypes"]
    spec = InstanceTypeSpec(
        service_code="AmazonEC2",
        region="eu-west-1",
        instance_type=described["InstanceType"],
        family=described["InstanceType"].split(".")[0],
        current_generation=described["CurrentGeneration"],
        architectures=tuple(described["ProcessorInfo"]["SupportedArchitectures"]),
        burstable=described["BurstablePerformanceSupported"],
        vcpus=described["VCpuInfo"]["DefaultVCpus"],
        memory_mib=described["MemoryInfo"]["SizeInMiB"],
        network_performance=described["NetworkInfo"]["NetworkPerformance"],
        as_of=AT,
        collected_at=AT,
    )
    assert (spec.vcpus, spec.memory_mib, spec.burstable) == (1, 1024, True)
    # t2 publishes no bandwidth figures, and None says so rather than a guess.
    assert spec.network_baseline_gbps is None


@pytest.mark.parametrize(("vcpus", "memory"), [(0, 1024), (1, 0)])
def test_an_instance_type_with_no_vcpus_or_memory_is_refused(vcpus: int, memory: int) -> None:
    with pytest.raises(ValueError, match="no vCPUs or no memory"):
        InstanceTypeSpec(
            service_code="AmazonEC2",
            region="eu-west-1",
            instance_type="x.large",
            family="x",
            current_generation=True,
            architectures=("x86_64",),
            burstable=False,
            vcpus=vcpus,
            memory_mib=memory,
            network_performance="High",
            as_of=AT,
            collected_at=AT,
        )
