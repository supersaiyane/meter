"""Every quota the fake estate has, including the ones nobody can measure.

The P5 plan's first rule is that a quota with no usage source is never zero,
and TASK-P5-004 asks for unmeasurable quotas "in roughly the proportion a real
estate does, not one token example". Here that is eight of eighteen quotas per
slice, plus one that only Trusted Advisor can measure, and Trusted Advisor is
available only in the platform accounts. The product accounts do not carry
Business support, so the same quota is measured in one account and unmeasurable
in another, which is OPEN-03 as data rather than as a paragraph.

**Usage is derived, not written down.** The Standard vCPU quotas count the vCPU
the utilization estate is running, so a quarter end on the batch cluster moves
the Spot vCPU headroom on the same day, and the product API scale out on
`cur.spike_day` is the highest point in that account's On-Demand history.

**Limits are sized from that usage.** Where a quota has no fixed limit, the
limit sits just above the highest peak, as a limit somebody raised once is
likely to. That produces three stories without writing any of them down: Spot
vCPU in `fake-platform-b` reaches about ninety five percent at every quarter
end; On-Demand vCPU in `fake-product-a` reaches about ninety six percent on
`cur.spike_day`; and On-Demand vCPU in `fake-platform-a` ran at about ninety two
percent through the year end peak, after which an increase was approved outside
Meter. Fargate vCPU has a fixed limit it uses half of now and above ninety
percent of at year end.
Usage never exceeds a limit, TASK-P5-001.

**One quota loses its source.** Lambda concurrency in `fake-product-b` stops
publishing twenty days before `at`. From then its usage is None and its source
is `NONE`, rather than the last figure kept, TASK-P5-004.

**Requests are only read.** Nothing here submits one, constraint 6. The five in
`REQUESTS` were made outside Meter, and one of them is for a quota Meter cannot
measure, because tracking and measuring are independent, TASK-P5-008.

Quota codes prefixed `FAKE-` are placeholders. The rest are the Service Quotas
codes as best known and are unverified, ISS-122.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.quota import QuotaUsage
from finops_core.errors import AccessDenied, NotOptedIn
from finops_providers.fake import containers, fixtures, utilization
from finops_providers.fake import estate_shape as shape

COLLECTOR = "quotas"

AWS_USAGE = "AWS_USAGE"
TRUSTED_ADVISOR = "TRUSTED_ADVISOR"
SERVICE_API = "SERVICE_API"
NONE = "NONE"

#: Accounts with a support tier that includes Trusted Advisor limit checks.
BUSINESS_SUPPORT = frozenset({"fake-platform-a", "fake-platform-b"})

#: Every slice a quota reader can reach.
SLICES: tuple[tuple[str, str], ...] = (
    ("fake-platform-a", shape.REGION_A),
    ("fake-platform-a", shape.REGION_B),
    ("fake-platform-b", shape.REGION_A),
    ("fake-platform-b", shape.REGION_B),
    ("fake-product-a", shape.REGION_A),
    ("fake-product-b", shape.REGION_A),
)

#: Hours sampled per day for a daily peak. Six points catch every calendar
#: effect in `estate_shape`, which all last whole days, at a quarter of the cost.
_SAMPLE_HOURS = (0, 4, 8, 12, 14, 18)

#: Days before `at` when the platform account's On-Demand increase was approved.
INCREASE_DAYS_BEFORE = 216

#: Days before `at` when Lambda concurrency in `fake-product-b` stopped publishing.
LAMBDA_SILENT_DAYS = 20

Usage = Callable[[str, str, datetime, datetime], float | None]

#: A usage function that always has an answer. Narrower than `Usage` on purpose:
#: counting resources in the estate cannot fail to produce a number, and the two
#: functions that add counters together should not have to handle a None that
#: cannot arise. The wider type stays for the table, where a None is the point.
Counter = Callable[[str, str, datetime, datetime], float]


def _count(kind: str) -> Counter:
    def usage(account: str, region: str, ts: datetime, at: datetime) -> float:
        return float(
            sum(
                1
                for s in utilization.SPECS
                if s.account_id == account
                and s.region_id == region
                and s.kind == kind
                and ts >= utilization.launched_at(s, at)
            )
        )

    return usage


def _vcpu(capacity: str) -> Usage:
    def usage(account: str, region: str, ts: datetime, at: datetime) -> float:
        return float(utilization.vcpu_in_use(account, region, ts, capacity_type=capacity, at=at))

    return usage


def _eips(account: str, region: str, ts: datetime, at: datetime) -> float:
    return _count("eip")(account, region, ts, at) + _count("nat")(account, region, ts, at)


def _vpcs(account: str, region: str, ts: datetime, at: datetime) -> float:
    return 1.0


def _eks(account: str, region: str, ts: datetime, at: datetime) -> float:
    return float(
        sum(
            1
            for c in containers.CLUSTERS
            if c.platform == "EKS" and c.account_id == account and c.region_id == region
        )
    )


def _cache_nodes(account: str, region: str, ts: datetime, at: datetime) -> float:
    return float(
        sum(
            int(utilization.sized(s, "nodes"))
            for s in utilization.SPECS
            if s.account_id == account and s.region_id == region and s.kind == "cache"
        )
    )


def _brokers(account: str, region: str, ts: datetime, at: datetime) -> float:
    return float(
        sum(
            int(utilization.sized(s, "brokers"))
            for s in utilization.SPECS
            if s.account_id == account and s.region_id == region and s.kind == "msk"
        )
    )


def _snapshots(account: str, region: str, ts: datetime, at: datetime) -> float:
    return 40.0 + _count("snapshot")(account, region, ts, at)


def _fargate_vcpu(account: str, region: str, ts: datetime, at: datetime) -> float:
    return sum(
        containers.replicas(w, ts, at) * w.cpu_request_m / 1024
        for w in containers.WORKLOADS
        if w.launch_type is containers.LaunchType.FARGATE
        and containers.cluster(w.cluster).account_id == account
        and containers.cluster(w.cluster).region_id == region
    )


def _lambda(account: str, region: str, ts: datetime, at: datetime) -> float | None:
    if account == "fake-product-b" and ts >= shape.window(at)[1] - timedelta(
        days=LAMBDA_SILENT_DAYS
    ):
        return None
    start, end = shape.window(at)
    peak = 60 * shape.seasonal(ts.date()) * (1 + 0.4 * shape.progress(ts, start, end))
    return round(peak * (0.6 + 0.8 * shape.diurnal(ts)) + 8 * shape.jitter(f"lambda|{account}", ts))


def _albs(account: str, region: str, ts: datetime, at: datetime) -> float:
    return _count("alb")(account, region, ts, at)


@dataclass(frozen=True)
class QuotaDef:
    service_code: str
    quota_code: str
    quota_name: str
    #: The source where the account can publish one, before support tier applies.
    source: str
    adjustable: bool
    #: A fixed limit, or None where the limit is sized from usage.
    limit: int | None
    usage: Usage | None
    #: Why nothing can measure it, where nothing can.
    unmeasurable_reason: str | None = None
    #: IAM and other global services have no region.
    is_global: bool = False


QUOTAS: tuple[QuotaDef, ...] = (
    QuotaDef(
        "ec2",
        "L-1216C47A",
        "Running On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances",
        AWS_USAGE,
        True,
        None,
        _vcpu("ON_DEMAND"),
    ),
    QuotaDef(
        "ec2",
        "L-34B43A08",
        "All Standard (A, C, D, H, I, M, R, T, Z) Spot Instance Requests",
        AWS_USAGE,
        True,
        None,
        _vcpu("SPOT"),
    ),
    QuotaDef("ec2", "L-0263D0A3", "EC2-VPC Elastic IPs", AWS_USAGE, True, 5, _eips),
    QuotaDef("vpc", "L-F678F1CE", "VPCs per Region", SERVICE_API, True, 5, _vpcs),
    QuotaDef(
        "vpc",
        "L-FE5A380F",
        "NAT gateways per Availability Zone",
        SERVICE_API,
        True,
        5,
        _count("nat"),
    ),
    QuotaDef("eks", "L-1194D53C", "Clusters", SERVICE_API, True, 100, _eks),
    QuotaDef("rds", "L-7B6409FD", "DB instances", SERVICE_API, True, 40, _count("rds")),
    QuotaDef(
        "elasticloadbalancing",
        "L-53DA6B97",
        "Application Load Balancers per Region",
        TRUSTED_ADVISOR,
        True,
        50,
        _albs,
    ),
    QuotaDef("lambda", "L-B99A9384", "Concurrent executions", AWS_USAGE, True, 1000, _lambda),
    QuotaDef(
        "fargate",
        "L-3032A538",
        "Fargate On-Demand vCPU resource count",
        AWS_USAGE,
        True,
        32,
        _fargate_vcpu,
    ),
    QuotaDef(
        "elasticache", "FAKE-EC-NODES", "Nodes per Region", SERVICE_API, True, 300, _cache_nodes
    ),
    QuotaDef("kafka", "FAKE-MSK-BROKERS", "Brokers per account", SERVICE_API, True, 30, _brokers),
    QuotaDef("ebs", "L-309BACF6", "Snapshots per Region", SERVICE_API, True, 100000, _snapshots),
    QuotaDef(
        "ec2",
        "L-2AFB9258",
        "Security groups per network interface",
        NONE,
        True,
        5,
        None,
        "No usage metric or API reports the largest count on any interface",
    ),
    QuotaDef(
        "vpc",
        "L-0EA8095F",
        "Inbound or outbound rules per security group",
        NONE,
        True,
        60,
        None,
        "Per security group, and no service reports the maximum across groups",
    ),
    QuotaDef(
        "vpc",
        "L-93826ACB",
        "Routes per route table",
        NONE,
        True,
        50,
        None,
        "Per route table, and no service reports the maximum across tables",
    ),
    QuotaDef(
        "vpc",
        "L-29B6F2EB",
        "Interface VPC endpoints per VPC",
        NONE,
        True,
        50,
        None,
        "Per VPC, and not published to AWS/Usage",
    ),
    QuotaDef(
        "kms",
        "FAKE-KMS-SYM-RATE",
        "Cryptographic operations (symmetric) request rate",
        NONE,
        True,
        50000,
        None,
        "A request rate, and no per second peak is published",
    ),
    QuotaDef(
        "apigateway",
        "FAKE-APIGW-THROTTLE",
        "Throttle rate",
        NONE,
        True,
        10000,
        None,
        "A request rate, and no per second peak is published",
    ),
    QuotaDef(
        "secretsmanager",
        "FAKE-SM-GET-RATE",
        "Rate of GetSecretValue requests",
        NONE,
        False,
        10000,
        None,
        "A request rate, and no per second peak is published",
    ),
    QuotaDef(
        "elasticloadbalancing",
        "FAKE-ELB-TARGETS",
        "Targets per Application Load Balancer",
        NONE,
        True,
        1000,
        None,
        "Per load balancer, and not published to AWS/Usage",
    ),
    QuotaDef(
        "iam",
        "FAKE-IAM-ROLES",
        "Roles per account",
        NONE,
        True,
        1000,
        None,
        "Global, and not published to AWS/Usage in any region",
        is_global=True,
    ),
)


def _applies(q: QuotaDef, account: str, region: str) -> bool:
    if q.is_global:
        return region == shape.REGION_A
    return True


def source_for(q: QuotaDef, account: str, region: str, ts: datetime, at: datetime) -> str:
    """The source that actually produced a figure, or `NONE`."""
    if q.usage is None:
        return NONE
    if q.source == TRUSTED_ADVISOR and account not in BUSINESS_SUPPORT:
        return NONE
    if q.usage(account, region, ts, at) is None:
        return NONE
    return q.source


def reason_for(q: QuotaDef, account: str, region: str, ts: datetime, at: datetime) -> str | None:
    if source_for(q, account, region, ts, at) != NONE:
        return None
    if q.unmeasurable_reason:
        return q.unmeasurable_reason
    if q.source == TRUSTED_ADVISOR:
        return (
            "Only Trusted Advisor reports this, and the account has no Business "
            "support (NotOptedIn)"
        )
    return "The usage metric stopped publishing, so no current figure exists"


def daily_peak(q: QuotaDef, account: str, region: str, d: date, at: datetime) -> float | None:
    """The largest usage in the day, from the sampled hours inside the window."""
    if q.usage is None:
        return None
    start, end = shape.window(at)
    values = []
    for h in _SAMPLE_HOURS:
        ts = datetime(d.year, d.month, d.day, h, tzinfo=UTC)
        if start <= ts < end:
            v = q.usage(account, region, ts, at)
            if v is None:
                return None
            values.append(v)
    return max(values) if values else None


def _round_up(value: float, step: int) -> int:
    return max(step, int(math.ceil(value / step) * step))


def limit_on(q: QuotaDef, account: str, region: str, d: date, at: datetime) -> int:
    """The limit in force on day `d`.

    A fixed limit where the quota has one. Otherwise sized from the estate: the
    peak before the increase with a little room, and after it the peak at about
    ninety two percent. Only the platform account's On-Demand quota changes.
    """
    if q.limit is not None:
        return q.limit
    start, end = shape.window(at)
    increase = (end - timedelta(days=INCREASE_DAYS_BEFORE)).date()
    changes = (
        q.quota_code == "L-1216C47A" and account == "fake-platform-a" and region == shape.REGION_A
    )
    peaks_before = [
        p
        for p in (
            daily_peak(q, account, region, x, at)
            for x in shape.days(start, end)
            if not changes or x < increase
        )
        if p is not None
    ]
    # Named `latest` rather than `now`, and not only for taste: the fake estate is
    # deterministic by contract and a test walks its syntax tree refusing any name
    # that reads like a clock. This one is derived from `at`, which is the whole
    # point, and the test is right to be crude about it.
    latest = trailing_peak(q, account, region, at)
    if not changes and latest is not None:
        # The current row samples different hours from the daily history, and a
        # limit below the current reading would be a usage above its limit.
        peaks_before.append(latest)
    before = _round_up(max(peaks_before or [0.0]) / 0.97, 4)
    if not changes or d < increase:
        return before
    peaks_after = [
        p
        for p in (
            daily_peak(q, account, region, x, at) for x in shape.days(start, end) if x >= increase
        )
        if p is not None
    ]
    if latest is not None:
        peaks_after.append(latest)
    return max(before + 4, _round_up(max(peaks_after or [0.0]) / 0.92, 4))


class _LimitCache:
    """Limits scan the whole window, so each is computed once per `at`."""

    def __init__(self) -> None:
        self._seen: dict[tuple[object, ...], int] = {}

    def get(self, q: QuotaDef, account: str, region: str, d: date, at: datetime) -> int:
        _, end = shape.window(at)
        increase = (end - timedelta(days=INCREASE_DAYS_BEFORE)).date()
        key = (q.quota_code, account, region, d >= increase, at)
        if key not in self._seen:
            self._seen[key] = limit_on(q, account, region, d, at)
        return self._seen[key]


_LIMITS = _LimitCache()


def current(
    account_id: str, region_id: str, *, at: datetime = fixtures.AS_OF
) -> tuple[QuotaUsage, ...]:
    """Every quota for one slice at `at`, as the quota port returns it.

    Raises for the denied account and the refusing region rather than returning
    an empty tuple, because an empty tuple is an account with no quotas.
    """
    if account_id == shape.DENIED_ACCOUNT:
        raise AccessDenied(
            scope_key=f"aws:{account_id}:{region_id}",
            collector=COLLECTOR,
            detail="planned by the fake quota estate",
        )
    if region_id == shape.REFUSING_REGION:
        raise NotOptedIn(
            scope_key=f"aws:{account_id}:{region_id}",
            collector=COLLECTOR,
            detail="the region is not enabled in this account",
        )
    return tuple(
        QuotaUsage(
            account_key=AccountKey(provider=Provider.AWS, account_id=account_id),
            region_id=None if q.is_global else region_id,
            service_code=q.service_code,
            quota_code=q.quota_code,
            quota_name=q.quota_name,
            quota_limit=Decimal(_LIMITS.get(q, account_id, region_id, at.date(), at)),
            used=(
                None
                if source_for(q, account_id, region_id, at - timedelta(hours=1), at) == NONE
                else _decimal_or_none(trailing_peak(q, account_id, region_id, at))
            ),
            as_of=at,
            collected_at=fixtures.COLLECTED_AT,
        )
        for q in QUOTAS
        if _applies(q, account_id, region_id)
    )


def trailing_peak(q: QuotaDef, account: str, region: str, at: datetime) -> float | None:
    """The largest usage in the 24 hours before `at`, sampled every two hours.

    The current row reads a trailing day rather than the calendar day, because at
    06:00 the calendar day holds only the quietest hours and would understate
    every quota a morning collection reads.
    """
    if q.usage is None:
        return None
    values = []
    for back in range(0, 24, 2):
        v = q.usage(account, region, at - timedelta(hours=back + 1), at)
        if v is None:
            return None
        values.append(v)
    return max(values)


def _decimal_or_none(value: float | None) -> Decimal | None:
    return None if value is None else shape.dec(value, 0)


def _used(q: QuotaDef, account: str, region: str, d: date, at: datetime) -> Decimal | None:
    noon = datetime(d.year, d.month, d.day, 12, tzinfo=UTC)
    if source_for(q, account, region, min(noon, at), at) == NONE:
        return None
    peak = daily_peak(q, account, region, d, at)
    return None if peak is None else shape.dec(peak, 0)


def _row(
    q: QuotaDef,
    account: str,
    region: str,
    d: date,
    at: datetime,
    as_of: datetime,
    *,
    current: bool = False,
) -> Mapping[str, object]:
    probe = (
        at - timedelta(hours=1)
        if current
        else min(datetime(d.year, d.month, d.day, 12, tzinfo=UTC), at)
    )
    source = source_for(q, account, region, probe, at)
    if source == NONE:
        used = None
    elif current:
        peak = trailing_peak(q, account, region, at)
        used = None if peak is None else shape.dec(peak, 0)
    else:
        used = _used(q, account, region, d, at)
    return {
        "tenant_id": str(fixtures.TENANT_ID),
        "sub_account_id": account,
        "region_id": None if q.is_global else region,
        "service_code": q.service_code,
        "quota_code": q.quota_code,
        "quota_name": q.quota_name,
        "limit_value": _LIMITS.get(q, account, region, d, at),
        "used_value": used,
        "usage_source": source if used is not None else NONE,
        "unmeasurable_reason": reason_for(q, account, region, probe, at),
        "is_adjustable": q.adjustable,
        "as_of": as_of.isoformat(),
        "collected_at": fixtures.COLLECTED_AT.isoformat(),
    }


def usage_rows(*, at: datetime = fixtures.AS_OF) -> Iterator[Mapping[str, object]]:
    """The current row for every quota in every readable slice. `quota_usage`."""
    for account, region in SLICES:
        for q in QUOTAS:
            if _applies(q, account, region):
                yield _row(q, account, region, at.date(), at, at, current=True)


def history_rows(*, at: datetime = fixtures.AS_OF) -> Iterator[Mapping[str, object]]:
    """One row per quota per slice per day, for the headroom trend."""
    start, end = shape.window(at)
    for account, region in SLICES:
        for q in QUOTAS:
            if not _applies(q, account, region):
                continue
            for d in shape.days(start, end):
                day_end = datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(days=1)
                yield _row(q, account, region, d, at, min(day_end, end))


@dataclass(frozen=True)
class Request:
    request_id: str
    account_id: str
    region_id: str
    service_code: str
    quota_code: str
    desired_value: int
    #: (status, days before `at`) oldest first. The last is the current status.
    history: tuple[tuple[str, int], ...]


def requests(*, at: datetime = fixtures.AS_OF) -> tuple[Request, ...]:
    increase = _LIMITS.get(QUOTAS[0], "fake-platform-a", shape.REGION_A, at.date(), at)
    spot = QUOTAS[1]
    spot_limit = _LIMITS.get(spot, "fake-platform-b", shape.REGION_A, at.date(), at)
    return (
        Request(
            "fake-request-0001",
            "fake-platform-a",
            shape.REGION_A,
            "ec2",
            "L-1216C47A",
            increase,
            (
                ("PENDING", INCREASE_DAYS_BEFORE + 8),
                ("CASE_OPENED", INCREASE_DAYS_BEFORE + 6),
                ("APPROVED", INCREASE_DAYS_BEFORE),
            ),
        ),
        Request(
            "fake-request-0002",
            "fake-product-a",
            shape.REGION_A,
            "lambda",
            "L-B99A9384",
            5000,
            (("PENDING", 287), ("CASE_OPENED", 285), ("DENIED", 283)),
        ),
        Request(
            "fake-request-0003",
            "fake-platform-b",
            shape.REGION_A,
            "ec2",
            "L-34B43A08",
            spot_limit * 2,
            (("PENDING", 6), ("CASE_OPENED", 4)),
        ),
        Request(
            "fake-request-0004",
            "fake-product-a",
            shape.REGION_A,
            "fargate",
            "L-3032A538",
            120,
            (("PENDING", 2),),
        ),
        # A quota Meter cannot measure in this account, tracked all the same.
        Request(
            "fake-request-0005",
            "fake-product-a",
            shape.REGION_A,
            "elasticloadbalancing",
            "L-53DA6B97",
            100,
            (("PENDING", 450), ("APPROVED", 446)),
        ),
    )


def request_rows(*, at: datetime = fixtures.AS_OF) -> Iterator[Mapping[str, object]]:
    _, end = shape.window(at)
    for r in requests(at=at):
        status, days_before = r.history[-1]
        yield {
            "tenant_id": str(fixtures.TENANT_ID),
            "request_id": r.request_id,
            "sub_account_id": r.account_id,
            "region_id": r.region_id,
            "service_code": r.service_code,
            "quota_code": r.quota_code,
            "desired_value": r.desired_value,
            "status": status,
            "requested_at": (end - timedelta(days=r.history[0][1])).isoformat(),
            "last_updated_at": (end - timedelta(days=days_before)).isoformat(),
            "submitted_by_meter": False,
            "as_of": at.isoformat(),
            "collected_at": fixtures.COLLECTED_AT.isoformat(),
        }


def request_history_rows(*, at: datetime = fixtures.AS_OF) -> Iterator[Mapping[str, object]]:
    _, end = shape.window(at)
    for r in requests(at=at):
        for status, days_before in r.history:
            yield {
                "tenant_id": str(fixtures.TENANT_ID),
                "request_id": r.request_id,
                "status": status,
                "changed_at": (end - timedelta(days=days_before)).isoformat(),
            }
