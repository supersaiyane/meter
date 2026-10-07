"""What every price catalog and instance catalog must do, fake or real. TASK-P9-002.

P9 spec sections 5.3, 5.4 and 14. The fakes pass it, and so does the AWS price list adapter,
TASK-P9-004, over a stubbed client serving the fake's own prices in GetProducts' shape; TASK-P9-005
adds the instance catalog's adapter the same way. A contract one implementation is held to and
another is not is a description of the first.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any

import pytest

from finops_core.domain.catalog import PricingCategory, PurchaseOption
from finops_core.errors import AccessDenied, NoData, NotOptedIn
from finops_core.ports import InstanceCatalog, PriceCatalog
from finops_fakes.catalog import FakeInstanceCatalog, FakePriceCatalog
from finops_fakes.estate_shape import REGIONS
from finops_fakes.prices import INSTANCE_USD
from tests.providers.aws.pricing import fake_backed

EC2 = "AmazonEC2"

PRICE_CATALOGS: dict[str, Callable[..., Any]] = {"fake": FakePriceCatalog, "aws": fake_backed}
INSTANCE_CATALOGS: dict[str, Callable[..., Any]] = {"fake": FakeInstanceCatalog}


@pytest.fixture(params=sorted(PRICE_CATALOGS))
def make_prices(request: pytest.FixtureRequest) -> Callable[..., Any]:
    return PRICE_CATALOGS[request.param]


@pytest.fixture(params=sorted(INSTANCE_CATALOGS))
def make_instances(request: pytest.FixtureRequest) -> Callable[..., Any]:
    return INSTANCE_CATALOGS[request.param]


# --- prices ----------------------------------------------------------------------


def test_it_is_a_price_catalog(make_prices: Callable[..., Any]) -> None:
    assert isinstance(make_prices(), PriceCatalog)


def test_each_region_has_one_current_version_published_before_it_was_read(
    make_prices: Callable[..., Any],
) -> None:
    versions = tuple(make_prices().versions(EC2))
    assert versions
    assert len({v.region for v in versions}) == len(versions)
    for version in versions:
        assert version.version
        assert version.as_of.tzinfo is not None
        assert version.collected_at >= version.as_of


def test_every_price_belongs_to_the_version_it_was_read_for(
    make_prices: Callable[..., Any],
) -> None:
    catalog = make_prices()
    for version in catalog.versions(EC2):
        found = tuple(catalog.prices(version))
        assert found
        assert all(p.region == version.region and p.version == version.version for p in found)
        assert all(p.service_code == version.service_code for p in found)
        counts = Counter(p.sku_price_id for p in found)
        assert max(counts.values()) == 1, "a price appears twice in one version"


def test_every_reserved_product_can_also_be_bought_on_demand(
    make_prices: Callable[..., Any],
) -> None:
    catalog = make_prices()
    version = next(iter(catalog.versions(EC2)))
    found = tuple(catalog.prices(version))
    on_demand = {p.sku for p in found if p.pricing_category is PricingCategory.STANDARD}
    reserved = {p.sku for p in found if p.pricing_category is PricingCategory.COMMITTED}
    assert reserved <= on_demand


def test_all_upfront_is_paid_up_front_and_nothing_an_hour(
    make_prices: Callable[..., Any],
) -> None:
    """As the real price list states it, tests/providers/aws/extracts."""
    catalog = make_prices()
    version = next(iter(catalog.versions(EC2)))
    upfront = [
        p for p in catalog.prices(version) if p.purchase_option is PurchaseOption.ALL_UPFRONT
    ]
    assert upfront
    assert all(p.recurring_unit_price == 0 and p.upfront_fee > 0 for p in upfront)


def test_a_reservation_costs_less_an_hour_than_on_demand(make_prices: Callable[..., Any]) -> None:
    catalog = make_prices()
    version = next(iter(catalog.versions(EC2)))
    found = tuple(catalog.prices(version))
    on_demand = {
        p.sku: p.effective_hourly for p in found if p.pricing_category is PricingCategory.STANDARD
    }
    for reserved in (p for p in found if p.pricing_category is PricingCategory.COMMITTED):
        assert reserved.effective_hourly is not None
        assert reserved.effective_hourly < on_demand[reserved.sku]


def test_a_service_and_region_the_list_does_not_hold_is_no_data(
    make_prices: Callable[..., Any],
) -> None:
    catalog = make_prices()
    version = next(iter(catalog.versions(EC2)))
    elsewhere = version.__class__(
        service_code=version.service_code,
        region="nowhere-1",
        version=version.version,
        as_of=version.as_of,
        collected_at=version.collected_at,
    )
    with pytest.raises(NoData):
        tuple(catalog.prices(elsewhere))


def test_a_refused_read_is_raised_by_its_cause(make_prices: Callable[..., Any]) -> None:
    with pytest.raises(AccessDenied):
        tuple(make_prices(failure=AccessDenied).versions(EC2))


# --- the fake's own promises ---------------------------------------------------------


def test_the_fake_prices_every_type_the_estate_bills_in_every_region() -> None:
    catalog = FakePriceCatalog()
    assert {v.region for v in catalog.versions(EC2)} == set(REGIONS)
    version = next(iter(catalog.versions(EC2)))
    priced = {p.details["instanceType"] for p in catalog.prices(version)}
    assert priced == set(INSTANCE_USD)


def test_the_fake_holds_no_other_service() -> None:
    assert tuple(FakePriceCatalog().versions("AmazonRDS")) == ()


# --- instance types ----------------------------------------------------------------


def test_it_is_an_instance_catalog(make_instances: Callable[..., Any]) -> None:
    assert isinstance(make_instances(), InstanceCatalog)


def test_each_type_is_described_once_with_its_size(make_instances: Callable[..., Any]) -> None:
    found = tuple(make_instances().instance_types(REGIONS[0]))
    assert found
    assert len({s.instance_type for s in found}) == len(found)
    assert all(s.vcpus > 0 and s.memory_mib > 0 and s.architectures for s in found)
    assert all(s.region == REGIONS[0] and s.collected_at >= s.as_of for s in found)


def test_a_region_not_opted_into_is_not_opted_in(make_instances: Callable[..., Any]) -> None:
    with pytest.raises(NotOptedIn):
        tuple(make_instances(not_opted_in=["eu-fake-1"]).instance_types("eu-fake-1"))


def test_every_type_the_estate_bills_is_described() -> None:
    described = {s.instance_type for s in FakeInstanceCatalog().instance_types(REGIONS[0])}
    assert described == set(INSTANCE_USD)
