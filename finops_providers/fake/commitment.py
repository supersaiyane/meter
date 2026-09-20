"""Commitments over the fake estate, in memory.

Every figure here is derived from `finops_providers.fake.cur.ESTATE` rather than
written down, so a commitment can never claim to cover more than the fake bill
actually contains. A hand written `eligible_spend` would have drifted the first
time a service or an account weight changed, and the drift would have shown up as
a coverage percentage nobody could reconcile against the spend screen.

The four commitments are chosen to make the screen's one hard distinction
unavoidable.

`fake-sp-compute` is fully utilized and covers under a third of eligible compute:
the commitment is correctly sized and the estate is under committed, which is a
buy signal. `fake-ri-rds` covers almost all of its service and is under utilized:
the last purchase was too large, and the money is already gone. Reading either
number alone gives the opposite answer to reading both, which is the whole reason
utilization and coverage are separate figures.

`fake-sp-expired` ended inside the window. It is reported, not dropped, because
the coverage gap its expiry leaves is the finding. `fake-sp-queued` has not
started, so it has committed nothing: its utilization is None rather than zero,
because zero would say the whole commitment was wasted.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TypedDict
from uuid import UUID

from finops_core.domain.cost import (
    ACTIVE,
    BY_SERVICE,
    EXPIRED,
    QUEUED,
    CommitmentCoverage,
    CommitmentUse,
    CostRecord,
)
from finops_core.errors import CollectionError, NoData
from finops_providers.fake import cur, fixtures

COLLECTOR = "commitment"

SAVINGS_PLAN = "SavingsPlan"
RESERVED_INSTANCE = "ReservedInstance"

#: What a compute Savings Plan is eligible to cover. Lambda belongs here as well
#: as EC2, which is why coverage is per service and not per plan: one plan covers
#: two services and neither service knows which plan covered it.
COMPUTE_SERVICES = ("AmazonEC2", "AWSLambda")

#: What a database reservation covers.
DATABASE_SERVICES = ("AmazonRDS",)


class _Common(TypedDict):
    """The three fields every fact carries, so `**common` type checks.

    A plain dict widens to `dict[str, object]` and the entities take a datetime and
    a UUID, so unpacking one is an error mypy is right to raise.
    """

    as_of: datetime
    collected_at: datetime
    tenant_id: UUID


CENTS = Decimal("0.01")

#: Estates already built, keyed by the clock they were built at.
_BILLS: dict[datetime, tuple[CostRecord, ...]] = {}


def _money(amount: Decimal) -> Decimal:
    return amount.quantize(CENTS, rounding=ROUND_HALF_UP)


def _bill(at: datetime) -> tuple[CostRecord, ...]:
    """The estate as it stands at `at`, built once per clock.

    **Not `cur.ESTATE`, and this is the bug that reached a seeded database.** The
    module level constant is built at `fixtures.AS_OF`, so its periods are June to
    August 2026. A demo seeded in September asks for September, finds nothing, and
    every commitment reports a committed, used and wasted of zero. The screen then
    says the estate has four commitments obliging nothing, which is a sentence about
    a fixture rather than about anything real, and every test missed it because they
    all asked for an August window where the constant happened to be right.

    Cached because `coverages` calls `uses`, and rebuilding two thousand rows five
    times per request is a cost a fake has no business imposing.
    """
    if at not in _BILLS:
        _BILLS[at] = cur.estate(at=at)
    return _BILLS[at]


def _spend_on(services: Iterable[str], period: date, at: datetime) -> Decimal:
    """What the fake estate actually billed for these services in the period.

    Summed from the same rows the cost screens read, so a coverage percentage on the
    commitments screen and a service total on the spend screen are two views of one
    number rather than two numbers that happen to be close.
    """
    wanted = frozenset(services)
    return sum(
        (
            row.effective_cost
            for row in _bill(at)
            if row.billing_period_start == period and row.service_name in wanted
        ),
        Decimal("0"),
    )


def _period_containing(window_start: date) -> date:
    return date(window_start.year, window_start.month, 1)


def uses(
    window_start: date, window_end: date, *, at: datetime = fixtures.AS_OF
) -> tuple[CommitmentUse, ...]:
    """The four commitments, sized against the estate in this window."""
    period = _period_containing(window_start)
    compute = _spend_on(COMPUTE_SERVICES, period, at)
    database = _spend_on(DATABASE_SERVICES, period, at)

    # Fully utilized and under committed. Thirty percent of eligible compute, all
    # of it consumed, so utilization is one and coverage is under a third.
    live_committed = _money(compute * Decimal("0.30"))

    # The expired plan was live for part of the window and covered a little more.
    expired_committed = _money(compute * Decimal("0.08"))

    # Over bought. Ninety percent of the database spend committed and under two
    # thirds of it consumed, so the waste is real money and the coverage looks
    # healthy while the purchase was a mistake.
    database_committed = _money(database * Decimal("0.90"))
    database_used = _money(database_committed * Decimal("0.62"))

    common: _Common = {"as_of": at, "collected_at": at, "tenant_id": fixtures.TENANT_ID}

    return (
        CommitmentUse(
            **common,
            commitment_id="fake-sp-compute",
            commitment_type=SAVINGS_PLAN,
            status=ACTIVE,
            term_start=date(2026, 1, 1),
            term_end=date(2027, 1, 1),
            window_start=window_start,
            window_end=window_end,
            committed=live_committed,
            used=live_committed,
            wasted=Decimal("0.00"),
        ),
        CommitmentUse(
            **common,
            commitment_id="fake-ri-rds",
            commitment_type=RESERVED_INSTANCE,
            status=ACTIVE,
            term_start=date(2026, 3, 1),
            term_end=date(2027, 3, 1),
            window_start=window_start,
            window_end=window_end,
            committed=database_committed,
            used=database_used,
            wasted=database_committed - database_used,
        ),
        CommitmentUse(
            **common,
            commitment_id="fake-sp-expired",
            commitment_type=SAVINGS_PLAN,
            status=EXPIRED,
            term_start=date(2025, 8, 1),
            # Inside the window on purpose. A commitment that ended mid period is
            # the case a collector is most likely to drop, and the gap it leaves
            # is exactly what somebody needs to be told about.
            term_end=date(window_start.year, window_start.month, 15),
            window_start=window_start,
            window_end=window_end,
            committed=expired_committed,
            used=expired_committed,
            wasted=Decimal("0.00"),
        ),
        CommitmentUse(
            **common,
            commitment_id="fake-sp-queued",
            commitment_type=SAVINGS_PLAN,
            status=QUEUED,
            # Starts after the window ends, so it obliged nothing inside it.
            term_start=window_end,
            term_end=date(window_end.year + 1, window_end.month, window_end.day),
            window_start=window_start,
            window_end=window_end,
            committed=Decimal("0.00"),
            used=Decimal("0.00"),
            wasted=Decimal("0.00"),
        ),
    )


def coverages(
    window_start: date, window_end: date, *, at: datetime = fixtures.AS_OF
) -> tuple[CommitmentCoverage, ...]:
    """Coverage per service, derived from what the commitments actually consumed.

    Built from `uses` rather than beside it. Two independently written sets of
    numbers would eventually disagree, and a covered total larger than the
    commitments that produced it is the sort of inconsistency a reader spots
    immediately and cannot explain.
    """
    period = _period_containing(window_start)
    live = {use.commitment_id: use for use in uses(window_start, window_end, at=at)}
    common: _Common = {"as_of": at, "collected_at": at, "tenant_id": fixtures.TENANT_ID}

    compute_covered = live["fake-sp-compute"].used + live["fake-sp-expired"].used
    database_covered = live["fake-ri-rds"].used

    return (
        CommitmentCoverage(
            **common,
            commitment_type=SAVINGS_PLAN,
            dimension=BY_SERVICE,
            dimension_value="AmazonEC2",
            window_start=window_start,
            window_end=window_end,
            eligible_spend=_spend_on(("AmazonEC2",), period, at),
            covered_spend=compute_covered,
        ),
        CommitmentCoverage(
            **common,
            commitment_type=SAVINGS_PLAN,
            dimension=BY_SERVICE,
            dimension_value="AWSLambda",
            window_start=window_start,
            window_end=window_end,
            eligible_spend=_spend_on(("AWSLambda",), period, at),
            # The compute plan's consumption all landed on EC2, so Lambda is
            # eligible and entirely uncovered. Zero is the right answer here and
            # says buy, which is different from the None a service with no
            # eligible spend at all would produce.
            covered_spend=Decimal("0.00"),
        ),
        CommitmentCoverage(
            **common,
            commitment_type=RESERVED_INSTANCE,
            dimension=BY_SERVICE,
            dimension_value="AmazonRDS",
            window_start=window_start,
            window_end=window_end,
            eligible_spend=_spend_on(DATABASE_SERVICES, period, at),
            covered_spend=database_covered,
        ),
    )


class FakeCommitmentReport:
    """`CommitmentReport` in memory. Every failure is asked for, never incidental."""

    def __init__(
        self,
        failure: type[CollectionError] | None = None,
        *,
        holds_nothing: bool = False,
        at: datetime = fixtures.AS_OF,
    ) -> None:
        self._failure = failure
        self._holds_nothing = holds_nothing
        self._at = at

    def _fail_if_planned(self) -> None:
        if self._failure is not None:
            raise self._failure(
                scope_key=fixtures.ORGANIZATION_SCOPE,
                collector=COLLECTOR,
                detail="planned by the fake commitment report",
            )

    def utilization(self, window_start: date, window_end: date) -> Iterable[CommitmentUse]:
        self._fail_if_planned()
        if self._holds_nothing:
            # A payer with no commitments at all. Typed, because an empty list and
            # a failed read look identical to a screen and mean opposite things.
            raise NoData(
                scope_key=fixtures.ORGANIZATION_SCOPE,
                collector=COLLECTOR,
                detail="this payer holds no commitments",
            )
        return uses(window_start, window_end, at=self._at)

    def coverage(self, window_start: date, window_end: date) -> Iterable[CommitmentCoverage]:
        self._fail_if_planned()
        if self._holds_nothing:
            raise NoData(
                scope_key=fixtures.ORGANIZATION_SCOPE,
                collector=COLLECTOR,
                detail="nothing in the window was eligible for a commitment",
            )
        return coverages(window_start, window_end, at=self._at)
