"""The managed services priced from AWS's real rows. TASK-P16-004, FEAT-095, spec section 5.3.

The catalog here is AWS's own eu-west-1 price lists, pruned to the products in
`tests/providers/aws/extracts` and read through the real price list adapter, so every figure is
AWS's published price. It answers as `StoredCatalogue` does: the one on demand row holding every
attribute asked, by its unit, never an Extended Support surcharge, and two rows refused.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import pytest

from finops_core.domain.catalog import Price, PricingCategory
from finops_query.plan_pricing import price_change
from finops_query.plan_quotes import Catalogue, Quote
from finops_query.plan_reading import PlannedChange
from finops_query.plan_services import AURORA, BACKUPS, GP3_SEARCH, MANAGED_STORAGE, ULTRAWARM
from tests.providers.aws.real_prices import REGION, real_prices

FILES = {
    "AmazonRDS": ("rds-eu-west-1-postgresql-and-aurora.json",),
    "AmazonRedshift": ("redshift-eu-west-1-ra3-xlplus.json",),
    "AmazonES": ("opensearch-eu-west-1-r6g-large-and-storage.json",),
    "AmazonElastiCache": (
        "elasticache-eu-west-1-cache-m5-large.json",
        "elasticache-eu-west-1-extended-support.json",
    ),
}
#: The units each term is sold in, as `StoredCatalogue` reads them.
TERMS = {
    "hrs": "hours",
    "gb-mo": "storage",
    "iops-mo": "iops",
    "piops-mo": "iops",
    "mbps-mo": "throughput",
    "mibps-mo": "throughput",
    "gibps-mo": "throughput",
}


class RealRows:
    """AWS's rows, read through the adapter, answered as the stored catalog answers."""

    def __init__(self) -> None:
        self.rows: dict[str, list[tuple[str, Price]]] = {}
        for service, names in FILES.items():
            for name in names:
                version, prices = real_prices(service, name)
                rows = self.rows.setdefault(service, [])
                rows.extend((version.version, one) for one in prices)

    def instance_hour(self, region: str, instance_type: str) -> Quote | str:
        return f"{instance_type} in {region} is not in these extracts"

    def volume_month(self, region: str, volume_type: str, term: str) -> Quote | str:
        return f"{volume_type} {term} in {region} is not in these extracts"

    def service_price(
        self, service: str, region: str, attributes: Mapping[str, str], term: str
    ) -> Quote | str:
        matching = [
            (version, one)
            for version, one in self.rows.get(service, [])
            if one.pricing_category is PricingCategory.STANDARD
            and "extendedSupport" not in one.details
            and TERMS.get(one.pricing_unit.lower()) == term
            and all(one.details.get(key) == value for key, value in attributes.items())
        ]
        named = ", ".join(f"{key} {value}" for key, value in sorted(attributes.items()))
        if not matching:
            return f"the catalog holds no {service} {term} price for {named} in {region}"
        if len({one.recurring_unit_price for _, one in matching}) > 1:
            return f"the catalog holds several {service} {term} prices for {named}"
        version, one = matching[0]
        return Quote(one.sku_price_id, one.recurring_unit_price, one.pricing_unit, version)


ROWS: Catalogue = RealRows()


def planned(resource_type: str, after: dict[str, Any], unknown: tuple[str, ...] = ()) -> Any:
    change = PlannedChange(
        address=f"{resource_type}.this",
        resource_type=resource_type,
        actions=("create",),
        region=REGION,
        before={},
        after=after,
        unknown=unknown,
    )
    return price_change(change, ROWS)


def parts(resource_type: str, after: dict[str, Any]) -> list[tuple[str, Decimal]]:
    line = planned(resource_type, after)
    assert line.priced, line.reason
    return [(one.what, one.monthly) for one in line.after.components]


def refused(resource_type: str, after: dict[str, Any], unknown: tuple[str, ...] = ()) -> str:
    line = planned(resource_type, after, unknown)
    assert line.reason is not None and line.after is None, line
    return str(line.reason)


def database(**more: Any) -> dict[str, Any]:
    base = {"instance_class": "db.m6g.large", "engine": "postgres", "multi_az": False}
    return {**base, "storage_type": "gp3", "allocated_storage": 100, **more}


def test_a_postgresql_instance_is_its_hours_and_its_storage_at_aws_prices() -> None:
    assert parts("aws_db_instance", database()) == [
        ("db.m6g.large, PostgreSQL, Single-AZ, on demand", Decimal("128.48")),
        ("gp3 storage, 100 GiB", Decimal("12.7")),
    ]
    assert planned("aws_db_instance", database()).notes == (BACKUPS,)


def test_gp3_iops_and_throughput_are_priced_above_what_rds_includes() -> None:
    above = database(allocated_storage=500, iops=15000, storage_throughput=600)
    assert parts("aws_db_instance", above)[1:] == [
        ("gp3 storage, 500 GiB", Decimal("63.5")),
        ("gp3 iops, 3000 IOPS", Decimal("66")),
        ("gp3 throughput, 100 MiB/s", Decimal("8.8")),
    ]
    included = database(allocated_storage=500, iops=12000, storage_throughput=500)
    assert len(parts("aws_db_instance", included)) == 2


@pytest.mark.parametrize(
    ("storage", "expected"),
    [
        ({"storage_type": "io1", "allocated_storage": 400, "iops": 5000}, ["55.2", "550"]),
        ({"storage_type": "io2", "allocated_storage": 400, "iops": 5000}, ["55.2", "550"]),
        ({"storage_type": "standard", "allocated_storage": 100}, ["11"]),
        ({"storage_type": "gp2", "allocated_storage": 100}, ["12.7"]),
    ],
)
def test_each_storage_type_is_priced_from_its_own_row(
    storage: dict[str, Any], expected: list[str]
) -> None:
    found = parts("aws_db_instance", database(**storage))[1:]
    assert [amount for _, amount in found] == [Decimal(one) for one in expected]


def test_what_cannot_be_priced_beside_the_hours_is_a_note() -> None:
    multi = planned("aws_db_instance", database(multi_az=True))
    assert multi.monthly_after == Decimal("256.96")
    assert multi.notes[1].startswith(
        "storage not priced: the catalog holds no AmazonRDS storage price for databaseEngine "
        "PostgreSQL, deploymentOption Multi-AZ, volumeType General Purpose-GP3"
    )
    bare = planned("aws_db_instance", database(storage_type="io1", allocated_storage=400))
    assert "iops not priced: it gives none" in bare.notes
    later = planned("aws_db_instance", database(), unknown=("allocated_storage",))
    assert "storage not priced: allocated_storage is known only after apply" in later.notes


@pytest.mark.parametrize(
    ("after", "unknown", "says"),
    [
        (database(engine="oracle-ee"), (), "priced by a licence and edition"),
        (database(engine="sqlserver-se"), (), "priced by a licence and edition"),
        (database(engine="aurora-postgresql"), (), "priced through its aws_rds_cluster_instance"),
        (database(engine="neptune"), (), "the neptune engine is not one Meter prices"),
        (database(instance_class=None), ("instance_class",), "instance_class is known only"),
        (database(multi_az=None), ("multi_az",), "multi_az is known only after apply"),
        (database(instance_class="db.m9.huge"), (), "holds no AmazonRDS hours price"),
    ],
)
def test_a_database_that_cannot_rest_on_its_hours_says_why(
    after: dict[str, Any], unknown: tuple[str, ...], says: str
) -> None:
    kept = {key: value for key, value in after.items() if value is not None}
    assert says in refused("aws_db_instance", kept, unknown)


def test_an_aurora_instance_is_priced_as_aurora_standard() -> None:
    aurora = {"instance_class": "db.r6g.large", "engine": "aurora-postgresql"}
    line = planned("aws_rds_cluster_instance", aurora)
    assert line.monthly_after == Decimal("208.78")
    assert line.after.components[0].quote.sku_price_id.startswith("EQQGP475ZHNCR63P")
    assert line.notes == (AURORA,)
    serverless = {**aurora, "instance_class": "db.serverless"}
    assert "billed by the capacity it uses" in refused("aws_rds_cluster_instance", serverless)
    plain = {**aurora, "engine": "mysql"}
    assert "not one Meter prices for a cluster" in refused("aws_rds_cluster_instance", plain)


VALKEY = {"node_type": "cache.m5.large", "engine": "valkey"}


def test_an_elasticache_cluster_is_its_nodes_and_a_group_member_is_priced_with_its_group() -> None:
    assert parts("aws_elasticache_cluster", {**VALKEY, "num_cache_nodes": 2}) == [
        ("cache.m5.large, Valkey, 2 nodes, on demand", Decimal("200.896")),
    ]
    member = {**VALKEY, "replication_group_id": "sessions"}
    assert "a node of replication group sessions" in refused("aws_elasticache_cluster", member)
    none = {**VALKEY, "num_cache_nodes": 0}
    assert "its num_cache_nodes is 0" in refused("aws_elasticache_cluster", none)
    redis = {**VALKEY, "engine": "redis"}
    assert "holds no AmazonElastiCache hours price for cacheEngine Redis" in refused(
        "aws_elasticache_cluster", redis
    )
    surcharge = {**VALKEY, "node_type": "cache.m5.xlarge"}
    assert "holds no AmazonElastiCache hours price" in refused("aws_elasticache_cluster", surcharge)


@pytest.mark.parametrize(
    ("counts", "nodes"),
    [
        ({"num_cache_clusters": 3}, 3),
        ({"num_node_groups": 2, "replicas_per_node_group": 1}, 4),
        ({"num_node_groups": 2}, 2),
    ],
)
def test_a_replication_group_counts_its_clusters_or_its_shards_and_replicas(
    counts: dict[str, int], nodes: int
) -> None:
    ((what, monthly),) = parts("aws_elasticache_replication_group", {**VALKEY, **counts})
    assert what == f"cache.m5.large, Valkey, {nodes} nodes, on demand"
    assert monthly == Decimal("730") * nodes * Decimal("0.1376")


def test_a_replication_group_that_gives_no_count_says_why() -> None:
    assert "neither num_cache_clusters nor num_node_groups" in refused(
        "aws_elasticache_replication_group", VALKEY
    )
    assert "num_cache_clusters is known only after apply" in refused(
        "aws_elasticache_replication_group", VALKEY, ("num_cache_clusters",)
    )


def test_a_redshift_cluster_is_its_nodes_and_managed_storage_is_named() -> None:
    multi = {"node_type": "ra3.xlplus", "cluster_type": "multi-node", "number_of_nodes": 2}
    assert parts("aws_redshift_cluster", multi) == [
        ("ra3.xlplus, 2 nodes, on demand", Decimal("1754.92")),
    ]
    assert planned("aws_redshift_cluster", multi).notes == (MANAGED_STORAGE,)
    single = {**multi, "cluster_type": "single-node", "number_of_nodes": 4}
    assert planned("aws_redshift_cluster", single).monthly_after == Decimal("877.46")
    old = {"node_type": "dc2.8xlarge", "cluster_type": "single-node"}
    assert "holds no AmazonRedshift hours price" in refused("aws_redshift_cluster", old)


def search(data: dict[str, Any], ebs: dict[str, Any] | None = None) -> dict[str, Any]:
    config = {"instance_type": "r6g.large.search", "instance_count": 3, **data}
    return {"cluster_config": [config], "ebs_options": [ebs or {"ebs_enabled": False}]}


GP3_DISK = {"ebs_enabled": True, "volume_type": "gp3", "volume_size": 100}


def test_a_search_domain_is_its_data_nodes_and_their_storage() -> None:
    assert parts("aws_opensearch_domain", search({}, GP3_DISK)) == [
        ("r6g.large.search, 3 data nodes, on demand", Decimal("409.53")),
        ("gp3 storage, 100 GiB on each of 3 data nodes", Decimal("40.26")),
    ]
    legacy = search({"instance_type": "r6g.large.elasticsearch"}, GP3_DISK)
    assert planned("aws_elasticsearch_domain", legacy).monthly_after == Decimal("449.79")
    provisioned = {**GP3_DISK, "iops": 4000}
    assert GP3_SEARCH in planned("aws_opensearch_domain", search({}, provisioned)).notes


def test_io1_search_storage_prices_its_iops_on_each_data_node() -> None:
    io1 = {"ebs_enabled": True, "volume_type": "io1", "volume_size": 100, "iops": 1000}
    found = parts("aws_opensearch_domain", search({"instance_count": 2}, io1))
    assert [amount for _, amount in found] == [
        Decimal("273.02"),
        Decimal("37.2"),
        Decimal("194"),
    ]


def test_master_and_warm_nodes_it_cannot_price_are_notes() -> None:
    roles = {
        "dedicated_master_enabled": True,
        "warm_enabled": True,
        "warm_type": "ultrawarm1.medium.search",
        "warm_count": 2,
    }
    line = planned("aws_opensearch_domain", search(roles))
    assert line.monthly_after == Decimal("409.53")
    assert line.notes == (
        "master nodes not priced: it gives no dedicated_master_type and dedicated_master_count",
        "warm nodes not priced: the catalog holds no AmazonES hours price for instanceType "
        "ultrawarm1.medium.search in eu-west-1",
        ULTRAWARM,
    )
    assert "cluster_config is known only after apply" in refused(
        "aws_opensearch_domain", {}, ("cluster_config",)
    )
