"""A bill for the fake estate, in FOCUS 1.1.

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

from finops_core.domain.cost import CostRecord, source_fingerprint
from finops_core.errors import CollectionError, NoData
from finops_fakes import fixtures, prices, utilization

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
    )


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
        for index, day in enumerate(_days_in(period, at=at)):
            # A slow rise, so a trend is a trend rather than one number drawn thirty
            # times. Deterministic, so it is the same rise every run.
            drift = Decimal(1) + (Decimal(index) / Decimal(200))
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


ESTATE: tuple[CostRecord, ...] = estate()

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
    ) -> None:
        base = ESTATE if rows is None else rows
        self._rows = restate(base) if restated else base
        self._failure = failure

    def _fail_if_planned(self) -> None:
        if self._failure is not None:
            raise self._failure(
                scope_key=fixtures.ORGANIZATION_SCOPE,
                collector=COLLECTOR,
                detail="planned by the fake cost export",
            )

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
