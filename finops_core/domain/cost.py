"""One row of cost, in FOCUS 1.4's mandatory columns, with the Meter columns alongside it.

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
from hashlib import sha256
from types import MappingProxyType
from uuid import UUID

from finops_core.domain.ai import TOKEN_TYPES
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


def source_fingerprint(
    *,
    billing_account_id: str,
    sub_account_id: str | None,
    charge_period_start: datetime,
    charge_period_end: datetime,
    service_name: str,
    resource_id: str | None,
    sku_id: str | None,
    charge_category: str,
    commitment_discount_id: str | None,
) -> str:
    """The identity of a line item, as a sha256 hex digest.

    The primary key of `cost_focus_daily` is
    `(tenant_id, billing_period_start, source_fingerprint)`, so this is what
    makes an ingest idempotent across a restated month.

    **It hashes the columns that identify the charge and never the columns that
    state its size.** AWS restates the current month continuously, and a
    fingerprint that included the cost would make a restated row a new row,
    which is the exact failure the key exists to prevent: the month would grow
    by one copy of every corrected line item.

    `sha256` and not `hash()`. The builtin is salted per process, so a
    fingerprint from it is stable within one run and different in the next, and
    the symptom is a table that doubles every time the worker restarts.

    It lives here rather than in either adapter because both adapters must
    produce the same digest for the same charge. Two implementations of an
    identity is how a duplicate is created.
    """
    parts = (
        billing_account_id,
        sub_account_id or "",
        charge_period_start.isoformat(),
        charge_period_end.isoformat(),
        service_name,
        resource_id or "",
        sku_id or "",
        charge_category,
        commitment_discount_id or "",
    )
    # A unit separator, because it cannot occur in any of these values and a
    # comma can. Joining on a character that appears in the data lets two
    # different charges hash to one fingerprint.
    return sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


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


#: Which collector wrote a cost row, P13 spec section 5.3. Each restates only its own, because
#: a restatement removes what its run did not see and one source never sees another's rows. The
#: bill's is named here because every row before P13 was the bill's; the others are named by
#: their collectors, and the table's constraint holds the vocabulary, ADR-0028 keeping a vendor's
#: name out of this package.
AWS_EXPORT = "aws_export"


@dataclass(frozen=True, kw_only=True)
class CostRecord(Fact):
    """A FOCUS charge row. Field names are the specification's.

    FOCUS 1.1's columns, and from P10 the columns FOCUS 1.4 makes mandatory and the two that
    tie a row to its invoice, ADR-0034. The 1.4 columns are optional here because an export
    older than FOCUS 1.2 carries none of them, and a null is what Meter knows.
    """

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
    #: FOCUS 1.4, P10. Null where the export does not carry the column, never a guess.
    billing_account_name: str | None = None
    #: An ISO 4217 code of three capital letters, which the adapter and a constraint hold.
    billing_currency: str | None = None
    charge_class: str | None = None
    pricing_unit: str | None = None
    #: FOCUS 1.3 replaced `provider_name` with this. Until an export carries it, it is
    #: `provider_name`, filled in `__post_init__` so every source keeps the same rule.
    service_provider_name: str | None = None
    #: Equal to the service provider unless a host is exposed, as FOCUS 1.4 requires.
    host_provider_name: str | None = None
    invoice_id: str | None = None
    #: Meter's invoice detail is a whole invoice, AWS returning no line items, so this is
    #: the `invoice_id` unless a source says otherwise.
    invoice_detail_id: str | None = None
    #: Split cost allocation, FEAT-035. Absent on every charge that is not a pod's,
    #: and absent on every export where split cost allocation is not enabled, which
    #: is ISS-003. None rather than zero: a cluster costing nothing is a claim.
    eks_cluster_name: str | None = None
    eks_namespace: str | None = None
    eks_workload_name: str | None = None
    eks_workload_type: str | None = None
    eks_pod_name: str | None = None
    #: A breakdown of money already counted in `billed_cost`, never an addition to
    #: it. Adding these would double count every clustered charge.
    split_cost: Decimal | None = None
    split_usage: Decimal | None = None
    split_usage_ratio: Decimal | None = None
    #: The cluster's unallocated remainder. Arrives on rows with no workload at all,
    #: which is why nothing requires a dimension beside a measure.
    unused_cost: Decimal | None = None
    #: Which collector wrote the row, a Meter column. The bill's unless a provider's adapter
    #: says otherwise, which is what every row written before P13 was.
    ingest_source: str = AWS_EXPORT
    #: FOCUS reserves `x_` for a producer's own columns, and these stand in for the token
    #: fields FOCUS 1.5 is expected to name, OPEN-34. All null on a row that is not AI.
    #: The provider's usage type as billed, AWS's `x_UsageType`.
    x_usage_type: str | None = None
    #: The IAM principal that made the request, CUR 2.0's `line_item_iam_principal`.
    x_iam_principal: str | None = None
    #: Read by the source's adapter: from the usage type on the AWS bill, from a provider's own
    #: cost report otherwise. Never guessed: a source that cannot say leaves them null.
    x_ai_model: str | None = None
    x_ai_token_type: str | None = None
    x_ai_tokens: Decimal | None = None

    def __post_init__(self) -> None:
        # Frozen stops the attribute being rebound. It does not stop the dict
        # behind it being edited, and a shared tag dictionary quietly mutated by
        # one caller is the kind of defect that only shows up in aggregate.
        object.__setattr__(self, "tags", MappingProxyType(dict(self.tags)))
        # One rule for every source, P10 spec section 5.2: FOCUS introduced the service
        # provider to replace `provider_name`, and the host equals it unless one is exposed.
        if self.service_provider_name is None:
            object.__setattr__(self, "service_provider_name", self.provider_name)
        if self.host_provider_name is None:
            object.__setattr__(self, "host_provider_name", self.service_provider_name)
        if self.invoice_detail_id is None and self.invoice_id is not None:
            object.__setattr__(self, "invoice_detail_id", self.invoice_id)
        if not self.ingest_source:
            raise ValueError("a cost row names the collector that wrote it")
        if self.x_ai_token_type is not None and self.x_ai_token_type not in TOKEN_TYPES:
            raise ValueError(f"unknown token type {self.x_ai_token_type!r}")


#: A commitment whose term has not started. AWS queues a Savings Plan to begin on
#: the hour after purchase, and a queued plan has committed nothing and consumed
#: nothing, which is a third state rather than a zero of either.
QUEUED = "QUEUED"
ACTIVE = "ACTIVE"
EXPIRED = "EXPIRED"

#: What a coverage figure is broken down by. Coverage is never per commitment,
#: see `CommitmentCoverage`.
BY_SERVICE = "SERVICE"
BY_REGION = "REGION"


@dataclass(frozen=True, kw_only=True)
class CommitmentUse(Fact):
    """What one commitment obliged us to pay, and how much of it was consumed.

    Utilization only. Coverage is a different entity at a different grain, and the
    reason is not tidiness: see `CommitmentCoverage`.

    **An expired commitment is a row, not an absence.** The money was spent, and
    the coverage gap its expiry leaves is the finding. Dropping it would make the
    estate look like it never had the commitment, which is exactly the situation
    somebody needs to be told about.
    """

    tenant_id: UUID
    commitment_id: str
    #: SavingsPlan or ReservedInstance. Not an enum, because a provider that
    #: invents a third kind should reach a screen rather than a parse failure.
    commitment_type: str
    status: str
    term_start: date
    #: Exclusive, like every other period in this schema.
    term_end: date

    #: The window this row reports on, which is shorter than the term.
    window_start: date
    window_end: date

    #: What the commitment obliged us to pay across the window.
    committed: Decimal
    #: How much of that obligation real usage consumed.
    used: Decimal
    #: `committed` minus `used`. Money already spent that bought nothing, which is
    #: the one figure here a reader can act on without further arithmetic.
    wasted: Decimal

    def __post_init__(self) -> None:
        if self.term_end <= self.term_start:
            raise ValueError(
                f"a commitment term ends after it starts: {self.term_start} to {self.term_end}"
            )
        if self.window_end <= self.window_start:
            raise ValueError(
                f"a window ends after it starts: {self.window_start} to {self.window_end}"
            )
        if self.committed < 0 or self.used < 0:
            raise ValueError("a commitment's money is never negative")
        if self.wasted != self.committed - self.used:
            # Carried rather than computed on read, so a screen and a file cannot
            # disagree about it, and checked here as well as in the database
            # because an adapter is where a wrong subtraction would enter.
            raise ValueError(
                f"wasted is committed minus used: {self.committed} - {self.used} "
                f"is not {self.wasted}"
            )

    @property
    def utilization(self) -> Decimal | None:
        """How much of what we paid for was consumed, as a fraction.

        None where nothing was committed in the window, which is what a queued
        commitment looks like. Zero would say the whole commitment was wasted, and
        it was not: it has not started.
        """
        if self.committed == 0:
            return None
        return self.used / self.committed

    @property
    def is_expired(self) -> bool:
        return self.status == EXPIRED


@dataclass(frozen=True, kw_only=True)
class CommitmentCoverage(Fact):
    """How much of the eligible estate was on a commitment, for one dimension.

    **Separate from `CommitmentUse`, and not by choice.** Utilization is a fact
    about one commitment: this plan obliged us to pay so much and consumed so
    much of it. Coverage is a fact about a slice of the estate: of the EC2 spend
    that could have been on a commitment, this much was. A provider reports the
    first per commitment and the second per service or region, because a dollar of
    covered spend cannot be attributed to one of three overlapping plans, and
    neither can we. Putting a coverage figure on a commitment row would invent a
    number nobody measured, and summing such a column would count the same
    eligible dollar once per commitment.

    The two answers also point at opposite actions, which is why neither may be
    derived from the other. A plan at full utilization covering a tenth of the
    estate says buy more. A plan at half utilization covering everything says the
    last purchase was too large.
    """

    tenant_id: UUID
    commitment_type: str
    #: SERVICE or REGION.
    dimension: str
    dimension_value: str
    window_start: date
    window_end: date

    #: Spend in the window a commitment of this kind could have covered, priced
    #: at on demand.
    eligible_spend: Decimal
    #: How much of that eligible spend a commitment actually covered.
    covered_spend: Decimal

    def __post_init__(self) -> None:
        if self.window_end <= self.window_start:
            raise ValueError(
                f"a window ends after it starts: {self.window_start} to {self.window_end}"
            )
        if self.eligible_spend < 0 or self.covered_spend < 0:
            raise ValueError("coverage money is never negative")
        if self.covered_spend > self.eligible_spend:
            raise ValueError(
                f"a commitment cannot cover more than was eligible: "
                f"{self.covered_spend} of {self.eligible_spend}"
            )

    @property
    def coverage(self) -> Decimal | None:
        """The covered fraction, or None where nothing was eligible.

        Zero would say the estate is uncovered and somebody should buy. None says
        there was nothing there to buy for, which is a different sentence.
        """
        if self.eligible_spend == 0:
            return None
        return self.covered_spend / self.eligible_spend


@dataclass(frozen=True, kw_only=True)
class CommitmentDay(Fact):
    """One kind of commitment on one day: what it obliged, used and covered. TASK-P8-013.

    **Per kind, not per commitment, and not by choice.** Cost Explorer reports daily Savings
    Plans use only as one total across every plan, so a row per plan per day would cost one
    request per plan per day, and reservations are read at the same grain so the two kinds
    stay comparable. Coverage shares the row because at this grain both figures belong to
    the kind and the day, and neither is attributed to a plan: the rule that keeps
    `CommitmentUse` and `CommitmentCoverage` apart is about attributing coverage to one
    commitment, and nothing here does.

    `as_of` is the end of the day described. A day is true once it has ended, and stamping it
    with the moment of the call would make a month of days look as fresh as the last one.
    """

    tenant_id: UUID
    commitment_type: str
    day: date

    #: What the commitments of this kind obliged us to pay that day.
    committed: Decimal
    #: Of that, what was consumed. For a reservation, derived from hours, as
    #: `CommitmentUse` says of the same figure.
    used: Decimal
    #: Spend that day a commitment of this kind could have covered, priced on demand.
    eligible_spend: Decimal
    #: Of that, what a commitment actually covered.
    covered_spend: Decimal

    def __post_init__(self) -> None:
        for name in ("committed", "used", "eligible_spend", "covered_spend"):
            if isinstance(getattr(self, name), float):
                raise TypeError(f"{name} is Decimal, not float")
        if min(self.committed, self.used, self.eligible_spend, self.covered_spend) < 0:
            raise ValueError("a commitment day's money is never negative")
        if self.used > self.committed:
            raise ValueError(
                f"a day cannot use more than was committed: {self.used} of {self.committed}"
            )
        if self.covered_spend > self.eligible_spend:
            raise ValueError(
                f"a day cannot cover more than was eligible: "
                f"{self.covered_spend} of {self.eligible_spend}"
            )

    @property
    def utilization(self) -> Decimal | None:
        """Used over committed, or None on a day nothing was committed."""
        if self.committed == 0:
            return None
        return self.used / self.committed

    @property
    def coverage(self) -> Decimal | None:
        """Covered over eligible, or None on a day nothing was eligible."""
        if self.eligible_spend == 0:
            return None
        return self.covered_spend / self.eligible_spend
