"""The Savings Plans rate adapter, held to the API's shape. TASK-P9-012, FEAT-071.

The search results are written in the shape the botocore 1.43.108 model gives
`DescribeSavingsPlansOfferingRates`, and `tests/providers/aws/test_response_shapes.py` holds every
name read here to that model.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from finops_core.domain.catalog import SAVINGS_PLANS, PricingCategory, PurchaseOption
from finops_core.errors import AccessDenied, NoData, SchemaDrift, Throttled
from finops_providers.aws.savings_plans import AwsSavingsPlansRates
from tests.providers.aws.pricing import StubSavingsPlans

AT = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
REGION = "eu-west-1"
OFFERING = "9a2bf7e1-1111-4c1d-8d3e-0123456789ab"


def result(**overrides: Any) -> dict[str, Any]:
    """One rate: a one year No Upfront Compute plan's rate for Linux m5.large in eu-west-1."""
    offering = {
        "offeringId": OFFERING,
        "paymentOption": "No Upfront",
        "planType": "Compute",
        "durationSeconds": 31536000,
        "currency": "USD",
        "planDescription": "1 year No Upfront Compute Savings Plan",
        **overrides.pop("offering", {}),
    }
    return {
        "savingsPlanOffering": offering,
        "rate": "0.0770",
        "unit": "Hrs",
        "productType": "EC2",
        "serviceCode": "AmazonEC2",
        "usageType": "EU-BoxUsage:m5.large",
        "operation": "RunInstances",
        "properties": [
            {"name": "region", "value": REGION},
            {"name": "instanceType", "value": "m5.large"},
            {"name": "instanceFamily", "value": "m5"},
            {"name": "productDescription", "value": "Linux/UNIX"},
            {"name": "tenancy", "value": "shared"},
        ],
        **overrides,
    }


class Serving:
    """A client that answers every request with the same results, whatever it asked for."""

    def __init__(self, results: list[dict[str, Any]]) -> None:
        self._results = results

    def get_paginator(self, _operation: str) -> Serving:
        return self

    def paginate(self, **_request: Any) -> Iterator[dict[str, Any]]:
        yield {"searchResults": self._results}


def read(*results: dict[str, Any], failure: str | None = None) -> tuple[Any, StubSavingsPlans]:
    client = StubSavingsPlans(list(results), failure=failure)
    return AwsSavingsPlansRates(client=client, clock=lambda: AT).rates(REGION), client


def test_a_rate_is_a_committed_price_of_the_plans_length_and_payment() -> None:
    sheet, _ = read(result())
    (price,) = sheet.prices
    assert price.service_code == SAVINGS_PLANS
    assert price.sku == OFFERING
    assert price.sku_price_id == f"{OFFERING}.EU-BoxUsage:m5.large.RunInstances"
    assert (price.pricing_category, price.lease_years) == (PricingCategory.COMMITTED, 1)
    assert price.purchase_option is PurchaseOption.NO_UPFRONT
    assert (price.offering_class, price.pricing_unit) == ("Compute", "Hrs")
    assert price.recurring_unit_price == Decimal("0.0770")
    assert price.details == {
        "instanceType": "m5.large",
        "instanceFamily": "m5",
        "productDescription": "Linux/UNIX",
        "tenancy": "shared",
        "discountedServiceCode": "AmazonEC2",
        "productType": "EC2",
    }
    assert (price.effective_date, price.as_of, price.collected_at) == (date(2026, 10, 8), AT, AT)
    assert sheet.version.region == REGION
    assert len(sheet.version.version) == 20


def test_each_plan_type_and_payment_option_is_asked_for_alone() -> None:
    _, client = read(result())
    asked = [(r["savingsPlanTypes"], r["savingsPlanPaymentOptions"]) for r in client.requests]
    assert asked == [
        (["Compute"], ["No Upfront"]),
        (["Compute"], ["Partial Upfront"]),
        (["Compute"], ["All Upfront"]),
        (["EC2Instance"], ["No Upfront"]),
        (["EC2Instance"], ["Partial Upfront"]),
        (["EC2Instance"], ["All Upfront"]),
    ]
    first = client.requests[0]
    assert first["products"] == ["EC2"]
    assert first["filters"] == [
        {"name": "region", "values": [REGION]},
        {"name": "tenancy", "values": ["shared"]},
    ]
    assert first["maxResults"] == 1000


def test_a_three_year_all_upfront_rate_is_read_as_one() -> None:
    three = result(offering={"durationSeconds": 94608000, "paymentOption": "All Upfront"})
    sheet, _ = read(three)
    (price,) = sheet.prices
    assert (price.lease_years, price.purchase_option) == (3, PurchaseOption.ALL_UPFRONT)


def test_the_same_rate_twice_is_kept_once() -> None:
    sheet, _ = read(result(), result())
    assert len(sheet.prices) == 1


def test_the_version_moves_when_a_rate_does() -> None:
    before, _ = read(result())
    after, _ = read(result(rate="0.0771"))
    again, _ = read(result())
    assert before.version.version != after.version.version
    assert before.version.version == again.version.version


@pytest.mark.parametrize(
    ("overrides", "says"),
    [
        ({"rate": "0"}, "nought"),
        ({"rate": "not a number"}, "cannot read"),
        ({"offering": {"durationSeconds": 86400}}, "lasts 86400"),
        ({"offering": {"durationSeconds": "long"}}, "cannot read"),
        ({"offering": {"currency": "CNY"}}, "CNY"),
        ({"offering": {"paymentOption": "Some Upfront"}}, "cannot read"),
        ({"unit": None}, "no offering"),
        ({"usageType": ""}, "no offering"),
        ({"properties": [{"name": "region", "value": "us-east-1"}]}, "rate for us-east-1"),
    ],
)
def test_a_rate_this_cannot_read_is_schema_drift(overrides: dict[str, Any], says: str) -> None:
    rates = AwsSavingsPlansRates(client=Serving([result(**overrides)]), clock=lambda: AT)
    with pytest.raises(SchemaDrift, match=says):
        rates.rates(REGION)


def test_a_region_with_no_rate_is_no_data() -> None:
    with pytest.raises(NoData):
        read()


@pytest.mark.parametrize(
    ("code", "cause"), [("AccessDenied", AccessDenied), ("Throttled", Throttled)]
)
def test_a_refused_read_is_raised_by_its_cause(code: str, cause: type[Exception]) -> None:
    with pytest.raises(cause):
        read(result(), failure=code)
