"""The managed services in a plan priced from the catalog. TASK-P16-004, FEAT-095, spec 5.3.

RDS, Aurora, ElastiCache, Redshift and OpenSearch, each asked of the catalog by the attributes
AWS's own price lists tell their prices apart by, read from the eu-west-1 lists of 2026-10-06 and
2026-10-15 kept in `tests/providers/aws/extracts`. A line rests on its nodes' hours; storage and
provisioned performance that cannot be priced are notes, and what is billed by use is named.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

from finops_query.plan_quotes import (
    Catalogue,
    Component,
    Priced,
    Pricer,
    Values,
    decimal_of,
    hours,
    positive,
)

RDS: Final = "AmazonRDS"
CACHE: Final = "AmazonElastiCache"
REDSHIFT: Final = "AmazonRedshift"
SEARCH: Final = "AmazonES"

#: Terraform's engine names and the price list's, for the engines that need no licence.
DB_ENGINES: Final = {"postgres": "PostgreSQL", "mysql": "MySQL", "mariadb": "MariaDB"}
#: Engines whose price turns on a licence and an edition the plan does not give in full.
LICENSED: Final = ("oracle", "sqlserver", "db2", "custom-")
AURORA_ENGINES: Final = {"aurora-postgresql": "Aurora PostgreSQL", "aurora-mysql": "Aurora MySQL"}
NO_LICENCE: Final = "No license required"
#: RDS storage types by the price list's volume type.
DB_STORAGE: Final = {
    "gp2": "General Purpose",
    "gp3": "General Purpose-GP3",
    "io1": "Provisioned IOPS",
    "io2": "Provisioned IOPS-IO2",
    "standard": "Magnetic",
}
#: RDS provisioned IOPS rows carry no volume type; their group description names it.
DB_IOPS: Final = {
    "io1": "RDS Provisioned IOPS",
    "io2": "RDS Provisioned IO2 IOPS",
    "gp3": "RDS Provisioned GP3 IOPS",
}
DB_THROUGHPUT: Final = "RDS Provisioned Throughput"
#: What RDS includes with gp3 once IOPS may be provisioned at all. Provisioning opens at a storage
#: threshold, and from it RDS includes 12,000 IOPS and 500 MiB/s, so whatever is provisioned above
#: these is billed, whatever the threshold. AWS RDS User Guide, Storage, read 2026-10-16.
RDS_GP3_IOPS: Final = 12000
RDS_GP3_MIBPS: Final = 500
CACHE_ENGINES: Final = {"redis": "Redis", "valkey": "Valkey", "memcached": "Memcached"}
#: OpenSearch's EBS storage by its storage medium in the price list.
SEARCH_STORAGE: Final = {"gp2": "GP2", "gp3": "GP3", "io1": "PIOPS-Storage", "standard": "Magnetic"}
_ELASTICSEARCH: Final = re.compile(r"\.elasticsearch$")

BACKUPS: Final = "backup storage beyond the database's own size is billed by use"
AURORA: Final = (
    "priced as Aurora Standard: an I/O-Optimized cluster costs more an hour and nothing for I/O, "
    "and Aurora's storage and I/O are billed by use"
)
MANAGED_STORAGE: Final = "managed storage not priced: it is billed by what is stored"
ULTRAWARM: Final = "UltraWarm storage not priced: it is billed by what is stored"
GP3_SEARCH: Final = (
    "gp3 iops and throughput not priced: what OpenSearch includes grows with the volume"
)


def _named(side: Values, *names: str) -> tuple[str, ...] | str:
    """The named values as text, or why the first of them that is not text is missing."""
    found: list[str] = []
    for name in names:
        reason = side.absent(name)
        if reason is not None:
            return reason
        value = side.values.get(name)
        if not isinstance(value, str) or not value:
            return f"it names no {name}"
        found.append(value)
    return tuple(found)


def _count(side: Values, name: str, default: int) -> int | float | str:
    """A count Terraform gives, its default where it gives none, or why it is not known."""
    reason = side.absent(name)
    if reason is not None:
        return reason
    value = side.values.get(name)
    if value is None:
        return default
    return value if positive(value) else f"its {name} is {value!r}"


def _db_instance(side: Values, region: str, catalogue: Catalogue) -> Priced | str:
    """An RDS instance's hours, then its storage and provisioned IOPS and throughput."""
    named = _named(side, "instance_class", "engine")
    if isinstance(named, str):
        return named
    instance_class, engine = named
    if engine.startswith(LICENSED):
        return f"{engine} is priced by a licence and edition the plan does not give in full"
    if engine in AURORA_ENGINES:
        return "an Aurora database is priced through its aws_rds_cluster_instance"
    database = DB_ENGINES.get(engine)
    if database is None:
        return f"the {engine} engine is not one Meter prices"
    reason = side.absent("multi_az")
    if reason is not None:
        return reason
    deployment = "Multi-AZ" if side.values.get("multi_az") is True else "Single-AZ"
    asked = {"instanceType": instance_class, "databaseEngine": database}
    asked |= {"deploymentOption": deployment, "licenseModel": NO_LICENCE}
    quote = catalogue.service_price(RDS, region, asked, "hours")
    if isinstance(quote, str):
        return quote
    components = [
        Component(f"{instance_class}, {database}, {deployment}, on demand", hours(), quote)
    ]
    notes = [BACKUPS]
    common = {"databaseEngine": database, "deploymentOption": deployment}
    _db_storage(side, (region, catalogue), common, components, notes)
    return tuple(components), tuple(notes)


def _db_storage(
    side: Values,
    where: tuple[str, Catalogue],
    common: Mapping[str, str],
    components: list[Component],
    notes: list[str],
) -> None:
    """An RDS instance's storage and what is provisioned above it; what cannot be is a note."""
    region, catalogue = where
    for name in ("storage_type", "allocated_storage"):
        reason = side.absent(name)
        if reason is not None:
            notes.append(f"storage not priced: {reason}")
            return
    kind, size = side.values.get("storage_type"), side.values.get("allocated_storage")
    if kind not in DB_STORAGE:
        notes.append(f"storage not priced: its storage type {kind!r} is not one the catalog prices")
        return
    if not positive(size):
        notes.append("storage not priced: it gives no allocated_storage")
        return

    def add(term: str, attributes: Mapping[str, str], quantity: Any, what: str) -> None:
        quote = catalogue.service_price(RDS, region, {**common, **attributes}, term)
        if isinstance(quote, str):
            notes.append(f"{term} not priced: {quote}")
        else:
            components.append(Component(what, decimal_of(quantity), quote))

    add("storage", {"volumeType": DB_STORAGE[kind]}, size, f"{kind} storage, {size} GiB")
    iops, throughput = side.values.get("iops"), side.values.get("storage_throughput")
    if kind in ("io1", "io2"):
        if positive(iops):
            add("iops", {"groupDescription": DB_IOPS[kind]}, iops, f"{kind} iops, {iops} IOPS")
        else:
            notes.append(f"iops not priced: {side.absent('iops') or 'it gives none'}")
    elif kind == "gp3":
        if positive(iops) and iops > RDS_GP3_IOPS:
            extra = iops - RDS_GP3_IOPS
            add("iops", {"groupDescription": DB_IOPS[kind]}, extra, f"gp3 iops, {extra} IOPS")
        if positive(throughput) and throughput > RDS_GP3_MIBPS:
            extra = throughput - RDS_GP3_MIBPS
            group = {"groupDescription": DB_THROUGHPUT}
            add("throughput", group, extra, f"gp3 throughput, {extra} MiB/s")


def _cluster_instance(side: Values, region: str, catalogue: Catalogue) -> Priced | str:
    """An Aurora instance's hours, priced as Aurora Standard."""
    named = _named(side, "instance_class", "engine")
    if isinstance(named, str):
        return named
    instance_class, engine = named
    if instance_class == "db.serverless":
        return "Aurora Serverless v2 is billed by the capacity it uses"
    database = AURORA_ENGINES.get(engine)
    if database is None:
        return f"the {engine} engine is not one Meter prices for a cluster instance"
    asked = {"instanceType": instance_class, "databaseEngine": database}
    asked |= {"deploymentOption": "Single-AZ", "storage": "EBS Only"}
    quote = catalogue.service_price(RDS, region, asked, "hours")
    if isinstance(quote, str):
        return quote
    return (Component(f"{instance_class}, {database}, on demand", hours(), quote),), (AURORA,)


def _nodes(
    region: str,
    catalogue: Catalogue,
    asked: tuple[str, Mapping[str, str]],
    count: int | float,
    what: str,
) -> Component | str:
    """Nodes of one type running all month, or why the catalog cannot price them."""
    service, attributes = asked
    quote = catalogue.service_price(service, region, attributes, "hours")
    if isinstance(quote, str):
        return quote
    noun = "node" if count == 1 else "nodes"
    return Component(f"{what}, {count} {noun}, on demand", hours(count), quote)


def _cache_engine(side: Values) -> str:
    engine = side.values.get("engine")
    return CACHE_ENGINES.get(engine, "") if isinstance(engine, str) else ""


def _cache_cluster(side: Values, region: str, catalogue: Catalogue) -> Priced | str:
    """An ElastiCache cluster's nodes, unless it is a node of a replication group."""
    group = side.values.get("replication_group_id")
    if isinstance(group, str) and group:
        return f"it is a node of replication group {group}, which is priced with the group"
    named = _named(side, "node_type", "engine")
    if isinstance(named, str):
        return named
    engine = _cache_engine(side)
    if not engine:
        return f"the {named[1]} engine is not one Meter prices"
    count = _count(side, "num_cache_nodes", 1)
    if isinstance(count, str):
        return count
    asked = (CACHE, {"instanceType": named[0], "cacheEngine": engine})
    priced = _nodes(region, catalogue, asked, count, f"{named[0]}, {engine}")
    return priced if isinstance(priced, str) else ((priced,), ())


def _replication_group(side: Values, region: str, catalogue: Catalogue) -> Priced | str:
    """A replication group's nodes: its cache clusters, or its node groups and their replicas."""
    named = _named(side, "node_type", "engine")
    if isinstance(named, str):
        return named
    engine = _cache_engine(side)
    if not engine:
        return f"the {named[1]} engine is not one Meter prices"
    clusters, groups = side.values.get("num_cache_clusters"), side.values.get("num_node_groups")
    if positive(clusters):
        count: int | float = clusters
    elif positive(groups):
        replicas = side.values.get("replicas_per_node_group")
        count = groups * (1 + (replicas if positive(replicas) else 0))
    else:
        reason = side.absent("num_cache_clusters") or side.absent("num_node_groups")
        return reason or "it gives neither num_cache_clusters nor num_node_groups"
    asked = (CACHE, {"instanceType": named[0], "cacheEngine": engine})
    priced = _nodes(region, catalogue, asked, count, f"{named[0]}, {engine}")
    return priced if isinstance(priced, str) else ((priced,), ())


def _redshift(side: Values, region: str, catalogue: Catalogue) -> Priced | str:
    """A Redshift cluster's nodes; RA3's managed storage is billed by what is stored."""
    named = _named(side, "node_type")
    if isinstance(named, str):
        return named
    (node_type,) = named
    single = side.values.get("cluster_type") == "single-node"
    count = 1 if single else _count(side, "number_of_nodes", 1)
    if isinstance(count, str):
        return count
    asked = (REDSHIFT, {"instanceType": node_type})
    priced = _nodes(region, catalogue, asked, count, node_type)
    if isinstance(priced, str):
        return priced
    notes = (MANAGED_STORAGE,) if node_type.startswith(("ra3.", "rg.")) else ()
    return (priced,), notes


def _search_domain(side: Values, region: str, catalogue: Catalogue) -> Priced | str:
    """A search domain's data, master and warm nodes, and its EBS storage on each data node."""
    reason = side.absent("cluster_config") or side.absent("cluster_config[0].instance_type")
    if reason is not None:
        return reason
    configs = side.values.get("cluster_config") or ()
    config: Mapping[str, Any] = configs[0] if configs else {}
    data_type = config.get("instance_type")
    if not isinstance(data_type, str) or not data_type:
        return "it names no cluster_config instance_type"
    given = config.get("instance_count")
    data_count = given if positive(given) else 1
    priced = _search_nodes(region, catalogue, data_type, data_count, "data")
    if isinstance(priced, str):
        return priced
    components: list[Component] = [priced]
    notes: list[str] = []
    for role, enabled, kind, count in (
        ("master", "dedicated_master_enabled", "dedicated_master_type", "dedicated_master_count"),
        ("warm", "warm_enabled", "warm_type", "warm_count"),
    ):
        if config.get(enabled) is not True:
            continue
        node_type, number = config.get(kind), config.get(count)
        if not isinstance(node_type, str) or not node_type or not positive(number):
            notes.append(f"{role} nodes not priced: it gives no {kind} and {count}")
            continue
        found = _search_nodes(region, catalogue, node_type, number, role)
        if isinstance(found, str):
            notes.append(f"{role} nodes not priced: {found}")
        else:
            components.append(found)
    if config.get("warm_enabled") is True:
        notes.append(ULTRAWARM)
    _search_storage(side, (region, catalogue), data_count, components, notes)
    return tuple(components), tuple(notes)


def _search_nodes(
    region: str, catalogue: Catalogue, node_type: str, count: int | float, role: str
) -> Component | str:
    name = _ELASTICSEARCH.sub(".search", node_type)
    quote = catalogue.service_price(SEARCH, region, {"instanceType": name}, "hours")
    if isinstance(quote, str):
        return quote
    return Component(f"{name}, {count} {role} nodes, on demand", hours(count), quote)


def _search_storage(
    side: Values,
    where: tuple[str, Catalogue],
    data_count: int | float,
    components: list[Component],
    notes: list[str],
) -> None:
    """EBS storage on every data node, and io1's IOPS; gp3's included performance is not read."""
    region, catalogue = where
    for name in ("ebs_options", "ebs_options[0].volume_type", "ebs_options[0].volume_size"):
        reason = side.absent(name)
        if reason is not None:
            notes.append(f"storage not priced: {reason}")
            return
    blocks = side.values.get("ebs_options") or ()
    options: Mapping[str, Any] = blocks[0] if blocks else {}
    if options.get("ebs_enabled") is not True:
        return
    kind: Any = options.get("volume_type")
    size: Any = options.get("volume_size")
    if kind not in SEARCH_STORAGE or not positive(size):
        notes.append(f"storage not priced: it gives a {kind} volume of {size!r} GiB")
        return
    quote = catalogue.service_price(
        SEARCH, region, {"storageMedia": SEARCH_STORAGE[kind]}, "storage"
    )
    if isinstance(quote, str):
        notes.append(f"storage not priced: {quote}")
        return
    total = decimal_of(size) * decimal_of(data_count)
    what = f"{kind} storage, {size} GiB on each of {data_count} data nodes"
    components.append(Component(what, total, quote))
    if kind == "gp3" and (options.get("iops") or options.get("throughput")):
        notes.append(GP3_SEARCH)
    iops: Any = options.get("iops")
    if kind == "io1" and positive(iops):
        found = catalogue.service_price(SEARCH, region, {"storageMedia": "PIOPS"}, "iops")
        if isinstance(found, str):
            notes.append(f"iops not priced: {found}")
        else:
            amount = decimal_of(iops) * decimal_of(data_count)
            components.append(Component(f"io1 iops, {iops} on each data node", amount, found))


#: The pricer for each managed service type Meter prices.
SERVICE_PRICERS: Final[Mapping[str, Pricer]] = {
    "aws_db_instance": _db_instance,
    "aws_rds_cluster_instance": _cluster_instance,
    "aws_elasticache_cluster": _cache_cluster,
    "aws_elasticache_replication_group": _replication_group,
    "aws_redshift_cluster": _redshift,
    "aws_opensearch_domain": _search_domain,
    "aws_elasticsearch_domain": _search_domain,
}
