"""The commitments the fake estate holds, for the inventory and the screens that read it. FEAT-086.

TASK-P14-002. Deliberately unflattering, the way an estate is:

- `fake-platform-a` holds a Compute Savings Plan that ends in three weeks, so the renewal calendar
  has a month to warn about, an EC2 Instance Savings Plan with two years left, and four EC2
  reservations in the fake Region.
- `fake-platform-b` holds a Savings Plan that retired two months ago, which is a row, not an
  absence: its usage went back on demand the day it ended.
- `fake-product-a` holds two RDS reservations, paid all upfront, and three ElastiCache nodes.
- The account the fake estate refuses, `fixtures.DENIED_ACCOUNT_KEY`, refuses here too.

Every date is placed relative to the clock the fake is given, so a seed run on any day sees the same
shape: one commitment always about to end.

`FakePurchaseRecommendations`, TASK-P14-006, is AWS's advice about that estate: buy a Compute
Savings Plan, buy EC2 and RDS reservations, and nothing for the EC2 Instance type or any other
service, which is an answer AWS gives and the screen has to draw. Its figures are modelled.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Final
from uuid import UUID

from finops_core.domain.account import AccountKey
from finops_core.domain.commitments import (
    ACTIVE,
    ALL_UPFRONT,
    EC2,
    ELASTICACHE,
    NO_UPFRONT,
    PARTIAL_UPFRONT,
    RDS,
    RESERVATION,
    SAVINGS_PLAN,
    CommitmentPolicy,
    HeldCommitment,
    PurchaseRecommendation,
)
from finops_core.errors import AccessDenied
from finops_fakes import fixtures

COLLECTOR: Final = "commitment_inventory"
CURRENCY: Final = "USD"


@dataclass(frozen=True, kw_only=True)
class FakeHolding:
    """One commitment the fake estate holds, placed in time by days from the clock."""

    account: str
    kind: str
    commitment_id: str
    program: str
    region: str | None
    applies_to: str | None
    quantity: int | None
    hourly: Decimal | None
    term_months: int
    payment: str
    upfront: Decimal
    recurring: Decimal
    #: How many days before the clock the commitment started.
    started_days_ago: int
    state: str = ACTIVE


HOLDINGS: Final[tuple[FakeHolding, ...]] = (
    FakeHolding(
        account="fake-platform-a",
        kind=SAVINGS_PLAN,
        commitment_id="sp-fake-compute-0001",
        program="Compute",
        region=None,
        applies_to=None,
        quantity=None,
        hourly=Decimal("3.20"),
        term_months=12,
        payment=NO_UPFRONT,
        upfront=Decimal(0),
        recurring=Decimal("3.20"),
        # A year's term started 344 days ago ends in three weeks.
        started_days_ago=344,
    ),
    FakeHolding(
        account="fake-platform-a",
        kind=SAVINGS_PLAN,
        commitment_id="sp-fake-ec2-0001",
        program="EC2Instance",
        region=fixtures.REGION,
        applies_to="m5",
        quantity=None,
        hourly=Decimal("1.10"),
        term_months=36,
        payment=PARTIAL_UPFRONT,
        upfront=Decimal("14454.00"),
        recurring=Decimal("0.55"),
        started_days_ago=400,
    ),
    FakeHolding(
        account="fake-platform-a",
        kind=RESERVATION,
        commitment_id="ri-fake-ec2-0001",
        program=EC2,
        region=fixtures.REGION,
        applies_to="m5.large",
        quantity=4,
        hourly=None,
        term_months=12,
        payment=NO_UPFRONT,
        upfront=Decimal(0),
        recurring=Decimal("0.244"),
        started_days_ago=90,
    ),
    FakeHolding(
        account="fake-platform-b",
        kind=SAVINGS_PLAN,
        commitment_id="sp-fake-compute-0000",
        program="Compute",
        region=None,
        applies_to=None,
        quantity=None,
        hourly=Decimal("0.80"),
        term_months=12,
        payment=NO_UPFRONT,
        upfront=Decimal(0),
        recurring=Decimal("0.80"),
        # Ended about two months ago.
        started_days_ago=425,
        state="retired",
    ),
    FakeHolding(
        account="fake-product-a",
        kind=RESERVATION,
        commitment_id="ri-fake-rds-0001",
        program=RDS,
        region=fixtures.REGION,
        applies_to="db.r6g.large",
        quantity=2,
        hourly=None,
        term_months=12,
        payment=ALL_UPFRONT,
        upfront=Decimal("3504.00"),
        recurring=Decimal(0),
        started_days_ago=210,
    ),
    FakeHolding(
        account="fake-product-a",
        kind=RESERVATION,
        commitment_id="ri-fake-cache-0001",
        program=ELASTICACHE,
        region=fixtures.REGION,
        applies_to="cache.r6g.large",
        quantity=3,
        hourly=None,
        term_months=36,
        payment=PARTIAL_UPFRONT,
        upfront=Decimal("1200.00"),
        recurring=Decimal("0.05"),
        started_days_ago=500,
    ),
)


class FakeCommitmentHoldings:
    """`CommitmentHoldings` over `HOLDINGS`, at the clock it is given.

    `home_region` is where the Regional commitments are held: the fake Region for the seed and the
    tests, and the first collection Region on the local stack, whose units name real Regions.
    """

    def __init__(
        self, *, at: datetime = fixtures.AS_OF, home_region: str = fixtures.REGION
    ) -> None:
        self._at = at
        self._home = home_region

    def savings_plans(self, account: AccountKey) -> Iterable[HeldCommitment]:
        self._refuse(account, f"{account}:savingsplans")
        return tuple(
            self._held(one)
            for one in HOLDINGS
            if one.account == account.account_id and one.kind == SAVINGS_PLAN
        )

    def reservations(self, account: AccountKey, region: str) -> Iterable[HeldCommitment]:
        self._refuse(account, f"{account}:{region}")
        return tuple(
            self._held(one)
            for one in HOLDINGS
            if one.account == account.account_id
            and one.kind == RESERVATION
            and region == self._home
        )

    @staticmethod
    def _refuse(account: AccountKey, scope: str) -> None:
        if account == fixtures.DENIED_ACCOUNT_KEY:
            raise AccessDenied(
                scope_key=scope,
                collector=COLLECTOR,
                detail="the fake estate refuses this account's collector role",
            )

    def _held(self, one: FakeHolding) -> HeldCommitment:
        starts = (self._at - timedelta(days=one.started_days_ago)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return HeldCommitment(
            tenant_id=fixtures.TENANT_ID,
            kind=one.kind,
            commitment_id=one.commitment_id,
            program=one.program,
            account_id=one.account,
            region_id=None if one.region is None else self._home,
            applies_to=one.applies_to,
            quantity=one.quantity,
            hourly_commitment=one.hourly,
            term_months=one.term_months,
            payment_option=one.payment,
            upfront_amount=one.upfront,
            recurring_hourly=one.recurring,
            currency=CURRENCY,
            starts_at=starts,
            # A term of whole years is 365 days a year, as the sources state it.
            ends_at=starts + timedelta(days=365 * one.term_months // 12),
            state=one.state,
            as_of=self._at,
            collected_at=self._at,
        )


#: AWS's advice for a Savings Plans type: the hourly commitment, its monthly savings and percent.
PLAN_ADVICE: Final[dict[str, tuple[Decimal, Decimal, Decimal]]] = {
    "Compute": (Decimal("0.850"), Decimal("142.35"), Decimal("21.4")),
}
#: AWS's advice for a reserved service, by Cost Explorer's name for it: units, monthly savings,
#: percent, and the all upfront price of one unit for one year.
RESERVATION_ADVICE: Final[dict[str, tuple[Decimal, Decimal, Decimal, Decimal]]] = {
    "Amazon Elastic Compute Cloud - Compute": (
        Decimal("2"),
        Decimal("88.60"),
        Decimal("31.0"),
        Decimal("612.00"),
    ),
    "Amazon Relational Database Service": (
        Decimal("1"),
        Decimal("54.20"),
        Decimal("28.5"),
        Decimal("1180.00"),
    ),
}
#: How much of a commitment's price is paid at purchase, by payment option.
UPFRONT_SHARE: Final = {
    NO_UPFRONT: Decimal(0),
    PARTIAL_UPFRONT: Decimal("0.5"),
    ALL_UPFRONT: Decimal(1),
}
HOURS_A_YEAR: Final = Decimal(8760)
LOOKBACK_DAYS: Final = 30
#: AWS generates its recommendations ahead of the read; the fake places that hours before the clock.
GENERATED_BEFORE: Final = timedelta(hours=6)


class FakePurchaseRecommendations:
    """`PurchaseRecommendations` over the two advice tables, in the policy's terms."""

    def __init__(self, tenant_id: UUID, *, at: datetime = fixtures.AS_OF) -> None:
        self._tenant = tenant_id
        self._at = at

    def savings_plans(self, program: str, policy: CommitmentPolicy) -> PurchaseRecommendation:
        advice = PLAN_ADVICE.get(program)
        if advice is None:
            return self._nothing(SAVINGS_PLAN, program, policy)
        hourly, savings, percent = advice
        upfront = hourly * HOURS_A_YEAR * policy.term_years * UPFRONT_SHARE[policy.payment_option]
        return self._advice(
            SAVINGS_PLAN,
            program,
            policy,
            savings=savings,
            percent=percent,
            upfront=upfront,
            hourly=hourly,
        )

    def reservations(self, service: str, policy: CommitmentPolicy) -> PurchaseRecommendation:
        advice = RESERVATION_ADVICE.get(service)
        if advice is None:
            return self._nothing(RESERVATION, service, policy)
        units, savings, percent, price = advice
        upfront = units * price * policy.term_years * UPFRONT_SHARE[policy.payment_option]
        return self._advice(
            RESERVATION,
            service,
            policy,
            savings=savings,
            percent=percent,
            upfront=upfront,
            units=units,
        )

    def _nothing(self, kind: str, program: str, policy: CommitmentPolicy) -> PurchaseRecommendation:
        return self._advice(
            kind,
            program,
            policy,
            savings=Decimal(0),
            percent=None,
            upfront=Decimal(0),
            recommended=False,
        )

    def _advice(
        self,
        kind: str,
        program: str,
        policy: CommitmentPolicy,
        *,
        savings: Decimal,
        percent: Decimal | None,
        upfront: Decimal,
        hourly: Decimal | None = None,
        units: Decimal | None = None,
        recommended: bool = True,
    ) -> PurchaseRecommendation:
        return PurchaseRecommendation(
            tenant_id=self._tenant,
            kind=kind,
            program=program,
            term_years=policy.term_years,
            payment_option=policy.payment_option,
            lookback_days=LOOKBACK_DAYS,
            recommended=recommended,
            hourly_commitment=hourly,
            units=units,
            estimated_monthly_savings=savings,
            estimated_savings_percent=percent,
            upfront_cost=upfront,
            currency=CURRENCY,
            as_of=self._at - GENERATED_BEFORE,
            collected_at=self._at,
        )
