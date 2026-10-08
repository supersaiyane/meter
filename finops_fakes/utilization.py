"""What each resource is configured as, and how much of it is used, every hour.

This is the estate P3 reads, TASK-P3-006, and the inventory P4 reads. It answers
the question the cost estate cannot: not what a resource cost, but whether it
needed to be that size.

**It contains waste that is not waste.** A detector passing against an estate
where every quiet resource is wasteful proves nothing, so the decoys P3 asks for
are here, and each is named in `planted.py` with the outcome a correct detector
reaches:

- a burstable instance at twenty percent with a healthy credit balance
- a development box busy by day and idle at night and at weekends
- an instance with nine days of history, under the fourteen day floor
- a batch node group quiet most of the quarter that scales out several times
  at its end, whose mean says shrink and whose 99th percentile says no
- a memory bound instance whose CPU alone says shrink
- a disaster recovery replica that is quiet because it is a replica

and a genuine example of every waste and pressure class beside them.

**Unobserved is not zero.** An instance without the CloudWatch agent publishes
no memory series at all, and an unattached volume publishes no volume series.
Both are absences a detector has to handle, TASK-P3-007, and neither is filled
in here.

**The denied account and the refusing region have nothing.** `series_for`
raises for them, as the cost export raises a planned failure, so the collector's
partial failure path runs on every test above it.

**Sized from the estate where the estate has a size.** The Elastic Kubernetes
Service node groups take their node counts from the pods in `containers.py`, and
the product API group scales out six times on `cur.spike_day`, which is the day
the bill shows EC2 in that account at six times its usual cost. The anomaly on
the cost screen and the capacity on the utilization screen are the same event.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from types import MappingProxyType

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.metrics import MetricPoint
from finops_core.domain.resource import ResourceRef
from finops_core.errors import AccessDenied, NotOptedIn
from finops_fakes import containers, cur, fixtures, ownership
from finops_fakes import estate_shape as shape
from finops_fakes.containers import SeriesPoint

COLLECTOR = "waste_compute"
GIB = 1024 * 1024 * 1024
MIB = 1024 * 1024


#: What a configuration value can be. Closed on purpose: a reader either counts it
#: or writes it into a CSV cell, and a wider type would push a cast onto every one.
#: `None` is in the union because absent is not zero anywhere in this estate: an
#: unattached volume has no `attached_to`, a log group with no policy has no
#: `retention_days`, and both have to survive as nulls rather than as defaults.
ConfigValue = str | int | float | bool | None

#: A behaviour profile: a shape selector, then the numbers that shape walks
#: between. Heterogeneous and variable length, because the shapes carry different
#: counts, so the readers below take the numbers through `_knobs` rather than
#: indexing into a union and hoping.
Profile = tuple[str | float, ...]


def _knobs(profile: Profile) -> tuple[float, ...]:
    """Everything after the shape selector, as numbers.

    One place where the heterogeneous tuple becomes numeric, rather than a cast at
    each of the five branches that reads one. A profile whose selector is followed
    by anything but numbers is a typo in `SPECS` and raises here, which is where a
    reader can see which resource it was.
    """
    return tuple(float(knob) for knob in profile[1:])


def sized(s: Spec, key: str) -> float:
    """One numeric configuration value, or a failure naming the resource.

    `ConfigValue` includes None because absent is not zero in this estate, so every
    arithmetic reader has to say that it needs a number here. Raising rather than
    defaulting is the point: a missing `vcpu` is a typo in `SPECS`, and a silent
    zero would put a resource at nought percent utilization of nothing.
    """
    value = s.config.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{s.resource_id} has no numeric {key!r}, it has {value!r}")
    return float(value)


@dataclass(frozen=True)
class Spec:
    """One resource: what it is, how it is configured, how it behaves."""

    resource_id: str
    account_id: str
    region_id: str
    zone: str | None
    resource_type: str
    name: str
    kind: str
    #: The provisioned size, by resource type. `str | int | float | bool` rather
    #: than `object`, because every reader of this either counts it or formats it,
    #: and `object` pushes a cast to all of them.
    config: Mapping[str, ConfigValue]
    dimension: str
    #: A behaviour profile: how many points, and the first and last value it walks
    #: between. Typed as a variable length tuple of numbers because the three kinds
    #: carry different lengths and `_fill` reads only the last two.
    cpu: Profile = ()
    mem: Profile | None = None
    disk: Profile | None = None
    #: Days before `at` the resource was launched. None means before the window.
    launched_days_before: int | None = None
    #: Days before `at` the resource stopped being used. None means it never did.
    idle_since_days: int | None = None
    planted: str | None = None
    extra_tags: Mapping[str, str] = field(default_factory=dict)


def _az(region: str, letter: str = "a") -> str:
    return shape.zone(region, letter)


A, B = shape.REGION_A, shape.REGION_B

SPECS: tuple[Spec, ...] = (
    # ------------------------------------------------------------ fake-platform-a
    Spec(
        "amazonec2/fake-platform-a/0001",
        "fake-platform-a",
        A,
        None,
        "AWS::AutoScaling::AutoScalingGroup",
        "platform-eks-ondemand",
        "asg_eks",
        {
            "instance_type": "m6i.2xlarge",
            "vcpu": 8,
            "memory_gib": 32,
            "capacity_type": "ON_DEMAND",
            "min_size": 2,
            "max_size": 12,
            "cluster": "platform-eks",
            "cloudwatch_agent": True,
        },
        "AutoScalingGroupName",
    ),
    Spec(
        "amazonec2/fake-platform-a/0002",
        "fake-platform-a",
        A,
        None,
        "AWS::AutoScaling::AutoScalingGroup",
        "platform-eks-spot",
        "asg_eks",
        {
            "instance_type": "m6i.2xlarge",
            "vcpu": 8,
            "memory_gib": 32,
            "capacity_type": "SPOT",
            "min_size": 1,
            "max_size": 10,
            "cluster": "platform-eks",
            "cloudwatch_agent": True,
        },
        "AutoScalingGroupName",
    ),
    Spec(
        "amazonrds/fake-platform-a/0001",
        "fake-platform-a",
        A,
        _az(A),
        "AWS::RDS::DBInstance",
        "core-ledger-db",
        "rds",
        {
            "instance_class": "db.r6g.2xlarge",
            "vcpu": 8,
            "memory_gib": 64,
            "engine": "postgres",
            "multi_az": True,
            "storage_gib": 2000,
            "storage_type": "gp3",
            "max_connections": 1600,
        },
        "DBInstanceIdentifier",
        cpu=("steady", 30, 22, 0.35),
        disk=("fill", 0.44, 0.76),
        planted="RDS_STORAGE_GROWING",
    ),
    Spec(
        "amazonrds/fake-platform-a/0002",
        "fake-platform-a",
        B,
        _az(B),
        "AWS::RDS::DBInstance",
        "core-ledger-db-dr",
        "rds",
        {
            "instance_class": "db.r6g.2xlarge",
            "vcpu": 8,
            "memory_gib": 64,
            "engine": "postgres",
            "multi_az": False,
            "storage_gib": 2000,
            "storage_type": "gp3",
            "replica_of": "amazonrds/fake-platform-a/0001",
            "max_connections": 1600,
        },
        "DBInstanceIdentifier",
        cpu=("idle", 3.5),
        disk=("fill", 0.44, 0.76),
        planted="DR_REPLICA_QUIET_BY_DESIGN",
        extra_tags={"purpose": "disaster-recovery"},
    ),
    Spec(
        "amazonmsk/fake-platform-a/0001",
        "fake-platform-a",
        A,
        None,
        "AWS::MSK::Cluster",
        "payments-events",
        "msk",
        {
            "broker_instance_type": "kafka.m5.large",
            "brokers": 3,
            "vcpu_per_broker": 2,
            "memory_gib_per_broker": 8,
            "storage_gib_per_broker": 1000,
        },
        "Cluster Name",
        cpu=("steady", 22, 14, 0.30),
        disk=("fill", 0.42, 0.86),
        planted="MSK_DISK_NEAR_FULL",
    ),
    Spec(
        "amazonvpc/fake-platform-a/nat-0001",
        "fake-platform-a",
        A,
        _az(A),
        "AWS::EC2::NatGateway",
        "platform-egress",
        "nat",
        {"gib_per_hour": 6.0},
        "NatGatewayId",
    ),
    Spec(
        "amazoncloudwatch/fake-platform-a/lg-0001",
        "fake-platform-a",
        A,
        None,
        "AWS::Logs::LogGroup",
        "/platform/eks/application",
        "log_group",
        {"retention_days": 30, "stored_gib": 180, "mib_per_hour": 900, "last_queried_days_ago": 1},
        "LogGroupName",
    ),
    Spec(
        "amazoncloudwatch/fake-platform-a/lg-0002",
        "fake-platform-a",
        A,
        None,
        "AWS::Logs::LogGroup",
        "/platform/eks/debug",
        "log_group",
        {
            "retention_days": None,
            "stored_gib": 2600,
            "mib_per_hour": 1400,
            "last_queried_days_ago": 3,
        },
        "LogGroupName",
        planted="LOG_GROUP_NO_RETENTION",
    ),
    Spec(
        "amazoncloudwatch/fake-platform-a/alarm-0001",
        "fake-platform-a",
        A,
        None,
        "AWS::CloudWatch::Alarm",
        "platform-eks-node-disk",
        "alarm",
        {"state": "INSUFFICIENT_DATA", "state_since_days_ago": 41, "metric": "disk_used_percent"},
        "AlarmName",
        planted="ALARM_INSUFFICIENT_DATA_30D",
    ),
    Spec(
        "amazoncloudwatch/fake-platform-a/alarm-0002",
        "fake-platform-a",
        A,
        None,
        "AWS::CloudWatch::Alarm",
        "core-ledger-db-cpu",
        "alarm",
        {"state": "INSUFFICIENT_DATA", "state_since_hours_ago": 1, "metric": "CPUUtilization"},
        "AlarmName",
        planted="ALARM_INSUFFICIENT_DATA_1H",
    ),
    # ------------------------------------------------------------ fake-platform-b
    Spec(
        "amazonec2/fake-platform-b/0001",
        "fake-platform-b",
        A,
        None,
        "AWS::AutoScaling::AutoScalingGroup",
        "batch-eks-spot",
        "asg_eks",
        {
            "instance_type": "c6i.4xlarge",
            "vcpu": 16,
            "memory_gib": 32,
            "capacity_type": "SPOT",
            "min_size": 2,
            "max_size": 20,
            "cluster": "batch-eks",
            "cloudwatch_agent": True,
        },
        "AutoScalingGroupName",
        planted="BATCH_P99_DISAGREES_WITH_MEAN",
    ),
    Spec(
        "amazonrds/fake-platform-b/0001",
        "fake-platform-b",
        A,
        _az(A),
        "AWS::RDS::DBInstance",
        "reporting-db",
        "rds",
        {
            "instance_class": "db.r6g.xlarge",
            "vcpu": 4,
            "memory_gib": 32,
            "engine": "postgres",
            "multi_az": False,
            "storage_gib": 500,
            "storage_type": "gp3",
            "max_connections": 800,
        },
        "DBInstanceIdentifier",
        cpu=("steady", 3.5, 3.0, 0.0),
        disk=("fill", 0.30, 0.34),
        planted="RDS_OVERSIZED",
    ),
    Spec(
        "amazonebs/fake-platform-b/0001",
        "fake-platform-b",
        A,
        _az(A),
        "AWS::EC2::Volume",
        "old-batch-scratch",
        "volume",
        {
            "volume_type": "gp2",
            "size_gib": 500,
            "iops": 1500,
            "attached_to": None,
            "detached_days_ago": 140,
        },
        "VolumeId",
        planted="EBS_UNATTACHED",
    ),
    Spec(
        "amazonebs/fake-platform-b/0002",
        "fake-platform-b",
        A,
        _az(A),
        "AWS::EC2::Volume",
        "batch-shared-data",
        "volume",
        {
            "volume_type": "gp2",
            "size_gib": 1000,
            "iops": 3000,
            "attached_to": "amazonec2/fake-platform-b/0001",
        },
        "VolumeId",
        planted="EBS_GP2_TO_GP3",
    ),
    Spec(
        "amazonebs/fake-platform-b/snap-0001",
        "fake-platform-b",
        A,
        None,
        "AWS::EC2::Snapshot",
        "pre-migration-2024",
        "snapshot",
        {
            "size_gib": 800,
            "age_days": 410,
            "source_volume": "amazonebs/fake-platform-b/0009",
            "source_volume_exists": False,
        },
        "SnapshotId",
        planted="SNAPSHOT_ORPHANED",
    ),
    Spec(
        "amazoncloudwatch/fake-platform-b/lg-0001",
        "fake-platform-b",
        A,
        None,
        "AWS::Logs::LogGroup",
        "/batch/risk/raw",
        "log_group",
        {
            "retention_days": 365,
            "stored_gib": 3100,
            "mib_per_hour": 1600,
            "last_queried_days_ago": 118,
        },
        "LogGroupName",
        planted="LOG_GROUP_UNQUERIED_90D",
    ),
    Spec(
        "amazoncloudwatch/fake-platform-b/lg-0002",
        "fake-platform-b",
        A,
        None,
        "AWS::Logs::LogGroup",
        "/batch/risk/raw-copy",
        "log_group",
        {
            "retention_days": 365,
            "stored_gib": 3050,
            "mib_per_hour": 1600,
            "last_queried_days_ago": None,
            "duplicate_of": "amazoncloudwatch/fake-platform-b/lg-0001",
        },
        "LogGroupName",
        planted="LOG_GROUP_DUPLICATE_DELIVERY",
    ),
    Spec(
        "amazoncloudwatch/fake-platform-b/metric-0001",
        "fake-platform-b",
        A,
        None,
        "Custom::CloudWatch::Metric",
        "Batch/Risk JobLagSeconds",
        "custom_metric",
        {
            "namespace": "Batch/Risk",
            "metric": "JobLagSeconds",
            "last_read_days_ago": None,
            "published_since_days_ago": 300,
        },
        "JobName",
        planted="CUSTOM_METRIC_UNQUERIED",
    ),
    # ------------------------------------------------------------ fake-product-a
    Spec(
        "amazonec2/fake-product-a/0001",
        "fake-product-a",
        A,
        None,
        "AWS::AutoScaling::AutoScalingGroup",
        "product-api",
        "asg",
        {
            "instance_type": "m6i.xlarge",
            "vcpu": 4,
            "memory_gib": 16,
            "capacity_type": "ON_DEMAND",
            "min_size": 3,
            "max_size": 30,
            "base_nodes": 4,
            "cloudwatch_agent": True,
        },
        "AutoScalingGroupName",
        cpu=("steady", 28, 22, 0.20),
        mem=("steady", 52, 10),
        planted="ASG_SCALE_OUT_ON_SPIKE_DAY",
    ),
    Spec(
        "amazonec2/fake-product-a/0002",
        "fake-product-a",
        A,
        _az(A),
        "AWS::EC2::Instance",
        "statements-bastion",
        "instance",
        {
            "instance_type": "t3.medium",
            "vcpu": 2,
            "memory_gib": 4,
            "burstable": True,
            "cloudwatch_agent": True,
            "root_volume_gib": 50,
        },
        "InstanceId",
        cpu=("fixed", 20.0),
        mem=("steady", 38, 6),
        disk=("fill", 0.22, 0.25),
        planted="BURSTABLE_HEALTHY_CREDITS",
    ),
    Spec(
        "amazonec2/fake-product-a/0003",
        "fake-product-a",
        A,
        _az(A, "b"),
        "AWS::EC2::Instance",
        "fraud-scorer",
        "instance",
        {
            "instance_type": "c6i.2xlarge",
            "vcpu": 8,
            "memory_gib": 16,
            "cloudwatch_agent": True,
            "root_volume_gib": 100,
        },
        "InstanceId",
        cpu=("hot", 80),
        mem=("steady", 61, 8),
        disk=("fill", 0.40, 0.46),
        planted="EC2_OVER_UTILIZED",
    ),
    Spec(
        "amazonec2/fake-product-a/0004",
        "fake-product-a",
        A,
        _az(A, "c"),
        "AWS::EC2::Instance",
        "customer-search",
        "instance",
        {
            "instance_type": "r6i.xlarge",
            "vcpu": 4,
            "memory_gib": 32,
            "cloudwatch_agent": True,
            "root_volume_gib": 100,
            "data_volume": "amazonebs/fake-product-a/0001",
        },
        "InstanceId",
        cpu=("steady", 6, 5, 0.10),
        mem=("fill_pct", 80, 93),
        disk=("fill", 0.64, 0.91),
        planted="MEMORY_BOUND_CPU_LOOKS_IDLE",
    ),
    Spec(
        "amazonebs/fake-product-a/0001",
        "fake-product-a",
        A,
        _az(A, "c"),
        "AWS::EC2::Volume",
        "customer-search-index",
        "volume",
        {
            "volume_type": "gp3",
            "size_gib": 750,
            "iops": 3000,
            "throughput_mibps": 125,
            "attached_to": "amazonec2/fake-product-a/0004",
        },
        "VolumeId",
        disk=("fill", 0.64, 0.91),
        planted="EBS_NEAR_FULL",
    ),
    Spec(
        "amazonrds/fake-product-a/0001",
        "fake-product-a",
        A,
        _az(A),
        "AWS::RDS::DBInstance",
        "customer-db",
        "rds",
        {
            "instance_class": "db.r6g.xlarge",
            "vcpu": 4,
            "memory_gib": 32,
            "engine": "postgres",
            "multi_az": True,
            "storage_gib": 1000,
            "storage_type": "gp3",
            "max_connections": 800,
        },
        "DBInstanceIdentifier",
        cpu=("steady", 34, 24, 0.25),
        disk=("fill", 0.35, 0.52),
    ),
    Spec(
        "amazonelasticache/fake-product-a/0001",
        "fake-product-a",
        A,
        _az(A),
        "AWS::ElastiCache::CacheCluster",
        "session-cache",
        "cache",
        {
            "node_type": "cache.r6g.xlarge",
            "nodes": 2,
            "vcpu": 4,
            "memory_gib": 26.32,
            "engine": "redis",
        },
        "CacheClusterId",
        cpu=("steady", 4, 3, 0.05),
        mem=("steady", 14, 3),
        planted="CACHE_OVERSIZED",
    ),
    Spec(
        "amazonelasticache/fake-product-a/0002",
        "fake-product-a",
        A,
        _az(A, "b"),
        "AWS::ElastiCache::CacheCluster",
        "rate-limit-cache",
        "cache",
        {
            "node_type": "cache.t4g.small",
            "nodes": 1,
            "vcpu": 2,
            "memory_gib": 1.37,
            "engine": "redis",
        },
        "CacheClusterId",
        cpu=("steady", 18, 14, 0.30),
        mem=("fill_pct", 80, 94),
        planted="CACHE_MEMORY_PRESSURE",
    ),
    Spec(
        "elasticloadbalancing/fake-product-a/0001",
        "fake-product-a",
        A,
        None,
        "AWS::ElasticLoadBalancingV2::LoadBalancer",
        "product-public-alb",
        "alb",
        {
            "scheme": "internet-facing",
            "requests_per_hour": 180000,
            "targets": "amazonec2/fake-product-a/0001",
        },
        "LoadBalancer",
    ),
    Spec(
        "elasticloadbalancing/fake-product-a/0002",
        "fake-product-a",
        A,
        None,
        "AWS::ElasticLoadBalancingV2::LoadBalancer",
        "legacy-statements-alb",
        "alb",
        {"scheme": "internal", "requests_per_hour": 2400, "targets": None},
        "LoadBalancer",
        idle_since_days=63,
        planted="ALB_IDLE",
    ),
    Spec(
        "amazonvpc/fake-product-a/eip-0001",
        "fake-product-a",
        A,
        None,
        "AWS::EC2::EIP",
        "old-partner-endpoint",
        "eip",
        {"associated_with": None, "released_days_ago": None},
        "AllocationId",
        planted="EIP_UNASSOCIATED",
    ),
    # ------------------------------------------------------------ fake-product-b (untagged)
    Spec(
        "amazonec2/fake-product-b/0001",
        "fake-product-b",
        A,
        _az(A),
        "AWS::EC2::Instance",
        "dev-workstation",
        "instance",
        {
            "instance_type": "m6i.large",
            "vcpu": 2,
            "memory_gib": 8,
            "cloudwatch_agent": True,
            "root_volume_gib": 1000,
        },
        "InstanceId",
        cpu=("dev",),
        mem=("steady", 45, 20),
        disk=("fill", 0.07, 0.08),
        planted="DEV_BOX_IDLE_AT_NIGHT",
        # TASK-P11-003. The `sandbox` application, which names no owner.
        extra_tags={ownership.APPLICATION_TAG: ownership.SANDBOX},
    ),
    Spec(
        "amazonebs/fake-product-b/0001",
        "fake-product-b",
        A,
        _az(A),
        "AWS::EC2::Volume",
        "dev-workstation-root",
        "volume",
        {
            "volume_type": "gp3",
            "size_gib": 1000,
            "iops": 3000,
            "throughput_mibps": 125,
            "attached_to": "amazonec2/fake-product-b/0001",
        },
        "VolumeId",
        disk=("fill", 0.07, 0.08),
        planted="EBS_OVERSIZED",
        # TASK-P11-001. An owner under a second tag key, in the account that carries no team tag:
        # a deployment naming `owner` among its owner tag keys finds this team, P11 spec 5.2.
        extra_tags={"owner": "data-platform"},
    ),
    Spec(
        "amazonec2/fake-product-b/0002",
        "fake-product-b",
        A,
        _az(A, "b"),
        "AWS::EC2::Instance",
        "poc-ml-box",
        "instance",
        {
            "instance_type": "m6i.4xlarge",
            "vcpu": 16,
            "memory_gib": 64,
            "cloudwatch_agent": True,
            "root_volume_gib": 200,
        },
        "InstanceId",
        cpu=("idle", 0.9),
        mem=("steady", 6, 1),
        disk=("fill", 0.12, 0.12),
        launched_days_before=240,
        planted="EC2_IDLE",
    ),
    Spec(
        "amazonec2/fake-product-b/0003",
        "fake-product-b",
        A,
        _az(A),
        "AWS::EC2::Instance",
        "new-api-canary",
        "instance",
        {
            "instance_type": "m6i.xlarge",
            "vcpu": 4,
            "memory_gib": 16,
            "cloudwatch_agent": True,
            "root_volume_gib": 50,
        },
        "InstanceId",
        cpu=("idle", 2.0),
        mem=("steady", 12, 2),
        disk=("fill", 0.10, 0.10),
        launched_days_before=9,
        planted="UNDER_HISTORY_FLOOR",
    ),
    Spec(
        "amazonec2/fake-product-b/0004",
        "fake-product-b",
        A,
        _az(A, "c"),
        "AWS::EC2::Instance",
        "legacy-app",
        "instance",
        {
            "instance_type": "m5.2xlarge",
            "vcpu": 8,
            "memory_gib": 32,
            "cloudwatch_agent": False,
            "root_volume_gib": 100,
        },
        "InstanceId",
        cpu=("steady", 5, 5, 0.0),
        mem=None,
        disk=None,
        planted="OVERSIZED_MEMORY_UNOBSERVED",
        # TASK-P11-003. AppRegistry's application `checkout`, by its awsApplication tag.
        extra_tags={ownership.APPLICATION_TAG: ownership.CHECKOUT},
    ),
    Spec(
        "amazonrds/fake-product-b/0001",
        "fake-product-b",
        A,
        _az(A),
        "AWS::RDS::DBInstance",
        "poc-db",
        "rds",
        {
            "instance_class": "db.m6g.large",
            "vcpu": 2,
            "memory_gib": 8,
            "engine": "mysql",
            "multi_az": False,
            "storage_gib": 200,
            "storage_type": "gp3",
            "max_connections": 400,
        },
        "DBInstanceIdentifier",
        cpu=("steady", 12, 10, 0.0),
        disk=("fill", 0.20, 0.21),
        idle_since_days=47,
        planted="RDS_IDLE",
        # TASK-P11-003. The `reporting` application's, by the stack that made it.
        extra_tags={ownership.STACK_TAG: ownership.REPORTING_STACK},
    ),
    Spec(
        "amazonvpc/fake-product-b/nat-0001",
        "fake-product-b",
        A,
        _az(A),
        "AWS::EC2::NatGateway",
        "dev-egress",
        "nat",
        {"gib_per_hour": 0.04},
        "NatGatewayId",
        planted="NAT_IDLE",
    ),
)

_BY_ID: Mapping[str, Spec] = MappingProxyType({s.resource_id: s for s in SPECS})


#: Which billing service each resource id prefix belongs to. The estate names its
#: resources `{service}/{account}/{index}` in lower case, and the capitalisation AWS
#: uses is not derivable from that, so it is written down once here rather than
#: guessed at by whichever module needs it. `cur.py` reads this, which is what makes
#: the bill and the estate join on more than coincidence.
SERVICE_BY_PREFIX: Mapping[str, str] = MappingProxyType(
    {
        "amazonec2": "AmazonEC2",
        "amazonrds": "AmazonRDS",
        "amazonebs": "AmazonEBS",
        "amazonelasticache": "AmazonElastiCache",
        "amazonmsk": "AmazonMSK",
        "amazonvpc": "AmazonVPC",
        "amazoncloudwatch": "AmazonCloudWatch",
        "elasticloadbalancing": "ElasticLoadBalancing",
    }
)


def service_of(resource_id: str) -> str:
    """Which service a resource bills under.

    Raises on an unknown prefix rather than returning a default, because a resource
    billed under a service nobody named would sit in the bill under a heading no
    screen groups by, and would then be missing from every total without being
    missing from the table.
    """
    prefix = resource_id.split("/")[0]
    if prefix not in SERVICE_BY_PREFIX:
        raise ValueError(f"{resource_id} has no known billing service for prefix {prefix!r}")
    return SERVICE_BY_PREFIX[prefix]


def specs_for(account_id: str, service_name: str) -> tuple[Spec, ...]:
    """Every resource one account runs under one service, in id order.

    The join `cur.py` needs, expressed once. A caller filtering `SPECS` itself would
    be a second implementation of the prefix rule above.
    """
    return tuple(
        s for s in SPECS if s.account_id == account_id and service_of(s.resource_id) == service_name
    )


def spec(resource_id: str) -> Spec:
    return _BY_ID[resource_id]


def _tags(s: Spec) -> Mapping[str, str]:
    """The same tagging holes the bill has: `fake-product-b` carries no team tag.

    A resource's own extra tags survive the hole, so the one planted under a second owner key,
    TASK-P11-001, carries it with no `team` beside it.
    """
    owner = cur.OWNERS.get(s.account_id)
    if owner is None:
        return MappingProxyType(dict(s.extra_tags))
    return MappingProxyType({"team": owner, "finops:module": "fixture", **s.extra_tags})


def tags_of(resource_id: str) -> Mapping[str, str]:
    """A resource's tags as the inventory reads them, none for one the estate does not hold."""
    found = _BY_ID.get(resource_id)
    return _tags(found) if found is not None else MappingProxyType({})


def launched_at(s: Spec, at: datetime = fixtures.AS_OF) -> datetime:
    """When the resource first existed, bounded below by the window start."""
    start, end = shape.window(at)
    if s.launched_days_before is None:
        return start
    return end - timedelta(days=s.launched_days_before)


def resources(*, at: datetime = fixtures.AS_OF) -> tuple[ResourceRef, ...]:
    """Every readable resource at `at`, as the inventory port returns it."""
    return tuple(
        ResourceRef(
            account_key=AccountKey(provider=Provider.AWS, account_id=s.account_id),
            resource_id=s.resource_id,
            resource_type=s.resource_type,
            region_id=s.region_id,
            name=s.name,
            tags=_tags(s),
            as_of=at,
            collected_at=fixtures.COLLECTED_AT,
        )
        for s in SPECS
    )


def configuration(resource_id: str) -> Mapping[str, object]:
    """What the resource was provisioned as. `ResourceRef` has no place for this.

    The size is what every rightsizing verdict compares use against, so it has to
    travel with the resource somehow. P4's `topology_node` is the likely home;
    until TASK-P4-001 decides, it is a separate mapping keyed on the identifier.
    """
    return MappingProxyType(dict(spec(resource_id).config))


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------


def _cpu(s: Spec, ts: datetime, at: datetime) -> tuple[float, float]:
    """(average, maximum) CPU percent for the hour starting at `ts`."""
    start, end = shape.window(at)
    d = ts.date()
    kind = s.cpu[0]
    knobs = _knobs(s.cpu)
    j = shape.jitter(f"{s.resource_id}|cpu", ts)
    if kind == "steady":
        base, amp, growth = knobs
        avg = (base + amp * shape.diurnal(ts)) * shape.seasonal(d) * (
            1 + growth * shape.progress(ts, start, end)
        ) + 1.5 * j
    elif kind == "idle":
        avg = knobs[0] + 0.35 * j
    elif kind == "dev":
        avg = 55 + 15 * shape.diurnal(ts) + 5 * j if shape.is_business_hours(ts) else 1.2 + 0.5 * j
    elif kind == "hot":
        avg = knobs[0] + 12 * shape.diurnal(ts) * shape.seasonal(d) + 2 * j
    elif kind == "fixed":
        avg = knobs[0] + 1.5 * j
    else:  # pragma: no cover - a new profile must be added above, not defaulted
        raise ValueError(f"unknown cpu profile {kind!r} on {s.resource_id}")
    if s.idle_since_days is not None and ts >= end - timedelta(days=s.idle_since_days):
        avg = 0.6 + 0.2 * j
    avg = shape.clamp(avg, 0.1, 100)
    peak = avg * (1.18 + 0.3 * abs(shape.jitter(f"{s.resource_id}|cpumax", ts))) + 1.0
    return avg, shape.clamp(peak, avg, 100)


def _fill(s: Spec, ts: datetime, at: datetime, profile: Profile | None) -> float:
    """How full, between the profile's two ends, at `ts`.

    `profile` is optional because `Spec.disk` and `Spec.mem` are, and a kind that
    reaches here without one is a typo in `SPECS` rather than a case to default:
    filling to nought would report an empty disk on a resource nobody sized.
    """
    if profile is None:
        raise ValueError(f"{s.resource_id} needs a fill profile and has none")
    _, end = shape.window(at)
    frac = shape.progress(ts, launched_at(s, at), end)
    first, last = _knobs(profile)
    return first + (last - first) * frac


def _mem(s: Spec, ts: datetime, at: datetime) -> tuple[float, float] | None:
    if s.mem is None:
        return None
    j = shape.jitter(f"{s.resource_id}|mem", ts)
    if s.mem[0] == "steady":
        base, amp = _knobs(s.mem)
        avg = base + amp * shape.diurnal(ts) + 1.2 * j
    else:  # fill_pct
        avg = _fill(s, ts, at, s.mem) + 1.0 * shape.diurnal(ts) + 0.8 * j
    avg = shape.clamp(avg, 0.5, 99.5)
    return avg, shape.clamp(avg + 1.5 + abs(j), avg, 100)


def _running(s: Spec, ts: datetime, at: datetime) -> bool:
    return ts >= launched_at(s, at)


def _points(s: Spec, ts: datetime, at: datetime) -> Iterator[tuple[str, str, str, str, Decimal]]:
    """(namespace, metric, statistic, unit, value) for one resource, one hour."""
    d = ts.date()
    start, end = shape.window(at)
    grow = 1 + 0.25 * shape.progress(ts, start, end)
    if s.kind in ("instance", "asg", "asg_eks"):
        if s.kind == "asg_eks":
            c = containers.cluster(str(s.config["cluster"]))
            group = next(g for g in c.node_groups if g.resource_id == s.resource_id)
            count = containers.nodes_in_group(group, c, ts, at)
            used_cpu, used_mem = containers.cluster_use(c, ts, at)
            total_vcpu = sum(
                containers.nodes_in_group(g, c, ts, at) * g.vcpu for g in c.node_groups
            )
            total_mem = sum(
                containers.nodes_in_group(g, c, ts, at) * g.memory_gib for g in c.node_groups
            )
            cpu = shape.clamp(
                100 * used_cpu / (total_vcpu * 1000) + 5 + shape.jitter(s.resource_id, ts), 0.5, 100
            )
            cpu_max = shape.clamp(cpu * 1.3, cpu, 100)
            mem = shape.clamp(100 * used_mem / (total_mem * 1024) + 11, 1, 99)
            mem_pair: tuple[float, float] | None = (mem, shape.clamp(mem * 1.06, mem, 100))
        else:
            cpu, cpu_max = _cpu(s, ts, at)
            mem_pair = _mem(s, ts, at)
            count = 1
            if s.kind == "asg":
                base = int(sized(s, "base_nodes"))
                count = max(
                    int(sized(s, "min_size")),
                    round(base * (0.8 + 0.6 * shape.diurnal(ts)) * shape.seasonal(d) * grow),
                )
                if s.account_id == cur.SPIKE_ACCOUNT and d == cur.spike_day(at):
                    count *= int(cur.SPIKE_MULTIPLIER)
        yield ("AWS/EC2", "CPUUtilization", "Average", "Percent", shape.dec(cpu))
        yield ("AWS/EC2", "CPUUtilization", "Maximum", "Percent", shape.dec(cpu_max))
        net = (
            40
            * MIB
            * count
            * (0.3 + shape.diurnal(ts))
            * (1 + 0.1 * shape.jitter(f"{s.resource_id}|net", ts))
        )
        if s.cpu and s.cpu[0] == "idle":
            net = 2 * MIB
        yield ("AWS/EC2", "NetworkIn", "Sum", "Bytes", shape.dec(net, 0))
        yield ("AWS/EC2", "NetworkOut", "Sum", "Bytes", shape.dec(net * 0.7, 0))
        if s.kind != "instance":
            yield (
                "AWS/AutoScaling",
                "GroupInServiceInstances",
                "Average",
                "Count",
                shape.dec(count, 0),
            )
        if s.config.get("burstable"):
            credit_balance = 480 + 60 * shape.jitter(f"{s.resource_id}|credit", ts)
            yield ("AWS/EC2", "CPUCreditBalance", "Average", "Count", shape.dec(credit_balance, 2))
        if s.config.get("cloudwatch_agent") and mem_pair is not None:
            yield ("CWAgent", "mem_used_percent", "Average", "Percent", shape.dec(mem_pair[0]))
            yield ("CWAgent", "mem_used_percent", "Maximum", "Percent", shape.dec(mem_pair[1]))
        if s.config.get("cloudwatch_agent") and s.disk is not None:
            yield (
                "CWAgent",
                "disk_used_percent",
                "Maximum",
                "Percent",
                shape.dec(100 * _fill(s, ts, at, s.disk)),
            )
        return
    if s.kind == "rds":
        cpu, cpu_max = _cpu(s, ts, at)
        idle = s.idle_since_days is not None and ts >= end - timedelta(days=s.idle_since_days)
        if s.config.get("replica_of"):
            conns = 2.0
        elif idle:
            conns = 0.0
        else:
            conns = (
                sized(s, "max_connections") * 0.18 * (0.4 + shape.diurnal(ts)) * shape.seasonal(d)
            )
        mem_gib = sized(s, "memory_gib")
        free_mem = mem_gib * GIB * (0.30 + 0.05 * shape.jitter(f"{s.resource_id}|fm", ts))
        storage = sized(s, "storage_gib") * GIB * (1 - _fill(s, ts, at, s.disk))
        yield ("AWS/RDS", "CPUUtilization", "Average", "Percent", shape.dec(cpu))
        yield ("AWS/RDS", "CPUUtilization", "Maximum", "Percent", shape.dec(cpu_max))
        yield ("AWS/RDS", "DatabaseConnections", "Average", "Count", shape.dec(conns, 2))
        yield ("AWS/RDS", "FreeableMemory", "Average", "Bytes", shape.dec(free_mem, 0))
        yield ("AWS/RDS", "FreeStorageSpace", "Minimum", "Bytes", shape.dec(storage, 0))
        return
    if s.kind == "cache":
        cpu, cpu_max = _cpu(s, ts, at)
        used = _mem(s, ts, at)
        if used is None:  # pragma: no cover - every cache spec carries a memory profile
            raise ValueError(f"{s.resource_id} is a cache with no memory profile")
        evictions = max(0.0, (used[1] - 94.0) * 140.0)
        yield ("AWS/ElastiCache", "CPUUtilization", "Average", "Percent", shape.dec(cpu))
        yield ("AWS/ElastiCache", "CPUUtilization", "Maximum", "Percent", shape.dec(cpu_max))
        yield (
            "AWS/ElastiCache",
            "DatabaseMemoryUsagePercentage",
            "Average",
            "Percent",
            shape.dec(used[0]),
        )
        yield (
            "AWS/ElastiCache",
            "DatabaseMemoryUsagePercentage",
            "Maximum",
            "Percent",
            shape.dec(used[1]),
        )
        yield ("AWS/ElastiCache", "Evictions", "Sum", "Count", shape.dec(evictions, 0))
        yield (
            "AWS/ElastiCache",
            "CurrConnections",
            "Average",
            "Count",
            shape.dec(120 * (0.4 + shape.diurnal(ts)), 0),
        )
        return
    if s.kind == "alb":
        idle = s.idle_since_days is not None and ts >= end - timedelta(days=s.idle_since_days)
        requests = (
            0.0
            if idle
            else sized(s, "requests_per_hour")
            * (0.2 + shape.diurnal(ts))
            * shape.seasonal(d)
            * grow
        )
        yield ("AWS/ApplicationELB", "RequestCount", "Sum", "Count", shape.dec(requests, 0))
        yield (
            "AWS/ApplicationELB",
            "ActiveConnectionCount",
            "Sum",
            "Count",
            shape.dec(requests * 0.3, 0),
        )
        return
    if s.kind == "nat":
        gib = sized(s, "gib_per_hour") * (0.3 + shape.diurnal(ts)) * grow
        yield ("AWS/NATGateway", "BytesOutToDestination", "Sum", "Bytes", shape.dec(gib * GIB, 0))
        yield (
            "AWS/NATGateway",
            "ActiveConnectionCount",
            "Maximum",
            "Count",
            shape.dec(gib * 900, 0),
        )
        return
    if s.kind == "volume":
        if s.config.get("attached_to") is None:
            # An unattached volume publishes nothing. The finding is in its
            # configuration, and a detector reading only metrics never sees it.
            return
        busy = shape.clamp(
            900 + 1800 * shape.diurnal(ts) + 200 * shape.jitter(s.resource_id, ts), 0, 3600
        )
        yield ("AWS/EBS", "VolumeReadOps", "Sum", "Count", shape.dec(busy * 12, 0))
        yield ("AWS/EBS", "VolumeWriteOps", "Sum", "Count", shape.dec(busy * 7, 0))
        yield ("AWS/EBS", "VolumeIdleTime", "Sum", "Seconds", shape.dec(3600 - busy, 0))
        return
    if s.kind == "msk":
        cpu, cpu_max = _cpu(s, ts, at)
        yield ("AWS/Kafka", "CpuUser", "Average", "Percent", shape.dec(cpu))
        yield ("AWS/Kafka", "CpuUser", "Maximum", "Percent", shape.dec(cpu_max))
        yield (
            "AWS/Kafka",
            "KafkaDataLogsDiskUsed",
            "Maximum",
            "Percent",
            shape.dec(100 * _fill(s, ts, at, s.disk)),
        )
        return
    if s.kind == "log_group":
        mib = sized(s, "mib_per_hour") * (0.5 + shape.diurnal(ts)) * grow
        yield ("AWS/Logs", "IncomingBytes", "Sum", "Bytes", shape.dec(mib * MIB, 0))
        return
    if s.kind == "custom_metric":
        lag = 40 + 25 * shape.diurnal(ts) + 10 * shape.jitter(s.resource_id, ts)
        yield (
            str(s.config["namespace"]),
            str(s.config["metric"]),
            "Average",
            "Seconds",
            shape.dec(lag, 2),
        )
        return
    # alarm, eip and snapshot publish nothing hourly. Their findings are state.


def _series_for_spec(
    s: Spec, start: datetime, end: datetime, at: datetime
) -> Iterator[SeriesPoint]:
    key = AccountKey(provider=Provider.AWS, account_id=s.account_id)
    for ts in shape.hours(max(start, launched_at(s, at)), end):
        if not _running(s, ts, at):
            continue
        for namespace, metric, statistic, unit, value in _points(s, ts, at):
            yield SeriesPoint(
                resource_id=s.resource_id,
                dimension=s.dimension,
                point=MetricPoint(
                    account_key=key,
                    namespace=namespace,
                    metric_name=metric,
                    statistic=statistic,
                    unit=unit,
                    value=value,
                    at=ts,
                    as_of=ts + shape.STEP,
                    collected_at=fixtures.COLLECTED_AT,
                ),
            )


def series_for(
    account_id: str,
    region_id: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    at: datetime = fixtures.AS_OF,
) -> Iterator[SeriesPoint]:
    """Every hourly point for one account and region, as a collector fans out.

    Raises for the denied account and the refusing region before yielding
    anything, so a caller cannot mistake a refusal for a quiet estate.
    """
    if account_id == shape.DENIED_ACCOUNT:
        raise AccessDenied(
            scope_key=f"aws:{account_id}:{region_id}",
            collector=COLLECTOR,
            detail="planned by the fake utilization estate",
        )
    if region_id == shape.REFUSING_REGION:
        raise NotOptedIn(
            scope_key=f"aws:{account_id}:{region_id}",
            collector=COLLECTOR,
            detail="the region is not enabled in this account",
        )
    w_start, w_end = shape.window(at)
    for s in SPECS:
        if s.account_id == account_id and s.region_id == region_id:
            yield from _series_for_spec(s, start or w_start, end or w_end, at)


def series(
    *, start: datetime | None = None, end: datetime | None = None, at: datetime = fixtures.AS_OF
) -> Iterator[SeriesPoint]:
    """Every readable hourly point in the estate, resource by resource."""
    w_start, w_end = shape.window(at)
    for s in SPECS:
        yield from _series_for_spec(s, start or w_start, end or w_end, at)


# ---------------------------------------------------------------------------
# What the quota estate counts
# ---------------------------------------------------------------------------

#: Instance families the On-Demand Standard vCPU quota covers.
_STANDARD = ("a", "c", "d", "h", "i", "m", "r", "t", "z")


def vcpu_in_use(
    account_id: str,
    region_id: str,
    ts: datetime,
    *,
    capacity_type: str,
    at: datetime = fixtures.AS_OF,
) -> int:
    """vCPU running in one account and region, derived from the estate above.

    The quota estate's usage figure for the Standard vCPU quotas is this number,
    so a node group scaling out for a quarter end batch moves the quota headroom
    on the same day.
    """
    total = 0
    for s in SPECS:
        if s.account_id != account_id or s.region_id != region_id:
            continue
        itype = str(s.config.get("instance_type", ""))
        if not itype or itype[0] not in _STANDARD or not _running(s, ts, at):
            continue
        vcpu = int(sized(s, "vcpu"))
        cap = str(s.config.get("capacity_type", "ON_DEMAND"))
        if cap != capacity_type:
            continue
        if s.kind == "instance":
            total += vcpu
        elif s.kind == "asg_eks":
            c = containers.cluster(str(s.config["cluster"]))
            group = next(g for g in c.node_groups if g.resource_id == s.resource_id)
            total += vcpu * containers.nodes_in_group(group, c, ts, at)
        elif s.kind == "asg":
            points = {p[1]: p[4] for p in _points(s, ts, at) if p[1] == "GroupInServiceInstances"}
            total += vcpu * int(points["GroupInServiceInstances"])
    return total


def inventory_rows(*, at: datetime = fixtures.AS_OF) -> Iterator[Mapping[str, object]]:
    """One row per resource: identity, tags, configuration and planted finding."""
    for s in SPECS:
        yield {
            "tenant_id": str(fixtures.TENANT_ID),
            "sub_account_id": s.account_id,
            "region_id": s.region_id,
            "availability_zone": s.zone,
            "resource_id": s.resource_id,
            "resource_type": s.resource_type,
            "name": s.name,
            "tags": dict(_tags(s)),
            "configuration": dict(s.config),
            "launched_at": launched_at(s, at).isoformat(),
            "as_of": at.isoformat(),
            "collected_at": fixtures.COLLECTED_AT.isoformat(),
        }
