"""A commitment the organization holds: what it is, what it costs and when it ends. FEAT-086.

P14 spec sections 5.3 and 6, TASK-P14-002. FEAT-024 reads how much of a commitment was used and
how much of the estate was covered, from Cost Explorer, and infers a commitment's term from the
reporting window. This is the commitment itself, read from the service that sold it: its real
start and end, its term, its payment option and the hourly commitment or the quantity it buys.

**Exactly one of quantity and hourly commitment.** A Savings Plan commits an amount of money an
hour; a reservation buys a number of instances or nodes. Holding both on one row would invite a
sum of dollars and instances, and holding neither would be a commitment to nothing.

**A retired commitment is a row.** It ended, and the usage it covered went back on demand the next
day, which is the event a renewal calendar exists to see coming.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from finops_core.domain.fact import Fact

#: The two kinds. Strings rather than an enum, as `CommitmentUse.commitment_type` is, so a kind a
#: provider invents reaches a screen rather than a parse failure.
SAVINGS_PLAN: Final = "savings_plan"
RESERVATION: Final = "reservation"
KINDS: Final = (SAVINGS_PLAN, RESERVATION)

#: The reserved services the inventory reads, as a reservation's program names them.
EC2: Final = "EC2"
RDS: Final = "RDS"

#: The payment options, as both Savings Plans and reservations spell them.
NO_UPFRONT: Final = "No Upfront"
PARTIAL_UPFRONT: Final = "Partial Upfront"
ALL_UPFRONT: Final = "All Upfront"

#: An active commitment, as both sources spell it.
ACTIVE: Final = "active"

#: Seconds in the 365 day year both sources state a term in.
_YEAR_SECONDS: Final = 365 * 24 * 3600


@dataclass(frozen=True, kw_only=True)
class HeldCommitment(Fact):
    """One commitment, as the service that sold it describes it."""

    tenant_id: UUID
    kind: str
    #: The source's own identifier: a Savings Plan's id or a reservation's.
    commitment_id: str
    #: The Savings Plans type, `Compute`, `EC2Instance`, `SageMaker` or `Database`; or the reserved
    #: service, `EC2`, `RDS` and the others P14 reads.
    program: str
    #: The account that bought it, which is the account that holds it.
    account_id: str
    #: The Region a reservation or an EC2 Instance Savings Plan applies in; None for one that
    #: applies in every Region.
    region_id: str | None
    #: The instance type, class or family it applies to, where it names one.
    applies_to: str | None
    #: How many instances or nodes a reservation buys. None for a Savings Plan.
    quantity: int | None
    #: What a Savings Plan commits an hour, in its currency. None for a reservation.
    hourly_commitment: Decimal | None
    term_months: int
    payment_option: str
    #: Paid at the start, in its currency. Zero for no upfront.
    upfront_amount: Decimal
    #: Charged every hour of the term, in its currency.
    recurring_hourly: Decimal
    currency: str
    starts_at: datetime
    ends_at: datetime
    state: str

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"a commitment is a savings plan or a reservation, not {self.kind!r}")
        if (self.quantity is None) == (self.hourly_commitment is None):
            raise ValueError(
                f"{self.commitment_id} must name exactly one of a quantity and an hourly "
                "commitment: a reservation buys instances, a Savings Plan an hourly amount"
            )
        if self.term_months <= 0:
            raise ValueError(f"{self.commitment_id} has a term of {self.term_months} months")
        if self.ends_at <= self.starts_at:
            raise ValueError(f"{self.commitment_id} ends before it starts")
        if self.collected_at < self.as_of:
            raise ValueError(f"{self.commitment_id} was collected before it was true")


def term_months(seconds: int) -> int:
    """A term in seconds, as both sources give it, in whole months: a year is twelve.

    AWS sells one and three year terms and states them in seconds of 365 day years, so the
    division is exact for every term it sells; anything else rounds to the nearest month rather
    than claiming a precision the source did not have.
    """
    return max(1, round(seconds / _YEAR_SECONDS * 12))
