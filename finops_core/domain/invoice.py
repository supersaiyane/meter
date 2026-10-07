"""An invoice the provider issued, and the billing period it closes.

FEAT-076, TASK-P10-003, P10 spec sections 5.3 and 6. FOCUS 1.4's Invoice Detail and Billing
Period datasets, at the grain AWS gives: `ListInvoiceSummaries` returns whole invoices and no
line items, so one invoice is one detail and its detail id is its invoice id.

**An invoice is read, never derived.** Its amounts are the provider's, before tax, the tax and
the total, in the currency it was issued in. Meter's own sum over the cost rows is compared
with it in TASK-P10-004 and never written over it, because the point of reading the invoice is
to have a figure Meter did not produce.

**A credit memo is an invoice of its own.** It carries the invoice it corrects, so the
comparison can show the correction beside what it corrects rather than netting the two away.

**A period is Closed once its invoice is issued.** FOCUS 1.4 defines Closed as every expected
invoice issued and the data final. Meter cannot know what else a provider means to issue, so
it reads an issued invoice as closing its period and says so; when a period is final is
OPEN-08.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from finops_core.domain.fact import Fact


class InvoiceType(StrEnum):
    """What a provider issued: an invoice, or a credit memo correcting one."""

    INVOICE = "INVOICE"
    CREDIT_MEMO = "CREDIT_MEMO"


class BillingPeriodStatus(StrEnum):
    """FOCUS 1.4's two states, in FOCUS's own words."""

    #: Still being billed: records may be added or revised.
    OPEN = "Open"
    #: An invoice has been issued for it.
    CLOSED = "Closed"


@dataclass(frozen=True, kw_only=True)
class Invoice(Fact):
    """One invoice as the provider issued it. `as_of` is the issue time."""

    invoice_id: str
    invoice_type: InvoiceType
    #: The invoice a credit memo corrects, and None on an invoice.
    original_invoice_id: str | None
    billing_account_id: str
    billing_period_start: date
    billing_period_end: date
    #: The entity that issued it, which is not always the provider: Marketplace charges are
    #: invoiced by another entity, and each entity's invoice is compared on its own.
    invoice_issuer_name: str
    #: An ISO 4217 code, three capital letters.
    billing_currency: str
    billed_cost_before_tax: Decimal
    tax: Decimal
    billed_cost: Decimal
    issued_at: datetime
    due_date: date | None

    def __post_init__(self) -> None:
        if self.billing_period_end <= self.billing_period_start:
            raise ValueError("an invoice's billing period must end after it starts")
        if self.invoice_type is InvoiceType.CREDIT_MEMO and not self.original_invoice_id:
            raise ValueError("a credit memo names the invoice it corrects")

    @property
    def invoice_detail_id(self) -> str:
        """FOCUS 1.4's detail id, which is the invoice's own at the grain AWS gives."""
        return self.invoice_id


def next_month(month: date) -> date:
    """The first day of the month after `month`'s, which is where its billing period ends."""
    return date(month.year + month.month // 12, month.month % 12 + 1, 1)


def months(start: date, end: date) -> Iterator[date]:
    """The first day of every month from `start`'s up to, not including, `end`."""
    month = date(start.year, start.month, 1)
    while month < end:
        yield month
        month = next_month(month)
