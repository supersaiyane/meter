"""A bill for the fake estate, in FOCUS 1.4's mandatory columns.

The four row fixture in `fixtures.py` proves the port and cannot exercise a
screen: one service, one period, every row tagged, every cost a dollar. A
ranking of identical numbers is a list, an allocation view with nothing
unallocated is a view that never renders the row that matters, and a whole
month with no part month beside it never makes anybody label the open period.

So this estate carries the states the cost screens exist to tell apart, and it
is deliberately no easier than reality in the places that matter: real
fingerprints, `Decimal` money, two timestamps, and the account Meter cannot
assume a role into still appearing on the bill, because the bill comes from the
payer and not from the member account.

Nothing here is random. A fake whose numbers move between runs cannot be
asserted against, and this project has already been caught by a green test that
measured nothing.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType

from finops_core.domain.ai import CACHE_READ, CACHE_WRITE, INPUT, OUTPUT
from finops_core.domain.cost import CostRecord, source_fingerprint
from finops_core.errors import CollectionError, NoData
from finops_fakes import containers, fixtures, prices, utilization

COLLECTOR = "cost_focus"

#: June, July and August 2026. August is open at `fixtures.AS_OF`, which is
#: 2026-08-24, so it holds a part month and the other two are whole.
OLDEST_PERIOD = date(2026, 6, 1)
CLOSED_PERIOD = date(2026, 7, 1)
OPEN_PERIOD = date(2026, 8, 1)

#: Services that bill in aggregate, with a daily rate per account in dollars. These
#: two have no resources in the utilization estate and would not name one in a real
#: bill at this granularity either: a row with no `resource_id` is a fact about the
#: bill rather than a gap in it. Different sizes, because a ranking of equal numbers
#: tells a reader nothing.
AGGREGATE_SERVICES: Mapping[str, Decimal] = {
    "AmazonS3": Decimal("6.00"),
    "AWSLambda": Decimal("2.50"),
}

#: Every service the utilization estate names a resource under, derived from the
#: estate rather than listed. Until 2026-09-21 this was a hand written list of five
#: services and the bill named `{service}/{account}/0001` and nothing else, so of
#: the estate's 36 resources exactly two per account appeared on the bill. Every
#: consumer that joins a charge to a resource, which is FEAT-029 and FEAT-035, found
#: nothing for the other 26. `DATA_DICTIONARY.md` decision 6.
RESOURCE_SERVICES: tuple[str, ...] = tuple(sorted(set(utilization.SERVICE_BY_PREFIX.values())))

#: Every service on the bill. The aggregate ones and the estate's, in one place, so
#: a caller iterating services cannot see half of them.
SERVICES: tuple[str, ...] = tuple(sorted({*AGGREGATE_SERVICES, *RESOURCE_SERVICES}))

#: Which services report a resource. Derived, so adding a kind to the estate adds it
#: to the bill rather than adding it to one and not the other.
NAMES_A_RESOURCE = frozenset(RESOURCE_SERVICES)

#: The share of the estate each account carries. Not equal, so `by-account`
#: ranks as well.
ACCOUNT_WEIGHT: Mapping[str, Decimal] = {
    "fake-platform-a": Decimal("1.00"),
    "fake-platform-b": Decimal("0.62"),
    "fake-product-a": Decimal("0.41"),
    # Untagged throughout, which is what fills the unallocated bucket.
    "fake-product-b": Decimal("0.28"),
    # Meter cannot assume a role into this one and it is on the bill anyway.
    "fake-product-denied": Decimal("0.15"),
}

#: Who owns what, where anybody said. `fake-product-b` is absent on purpose.
OWNERS: Mapping[str, str] = {
    "fake-platform-a": "platform",
    "fake-platform-b": "platform",
    "fake-product-a": "product",
    "fake-product-denied": "product",
}


#: The one day in the estate that does not look like the days before it, and the
#: pair it happens to. TASK-P1-019.
#:
#: **It is a multiplier on a real day, not a row inserted into a table.** That is
#: the whole point of putting it here. A demo that writes a row straight into
#: `cost_anomaly` proves nothing: the screen would show a finding the detector never
#: made, and the first question anybody asks in a demo is whether the product found
#: it or somebody typed it. This way `make seed` writes an estate, the detector reads
#: it, and the row on the screen is a verdict.
#:
#: Sized to clear the detector's own bar rather than guessed at. The baseline is a
#: slow drift around one, so six times it is far outside three median absolute
#: deviations and far above the dollar floor, and it stays that way if either
#: setting is tuned.
SPIKE_ACCOUNT = "fake-product-a"
SPIKE_SERVICE = "AmazonEC2"
SPIKE_MULTIPLIER = Decimal("6")

#: The spike sits on the last day the estate bills, and it has to.
#:
#: `CostAnomalyCollector` judges one day, the most recent with data, because re
#: judging history every run would rewrite verdicts somebody may already have acted
#: on. A spike anywhere earlier would be part of the baseline by the time the detector
#: looked, and a median baseline does not move for one outlier, so the estate would
#: read as well behaved and the screen would be empty.
#:
#: That is a real property of the detector rather than a fixture convenience, and it
#: is worth stating here because it is the thing somebody will trip over: a database
#: seeded once holds verdicts for one day only. In production the collector has run
#: every day and has a verdict for each. A demo that wants a history of findings needs
#: the seed to run the detector once per day of history, which is ISS-186.
SPIKE_DAYS_BACK = 0


@dataclass(frozen=True)
class Landed:
    """A change somebody made, and what it did to the bill afterwards.

    Declared here and read by the demo seeder, so the bill and the recommendation
    that claims credit for it cannot disagree about when the work happened. Before
    this existed the seeder wrote three resources of its own with hand written
    charges, because no estate resource had a charge to compare, which meant the one
    screen that proves the product works was reading a fixture written for it.

    `days_ago` is when the change landed, counted back from `at`. `cost_factor` and
    `usage_factor` are what the resource bills and consumes from that day onward,
    relative to before. The pair is the whole point: cost alone cannot tell a saving
    from a workload that shrank, so a fixture that only moved cost could not produce
    an INCONCLUSIVE verdict and the third of FEAT-029's three verdicts would never be
    exercised.
    """

    resource_id: str
    waste_class: str
    days_ago: int
    cost_factor: Decimal
    usage_factor: Decimal
    why: str


#: How long ago every seeded change landed. Sixty days, because the realized savings
#: collector compares the thirty days before a change to the thirty days ending sixty
#: days after it, and a change any more recent has no complete after window.
LANDED_DAYS_AGO = 60

#: Three changes, one per verdict, on three resources the estate actually runs and
#: the planted findings actually name. The verdicts are not written down anywhere: the
#: collector reads these charges and reaches them, which is what makes the savings
#: screen show a measurement rather than a claim.
LANDED: tuple[Landed, ...] = (
    Landed(
        resource_id="amazonebs/fake-platform-b/0001",
        waste_class="EBS_UNATTACHED",
        days_ago=LANDED_DAYS_AGO,
        # Deleted, so both the charge and the provisioned GiB go to nothing. The
        # boundary case `finops_query.realized` is explicit about: an equal fall in
        # both is VERIFIED, because a resource that no longer exists is a saving
        # nobody can argue with, and calling it unprovable would make the metric
        # useless on the findings it is most certain about.
        cost_factor=Decimal("0"),
        usage_factor=Decimal("0"),
        why="a 500 GiB gp2 volume attached to nothing for 140 days, deleted",
    ),
    Landed(
        resource_id="elasticloadbalancing/fake-product-a/0002",
        waste_class="LOAD_BALANCER_IDLE",
        days_ago=LANDED_DAYS_AGO,
        # Marked done and the bill never moved. The most important row on the savings
        # screen, because it is the one that says the work did not happen.
        cost_factor=Decimal("1"),
        usage_factor=Decimal("1"),
        why="a load balancer with no targets, marked done and still running",
    ),
    Landed(
        resource_id="amazonvpc/fake-product-b/nat-0001",
        waste_class="NAT_GATEWAY_IDLE",
        days_ago=LANDED_DAYS_AGO,
        # Cost down sixty percent and the traffic down ninety. The fall cannot be
        # told apart from the workload behind it going away, and saying so rather
        # than claiming the saving is the whole of FEAT-029's third verdict.
        cost_factor=Decimal("0.40"),
        usage_factor=Decimal("0.10"),
        why="a gateway removed in the same week the service behind it was retired",
    ),
)

#: The landed changes by resource, so the row builder can ask in constant time.
_LANDED_BY_RESOURCE: Mapping[str, Landed] = MappingProxyType(
    {change.resource_id: change for change in LANDED}
)


def landed_on(at: datetime = fixtures.AS_OF) -> date:
    """The day every seeded change landed, derived from the clock like `spike_day`."""
    return at.date() - timedelta(days=LANDED_DAYS_AGO)


def _after_the_change(resource: str | None, day: date, at: datetime) -> tuple[Decimal, Decimal]:
    """The cost and usage multipliers for one resource on one day.

    Both are one before the change landed and before any change was recorded, so a
    resource nobody touched bills exactly as it did.
    """
    change = _LANDED_BY_RESOURCE.get(resource or "")
    if change is None or day < landed_on(at):
        return Decimal("1"), Decimal("1")
    return change.cost_factor, change.usage_factor


def _period_end(start: date) -> date:
    """The exclusive end of a monthly period, per `BillingPeriod`."""
    return date(start.year + (start.month // 12), (start.month % 12) + 1, 1)


def _days_in(period: date, *, at: datetime) -> tuple[date, ...]:
    """Every day the period has actually billed by `at`.

    A period still running has billed up to yesterday, which is what makes it
    shorter than a closed one and is the whole reason the open period label
    exists.
    """
    end = min(_period_end(period), at.date())
    return tuple(period + timedelta(days=offset) for offset in range((end - period).days))


def _tags(account: str, service: str) -> Mapping[str, str]:
    """What the estate managed to tag.

    Two holes, both realistic. One account nobody tagged at all, and CloudWatch
    everywhere, because log groups and metrics are created by tooling that was
    not thinking about allocation.
    """
    if account not in OWNERS or service == "AmazonCloudWatch":
        return MappingProxyType({})
    return MappingProxyType({"team": OWNERS[account], "finops:module": "fixture"})


#: The FOCUS service category per service. Written down rather than inferred from
#: whether a service names a resource, which was the old rule and put storage and
#: compute in one bucket the moment the bill learned about volumes.
CATEGORY: Mapping[str, str] = MappingProxyType(
    {
        "AmazonEC2": "Compute",
        "AmazonRDS": "Databases",
        "AmazonElastiCache": "Databases",
        "AmazonMSK": "Analytics",
        "AmazonEBS": "Storage",
        "AmazonS3": "Storage",
        "AWSLambda": "Compute",
        "AmazonVPC": "Networking",
        "ElasticLoadBalancing": "Networking",
        "AmazonCloudWatch": "Management and Governance",
    }
)


def _category(service: str) -> str:
    """The FOCUS category, or a failure naming the service.

    Raising rather than defaulting, because a service in an unexpected category is a
    row that groups under a heading no screen renders, and an absent heading is not
    something a reader notices.
    """
    if service not in CATEGORY:
        raise ValueError(f"{service} has no FOCUS service category")
    return CATEGORY[service]


def _row(
    *,
    account: str,
    service: str,
    day: date,
    period: date,
    drift: Decimal,
    resource: str | None,
    daily_usd: Decimal,
    at: datetime,
    usage_type: str | None = None,
) -> CostRecord:
    """One line item. The caller decides what it is about and what it costs.

    `resource` and `daily_usd` arrive from outside rather than being derived here,
    because the two kinds of line come from different places: a resource line is
    priced from the estate's own configuration through `prices.py`, and an aggregate
    line is a rate per account per service. Deriving both here meant the bill could
    only ever name `{service}/{account}/0001`, which is the join gap this closes.
    """
    charge_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    charge_end = charge_start + timedelta(days=1)
    # A change that landed moves both, and they move by different amounts on purpose.
    # Cost alone cannot tell a saving from a workload that shrank, so a bill whose
    # usage never moved could not produce an inconclusive verdict and the third of
    # FEAT-029's three verdicts would never be exercised by anything.
    cost_factor, usage_factor = _after_the_change(resource, day, at)
    effective = (daily_usd * drift * cost_factor).quantize(Decimal("0.0001"))
    # One unit a day before any change, which is what every existing row carried.
    consumed = (Decimal("1") * usage_factor).quantize(Decimal("0.0001"))
    # Closed once the month after it has begun, which is when the fake payer is invoiced.
    invoiced = period < date(at.year, at.month, 1)
    return CostRecord(
        tenant_id=fixtures.TENANT_ID,
        ingest_run_id=fixtures.INGEST_RUN_ID,
        source_fingerprint=source_fingerprint(
            billing_account_id=fixtures.ACCOUNT_IDS[0],
            sub_account_id=account,
            charge_period_start=charge_start,
            charge_period_end=charge_end,
            service_name=service,
            resource_id=resource,
            sku_id=None,
            charge_category="Usage",
            commitment_discount_id=None,
        ),
        as_of=charge_end,
        collected_at=fixtures.COLLECTED_AT,
        billing_account_id=fixtures.ACCOUNT_IDS[0],
        sub_account_id=account,
        billing_period_start=period,
        billing_period_end=_period_end(period),
        charge_period_start=charge_start,
        charge_period_end=charge_end,
        provider_name="Fake",
        publisher_name="Fake",
        invoice_issuer_name="Fake",
        service_name=service,
        service_category=_category(service),
        resource_id=resource,
        resource_name=resource,
        region_id=fixtures.REGION,
        availability_zone=None,
        charge_category="Usage",
        charge_description=f"{service} usage",
        sku_id=None,
        pricing_quantity=consumed,
        consumed_quantity=consumed,
        consumed_unit="Hrs",
        # Billed and effective differ, so a screen that renders one under the
        # other's label is wrong here rather than accidentally right.
        billed_cost=(effective * Decimal("1.08")).quantize(Decimal("0.0001")),
        effective_cost=effective,
        list_cost=(effective * Decimal("1.25")).quantize(Decimal("0.0001")),
        contracted_cost=None,
        commitment_discount_id=None,
        commitment_discount_type=None,
        commitment_discount_status=None,
        tags=_tags(account, service),
        billing_account_name="Fake payer",
        billing_currency=CURRENCY,
        pricing_unit="Hrs",
        invoice_id=invoice_id_for(period) if invoiced else None,
        x_usage_type=usage_type,
    )


#: The currency the fake estate is billed in. TASK-P10-002 and P10-003.
CURRENCY = "USD"


def invoice_id_for(period: date) -> str:
    """The invoice a closed period's rows carry. An open period has none, as AWS leaves the
    invoice id blank until it issues one, so its rows carry None and the period reads as open."""
    return f"fake-invoice-{period:%Y-%m}"


def periods_ending_at(at: datetime, count: int = 3) -> tuple[date, ...]:
    """The month containing `at` and the ones before it, oldest first.

    Derived rather than listed, so an estate built at a different clock is
    current at that clock. The constants above describe the estate at
    `fixtures.AS_OF` and are what every test asserting a fixed value uses, but a
    demo seeded next March wants next March's months, not these. A fixture
    pinned to a date stops being an open period the day that month ends, and
    then the screen that labels open periods has nothing to label.
    """
    cursor = date(at.year, at.month, 1)
    months: list[date] = []
    for _ in range(count):
        months.append(cursor)
        cursor = (
            date(cursor.year - 1, 12, 1)
            if cursor.month == 1
            else date(cursor.year, cursor.month - 1, 1)
        )
    return tuple(reversed(months))


def spike_day(at: datetime = fixtures.AS_OF) -> date:
    """The day the estate goes wrong, derived from the clock rather than written down.

    Named so a test and the demo runbook can both point at it without either one
    hardcoding a date that stops being inside the estate next month.
    """
    return at.date() - timedelta(days=SPIKE_DAYS_BACK + 1)


#: The drift the newest day carries, and how fast it falls going back in time. One
#: point one five at the clock, one at ninety days before it: the same range the old
#: per month sawtooth covered, so the level of every figure stays where it was while the
#: shape becomes a rise rather than thirty little ones.
DRIFT_CEILING = Decimal("1.15")
DRIFT_DIVISOR = Decimal("600")


def estate(
    *, at: datetime = fixtures.AS_OF, spike: bool = True, periods: int = 3
) -> tuple[CostRecord, ...]:
    """A bill, the newest period of it still running at `at`.

    One line per resource for the services the utilization estate names, priced from
    that resource's own configuration, and one line per account for the services
    that bill in aggregate. Before 2026-09-21 every service billed in aggregate and
    named `{service}/{account}/0001`, so a consumer joining a charge to a resource
    found nothing for all but two resources per account.

    `periods` is three by default, which is what every existing figure was computed
    against. A caller that needs to look further back asks for more: the realized
    savings collector compares a window ending sixty days after a change to one
    ending before it, which is ninety days of history and does not fit in three
    calendar months with any margin.

    `spike` is on by default, and a caller turning it off gets an estate where every
    pair is well behaved. That is only useful for asserting the detector finds nothing
    in a quiet estate, which is the other half of proving it works.
    """
    wrong_day = spike_day(at)
    rows: list[CostRecord] = []
    for period in periods_ending_at(at, periods):
        for day in _days_in(period, at=at):
            # A slow rise, so a trend is a trend rather than one number drawn thirty
            # times. Deterministic, so it is the same rise every run.
            #
            # Anchored to the estate's own clock and monotonic across months. It used
            # to be indexed by the day of the month, so it reset to the bottom on every
            # first: a sawtooth rather than a rise. An untouched resource's thirty day
            # cost then depended on where in the month its windows fell, and the planted
            # load balancer, whose bill is meant never to move, read as a saving and was
            # VERIFIED instead of REGRESSED on any date where the after window landed on
            # cheaper early month days. ISS-222. The range is the old one, one to one
            # point one five across the ninety days before the clock, so no figure moves
            # by more than the old sawtooth already moved it.
            drift = DRIFT_CEILING + (Decimal((day - at.date()).days) / DRIFT_DIVISOR)
            for account in fixtures.ACCOUNT_IDS:
                for service in SERVICES:
                    # One pair, one day, several times the usual. Applied to the
                    # drift so the row is built the same way as every other row and
                    # carries the same fingerprint shape: a spike that arrived
                    # through a different code path would be a spike the ingest
                    # never has to handle. It multiplies every line of the pair,
                    # resource lines included, because a real spike is a service
                    # costing more rather than one resource appearing.
                    wrong = (
                        spike
                        and day == wrong_day
                        and account == SPIKE_ACCOUNT
                        and service == SPIKE_SERVICE
                    )
                    rows.extend(
                        _lines(
                            account=account,
                            service=service,
                            day=day,
                            period=period,
                            drift=drift * SPIKE_MULTIPLIER if wrong else drift,
                            at=at,
                        )
                    )
    return tuple(rows)


def _usage_type(service: str, spec: utilization.Spec) -> str | None:
    """An EC2 instance's hours on demand, as the price list and the Savings Plans rates name them.

    TASK-P14-007. Meter's purchase plan prices the bill's usage by its usage type, and the fake
    catalog prices every type the estate runs under `BoxUsage:<type>`, so the demo's plan is priced
    from the same rates the catalog screens show.
    """
    instance = spec.config.get("instance_type") if service == "AmazonEC2" else None
    return f"BoxUsage:{instance}" if isinstance(instance, str) else None


def _lines(
    *, account: str, service: str, day: date, period: date, drift: Decimal, at: datetime
) -> tuple[CostRecord, ...]:
    """Every line one account owes for one service on one day.

    One per resource where the estate has them, priced from the resource's own
    configuration so the bill and the sizing estimate agree about what a thing costs.
    Otherwise one aggregate line, which is what an account with no resources of that
    service owes and is not the same as owing nothing: `fake-product-denied` is on
    the bill because the bill comes from the payer, and it runs nothing the
    utilization estate models.
    """
    specs = utilization.specs_for(account, service) if service in NAMES_A_RESOURCE else ()
    if specs:
        return tuple(
            _row(
                account=account,
                service=service,
                day=day,
                period=period,
                drift=drift,
                resource=spec.resource_id,
                daily_usd=prices.daily_usd(spec),
                at=at,
                usage_type=_usage_type(service, spec),
            )
            for spec in specs
        )

    rate = AGGREGATE_SERVICES.get(service)
    if rate is None:
        # A service the estate names resources under, for an account that runs none
        # of them. No line at all, because inventing an aggregate charge for a
        # service this account does not use would put spend on a screen that nothing
        # in the estate explains.
        return ()
    return (
        _row(
            account=account,
            service=service,
            day=day,
            period=period,
            drift=drift,
            resource=None,
            daily_usd=rate * ACCOUNT_WEIGHT[account],
            at=at,
        ),
    )


#: What share of a cluster's node cost lands on pods rather than on the gap between
#: what pods asked for and what the nodes provide. Derived per cluster from the
#: workloads' own requests below, not written down; this is only the ceiling, so a
#: perfectly packed cluster still leaves something in `unused_cost`.
PACKABLE = Decimal("0.92")


def split_rows(base: Iterable[CostRecord]) -> tuple[CostRecord, ...]:
    """Split cost allocation lines, re-attributing node cost to the pods on it.

    **These carry no money of their own.** `billed_cost` and `effective_cost` are
    zero and the figure lives in `split_cost`, which is how AWS writes a split line
    item and the only shape that cannot double count: the node's charge is already
    on the bill, and these say who was using it. A fake that put the cost in both
    places would make every container screen reconcile against a doubled total and
    the error would look like a rounding problem.

    The parent charge is not invented either. Every cluster's node groups name
    resources the cost estate already prices, so the amount being split is the
    amount actually on the fake bill for those instances, and the reconciliation
    test can assert against the rows rather than against a constant.

    ECS is absent on purpose: the columns are `eks_*` because split cost allocation
    is an EKS feature, and `product-ecs` is there for Fargate task sizing instead.
    """
    by_day: dict[tuple[str, date], Decimal] = {}
    for row in base:
        if row.resource_id is None:
            continue
        by_day[(row.resource_id, row.charge_period_start.date())] = row.effective_cost

    out: list[CostRecord] = []
    for cluster in containers.CLUSTERS:
        if cluster.platform != "EKS":
            continue
        workloads = containers.workloads_in(cluster.name)
        if not workloads:
            continue
        # Weight by what each workload reserves, because that is what split cost
        # allocation apportions by: a pod is charged for its request, not its use.
        weights = {w: Decimal(w.cpu_request_m) * Decimal(w.replicas) for w in workloads}
        total_weight = sum(weights.values())
        if total_weight <= 0:
            continue

        days = sorted(
            {
                day
                for group in cluster.node_groups
                for (resource, day) in by_day
                if resource == group.resource_id
            }
        )
        for day in days:
            parent = sum(
                by_day.get((group.resource_id, day), Decimal(0)) for group in cluster.node_groups
            )
            if parent <= 0:
                continue
            allocatable = (parent * PACKABLE).quantize(Decimal("0.0001"))
            spent = Decimal(0)
            for workload in workloads:
                share = (allocatable * weights[workload] / total_weight).quantize(Decimal("0.0001"))
                spent += share
                out.append(
                    _split_line(
                        cluster=cluster,
                        workload=workload,
                        day=day,
                        split_cost=share,
                        unused_cost=None,
                    )
                )
            # The remainder, on a line with no workload at all. This is the row a
            # constraint requiring a dimension beside a measure would have refused,
            # and it is the row that makes the cluster add up.
            out.append(
                _split_line(
                    cluster=cluster,
                    workload=None,
                    day=day,
                    split_cost=None,
                    unused_cost=parent - spent,
                )
            )
    return tuple(out)


def _split_line(
    *,
    cluster: containers.Cluster,
    workload: containers.Workload | None,
    day: date,
    split_cost: Decimal | None,
    unused_cost: Decimal | None,
) -> CostRecord:
    """One split line item: zero money of its own, and a grain the parent lacks."""
    charge_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    charge_end = charge_start + timedelta(days=1)
    period = date(day.year, day.month, 1)
    # A pod's share joins to the workload the container estate models. The
    # remainder gets a cluster level identity of its own rather than borrowing a
    # node's: a split line is a breakdown of a charge, and inside the cost series of
    # the instance it breaks down it would be read as part of that instance's bill by
    # anything that reads per resource.
    #
    # On 2026-10-01 this comment claimed the borrowed identity had flipped a realized
    # savings verdict. It had not. The flip reproduces on main, which has no split
    # lines at all, and its cause was the per month drift sawtooth, ISS-222. The
    # reason above stands on its own; the evidence once offered for it was wrong.
    resource = workload.key if workload else f"container/{cluster.name}/unallocated"
    return CostRecord(
        tenant_id=fixtures.TENANT_ID,
        ingest_run_id=fixtures.INGEST_RUN_ID,
        source_fingerprint=source_fingerprint(
            billing_account_id=fixtures.ACCOUNT_IDS[0],
            sub_account_id=cluster.account_id,
            charge_period_start=charge_start,
            charge_period_end=charge_end,
            service_name="AmazonEKS",
            resource_id=resource,
            sku_id=None,
            charge_category="Usage",
            commitment_discount_id=None,
        ),
        as_of=charge_end,
        collected_at=fixtures.COLLECTED_AT,
        billing_account_id=fixtures.ACCOUNT_IDS[0],
        sub_account_id=cluster.account_id,
        billing_period_start=period,
        billing_period_end=_period_end(period),
        charge_period_start=charge_start,
        charge_period_end=charge_end,
        provider_name="Fake",
        publisher_name="Fake",
        invoice_issuer_name="Fake",
        service_name="AmazonEKS",
        service_category="Compute",
        resource_id=resource,
        resource_name=resource,
        region_id=cluster.region_id,
        availability_zone=None,
        charge_category="Usage",
        charge_description="split cost allocation",
        sku_id=None,
        pricing_quantity=None,
        consumed_quantity=None,
        consumed_unit=None,
        # Zero, and this is the whole point. See the docstring.
        billed_cost=Decimal("0.0000"),
        effective_cost=Decimal("0.0000"),
        list_cost=None,
        contracted_cost=None,
        commitment_discount_id=None,
        commitment_discount_type=None,
        commitment_discount_status=None,
        tags={},
        eks_cluster_name=cluster.name,
        eks_namespace=workload.namespace if workload else None,
        eks_workload_name=workload.name if workload else None,
        eks_workload_type=workload.kind if workload else None,
        eks_pod_name=f"{workload.name}-0" if workload else None,
        split_cost=split_cost,
        split_usage=None,
        split_usage_ratio=None,
        unused_cost=unused_cost,
    )


ESTATE: tuple[CostRecord, ...] = estate()

#: The split cost allocation half of the bill, and **not** part of `ESTATE`.
#:
#: Opt in, so every P1 and P3 fixture reads exactly the bill it read before P6 existed
#: and a caller that wants the container grain asks for it with
#: `FakeCostExport(split=True)`. Without it an export carries none of these columns,
#: which is also the ISS-003 case: split cost allocation was never switched on.
#:
#: Corrected on 2026-10-04. This comment used to say that folding these rows into
#: `ESTATE` had flipped a realized savings verdict from REGRESSED to VERIFIED. That
#: was a misattribution: the flip reproduces on main without a single split line, and
#: was the drift sawtooth recorded as ISS-222. Opt in is still the better default for
#: the reason above, but nothing was ever shown to break when these rows were in.
SPLIT_LINES: tuple[CostRecord, ...] = split_rows(ESTATE)


#: Bedrock's half of the bill, P13, TASK-P13-002, and like the split lines **not** part of
#: `ESTATE`: opt in with `FakeCostExport(ai=True)`, so every earlier fixture reads the bill it
#: always read. Each feature is one account's application calling one model every day, billed
#: per token type in the usage type form AWS documents, `<Region>-<model>-input-tokens`.
#:
#: `support-assistant` calls through an application inference profile, so its lines name the
#: profile as the resource; `search-summaries` calls the model directly, so its lines name none,
#: which is the case a feature can then only be told apart by its tag and its principal.
@dataclass(frozen=True, kw_only=True)
class BedrockFeature:
    account: str
    feature: str
    model: str
    profile: bool
    #: Tokens a day by token type, before the drift every line of the estate carries.
    tokens: Mapping[str, Decimal]


#: USD per token by model and token type. The fake's, shaped like a price list rather than
#: copied from one, so no figure here is mistaken for a real price.
BEDROCK_PRICE: Mapping[str, Mapping[str, Decimal]] = MappingProxyType(
    {
        "ClaudeSonnet4": MappingProxyType(
            {
                "input-tokens": Decimal("0.000003"),
                "output-tokens": Decimal("0.000015"),
                "cache-read-input-token-count": Decimal("0.0000003"),
            }
        ),
        "NovaPro": MappingProxyType(
            {"input-tokens": Decimal("0.0000008"), "output-tokens": Decimal("0.0000032")}
        ),
    }
)

BEDROCK_FEATURES: tuple[BedrockFeature, ...] = (
    BedrockFeature(
        account="fake-platform-a",
        feature="support-assistant",
        model="ClaudeSonnet4",
        profile=True,
        tokens=MappingProxyType(
            {
                "input-tokens": Decimal("1200000"),
                "output-tokens": Decimal("240000"),
                "cache-read-input-token-count": Decimal("3000000"),
            }
        ),
    ),
    BedrockFeature(
        account="fake-product-a",
        feature="search-summaries",
        model="NovaPro",
        profile=False,
        tokens=MappingProxyType(
            {"input-tokens": Decimal("4000000"), "output-tokens": Decimal("600000")}
        ),
    ),
)

BEDROCK_SERVICE = "AmazonBedrock"
#: What each usage type suffix means, as the AWS adapter reads it, written down here rather than
#: imported so the fake estate depends on nothing but the domain.
BEDROCK_TOKEN_TYPE: Mapping[str, str] = MappingProxyType(
    {
        "input-tokens": INPUT,
        "output-tokens": OUTPUT,
        "cache-read-input-token-count": CACHE_READ,
        "cache-write-input-token-count": CACHE_WRITE,
    }
)
#: The Region code the fake's usage types start with, for `fixtures.REGION`.
BEDROCK_REGION_CODE = "USF1"


def bedrock_principal(feature: BedrockFeature) -> str:
    """The IAM principal the bill names for a feature's calls: its service's role."""
    return f"arn:aws:iam::{feature.account}:role/{feature.feature}-service"


def bedrock_profile(feature: BedrockFeature) -> str | None:
    """The application inference profile a feature calls through, or None if it calls direct."""
    if not feature.profile:
        return None
    return (
        f"arn:aws:bedrock:{fixtures.REGION}:{feature.account}:"
        f"application-inference-profile/{feature.feature}"
    )


def bedrock_rows(base: Iterable[CostRecord]) -> tuple[CostRecord, ...]:
    """Every feature's token lines, on every day the given bill has a line for.

    Derived from the bill being exported, as the split lines are, so the AI half always covers
    the same days and periods as the rest of whatever bill it joins.
    """
    days = sorted({(row.billing_period_start, row.charge_period_start) for row in base})
    out: list[CostRecord] = []
    for period, start in days:
        drift = DRIFT_CEILING + Decimal((start.date() - fixtures.AS_OF.date()).days) / DRIFT_DIVISOR
        for feature in BEDROCK_FEATURES:
            for suffix, daily in feature.tokens.items():
                out.append(_bedrock_line(feature, suffix, daily * drift, period, start))
    return tuple(out)


def _bedrock_line(
    feature: BedrockFeature, suffix: str, tokens: Decimal, period: date, start: datetime
) -> CostRecord:
    end = start + timedelta(days=1)
    usage_type = f"{BEDROCK_REGION_CODE}-{feature.model}-{suffix}"
    quantity = tokens.quantize(Decimal("1"))
    effective = (quantity * BEDROCK_PRICE[feature.model][suffix]).quantize(Decimal("0.0001"))
    resource = bedrock_profile(feature)
    tags = dict(_tags(feature.account, BEDROCK_SERVICE))
    tags["feature"] = feature.feature
    return CostRecord(
        tenant_id=fixtures.TENANT_ID,
        ingest_run_id=fixtures.INGEST_RUN_ID,
        source_fingerprint=source_fingerprint(
            billing_account_id=fixtures.ACCOUNT_IDS[0],
            sub_account_id=feature.account,
            charge_period_start=start,
            charge_period_end=end,
            service_name=BEDROCK_SERVICE,
            resource_id=resource,
            sku_id=usage_type,
            charge_category="Usage",
            commitment_discount_id=None,
        ),
        as_of=end,
        collected_at=fixtures.COLLECTED_AT,
        billing_account_id=fixtures.ACCOUNT_IDS[0],
        sub_account_id=feature.account,
        billing_period_start=period,
        billing_period_end=_period_end(period),
        charge_period_start=start,
        charge_period_end=end,
        provider_name="Fake",
        publisher_name="Fake",
        invoice_issuer_name="Fake",
        service_name=BEDROCK_SERVICE,
        service_category="AI and Machine Learning",
        resource_id=resource,
        resource_name=feature.feature if resource else None,
        region_id=fixtures.REGION,
        availability_zone=None,
        charge_category="Usage",
        charge_description=f"{feature.model} {suffix}",
        sku_id=usage_type,
        pricing_quantity=quantity,
        consumed_quantity=quantity,
        consumed_unit="Tokens",
        billed_cost=effective,
        effective_cost=effective,
        list_cost=effective,
        contracted_cost=None,
        commitment_discount_id=None,
        commitment_discount_type=None,
        commitment_discount_status=None,
        tags=tags,
        billing_account_name="Fake payer",
        billing_currency=CURRENCY,
        pricing_unit="Tokens",
        x_usage_type=usage_type,
        x_iam_principal=bedrock_principal(feature),
        x_ai_model=feature.model,
        x_ai_token_type=BEDROCK_TOKEN_TYPE[suffix],
        x_ai_tokens=quantity,
    )


#: The GPU half of the AI bill, TASK-P13-006, opt in with the Bedrock lines. Two accelerated
#: instances in one account: a small one running all day, and a large one six hours a day whose
#: agent publishes nothing, so the screen shows one measured and one not published.
@dataclass(frozen=True, kw_only=True)
class GpuInstance:
    account: str
    instance_id: str
    instance_type: str
    hours: Decimal
    #: USD an hour, the fake's, shaped like a price rather than copied from one.
    hourly: Decimal


GPU_INSTANCES: tuple[GpuInstance, ...] = (
    GpuInstance(
        account="fake-platform-a",
        instance_id="i-fakegpu0001",
        instance_type="g5.xlarge",
        hours=Decimal("24"),
        hourly=Decimal("1.006"),
    ),
    GpuInstance(
        account="fake-platform-a",
        instance_id="i-fakegpu0002",
        instance_type="p4d.24xlarge",
        hours=Decimal("6"),
        hourly=Decimal("32.77"),
    ),
)


def with_ai(base: tuple[CostRecord, ...]) -> tuple[CostRecord, ...]:
    """A bill with its Bedrock and GPU lines, P13.

    One definition, because the cost rows and the invoices of the same estate have to be built
    from the same bill, or the reconciliation reports a difference the fake invented.
    """
    return (*base, *bedrock_rows(base), *gpu_rows(base))


def gpu_rows(base: Iterable[CostRecord]) -> tuple[CostRecord, ...]:
    """Each GPU instance's hours, on every day the given bill has a line for."""
    days = sorted({(row.billing_period_start, row.charge_period_start) for row in base})
    out: list[CostRecord] = []
    for period, start in days:
        for gpu in GPU_INSTANCES:
            end = start + timedelta(days=1)
            usage_type = f"{BEDROCK_REGION_CODE}-BoxUsage:{gpu.instance_type}"
            cost = (gpu.hours * gpu.hourly).quantize(Decimal("0.0001"))
            out.append(
                CostRecord(
                    tenant_id=fixtures.TENANT_ID,
                    ingest_run_id=fixtures.INGEST_RUN_ID,
                    source_fingerprint=source_fingerprint(
                        billing_account_id=fixtures.ACCOUNT_IDS[0],
                        sub_account_id=gpu.account,
                        charge_period_start=start,
                        charge_period_end=end,
                        service_name="AmazonEC2",
                        resource_id=gpu.instance_id,
                        sku_id=usage_type,
                        charge_category="Usage",
                        commitment_discount_id=None,
                    ),
                    as_of=end,
                    collected_at=fixtures.COLLECTED_AT,
                    billing_account_id=fixtures.ACCOUNT_IDS[0],
                    sub_account_id=gpu.account,
                    billing_period_start=period,
                    billing_period_end=_period_end(period),
                    charge_period_start=start,
                    charge_period_end=end,
                    provider_name="Fake",
                    publisher_name="Fake",
                    invoice_issuer_name="Fake",
                    service_name="AmazonEC2",
                    service_category="Compute",
                    resource_id=gpu.instance_id,
                    resource_name=gpu.instance_id,
                    region_id=fixtures.REGION,
                    availability_zone=None,
                    charge_category="Usage",
                    charge_description=f"{gpu.instance_type} on demand",
                    sku_id=usage_type,
                    pricing_quantity=gpu.hours,
                    consumed_quantity=gpu.hours,
                    consumed_unit="Hrs",
                    billed_cost=cost,
                    effective_cost=cost,
                    list_cost=cost,
                    contracted_cost=None,
                    commitment_discount_id=None,
                    commitment_discount_type=None,
                    commitment_discount_status=None,
                    tags=dict(_tags(gpu.account, "AmazonEC2")),
                    billing_account_name="Fake payer",
                    billing_currency=CURRENCY,
                    pricing_unit="Hrs",
                    x_usage_type=usage_type,
                )
            )
    return tuple(out)


#: The line item AWS retracts when the closed period is restated, and the one
#: it corrects. Named so a test can assert on them rather than on a position in
#: a list that changes the moment a service is added.
_CLOSED = tuple(row for row in ESTATE if row.billing_period_start == CLOSED_PERIOD)
RETRACTED_FINGERPRINT = _CLOSED[0].source_fingerprint
CORRECTED_FINGERPRINT = _CLOSED[-1].source_fingerprint


def restate(rows: Iterable[CostRecord]) -> tuple[CostRecord, ...]:
    """The same bill after AWS restated it: one row corrected, one retracted.

    Both happen in a real restatement and they are not the same operation. A
    correction is an upsert. A retraction is the only destructive thing the
    ingest path does, and TASK-P1-005 has to be able to tell it from a read
    that failed half way.
    """
    out: list[CostRecord] = []
    for row in rows:
        if row.source_fingerprint == RETRACTED_FINGERPRINT:
            continue
        if row.source_fingerprint == CORRECTED_FINGERPRINT:
            corrected = row.effective_cost * Decimal("1.5")
            out.append(
                CostRecord(
                    **{
                        **row.__dict__,
                        "effective_cost": corrected.quantize(Decimal("0.0001")),
                    }
                )
            )
            continue
        out.append(row)
    return tuple(out)


class FakeCostExport:
    """`CostExport` in memory. Every failure is asked for, never incidental."""

    def __init__(
        self,
        rows: tuple[CostRecord, ...] | None = None,
        failure: type[CollectionError] | None = None,
        restated: bool = False,
        split: bool = False,
        ai: bool = False,
    ) -> None:
        base = ESTATE if rows is None else rows
        if ai:
            # Opt in, as the split lines are, and derived from the same bill so its days match.
            base = with_ai(base)
        if split:
            # Derived from the rows actually being exported, so the split lines always
            # re-attribute charges this bill really carries, whatever clock it was built
            # at. Filtering the module's pinned `SPLIT_LINES` instead found nothing for
            # a bill built at the real clock, which is every bill `make seed` builds, so
            # the demo would have shown clusters with no cost at all.
            base = (*base, *split_rows(base))
        self._rows = restate(base) if restated else base
        self._failure = failure
        self._split = split

    def _fail_if_planned(self) -> None:
        if self._failure is not None:
            raise self._failure(
                scope_key=fixtures.ORGANIZATION_SCOPE,
                collector=COLLECTOR,
                detail="planned by the fake cost export",
            )

    @property
    def split_cost_available(self) -> bool:
        """Whether this export carries the container grain, ISS-003 as a flag.

        A property on the export rather than something derived from the rows,
        because an estate with split cost allocation enabled and no clusters in it
        looks identical from the rows alone, and reporting that as a configuration
        gap would send somebody to fix a setting that is already right.
        """
        return self._split and any(row.eks_cluster_name for row in self._rows)

    def latest_available_period(self) -> date | None:
        self._fail_if_planned()
        if not self._rows:
            # The export exists and has published nothing, which the port
            # separates from an export that is missing. A caller that collapsed
            # the two would report a configuration fault as an empty bill.
            return None
        return max(row.billing_period_start for row in self._rows)

    def read_period(self, period_start: date, period_end: date) -> Iterable[CostRecord]:
        self._fail_if_planned()
        rows = tuple(
            row
            for row in self._rows
            if row.billing_period_start >= period_start and row.billing_period_end <= period_end
        )
        if not rows:
            raise NoData(
                scope_key=fixtures.ORGANIZATION_SCOPE,
                collector=COLLECTOR,
                detail=f"the estate holds no rows between {period_start} and {period_end}",
            )
        return rows
