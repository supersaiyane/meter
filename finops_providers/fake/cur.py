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
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType

from finops_core.domain.cost import CostRecord, source_fingerprint
from finops_core.errors import CollectionError, NoData
from finops_providers.fake import fixtures

COLLECTOR = "cost_focus"

#: June, July and August 2026. August is open at `fixtures.AS_OF`, which is
#: 2026-08-24, so it holds a part month and the other two are whole.
OLDEST_PERIOD = date(2026, 6, 1)
CLOSED_PERIOD = date(2026, 7, 1)
OPEN_PERIOD = date(2026, 8, 1)

#: A daily rate per account per service, in dollars. Every service is a
#: different size, because a ranking of equal numbers tells a reader nothing
#: and the screen's whole claim is that the top row is worth reading first.
SERVICES: Mapping[str, Decimal] = {
    "AmazonEC2": Decimal("40.00"),
    "AmazonRDS": Decimal("18.00"),
    "AmazonCloudWatch": Decimal("9.10"),
    "AmazonS3": Decimal("6.00"),
    "AWSLambda": Decimal("2.50"),
}

#: Which services report a resource. Storage and per request services bill in
#: aggregate at this granularity, and a row with no `resource_id` is a fact
#: about the bill rather than a gap in it.
NAMES_A_RESOURCE = frozenset({"AmazonEC2", "AmazonRDS"})

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


def _row(*, account: str, service: str, day: date, period: date, drift: Decimal) -> CostRecord:
    charge_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    charge_end = charge_start + timedelta(days=1)
    resource = f"{service.lower()}/{account}/0001" if service in NAMES_A_RESOURCE else None
    effective = (SERVICES[service] * ACCOUNT_WEIGHT[account] * drift).quantize(Decimal("0.0001"))
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
        service_category="Compute" if service in NAMES_A_RESOURCE else "Storage",
        resource_id=resource,
        resource_name=resource,
        region_id=fixtures.REGION,
        availability_zone=None,
        charge_category="Usage",
        charge_description=f"{service} usage",
        sku_id=None,
        pricing_quantity=Decimal("1"),
        consumed_quantity=Decimal("1"),
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


def estate(*, at: datetime = fixtures.AS_OF) -> tuple[CostRecord, ...]:
    """Three months of bill, the newest of them still running."""
    rows: list[CostRecord] = []
    for period in (OLDEST_PERIOD, CLOSED_PERIOD, OPEN_PERIOD):
        for index, day in enumerate(_days_in(period, at=at)):
            # A slow rise, so a trend is a trend rather than one number drawn
            # thirty times. Deterministic, so it is the same rise every run.
            drift = Decimal(1) + (Decimal(index) / Decimal(200))
            for account in fixtures.ACCOUNT_IDS:
                for service in SERVICES:
                    rows.append(
                        _row(account=account, service=service, day=day, period=period, drift=drift)
                    )
    return tuple(rows)


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
