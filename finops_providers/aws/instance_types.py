"""What an instance type is, from AWS's own descriptions. FEAT-072, TASK-P9-005.

P9 spec sections 5.4 and 14.3. Read only, constraint 6. **Unproved against a real account**, like
every adapter here: the EC2 shapes are the botocore 1.43.108 model's, and the price list shapes
are the real ElastiCache list's, saved in `tests/providers/aws/extracts`. Proof waits on ISS-002.

**EC2 describes itself.** `AwsInstanceCatalog` pages `DescribeInstanceTypes` in a Region the hub
reaches, ADR-0035. A figure the description leaves out is None, never a guess: t2 publishes no
bandwidth in gigabits, and its `network_baseline_gbps` is None.

**The managed services are described by their price list.** RDS, ElastiCache, Redshift and
OpenSearch publish no describe call the hub can reach for every Region, so
`PriceListInstanceCatalog` reads each Region's products and takes a class's vCPUs, memory and
network from the product attributes, spec section 14.3. Only products that carry vCPUs and memory
describe a class: in the real ElastiCache list for eu-west-1, 291 of the 493 instance products do
(measured on 2026-10-08), and the rest, Extended Support among them, are priced but say nothing of
size. The architecture is the processor the product names where it names one, and otherwise the
family's name, where a `g` after the generation is Graviton (m6g, t4g, c7gn).

**A burstable type's baseline** is the EC2 guide's, `finops_providers/aws/burstable.py`. A
burstable type the guide's table lacks is returned without one, and the collector refuses to store
it rather than store it unbounded.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.domain.catalog import InstanceTypeSpec
from finops_core.errors import NoData, SchemaDrift
from finops_providers.aws.burstable import baseline_of, counterpart, is_burstable_name
from finops_providers.aws.client import translate
from finops_providers.aws.price_list import FORMAT_VERSION

COLLECTOR: Final = "instance_catalog"
EC2: Final = "AmazonEC2"
#: A family whose generation is followed by a `g`: m6g, t4g, c7gn, is4gen. Graviton.
_GRAVITON: Final = re.compile(r"[a-z]+\d+[a-z]*g[a-z]*")
#: `6.38 GiB`, the price list's memory.
_GIB: Final = re.compile(r"\s*([0-9]+(?:\.[0-9]+)?)\s*GiB\s*")
_MIB_PER_GIB: Final = 1024
#: What a managed class's network reads as when its product does not say.
NOT_STATED: Final = "Not stated in the price list"


def _system_clock() -> datetime:
    return datetime.now(UTC)


def _burstable_fields(instance_type: str) -> dict[str, Any]:
    found = baseline_of(instance_type)
    if found is None:
        return {}
    row, source = found
    return {
        "baseline_cpu": row.per_vcpu,
        "maximum_credits": row.maximum_credits,
        "baseline_source": source,
    }


def _sum(values: list[Any]) -> Decimal | None:
    """The total of a figure every network card publishes, or None if any card leaves it out."""
    if not values or any(value is None for value in values):
        return None
    return sum((Decimal(str(value)) for value in values), Decimal(0))


class AwsInstanceCatalog:
    """EC2's own description of its instance types, one Region at a time."""

    def __init__(
        self,
        *,
        client_for: Callable[[str], Any],
        clock: Callable[[], datetime] = _system_clock,
    ) -> None:
        # An EC2 client for a Region, through the hub's endpoint there, ADR-0035.
        self._client_for = client_for
        self._clock = clock

    def instance_types(self, region: str) -> Iterable[InstanceTypeSpec]:
        scope = f"{EC2}:{region}"
        at = self._clock()
        found: dict[str, InstanceTypeSpec] = {}
        try:
            pages = self._client_for(region).get_paginator("describe_instance_types").paginate()
            for page in pages:
                for raw in page.get("InstanceTypes") or ():
                    spec = self._spec(raw, region, at, scope)
                    found.setdefault(spec.instance_type, spec)
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=scope, collector=COLLECTOR) from failure
        return tuple(found[name] for name in sorted(found))

    @staticmethod
    def _spec(raw: Any, region: str, at: datetime, scope: str) -> InstanceTypeSpec:
        name = str(raw.get("InstanceType") or "")
        try:
            network = raw.get("NetworkInfo") or {}
            cards = list(network.get("NetworkCards") or ())
            ebs = (raw.get("EbsInfo") or {}).get("EbsOptimizedInfo") or {}
            gpus = (raw.get("GpuInfo") or {}).get("Gpus") or ()
            burstable = bool(raw.get("BurstablePerformanceSupported", False))
            return InstanceTypeSpec(
                service_code=EC2,
                region=region,
                instance_type=name,
                family=name.split(".")[0],
                current_generation=bool(raw.get("CurrentGeneration", False)),
                architectures=tuple(raw["ProcessorInfo"]["SupportedArchitectures"]),
                burstable=burstable,
                vcpus=int(raw["VCpuInfo"]["DefaultVCpus"]),
                memory_mib=int(raw["MemoryInfo"]["SizeInMiB"]),
                network_performance=str(network["NetworkPerformance"]),
                network_baseline_gbps=_sum([c.get("BaselineBandwidthInGbps") for c in cards]),
                network_peak_gbps=_sum([c.get("PeakBandwidthInGbps") for c in cards]),
                ebs_baseline_mbps=ebs.get("BaselineBandwidthInMbps"),
                ebs_maximum_mbps=ebs.get("MaximumBandwidthInMbps"),
                gpu_count=sum(int(gpu.get("Count") or 0) for gpu in gpus),
                as_of=at,
                collected_at=at,
                **(_burstable_fields(name) if burstable else {}),
            )
        except (KeyError, TypeError, ValueError, InvalidOperation) as failure:
            raise SchemaDrift(
                scope_key=scope,
                collector=COLLECTOR,
                detail=f"an instance type this cannot read, {name or 'with no name'}",
            ) from failure


class PriceListInstanceCatalog:
    """One managed service's instance classes, from its price list products' attributes."""

    def __init__(
        self,
        *,
        client: Any,
        service_code: str,
        clock: Callable[[], datetime] = _system_clock,
    ) -> None:
        # The Pricing client in us-east-1, the one the price catalog reads through.
        self._client = client
        self._service = service_code
        self._clock = clock

    def instance_types(self, region: str) -> Iterable[InstanceTypeSpec]:
        scope = f"{self._service}:{region}"
        at = self._clock()
        found: dict[str, InstanceTypeSpec] = {}
        products = 0
        try:
            pages = self._client.get_paginator("get_products").paginate(
                ServiceCode=self._service,
                FormatVersion=FORMAT_VERSION,
                Filters=[{"Type": "TERM_MATCH", "Field": "regionCode", "Value": region}],
            )
            for page in pages:
                for document in page.get("PriceList") or ():
                    products += 1
                    spec = self._spec(document, region, at, scope)
                    if spec is not None:
                        found.setdefault(spec.instance_type, spec)
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=scope, collector=COLLECTOR) from failure
        if products == 0:
            raise NoData(
                scope_key=scope,
                collector=COLLECTOR,
                detail="the price list holds no product for this service in this Region",
            )
        return tuple(found[name] for name in sorted(found))

    def _spec(
        self, document: Any, region: str, at: datetime, scope: str
    ) -> InstanceTypeSpec | None:
        try:
            item = json.loads(document) if isinstance(document, str) else document
            attributes = dict(item["product"].get("attributes") or {})
        except (ValueError, KeyError, TypeError, AttributeError) as failure:
            raise SchemaDrift(
                scope_key=scope, collector=COLLECTOR, detail="a product this cannot read"
            ) from failure
        name = str(attributes.get("instanceType") or "")
        vcpus, memory = _count(attributes.get("vcpu")), _memory_mib(attributes)
        if not name or vcpus is None or memory is None:
            # Priced, but not a description of a size: Extended Support, serverless, storage.
            return None
        if attributes.get("regionCode", region) != region:
            raise SchemaDrift(
                scope_key=scope,
                collector=COLLECTOR,
                detail=f"{name} is described for another Region",
            )
        published = _published(item.get("publicationDate"), at)
        burstable = is_burstable_name(name)
        return InstanceTypeSpec(
            service_code=self._service,
            region=region,
            instance_type=name,
            family=counterpart(name).split(".")[0],
            current_generation=attributes.get("currentGeneration") != "No",
            architectures=(_architecture(name, attributes),),
            burstable=burstable,
            vcpus=vcpus,
            memory_mib=memory,
            network_performance=str(attributes.get("networkPerformance") or NOT_STATED),
            as_of=published,
            collected_at=max(at, published),
            **(_burstable_fields(name) if burstable else {}),
        )


def _count(value: Any) -> int | None:
    try:
        count = int(str(value))
    except (TypeError, ValueError):
        return None
    return count if count > 0 else None


def _memory_mib(attributes: dict[str, Any]) -> int | None:
    """`memory: 6.38 GiB`, or `memoryGib: 8`, in MiB. None when neither is a figure."""
    text = attributes.get("memory")
    match = _GIB.fullmatch(str(text)) if text is not None else None
    value = match.group(1) if match else attributes.get("memoryGib")
    try:
        mib = round(Decimal(str(value)) * _MIB_PER_GIB)
    except (InvalidOperation, ValueError):
        return None
    return int(mib) if mib > 0 else None


def _architecture(name: str, attributes: dict[str, Any]) -> str:
    processor = str(attributes.get("physicalProcessor") or "")
    if processor:
        return "arm64" if "Graviton" in processor else "x86_64"
    family = counterpart(name).split(".")[0]
    return "arm64" if _GRAVITON.fullmatch(family) else "x86_64"


def _published(value: Any, fallback: datetime) -> datetime:
    """The list's publication time, `2026-09-14T06:37:14Z`, or the read when it is absent."""
    if not value:
        return fallback
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return fallback
    return when if when.tzinfo else when.replace(tzinfo=UTC)
