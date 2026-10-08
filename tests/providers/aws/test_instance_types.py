"""The instance type adapters, held to AWS's own descriptions. TASK-P9-005, FEAT-072.

EC2's real `t2.micro` description and the real ElastiCache list for eu-west-1 are in
`tests/providers/aws/extracts`. The rest are written in the shape those two have.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from finops_core.errors import AccessDenied, NoData, NotOptedIn, SchemaDrift, Throttled
from finops_providers.aws.burstable import SOURCE
from finops_providers.aws.instance_types import (
    NOT_STATED,
    AwsInstanceCatalog,
    PriceListInstanceCatalog,
)
from tests.providers.aws.ec2_types import StubEc2
from tests.providers.aws.pricing import StubPricing

EXTRACTS = Path(__file__).resolve().parent / "extracts"
AT = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
CACHE = "AmazonElastiCache"
RDS = "AmazonRDS"


def extract(name: str) -> Any:
    return json.loads((EXTRACTS / name).read_text())


def ec2(*types: dict[str, Any], failure: str | None = None) -> AwsInstanceCatalog:
    return AwsInstanceCatalog(
        client_for=lambda _region: StubEc2(types, failure=failure), clock=lambda: AT
    )


def m5_xlarge(**overrides: Any) -> dict[str, Any]:
    """A described type with every figure the adapter reads, in EC2's shape."""
    return {
        "InstanceType": "m5.xlarge",
        "CurrentGeneration": True,
        "ProcessorInfo": {"SupportedArchitectures": ["x86_64"]},
        "BurstablePerformanceSupported": False,
        "VCpuInfo": {"DefaultVCpus": 4},
        "MemoryInfo": {"SizeInMiB": 16384},
        "NetworkInfo": {
            "NetworkPerformance": "Up to 10 Gigabit",
            "NetworkCards": [{"BaselineBandwidthInGbps": 1.25, "PeakBandwidthInGbps": 10.0}],
        },
        "EbsInfo": {
            "EbsOptimizedInfo": {"BaselineBandwidthInMbps": 1150, "MaximumBandwidthInMbps": 4750}
        },
        **overrides,
    }


# --- EC2 ---------------------------------------------------------------------------------


def test_the_real_t2_micro_description_is_a_burstable_type_with_the_guides_baseline() -> None:
    (raw,) = extract("describe-instance-types-t2-micro.json")["InstanceTypes"]
    (spec,) = ec2(raw).instance_types("eu-west-1")
    assert (spec.vcpus, spec.memory_mib, spec.architectures) == (1, 1024, ("i386", "x86_64"))
    assert spec.burstable is True
    assert (spec.baseline_cpu, spec.maximum_credits) == (Decimal("0.10"), Decimal(144))
    assert spec.baseline_source == SOURCE
    # t2 publishes no figures in gigabits, and None says so rather than a guess.
    assert spec.network_baseline_gbps is None
    assert spec.ebs_baseline_mbps is None
    assert (spec.region, spec.as_of, spec.collected_at) == ("eu-west-1", AT, AT)


def test_every_figure_published_is_read() -> None:
    (spec,) = ec2(m5_xlarge()).instance_types("eu-west-1")
    assert (spec.family, spec.network_baseline_gbps, spec.network_peak_gbps) == (
        "m5",
        Decimal("1.25"),
        Decimal("10.0"),
    )
    assert (spec.ebs_baseline_mbps, spec.ebs_maximum_mbps) == (1150, 4750)
    assert spec.baseline_cpu is None


def test_a_type_with_two_network_cards_is_their_sum_and_one_unpublished_is_none() -> None:
    cards = [
        {"BaselineBandwidthInGbps": 100.0, "PeakBandwidthInGbps": 100.0},
        {"BaselineBandwidthInGbps": 100.0, "PeakBandwidthInGbps": 100.0},
    ]
    gpus = {"Gpus": [{"Count": 8}, {"Count": 0}]}
    two = m5_xlarge(
        InstanceType="p5.48xlarge",
        NetworkInfo={"NetworkPerformance": "3200 Gigabit", "NetworkCards": cards},
        GpuInfo=gpus,
    )
    half = m5_xlarge(
        InstanceType="x.large",
        NetworkInfo={"NetworkPerformance": "High", "NetworkCards": [{}, cards[0]]},
    )
    found = {s.instance_type: s for s in ec2(two, half).instance_types("eu-west-1")}
    assert found["p5.48xlarge"].network_baseline_gbps == Decimal(200)
    assert found["p5.48xlarge"].gpu_count == 8
    assert found["x.large"].network_baseline_gbps is None


def test_a_burstable_type_the_table_lacks_is_returned_without_a_baseline() -> None:
    new = m5_xlarge(InstanceType="t9.micro", BurstablePerformanceSupported=True)
    (spec,) = ec2(new).instance_types("eu-west-1")
    assert spec.burstable is True
    assert spec.baseline_cpu is None and spec.baseline_source is None


def test_a_type_listed_twice_is_described_once() -> None:
    assert len(tuple(ec2(m5_xlarge(), m5_xlarge()).instance_types("eu-west-1"))) == 1


@pytest.mark.parametrize(
    "broken",
    [
        {"VCpuInfo": {}},
        {"MemoryInfo": None},
        {"NetworkInfo": {}},
        {"ProcessorInfo": {"SupportedArchitectures": []}},
        {"VCpuInfo": {"DefaultVCpus": 0}},
        {
            "EbsInfo": {
                "EbsOptimizedInfo": {"BaselineBandwidthInMbps": 10, "MaximumBandwidthInMbps": 5}
            }
        },
    ],
)
def test_a_description_this_cannot_read_is_schema_drift(broken: dict[str, Any]) -> None:
    with pytest.raises(SchemaDrift, match=r"m5\.xlarge"):
        ec2(m5_xlarge(**broken)).instance_types("eu-west-1")


@pytest.mark.parametrize(
    ("code", "cause"),
    [("AccessDenied", AccessDenied), ("Throttled", Throttled), ("NotOptedIn", NotOptedIn)],
)
def test_a_refused_describe_is_raised_by_its_cause(code: str, cause: type[Exception]) -> None:
    with pytest.raises(cause):
        ec2(m5_xlarge(), failure=code).instance_types("eu-west-1")


# --- the managed services ---------------------------------------------------------------


def products(offer: Any) -> list[str]:
    """An offer file's products as GetProducts items, as the price list adapter reads them."""
    return [
        json.dumps(
            {
                "product": product,
                "terms": {kind: by_sku[sku] for kind, by_sku in offer["terms"].items()},
                "publicationDate": offer["publicationDate"],
            }
        )
        for sku, product in offer["products"].items()
    ]


def managed(service: str, items: list[str], region: str = "eu-west-1") -> list[Any]:
    client = StubPricing(lists={}, products={f"{service}:{region}": items})
    catalog = PriceListInstanceCatalog(client=client, service_code=service, clock=lambda: AT)
    return list(catalog.instance_types(region))


def product(name: str, **attributes: Any) -> str:
    fields = {"instanceType": name, "vcpu": "2", "memory": "8 GiB", "regionCode": "eu-west-1"}
    return json.dumps({"product": {"sku": "S", "attributes": {**fields, **attributes}}})


def test_the_real_elasticache_node_is_described_by_its_attributes() -> None:
    (spec,) = managed(CACHE, products(extract("elasticache-eu-west-1-cache-m5-large.json")))
    assert (spec.instance_type, spec.family, spec.vcpus) == ("cache.m5.large", "m5", 2)
    assert spec.memory_mib == round(Decimal("6.38") * 1024)
    assert spec.network_performance == "Up to 10 Gigabit"
    assert (spec.current_generation, spec.architectures, spec.burstable) == (
        True,
        ("x86_64",),
        False,
    )
    assert spec.as_of == datetime(2026, 9, 14, 6, 37, 14, tzinfo=UTC)
    assert spec.collected_at == AT


def test_a_real_extended_support_product_describes_nothing() -> None:
    items = products(extract("elasticache-eu-west-1-extended-support.json"))
    assert managed(CACHE, items) == []


def test_a_managed_burstable_class_takes_the_ec2_rows_baseline_and_says_so() -> None:
    (spec,) = managed(RDS, [product("db.t3.micro")])
    assert spec.burstable is True
    assert spec.baseline_cpu == Decimal("0.10")
    assert spec.baseline_source == f"{SOURCE}, the row for t3.micro"
    assert spec.family == "t3"


@pytest.mark.parametrize(
    ("name", "attributes", "architecture"),
    [
        ("db.m6g.large", {}, "arm64"),
        ("cache.c7gn.large", {}, "arm64"),
        ("db.m5.large", {}, "x86_64"),
        ("db.r5.large", {"physicalProcessor": "AWS Graviton2"}, "arm64"),
        ("db.r6g.large", {"physicalProcessor": "Intel Xeon"}, "x86_64"),
    ],
)
def test_the_architecture_is_the_named_processor_or_the_familys_name(
    name: str, attributes: dict[str, str], architecture: str
) -> None:
    (spec,) = managed(RDS, [product(name, **attributes)])
    assert spec.architectures == (architecture,)


def test_memory_in_whole_gibibytes_and_unstated_network_are_read() -> None:
    item = product("or1.large.search", memory=None, memoryGib="16")
    (spec,) = managed("AmazonES", [item])
    assert spec.memory_mib == 16 * 1024
    assert spec.network_performance == NOT_STATED


@pytest.mark.parametrize(
    "attributes",
    [{"vcpu": "NA"}, {"memory": "NA"}, {"vcpu": "0"}, {"instanceType": ""}],
)
def test_a_product_that_states_no_size_describes_nothing(attributes: dict[str, str]) -> None:
    assert managed(RDS, [product("db.m5.large", **attributes)]) == []


def test_a_class_listed_by_several_products_is_described_once() -> None:
    assert len(managed(RDS, [product("db.m5.large"), product("db.m5.large", vcpu="4")])) == 1


@pytest.mark.parametrize(
    ("item", "says"),
    [
        (product("db.m5.large", regionCode="us-east-1"), "another Region"),
        ("{not json", "cannot read"),
        (json.dumps({"nothing": 1}), "cannot read"),
    ],
)
def test_a_product_this_cannot_read_is_schema_drift(item: str, says: str) -> None:
    with pytest.raises(SchemaDrift, match=says):
        managed(RDS, [item])


def test_a_region_with_no_products_is_no_data() -> None:
    with pytest.raises(NoData):
        managed(RDS, [])


@pytest.mark.parametrize(
    ("published", "expected"),
    [
        (None, AT),
        ("not a date", AT),
        ("2026-09-14T06:37:14", datetime(2026, 9, 14, 6, 37, 14, tzinfo=UTC)),
    ],
)
def test_a_missing_or_unreadable_publication_is_read_as_the_read(
    published: str | None, expected: datetime
) -> None:
    item = json.loads(product("db.m5.large"))
    item["publicationDate"] = published
    (spec,) = managed(RDS, [json.dumps(item)])
    assert spec.as_of == expected


def test_a_refused_price_list_read_is_raised_by_its_cause() -> None:
    client = StubPricing(lists={}, products={}, failure="Throttled")
    catalog = PriceListInstanceCatalog(client=client, service_code=RDS, clock=lambda: AT)
    with pytest.raises(Throttled):
        catalog.instance_types("eu-west-1")
