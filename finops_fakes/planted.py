"""Everything deliberately placed in the fake estates, and what should happen to it.

A detector test that asserts "found something" passes on a detector that flags
everything. The useful assertion is that it found exactly these, missed none,
refused the ones it has to refuse, and said "could not check" where it could
not. This module is the list those assertions read.

`expected` is one of:

- `FINDING`: a correct detector produces a recommendation
- `NO_FINDING`: it looks like waste or pressure and is not. A detector that flags
  it is wrong
- `PRESSURE`: over utilized rather than wasteful. Named so a rightsizing
  screen can show both directions, since the P3 plan's waste classes cover only
  one of them
- `REFUSE`: no estimate at all, not a cautious one
- `UNOBSERVED`: the signal cannot be read, and the output must say so in words
- `COVERAGE`: a statement about what could not be read, for P4 and P5

The codes are the `planted` values on the specs, clusters and workloads, so a
test can go from a row to its expectation without a second list.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Planted:
    code: str
    plan_task: str
    subjects: tuple[str, ...]
    expected: str
    why: str


PLANTED: tuple[Planted, ...] = (
    # --------------------------------------------------------------- P3 decoys
    Planted(
        "BURSTABLE_HEALTHY_CREDITS",
        "TASK-P3-006",
        ("amazonec2/fake-product-a/0002",),
        "NO_FINDING",
        "t3.medium at about 20 percent CPU with a credit balance that never drains. Correctly "
        "sized.",
    ),
    Planted(
        "DEV_BOX_IDLE_AT_NIGHT",
        "TASK-P3-006",
        ("amazonec2/fake-product-b/0001",),
        "NO_FINDING",
        "Busy in business hours, idle at night and weekends. Its mean is low and its p95 is not.",
    ),
    Planted(
        "UNDER_HISTORY_FLOOR",
        "TASK-P3-006",
        ("amazonec2/fake-product-b/0003",),
        "REFUSE",
        "Launched nine days before `at`. Under the fourteen day floor, so no estimate of any kind.",
    ),
    Planted(
        "BATCH_P99_DISAGREES_WITH_MEAN",
        "TASK-P3-002",
        ("amazonec2/fake-platform-b/0001",),
        "NO_FINDING",
        "Batch node group: CPU mean about 15 percent, p99 of the hourly maximum about 70 percent, "
        "and its node "
        "count jumps several times at every quarter end. Mean says shrink, p99 and node count say "
        "no.",
    ),
    Planted(
        "MEMORY_BOUND_CPU_LOOKS_IDLE",
        "TASK-P3-002",
        ("amazonec2/fake-product-a/0004",),
        "NO_FINDING",
        "CPU p95 under 12 percent, memory climbing from 80 to about 94 percent. A CPU only rule "
        "would "
        "downsize it into swapping.",
    ),
    Planted(
        "DR_REPLICA_QUIET_BY_DESIGN",
        "TASK-P3-008",
        ("amazonrds/fake-platform-a/0002",),
        "NO_FINDING",
        "Cross region read replica tagged purpose=disaster-recovery. Quiet because it is a "
        "standby. "
        "A detector that does not read the tag will flag it, and that is a decision for the P3 "
        "spec.",
    ),
    Planted(
        "ASG_SCALE_OUT_ON_SPIKE_DAY",
        "FEAT-026",
        ("amazonec2/fake-product-a/0001",),
        "NO_FINDING",
        "Scales to six times its size on cur.spike_day, the day the bill spikes. Recommendations "
        "are made "
        "at group level, never per instance, and one day of scale out is not a sizing signal.",
    ),
    # ------------------------------------------------------------- P3 genuine
    Planted(
        "EC2_IDLE",
        "TASK-P3-008",
        ("amazonec2/fake-product-b/0002",),
        "FINDING",
        "m6i.4xlarge under 1 percent CPU and 6 percent memory for 240 days. Stop or terminate.",
    ),
    Planted(
        "OVERSIZED_MEMORY_UNOBSERVED",
        "TASK-P3-007",
        ("amazonec2/fake-product-b/0004",),
        "FINDING",
        "m5.2xlarge at about 7 percent CPU with no CloudWatch agent. Recommend on CPU and say in "
        "the "
        "rationale that memory could not be checked. No memory series exists, which is not zero.",
    ),
    Planted(
        "RDS_OVERSIZED",
        "TASK-P3-008",
        ("amazonrds/fake-platform-b/0001",),
        "FINDING",
        "db.r6g.xlarge with p95 CPU under 10 percent and live connections. Downsize one class.",
    ),
    Planted(
        "RDS_IDLE",
        "TASK-P3-008",
        ("amazonrds/fake-product-b/0001",),
        "FINDING",
        "Zero connections for the last 47 days after a year of use. Snapshot and delete.",
    ),
    Planted(
        "CACHE_OVERSIZED",
        "TASK-P3-008",
        ("amazonelasticache/fake-product-a/0001",),
        "FINDING",
        "cache.r6g.xlarge at about 15 percent memory. Downsize node type.",
    ),
    Planted(
        "EBS_UNATTACHED",
        "TASK-P3-008",
        ("amazonebs/fake-platform-b/0001",),
        "FINDING",
        "500 GiB gp2 detached 140 days. Publishes no metrics at all; the finding is in "
        "configuration.",
    ),
    Planted(
        "EBS_GP2_TO_GP3",
        "TASK-P3-008",
        ("amazonebs/fake-platform-b/0002",),
        "FINDING",
        "1000 GiB gp2 attached and busy. Same performance on gp3 for less.",
    ),
    Planted(
        "EBS_OVERSIZED",
        "TASK-P3-008",
        ("amazonebs/fake-product-b/0001",),
        "FINDING",
        "1000 GiB volume about 7 percent used for two years.",
    ),
    Planted(
        "SNAPSHOT_ORPHANED",
        "TASK-P3-008",
        ("amazonebs/fake-platform-b/snap-0001",),
        "FINDING",
        "410 days old, source volume no longer exists.",
    ),
    Planted(
        "ALB_IDLE",
        "TASK-P3-008",
        ("elasticloadbalancing/fake-product-a/0002",),
        "FINDING",
        "No requests for 63 days and no targets.",
    ),
    Planted(
        "EIP_UNASSOCIATED",
        "TASK-P3-008",
        ("amazonvpc/fake-product-a/eip-0001",),
        "FINDING",
        "Allocated, associated with nothing.",
    ),
    Planted(
        "NAT_IDLE",
        "TASK-P3-008",
        ("amazonvpc/fake-product-b/nat-0001",),
        "FINDING",
        "Dev NAT gateway moving tens of MiB an hour. The hourly charge dominates.",
    ),
    # ---------------------------------------------------------- P3 CloudWatch
    Planted(
        "LOG_GROUP_NO_RETENTION",
        "TASK-P3-009",
        ("amazoncloudwatch/fake-platform-a/lg-0002",),
        "FINDING",
        "Never expire, 2.6 TiB stored, high ingest.",
    ),
    Planted(
        "LOG_GROUP_UNQUERIED_90D",
        "TASK-P3-009",
        ("amazoncloudwatch/fake-platform-b/lg-0001",),
        "FINDING",
        "High ingest, last queried 118 days ago. Real detector reads P2 evidence, see "
        "DATA_DICTIONARY.",
    ),
    Planted(
        "LOG_GROUP_DUPLICATE_DELIVERY",
        "TASK-P3-009",
        ("amazoncloudwatch/fake-platform-b/lg-0002",),
        "FINDING",
        "Receives the same stream as /batch/risk/raw and has never been queried.",
    ),
    Planted(
        "CUSTOM_METRIC_UNQUERIED",
        "TASK-P3-009",
        ("amazoncloudwatch/fake-platform-b/metric-0001",),
        "FINDING",
        "Published for 300 days, never read.",
    ),
    Planted(
        "ALARM_INSUFFICIENT_DATA_30D",
        "TASK-P3-009",
        ("amazoncloudwatch/fake-platform-a/alarm-0001",),
        "FINDING",
        "Insufficient data for 41 days.",
    ),
    Planted(
        "ALARM_INSUFFICIENT_DATA_1H",
        "TASK-P3-009",
        ("amazoncloudwatch/fake-platform-a/alarm-0002",),
        "NO_FINDING",
        "Insufficient data for one hour. Not a finding.",
    ),
    # -------------------------------------------------------------- pressure
    Planted(
        "EC2_OVER_UTILIZED",
        "rightsizing, upward",
        ("amazonec2/fake-product-a/0003",),
        "PRESSURE",
        "c6i.2xlarge at p95 above 90 percent CPU. Upsize or scale out.",
    ),
    Planted(
        "EBS_NEAR_FULL",
        "rightsizing, upward",
        ("amazonebs/fake-product-a/0001",),
        "PRESSURE",
        "Index volume fills from 64 to 91 percent over two years.",
    ),
    Planted(
        "CACHE_MEMORY_PRESSURE",
        "rightsizing, upward",
        ("amazonelasticache/fake-product-a/0002",),
        "PRESSURE",
        "cache.t4g.small climbing past 94 percent memory, with evictions once it does.",
    ),
    Planted(
        "MSK_DISK_NEAR_FULL",
        "rightsizing, upward",
        ("amazonmsk/fake-platform-a/0001",),
        "PRESSURE",
        "Broker data disk fills from 42 to 86 percent.",
    ),
    Planted(
        "RDS_STORAGE_GROWING",
        "rightsizing, upward",
        ("amazonrds/fake-platform-a/0001",),
        "PRESSURE",
        "Core ledger storage from 44 to 76 percent used. Healthy today, trending.",
    ),
    # -------------------------------------------------------------------- P6
    Planted(
        "CONTAINER_OVER_REQUESTED_5X",
        "TASK-P6-005",
        (
            "container/platform-eks/ledger/ledger-api",
            "container/platform-eks/ledger/ledger-projector",
        ),
        "FINDING",
        "Namespace ledger requests about five times what it uses.",
    ),
    Planted(
        "CONTAINER_NAMESPACE_RIGHT_SIZED",
        "TASK-P6-005",
        (
            "container/platform-eks/channels/web-bff",
            "container/platform-eks/channels/notifications",
        ),
        "NO_FINDING",
        "Namespace channels is sized correctly. A detector that flags everything fails here.",
    ),
    Planted(
        "CONTAINER_RIGHT_SIZED",
        "TASK-P6-005",
        ("container/platform-eks/payments/payments-api",),
        "NO_FINDING",
        "Requests close to p99 use with sensible headroom.",
    ),
    Planted(
        "CONTAINER_OOM_KILLED",
        "TASK-P6-007",
        ("container/platform-eks/payments/payments-worker",),
        "FINDING",
        "OOM killed on quarter end and peak retail days. Memory at peak plus 25 percent.",
    ),
    Planted(
        "CONTAINER_OOM_UNOBSERVED",
        "TASK-P6-007",
        ("container/batch-eks/risk/recon-batch",),
        "UNOBSERVED",
        "Cluster without enhanced observability. The 15 percent rule applies and the "
        "rationale must say the OOM check could not be made.",
    ),
    Planted(
        "CONTAINER_REQUEST_UNAVAILABLE",
        "TASK-P6-004",
        ("container/batch-eks/risk/risk-batch",),
        "UNOBSERVED",
        "Use is readable, request is not. Reported as unavailable, never as zero.",
    ),
    Planted(
        "FARGATE_OVERSIZED",
        "TASK-P6-008",
        ("container/product-ecs/default/statements-renderer",),
        "FINDING",
        "4 vCPU and 16 GiB using about 0.3 vCPU and 1.3 GiB. Snaps up to a valid combination.",
    ),
    Planted(
        "FARGATE_MEMORY_OVERSIZED",
        "TASK-P6-008",
        ("container/product-ecs/default/webhook-relay",),
        "FINDING",
        "1 vCPU and 8 GiB using 0.2 vCPU and under 1 GiB.",
    ),
    Planted(
        "FARGATE_RIGHT_SIZED",
        "TASK-P6-008",
        ("container/product-ecs/default/kyc-document-ocr",),
        "NO_FINDING",
        "Close to its task size at peak.",
    ),
    # -------------------------------------------------------------------- P4
    Planted(
        "TOPOLOGY_REGION_REFUSES",
        "P4 rule 2",
        ("fake-region-c",),
        "COVERAGE",
        "Every slice in the region is PARTIAL with NotOptedIn. Every consumer must refuse to "
        "score there.",
    ),
    Planted(
        "TOPOLOGY_DENIED_ACCOUNT",
        "TASK-P4-011",
        ("fake-product-denied",),
        "COVERAGE",
        "PARTIAL with AccessDenied in both readable regions.",
    ),
    Planted(
        "TOPOLOGY_UNREAD_SLICE",
        "TASK-P4-005",
        ("fake-product-b/eu-fake-1",),
        "COVERAGE",
        "Enrolled and never attempted. UNREAD, not PARTIAL, not COMPLETE.",
    ),
    Planted(
        "TOPOLOGY_EXTERIOR_ONLY_NODE",
        "P4 rule 1",
        ("amazonvpc/fake-product-denied/us-fake-1/vpc",),
        "COVERAGE",
        "Known only from the Transit Gateway attachment. Its interior is unknown, not empty.",
    ),
    Planted(
        "TOPOLOGY_SELF_REFERENCE_CYCLE",
        "TASK-P4-007",
        ("amazonvpc/fake-platform-a/us-fake-1/sg-cluster",),
        "COVERAGE",
        "A security group referencing itself, beside a two group cycle. Traversal must terminate.",
    ),
    Planted(
        "TOPOLOGY_CROSS_ACCOUNT_EDGES",
        "TASK-P4-004",
        ("amazonvpc/fake-platform-a/us-fake-1/tgw",),
        "COVERAGE",
        "Transit Gateway attachments, PrivateLink and an IAM trust cross account boundaries.",
    ),
    # -------------------------------------------------------------------- P5
    Planted(
        "QUOTA_NEAR_LIMIT",
        "TASK-P5-006",
        ("fake-platform-b/L-34B43A08",),
        "PRESSURE",
        "Spot vCPU reaches about 95 percent of its limit at every quarter end, when the batch "
        "cluster "
        "scales out, and sits near 40 percent between. A request for more is CASE_OPENED.",
    ),
    Planted(
        "QUOTA_SPIKE_NEAR_LIMIT",
        "TASK-P5-006",
        ("fake-product-a/L-1216C47A",),
        "PRESSURE",
        "On-Demand vCPU reaches about 96 percent of its limit on cur.spike_day, the day the bill "
        "spikes. "
        "The cost anomaly and the quota headroom are the same event.",
    ),
    Planted(
        "QUOTA_INCREASE_APPROVED",
        "TASK-P5-008",
        ("fake-platform-a/L-1216C47A", "fake-request-0001"),
        "COVERAGE",
        "Ran at about 92 percent of its limit through the year end peak, an increase was "
        "requested outside Meter and APPROVED. The limit history shows the step.",
    ),
    Planted(
        "QUOTA_CURRENTLY_TIGHT",
        "TASK-P5-006",
        ("fake-product-a/L-3032A538",),
        "PRESSURE",
        "Fargate vCPU at about half its limit now and above 90 percent at year end, "
        "with a PENDING request for more.",
    ),
    Planted(
        "QUOTA_HELD_BY_IDLE_RESOURCE",
        "TASK-P5-006",
        ("fake-product-b/L-1216C47A", "amazonec2/fake-product-b/0002"),
        "PRESSURE",
        "The untagged account sits at about 94 percent of its On-Demand vCPU limit, and 16 of "
        "those "
        "vCPU are the idle poc-ml-box. Acting on EC2_IDLE frees the headroom. Not planted on "
        "purpose: "
        "it fell out of deriving the quota from the estate, which is the argument for deriving it.",
    ),
    Planted(
        "QUOTA_LOW_USE",
        "TASK-P5-006",
        ("fake-platform-a/L-1194D53C",),
        "NO_FINDING",
        "One EKS cluster of one hundred. Visually distinct from the one near its limit.",
    ),
    Planted(
        "QUOTA_UNMEASURABLE",
        "TASK-P5-004",
        ("*/NONE",),
        "UNOBSERVED",
        "Eight of eighteen quotas per slice have no usage source. Listed separately, never zero.",
    ),
    Planted(
        "QUOTA_TRUSTED_ADVISOR_ONLY",
        "OPEN-03",
        ("fake-product-a/L-53DA6B97",),
        "UNOBSERVED",
        "Measurable in platform accounts with Business support, unmeasurable in product accounts.",
    ),
    Planted(
        "QUOTA_SOURCE_LOST",
        "TASK-P5-004",
        ("fake-product-b/L-B99A9384",),
        "UNOBSERVED",
        "Lambda concurrency stops publishing 20 days before `at`. Null and source NONE from then.",
    ),
    Planted(
        "QUOTA_REQUEST_DENIED",
        "TASK-P5-008",
        ("fake-request-0002",),
        "COVERAGE",
        "A DENIED request, the status a product is tempted to hide.",
    ),
    Planted(
        "QUOTA_REQUEST_UNMEASURABLE_TRACKED",
        "TASK-P5-008",
        ("fake-request-0005",),
        "COVERAGE",
        "A request for a quota Meter cannot measure in that account, tracked anyway.",
    ),
    # ----------------------------------------------------------- estate wide
    Planted(
        "DENIED_ACCOUNT_REFUSES_READS",
        "TASK-P0-021",
        ("fake-product-denied",),
        "REFUSE",
        "On the bill, readable nowhere else. Every reader raises AccessDenied.",
    ),
    Planted(
        "REGION_C_REFUSES_READS",
        "P4 rule 2",
        ("fake-region-c",),
        "REFUSE",
        "Every reader raises NotOptedIn.",
    ),
)

BY_CODE = {p.code: p for p in PLANTED}
