"""One row of cost, in FOCUS 1.1, with the Meter columns alongside it.

ADR-0002. The column names are the specification's, not ours. They are not
renamed to something more readable, because the entire value of adopting a
standard is that it is not ours to improve, and a rename is a mapping that
someone maintains forever.

`tests/core/test_domain.py::test_cost_record_matches_focus_columns` reads the
column list out of `docs/07-DATA-MODEL.md`, so this class and the table it is
stored in cannot drift apart in either direction.

Money is `Decimal` and never `float`. A float total over a month of line items
is wrong in the last places, and a cost report that does not reconcile with the
provider's invoice is a cost report nobody uses twice.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from finops_core.domain.fact import Fact


class CostMeasure(StrEnum):
    """Which number a total is. FOCUS names these and this does not improve on them.

    `EFFECTIVE` is amortized cost and is the primary measure everywhere, which
    the roadmap decided and this does not reopen. `BILLED` is what the invoice
    says and is shown only where the question is what the invoice says.

    The reason this exists at all is that the four are routinely equal. A month
    with no commitments in it has the same effective and billed cost, so a
    screen rendering one under the other's label is right until the month it is
    not, and then it is wrong by exactly the amount somebody is asking about.
    """

    EFFECTIVE = "effective"
    BILLED = "billed"
    LIST = "list"
    CONTRACTED = "contracted"


@dataclass(frozen=True, kw_only=True)
class BillingPeriod:
    """A billing interval, start inclusive and end exclusive.

    August 2026 is `start=2026-08-01, end=2026-09-01`. That is the FOCUS
    convention and the fixtures already followed it, but nothing in this
    repository wrote it down, so the first person to read the end as inclusive
    would have counted a day of September into August and found out at a
    reconciliation.

    Not a `Fact`, for the reason `IngestRun` is not one. A period is a calendar
    interval rather than something that was true about a cloud at a moment, and
    giving it an `as_of` would invite the question of what that value means.
    """

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError(
                f"a billing period that ends before it starts is not a period: "
                f"{self.start} to {self.end}"
            )

    def covers(self, day: date) -> bool:
        """Whether a day falls inside the period."""
        return self.start <= day < self.end

    def is_open(self, *, at: datetime) -> bool:
        """Whether charges can still land in this period at that moment.

        The clock is the caller's. A type that reads the wall clock cannot be
        tested at a boundary, and every test of it becomes a test of when it
        ran.
        """
        if at.tzinfo is None:
            raise ValueError(
                "is_open needs a timezone aware datetime. A naive one compares against "
                "an aware one by raising somewhere that says nothing about "
                "billing periods, per constraint 10."
            )
        return at < datetime(self.end.year, self.end.month, self.end.day, tzinfo=UTC)


@dataclass(frozen=True, kw_only=True)
class CostTotal(Fact):
    """An aggregate of cost, which always says which measure it is.

    Every total on a screen goes through this. A bare `Decimal` reaching a
    template is a number that will be labelled by whatever the template says,
    and the four measures are equal often enough that the mistake survives
    review.
    """

    amount: Decimal
    measure: CostMeasure

    def __post_init__(self) -> None:
        # Stated in this module's own docstring and stated again here, because
        # a docstring has never refused anything. A float total over a month of
        # line items is wrong in the last places, and a cost report that does
        # not reconcile with the invoice is one nobody uses twice.
        if not isinstance(self.amount, Decimal):
            raise TypeError(
                f"cost is Decimal and never {type(self.amount).__name__}. "
                "Money in binary floating point does not reconcile."
            )


@dataclass(frozen=True, kw_only=True)
class CostRecord(Fact):
    """A FOCUS 1.1 charge row. Field names are the specification's."""

    # Meter columns, alongside the FOCUS namespace and never inside it.
    tenant_id: UUID
    ingest_run_id: UUID
    source_fingerprint: str

    # FOCUS 1.1
    billing_account_id: str
    sub_account_id: str | None
    billing_period_start: date
    billing_period_end: date
    charge_period_start: datetime
    charge_period_end: datetime
    provider_name: str
    publisher_name: str | None
    invoice_issuer_name: str | None
    service_name: str
    service_category: str | None
    resource_id: str | None
    resource_name: str | None
    region_id: str | None
    availability_zone: str | None
    charge_category: str
    charge_description: str | None
    sku_id: str | None
    pricing_quantity: Decimal | None
    consumed_quantity: Decimal | None
    consumed_unit: str | None
    billed_cost: Decimal
    effective_cost: Decimal
    list_cost: Decimal | None
    contracted_cost: Decimal | None
    commitment_discount_id: str | None
    commitment_discount_type: str | None
    commitment_discount_status: str | None
    tags: Mapping[str, str]

    def __post_init__(self) -> None:
        # Frozen stops the attribute being rebound. It does not stop the dict
        # behind it being edited, and a shared tag dictionary quietly mutated by
        # one caller is the kind of defect that only shows up in aggregate.
        object.__setattr__(self, "tags", MappingProxyType(dict(self.tags)))
