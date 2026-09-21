"""Two clusters and an ECS service, with the findings P6 exists to make.

TASK-P6-005 asks for a specific estate and this is it:

- Two EKS clusters. `platform-eks` has enhanced observability and reports its
  requests. `batch-eks` does not, so a reader sees its use and **no request**.
  Its requests exist in this module, because the cluster really has them, and
  are withheld at the point of reading. A fake that simply had no request for
  that cluster would let a detector pass by never looking.
- All three OOM states. `payments-worker` is killed on the days memory reaches
  its limit, every other workload on the enhanced cluster is observed not to be,
  and every workload on `batch-eks` is unobserved. `None` means unobserved and
  is never rendered as `False`.
- `ledger`, a namespace requesting about five times what it uses.
- `channels`, a namespace sized correctly, so a detector that flags everything
  fails a test.
- Three Fargate tasks for TASK-P6-008, one of them far larger than it needs to
  be, so snapping up to the valid size matrix has something to snap.

Node counts are **derived from the requests**, not written down. A node group
grows when the pods scheduled onto it need more room, which is what makes the
bin packing and spot ratio figures on the cluster screen follow from the
workloads rather than sit beside them. The utilization estate reads the same
function for the Auto Scaling group behind each node group, so the vCPU the
quota estate counts is the vCPU these pods caused.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.metrics import MetricPoint
from finops_providers.fake import estate_shape as shape
from finops_providers.fake import fixtures

COLLECTOR = "container_usage"

#: The share of a node the kubelet and the system reserve leave to pods.
ALLOCATABLE_SHARE = 0.92

#: How full the scheduler is allowed to pack a node group before it scales out.
PACKING_TARGET = 0.72

#: Mebibyte in bytes, so byte values are never written as long literals.
MIB = 1024 * 1024


class LaunchType(StrEnum):
    EC2 = "EC2"
    FARGATE = "FARGATE"


class Shape(StrEnum):
    """How a workload's demand moves through the day and the year."""

    WEB = "WEB"
    STEADY = "STEADY"
    BATCH = "BATCH"
    DAEMON = "DAEMON"


@dataclass(frozen=True)
class NodeGroup:
    #: The Auto Scaling group's resource identifier in the utilization estate.
    resource_id: str
    capacity_type: str
    instance_type: str
    vcpu: int
    memory_gib: int
    #: The share of the cluster's nodes this group carries.
    share: float
    min_nodes: int


@dataclass(frozen=True)
class Cluster:
    name: str
    account_id: str
    region_id: str
    platform: str
    enhanced_observability: bool
    node_groups: tuple[NodeGroup, ...]


@dataclass(frozen=True)
class Workload:
    cluster: str
    namespace: str
    name: str
    kind: str
    launch_type: LaunchType
    #: The true request per pod or task. Withheld from a reader where the cluster
    #: cannot report it, see `observed_request`.
    cpu_request_m: int
    mem_request_mib: int
    cpu_limit_m: int | None
    mem_limit_mib: int | None
    replicas: int
    shape: Shape
    #: Per pod use at ordinary demand, before shape and season.
    cpu_use_m: float
    mem_use_mib: float
    #: Killed on the days memory reaches its limit.
    ooms_at_peak: bool = False
    planted: str | None = None

    @property
    def key(self) -> str:
        return f"container/{self.cluster}/{self.namespace}/{self.name}"


PLATFORM_EKS = Cluster(
    name="platform-eks",
    account_id="fake-platform-a",
    region_id=fixtures.REGION,
    platform="EKS",
    enhanced_observability=True,
    node_groups=(
        NodeGroup("amazonec2/fake-platform-a/0001", "ON_DEMAND", "m6i.2xlarge", 8, 32, 0.6, 2),
        NodeGroup("amazonec2/fake-platform-a/0002", "SPOT", "m6i.2xlarge", 8, 32, 0.4, 1),
    ),
)

BATCH_EKS = Cluster(
    name="batch-eks",
    account_id="fake-platform-b",
    region_id=fixtures.REGION,
    platform="EKS",
    enhanced_observability=False,
    node_groups=(
        NodeGroup("amazonec2/fake-platform-b/0001", "SPOT", "c6i.4xlarge", 16, 32, 1.0, 2),
    ),
)

PRODUCT_ECS = Cluster(
    name="product-ecs",
    account_id="fake-product-a",
    region_id=fixtures.REGION,
    platform="ECS",
    # Fargate reports the task size it was asked for, always.
    enhanced_observability=True,
    node_groups=(),
)

CLUSTERS: tuple[Cluster, ...] = (PLATFORM_EKS, BATCH_EKS, PRODUCT_ECS)
_CLUSTER = {c.name: c for c in CLUSTERS}

WORKLOADS: tuple[Workload, ...] = (
    # payments: one correctly sized, one killed at peak.
    Workload(
        "platform-eks",
        "payments",
        "payments-api",
        "Deployment",
        LaunchType.EC2,
        500,
        1024,
        1000,
        1536,
        6,
        Shape.WEB,
        330,
        700,
        planted="CONTAINER_RIGHT_SIZED",
    ),
    Workload(
        "platform-eks",
        "payments",
        "payments-worker",
        "Deployment",
        LaunchType.EC2,
        250,
        512,
        500,
        768,
        4,
        Shape.STEADY,
        190,
        560,
        ooms_at_peak=True,
        planted="CONTAINER_OOM_KILLED",
    ),
    # ledger: the namespace requesting about five times what it uses.
    Workload(
        "platform-eks",
        "ledger",
        "ledger-api",
        "Deployment",
        LaunchType.EC2,
        2000,
        4096,
        2000,
        4096,
        8,
        Shape.WEB,
        380,
        800,
        planted="CONTAINER_OVER_REQUESTED_5X",
    ),
    Workload(
        "platform-eks",
        "ledger",
        "ledger-projector",
        "Deployment",
        LaunchType.EC2,
        1000,
        2048,
        1000,
        2048,
        3,
        Shape.STEADY,
        190,
        400,
        planted="CONTAINER_OVER_REQUESTED_5X",
    ),
    # channels: the namespace sized correctly.
    Workload(
        "platform-eks",
        "channels",
        "web-bff",
        "Deployment",
        LaunchType.EC2,
        300,
        512,
        600,
        768,
        6,
        Shape.WEB,
        235,
        410,
        planted="CONTAINER_NAMESPACE_RIGHT_SIZED",
    ),
    Workload(
        "platform-eks",
        "channels",
        "notifications",
        "Deployment",
        LaunchType.EC2,
        200,
        256,
        400,
        384,
        2,
        Shape.STEADY,
        150,
        205,
        planted="CONTAINER_NAMESPACE_RIGHT_SIZED",
    ),
    Workload(
        "platform-eks",
        "observability",
        "fluent-bit",
        "DaemonSet",
        LaunchType.EC2,
        100,
        128,
        200,
        256,
        0,
        Shape.DAEMON,
        70,
        105,
    ),
    # batch-eks: requests exist and cannot be read.
    Workload(
        "batch-eks",
        "risk",
        "risk-batch",
        "Deployment",
        LaunchType.EC2,
        2000,
        8192,
        4000,
        12288,
        2,
        Shape.BATCH,
        1750,
        6100,
        planted="CONTAINER_REQUEST_UNAVAILABLE",
    ),
    Workload(
        "batch-eks",
        "risk",
        "recon-batch",
        "Deployment",
        LaunchType.EC2,
        1000,
        2048,
        2000,
        3072,
        2,
        Shape.STEADY,
        420,
        1300,
        planted="CONTAINER_OOM_UNOBSERVED",
    ),
    Workload(
        "batch-eks",
        "reporting",
        "report-gen",
        "Deployment",
        LaunchType.EC2,
        500,
        1024,
        1000,
        2048,
        3,
        Shape.STEADY,
        120,
        380,
    ),
    # Fargate: sizes are the task definition, and a request is always known.
    Workload(
        "product-ecs",
        "default",
        "statements-renderer",
        "Service",
        LaunchType.FARGATE,
        4096,
        16384,
        None,
        None,
        2,
        Shape.WEB,
        300,
        1300,
        planted="FARGATE_OVERSIZED",
    ),
    Workload(
        "product-ecs",
        "default",
        "kyc-document-ocr",
        "Service",
        LaunchType.FARGATE,
        2048,
        4096,
        None,
        None,
        3,
        Shape.WEB,
        1450,
        3400,
        planted="FARGATE_RIGHT_SIZED",
    ),
    Workload(
        "product-ecs",
        "default",
        "webhook-relay",
        "Service",
        LaunchType.FARGATE,
        1024,
        8192,
        None,
        None,
        2,
        Shape.STEADY,
        200,
        900,
        planted="FARGATE_MEMORY_OVERSIZED",
    ),
)


def cluster(name: str) -> Cluster:
    return _CLUSTER[name]


def workloads_in(cluster_name: str) -> tuple[Workload, ...]:
    return tuple(w for w in WORKLOADS if w.cluster == cluster_name)


def _growth(ts: datetime, at: datetime) -> float:
    start, end = shape.window(at)
    return 1.0 + 0.25 * shape.progress(ts, start, end)


def replicas(w: Workload, ts: datetime, at: datetime = fixtures.AS_OF) -> int:
    """Pods or tasks running in the hour starting at `ts`."""
    d = ts.date()
    if w.shape is Shape.DAEMON:
        return nodes(cluster(w.cluster), ts, at)
    if w.shape is Shape.WEB:
        load = (0.7 + 0.5 * shape.diurnal(ts)) * shape.seasonal(d) * _growth(ts, at)
        return max(2, round(w.replicas * load))
    if w.shape is Shape.BATCH:
        if shape.is_quarter_end(d):
            return w.replicas * 10
        if shape.is_month_end(d):
            return w.replicas * 4
    return w.replicas


def _requested_cpu_m(c: Cluster, ts: datetime, at: datetime) -> int:
    return sum(
        replicas(w, ts, at) * w.cpu_request_m
        for w in workloads_in(c.name)
        if w.shape is not Shape.DAEMON
    )


def nodes(c: Cluster, ts: datetime, at: datetime = fixtures.AS_OF) -> int:
    """Nodes across the whole cluster, derived from what the pods request."""
    if not c.node_groups:
        return 0
    largest = max(g.vcpu for g in c.node_groups)
    daemon = sum(w.cpu_request_m for w in workloads_in(c.name) if w.shape is Shape.DAEMON)
    per_node = largest * 1000 * ALLOCATABLE_SHARE - daemon
    needed = math.ceil(_requested_cpu_m(c, ts, at) / (per_node * PACKING_TARGET))
    return max(sum(g.min_nodes for g in c.node_groups), needed)


def nodes_in_group(
    group: NodeGroup, c: Cluster, ts: datetime, at: datetime = fixtures.AS_OF
) -> int:
    """This group's share of the cluster's nodes, never below its minimum."""
    return max(group.min_nodes, math.ceil(nodes(c, ts, at) * group.share))


def _peak_day(d: date) -> bool:
    return shape.is_quarter_end(d) or shape.is_peak_retail(d)


def oom_killed_on(w: Workload, d: date) -> bool:
    """The truth, whether or not any reader can see it."""
    return w.ooms_at_peak and _peak_day(d)


def observed_request(w: Workload) -> tuple[int, int] | None:
    """The request a reader of this cluster is given, or None where unavailable.

    None rather than zero. TASK-P6-006 puts a check constraint on a zero request
    beside a positive use, because that pair means the request was unread.
    """
    if w.launch_type is LaunchType.FARGATE or cluster(w.cluster).enhanced_observability:
        return w.cpu_request_m, w.mem_request_mib
    return None


def observed_oom(w: Workload, d: date) -> bool | None:
    """True, False, or None for unobserved. Three facts, TASK-P6-001."""
    if not cluster(w.cluster).enhanced_observability:
        return None
    return oom_killed_on(w, d)


def per_pod_use(
    w: Workload,
    ts: datetime,
    at: datetime = fixtures.AS_OF,  # noqa: ARG001  the daily row is keyed on ts alone
) -> tuple[float, float, float, float]:
    """(cpu average, cpu max, memory average, memory max) per pod, in m and MiB."""
    d = ts.date()
    wobble = shape.jitter(f"{w.key}|cpu", ts)
    if w.shape is Shape.WEB:
        cpu = w.cpu_use_m * (0.55 + 0.6 * shape.diurnal(ts)) * (1 + 0.08 * wobble)
    elif w.shape is Shape.BATCH:
        busy = shape.is_quarter_end(d) or shape.is_month_end(d)
        cpu = w.cpu_use_m * (1.0 if busy else 0.3) * (1 + 0.05 * wobble)
    else:
        cpu = w.cpu_use_m * (0.85 + 0.15 * shape.diurnal(ts)) * (1 + 0.05 * wobble)
    cpu_max = cpu * (1.15 + 0.2 * abs(shape.jitter(f"{w.key}|cpumax", ts)))

    mem = (
        w.mem_use_mib
        * (0.92 + 0.08 * shape.diurnal(ts))
        * (1 + 0.03 * shape.jitter(f"{w.key}|mem", ts))
    )
    mem_max = mem * (1.04 + 0.04 * abs(shape.jitter(f"{w.key}|memmax", ts)))
    if w.ooms_at_peak and _peak_day(d) and shape.is_kill_window(ts) and w.mem_limit_mib:
        # The hours it was killed in: working set pinned at the limit.
        mem_max = float(w.mem_limit_mib)
        mem = max(mem, 0.93 * w.mem_limit_mib)
    if w.mem_limit_mib:
        mem_max = min(mem_max, float(w.mem_limit_mib))
        mem = min(mem, mem_max)
    if w.cpu_limit_m:
        cpu_max = min(cpu_max, float(w.cpu_limit_m))
        cpu = min(cpu, cpu_max)
    return cpu, cpu_max, mem, mem_max


def cluster_use(c: Cluster, ts: datetime, at: datetime = fixtures.AS_OF) -> tuple[float, float]:
    """Total cpu m and memory MiB the cluster's pods use in the hour."""
    cpu = mem = 0.0
    for w in workloads_in(c.name):
        n = replicas(w, ts, at)
        pod_cpu, _, pod_mem, _ = per_pod_use(w, ts, at)
        cpu += n * pod_cpu
        mem += n * pod_mem
    return cpu, mem


# ---------------------------------------------------------------------------
# Hourly series, the shape Container Insights would return. TASK-P6-004.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeriesPoint:
    """One `MetricPoint` and the thing it is about.

    `MetricPoint` names an account and not a resource, deliberately thin until the
    sub project that first reads a series widens it, TASK-P0-007. P3 and P6 are
    that sub project, so the resource travels beside the point here rather than
    inside it, and nothing in `finops_core` is changed by this module.
    """

    resource_id: str
    dimension: str
    point: MetricPoint


def _point(
    account_id: str,
    namespace: str,
    metric: str,
    statistic: str,
    unit: str,
    value: Decimal,
    ts: datetime,
) -> MetricPoint:
    return MetricPoint(
        account_key=AccountKey(provider=Provider.AWS, account_id=account_id),
        namespace=namespace,
        metric_name=metric,
        statistic=statistic,
        unit=unit,
        value=value,
        at=ts,
        as_of=ts + shape.STEP,
        collected_at=fixtures.COLLECTED_AT,
    )


def series(
    *, start: datetime | None = None, end: datetime | None = None, at: datetime = fixtures.AS_OF
) -> Iterator[SeriesPoint]:
    """Every hourly container metric in `[start, end)`, defaulting to two years."""
    w_start, w_end = shape.window(at)
    start, end = start or w_start, end or w_end
    for ts in shape.hours(start, end):
        for c in CLUSTERS:
            if c.node_groups:
                yield from _node_points(c, ts, at)
        for w in WORKLOADS:
            yield from _workload_points(w, ts, at)


def _node_points(c: Cluster, ts: datetime, at: datetime) -> Iterator[SeriesPoint]:
    rid = f"container/{c.name}"
    n = nodes(c, ts, at)
    vcpu = sum(nodes_in_group(g, c, ts, at) * g.vcpu for g in c.node_groups)
    mem_gib = sum(nodes_in_group(g, c, ts, at) * g.memory_gib for g in c.node_groups)
    used_cpu, used_mem = cluster_use(c, ts, at)
    cpu_pct = shape.clamp(100 * used_cpu / (vcpu * 1000) + 4.0, 0, 100)
    mem_pct = shape.clamp(100 * used_mem / (mem_gib * 1024) + 9.0, 0, 100)
    fs_pct = shape.clamp(38 + 6 * shape.jitter(f"{rid}|fs", ts), 0, 100)
    for metric, stat, unit, value in (
        ("cluster_node_count", "Average", "Count", shape.dec(n, 0)),
        ("node_cpu_utilization", "Average", "Percent", shape.dec(cpu_pct)),
        (
            "node_cpu_utilization",
            "Maximum",
            "Percent",
            shape.dec(shape.clamp(cpu_pct * 1.25, 0, 100)),
        ),
        ("node_memory_utilization", "Average", "Percent", shape.dec(mem_pct)),
        (
            "node_memory_utilization",
            "Maximum",
            "Percent",
            shape.dec(shape.clamp(mem_pct * 1.08, 0, 100)),
        ),
        ("node_filesystem_utilization", "Maximum", "Percent", shape.dec(fs_pct)),
    ):
        yield SeriesPoint(
            rid,
            "ClusterName",
            _point(c.account_id, "ContainerInsights", metric, stat, unit, value, ts),
        )


def _workload_points(w: Workload, ts: datetime, at: datetime) -> Iterator[SeriesPoint]:
    c = cluster(w.cluster)
    n = replicas(w, ts, at)
    cpu, cpu_max, mem, mem_max = per_pod_use(w, ts, at)
    if w.launch_type is LaunchType.FARGATE:
        # ECS reports CPU in units of 1024 per vCPU, and memory in MiB.
        rows = (
            ("CpuUtilized", "Average", "None", shape.dec(n * cpu * 1.024)),
            ("CpuUtilized", "Maximum", "None", shape.dec(n * cpu_max * 1.024)),
            ("MemoryUtilized", "Maximum", "Megabytes", shape.dec(n * mem_max)),
            ("RunningTaskCount", "Average", "Count", shape.dec(n, 0)),
        )
        for metric, stat, unit, value in rows:
            yield SeriesPoint(
                w.key,
                "ServiceName",
                _point(c.account_id, "ECS/ContainerInsights", metric, stat, unit, value, ts),
            )
        return
    # The same window as the memory series above, through the one named predicate, so
    # the restart count and the pinned working set describe one event rather than two
    # that happen to coincide.
    killed = (
        1 if (oom_killed_on(w, ts.date()) and shape.is_kill_window(ts) and ts.hour % 2 == 0) else 0
    )
    # Rebound rather than reassigned, because the ECS branch above returns with a
    # four row tuple and this one is six. One name for two lengths is a type error
    # and, more usefully, two different sets of metrics under one word.
    pod_rows: tuple[tuple[str, str, str, Decimal], ...] = (
        ("pod_cpu_usage_total", "Average", "None", shape.dec(n * cpu)),
        ("pod_cpu_usage_total", "Maximum", "None", shape.dec(n * cpu_max)),
        ("pod_memory_working_set", "Average", "Bytes", shape.dec(n * mem * MIB, 0)),
        ("pod_memory_working_set", "Maximum", "Bytes", shape.dec(n * mem_max * MIB, 0)),
        ("pod_number_of_container_restarts", "Sum", "Count", shape.dec(killed, 0)),
        ("pod_number_of_running_pods", "Average", "Count", shape.dec(n, 0)),
    )
    for metric, stat, unit, value in pod_rows:
        yield SeriesPoint(
            w.key,
            "PodName",
            _point(c.account_id, "ContainerInsights", metric, stat, unit, value, ts),
        )


# ---------------------------------------------------------------------------
# Daily rows, the shape `container_usage` stores. TASK-P6-006.
# ---------------------------------------------------------------------------


def usage_rows(*, at: datetime = fixtures.AS_OF) -> Iterator[Mapping[str, object]]:
    """One row per workload per day, computed from the same hours as `series`.

    `cpu_used_max_millicores` is the largest hourly maximum in the day. The 99th
    percentile TASK-P6-007 sizes at is computed by the detector over the hourly
    series, and a daily column claiming to be that percentile would be a number
    this row cannot honestly hold.
    """
    start, end = shape.window(at)
    for w in WORKLOADS:
        c = cluster(w.cluster)
        request = observed_request(w)
        for d in shape.days(start, end):
            day_start = datetime(d.year, d.month, d.day, tzinfo=UTC)
            hrs = [
                h for h in shape.hours(day_start, day_start + timedelta(days=1)) if start <= h < end
            ]
            if not hrs:
                continue
            samples = [per_pod_use(w, h, at) for h in hrs]
            reps = [replicas(w, h, at) for h in hrs]
            yield {
                "tenant_id": str(fixtures.TENANT_ID),
                "sub_account_id": c.account_id,
                "region_id": c.region_id,
                "cluster_name": c.name,
                "platform": c.platform,
                "namespace": w.namespace,
                "workload": w.name,
                "workload_kind": w.kind,
                "launch_type": w.launch_type.value,
                "usage_date": d.isoformat(),
                "replicas_avg": shape.dec(sum(reps) / len(reps), 2),
                "cpu_request_millicores": request[0] if request else None,
                "memory_request_mib": request[1] if request else None,
                "cpu_limit_millicores": w.cpu_limit_m if request else None,
                "memory_limit_mib": w.mem_limit_mib if request else None,
                "cpu_used_avg_millicores": shape.dec(sum(s[0] for s in samples) / len(samples), 2),
                "cpu_used_max_millicores": shape.dec(max(s[1] for s in samples), 2),
                "memory_used_avg_mib": shape.dec(sum(s[2] for s in samples) / len(samples), 2),
                "memory_used_peak_mib": shape.dec(max(s[3] for s in samples), 2),
                "was_oom_killed": observed_oom(w, d),
                "observed_hours": len(hrs),
                "as_of": (day_start + timedelta(days=1)).isoformat(),
                "collected_at": fixtures.COLLECTED_AT.isoformat(),
            }


def node_group_rows(*, at: datetime = fixtures.AS_OF) -> Iterator[Mapping[str, object]]:
    """One row per node group per day, for spot ratio and bin packing. TASK-P6-011.

    `requested_*` is None on a cluster that cannot report requests, for the same
    reason as on the workload rows. Bin packing there is unknown, not zero.
    """
    start, end = shape.window(at)
    for c in CLUSTERS:
        for g in c.node_groups:
            for d in shape.days(start, end):
                day_start = datetime(d.year, d.month, d.day, tzinfo=UTC)
                hrs = [
                    h
                    for h in shape.hours(day_start, day_start + timedelta(days=1))
                    if start <= h < end
                ]
                if not hrs:
                    continue
                counts = [nodes_in_group(g, c, h, at) for h in hrs]
                totals = [nodes(c, h, at) or 1 for h in hrs]
                share = [n / max(t, n) for n, t in zip(counts, totals, strict=True)]
                req = [_requested_cpu_m(c, h, at) for h in hrs]
                use = [cluster_use(c, h, at) for h in hrs]
                avg_nodes = sum(counts) / len(counts)
                alloc_cpu = avg_nodes * g.vcpu * 1000 * ALLOCATABLE_SHARE
                alloc_mem = avg_nodes * g.memory_gib * 1024 * ALLOCATABLE_SHARE
                yield {
                    "tenant_id": str(fixtures.TENANT_ID),
                    "sub_account_id": c.account_id,
                    "region_id": c.region_id,
                    "cluster_name": c.name,
                    "node_group_resource_id": g.resource_id,
                    "capacity_type": g.capacity_type,
                    "instance_type": g.instance_type,
                    "usage_date": d.isoformat(),
                    "node_count_avg": shape.dec(avg_nodes, 2),
                    "node_count_max": max(counts),
                    "allocatable_cpu_millicores": shape.dec(alloc_cpu, 0),
                    "allocatable_memory_mib": shape.dec(alloc_mem, 0),
                    "requested_cpu_millicores": (
                        shape.dec(sum(r * s for r, s in zip(req, share, strict=True)) / len(hrs), 0)
                        if c.enhanced_observability
                        else None
                    ),
                    "used_cpu_millicores": shape.dec(
                        sum(u[0] * s for u, s in zip(use, share, strict=True)) / len(hrs), 0
                    ),
                    "used_memory_mib": shape.dec(
                        sum(u[1] * s for u, s in zip(use, share, strict=True)) / len(hrs), 0
                    ),
                    "as_of": (day_start + timedelta(days=1)).isoformat(),
                    "collected_at": fixtures.COLLECTED_AT.isoformat(),
                }


def cluster_rows() -> Iterator[Mapping[str, object]]:
    """Every cluster, including the one whose utilization cannot be read."""
    for c in CLUSTERS:
        yield {
            "tenant_id": str(fixtures.TENANT_ID),
            "sub_account_id": c.account_id,
            "region_id": c.region_id,
            "cluster_name": c.name,
            "platform": c.platform,
            "enhanced_observability": c.enhanced_observability,
            "request_unavailable_reason": (
                None
                if c.enhanced_observability
                else "Enhanced observability is not enabled, so pod requests are not published"
            ),
            "as_of": fixtures.AS_OF.isoformat(),
            "collected_at": fixtures.COLLECTED_AT.isoformat(),
        }
