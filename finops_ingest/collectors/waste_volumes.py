"""gp2 volumes priced as the gp3 that does the same work. TASK-P9-009, P9 spec section 5.8.

The volume pass of `waste_compute`, kept beside it rather than inside it: it shares the batch and
the writes and nothing else.

**What it reads.** For each attached gp2 volume the inventory names, four EBS series in the same
batch as the instances': read and write operations and read and write bytes, as hourly sums. IOPS
and MiB/s are the p99 of those per second. A volume publishing operations but no bytes has its
throughput unmeasured, which `finops_query.volumes` takes at what gp2 gives and says so; one
publishing neither is unobserved, and counted as such, never judged.

**What it prices against.** The newest EC2 price list version the catalog holds for the volume's
Region, the one an instance's target is priced from, and that version's four EBS prices. A Region
without them is a refusal naming what is missing, never a saving.

**The saving.** gp2's monthly cost less gp3's, both at list, scaled to what the bill shows for the
volume and never up, as an instance's is. Both modelled. Under the floor every waste rule uses it
is a refusal with the figure.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import text

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.metrics import MetricPoint
from finops_core.domain.waste import WasteClass
from finops_core.ports.metrics import MetricRequest
from finops_ingest.collectors.catalog_reads import latest_version, volume_prices
from finops_query.volumes import Gp3, VolumeDemand, gp3_for, working
from finops_query.waste import FLOOR_USD, Estimate, percentile

NAMESPACE: Final = "AWS/EBS"
OPERATIONS: Final = ("VolumeReadOps", "VolumeWriteOps")
BYTES: Final = ("VolumeReadBytes", "VolumeWriteBytes")
OPERATIONS_KEY: Final = "volume-ops:"
BYTES_KEY: Final = "volume-bytes:"
GP2: Final = "gp2"
SECONDS_PER_HOUR: Final = Decimal(3600)
MIB: Final = Decimal(1024 * 1024)
_CENT: Final = Decimal("0.01")


@dataclass(frozen=True)
class VolumeCandidate:
    """One attached EBS volume the inventory names."""

    resource_id: str
    account_id: str
    region_id: str
    observation_days: int
    monthly_cost: Decimal
    size_gib: int
    volume_type: str


#: What the pass read of a volume, restated each run. TASK-P15-006.
OBSERVE = text(
    "INSERT INTO volume_observation (tenant_id, sub_account_id, resource_id, region_id, "
    "volume_type, size_gib, as_of, collected_at) VALUES (:tenant, :account, :resource, :region, "
    ":type, :size, :now, :now) ON CONFLICT (tenant_id, sub_account_id, resource_id) DO UPDATE SET "
    "region_id = EXCLUDED.region_id, volume_type = EXCLUDED.volume_type, "
    "size_gib = EXCLUDED.size_gib, as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
)


def observe(
    connection: Any, tenant: object, volumes: Sequence[VolumeCandidate], now: datetime
) -> None:
    """Keep what this run read of every volume, of every type."""
    for volume in volumes:
        connection.execute(
            OBSERVE,
            {
                "tenant": tenant,
                "account": volume.account_id,
                "resource": volume.resource_id,
                "region": volume.region_id,
                "type": volume.volume_type,
                "size": volume.size_gib,
                "now": now,
            },
        )


def gp2_only(volumes: Sequence[VolumeCandidate]) -> list[VolumeCandidate]:
    """The volumes this pass judges. Every other type has no gp3 move to price."""
    return [volume for volume in volumes if volume.volume_type == GP2]


def requests(volumes: Sequence[VolumeCandidate]) -> list[MetricRequest]:
    """Operations and bytes, read and write, for each volume, to join the instances' batch."""
    return [
        MetricRequest(
            key=f"{prefix}{metric}:{volume.resource_id}",
            account=AccountKey(provider=Provider.AWS, account_id=volume.account_id),
            region=volume.region_id,
            namespace=NAMESPACE,
            metric_name=metric,
            dimensions={"VolumeId": volume.resource_id},
            statistic="Sum",
        )
        for volume in volumes
        for prefix, metrics in ((OPERATIONS_KEY, OPERATIONS), (BYTES_KEY, BYTES))
        for metric in metrics
    ]


def hourly_p99(streams: Sequence[Sequence[MetricPoint] | None]) -> Decimal | None:
    """The 99th percentile of what the streams moved together in an hour, None if unobserved.

    Read and write are summed per hour before the percentile, because a volume's limit bounds
    the two together. None where any stream is missing: half a sum is not a measurement.
    """
    if any(stream is None for stream in streams):
        return None
    hourly: dict[datetime, Decimal] = {}
    for stream in streams:
        for point in stream or ():
            hourly[point.at] = hourly.get(point.at, Decimal(0)) + point.value
    return percentile(list(hourly.values()), 99) if hourly else None


def demand(series: Mapping[str, Sequence[MetricPoint]], volume: VolumeCandidate) -> VolumeDemand:
    """IOPS and MiB/s at p99, each None where the volume published nothing to measure it by."""
    operations = hourly_p99(
        [series.get(f"{OPERATIONS_KEY}{m}:{volume.resource_id}") for m in OPERATIONS]
    )
    moved = hourly_p99([series.get(f"{BYTES_KEY}{m}:{volume.resource_id}") for m in BYTES])
    return VolumeDemand(
        iops_p99=None if operations is None else operations / SECONDS_PER_HOUR,
        mibps_p99=None if moved is None else moved / SECONDS_PER_HOUR / MIB,
    )


def judged(
    connection: Any, tenant: object, volume: VolumeCandidate, measured: VolumeDemand
) -> Estimate:
    """A gp2 to gp3 recommendation for one volume, or the refusal saying why there is none."""
    version = latest_version(connection, tenant, volume.region_id)
    if version is None:
        return _refused(
            f"the catalog holds no EC2 prices for {volume.region_id}, so gp3 has no price"
        )
    prices = volume_prices(connection, tenant, volume.region_id, version)
    if isinstance(prices, str):
        return _refused(prices)
    found = gp3_for(volume.size_gib, measured, prices)
    if isinstance(found, str):
        return _refused(f"No gp3 move: {found}")
    saving, scaled = _as_paid(found, volume.monthly_cost)
    reason = _rationale(found, version, scaled)
    if saving < FLOOR_USD:
        return _refused(f"{reason}. It saves {saving} a month, under the floor of {FLOOR_USD}")
    return Estimate(
        is_worth_acting_on=True,
        waste_class=WasteClass.EBS_GP2_TO_GP3,
        monthly_saving=saving,
        reason=reason,
        gp3_iops=found.iops,
        gp3_mibps=found.mibps,
    )


def _as_paid(found: Gp3, paid_monthly: Decimal) -> tuple[Decimal, str | None]:
    """The saving scaled to the bill, never up, and the clause saying so when it was scaled."""
    if found.gp2_monthly <= 0 or paid_monthly >= found.gp2_monthly:
        return found.saving, None
    ratio = paid_monthly / found.gp2_monthly
    clause = f"scaled to the bill, which shows {paid_monthly} against {found.gp2_monthly} at list"
    return (found.saving * ratio).quantize(_CENT), clause


def _rationale(found: Gp3, version: str, scaled: str | None) -> str:
    said = [working(found), *found.notes, f"priced from price list version {version}"]
    if scaled is not None:
        said.append(scaled)
    return ". ".join(part[0].upper() + part[1:] for part in said)


def _refused(reason: str) -> Estimate:
    return Estimate(
        is_worth_acting_on=False,
        waste_class=WasteClass.EBS_GP2_TO_GP3,
        monthly_saving=Decimal(0),
        reason=reason,
    )
