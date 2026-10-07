"""The payer's invoices as the AWS Invoicing API returns them.

FEAT-076, TASK-P10-003, P10 spec section 5.3.

**Unproved against a real account**, like every adapter in this package. The shapes below are
read from the service model botocore 1.43.108 installs, API version 2024-12-01, and the tests
answer from a literal. Proof waits on ISS-002, ISS-003 and TASK-P9-001.

**Asked one billing period at a time.** `ListInvoiceSummaries` filters either by a time
interval or by a billing period. The documentation does not say which date the interval is
held against, so this asks for each month by its period and nothing is inferred.

**Summaries only.** The API returns whole invoices and no line items, so one invoice is one
Invoice Detail row. A payment receipt is neither an invoice nor a credit memo and is skipped.

**Amounts are read, never defaulted.** A missing or unreadable amount, currency or date is
`SchemaDrift`, because an invoice read as zero is the defect the reconciliation exists to find.
The one exception is tax: an invoice with no tax breakdown has its tax taken as its total less
its amount before tax, which is what tax on an invoice is, rather than as zero.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.domain.invoice import Invoice, InvoiceType, months, next_month
from finops_core.errors import SchemaDrift
from finops_providers.aws.client import translate
from finops_providers.aws.cur import CURRENCY

COLLECTOR = "invoices"
ACCOUNT_ID = "ACCOUNT_ID"
KINDS = frozenset(member.value for member in InvoiceType)


def _system_clock() -> datetime:
    return datetime.now(UTC)


class AwsInvoices:
    """The payer's invoices and credit memos, read and never written."""

    def __init__(
        self, *, client: Any, account_id: str, clock: Callable[[], datetime] = _system_clock
    ) -> None:
        self._client = client
        # The payer, because invoices are issued to the management account for the whole org.
        self._account_id = account_id
        self._clock = clock

    def invoices(self, start: date, end: date) -> Iterable[Invoice]:
        at = self._clock()
        found: list[Invoice] = []
        try:
            for month in months(start, end):
                for raw in self._summaries(month):
                    if raw.get("InvoiceType") in KINDS:
                        found.append(self._one(raw, at))
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=self._account_id, collector=COLLECTOR) from failure
        return tuple(found)

    def _summaries(self, month: date) -> Iterator[Any]:
        pages = self._client.get_paginator("list_invoice_summaries").paginate(
            Selector={"ResourceType": ACCOUNT_ID, "Value": self._account_id},
            Filter={"BillingPeriod": {"Month": month.month, "Year": month.year}},
        )
        for page in pages:
            yield from page.get("InvoiceSummaries") or ()

    def _one(self, raw: Any, at: datetime) -> Invoice:
        invoice_id = str(raw.get("InvoiceId") or "").strip()
        if not invoice_id:
            raise self._drift("an invoice summary carries no invoice id")
        start = self._period(raw, invoice_id)
        issued = raw.get("IssuedDate")
        if not isinstance(issued, datetime):
            raise self._drift(f"invoice {invoice_id} has no issue date")
        issued = issued if issued.tzinfo else issued.replace(tzinfo=UTC)
        amount = raw.get("BaseCurrencyAmount") or {}
        currency = str(amount.get("CurrencyCode") or "")
        if not CURRENCY.fullmatch(currency):
            raise self._drift(f"invoice {invoice_id}'s currency {currency!r} is not ISO 4217")
        before_tax = self._amount(amount.get("TotalAmountBeforeTax"), invoice_id)
        total = self._amount(amount.get("TotalAmount"), invoice_id)
        taxes = ((amount.get("AmountBreakdown") or {}).get("Taxes") or {}).get("TotalAmount")
        tax = total - before_tax if taxes is None else self._amount(taxes, invoice_id)
        due = raw.get("DueDate")
        return Invoice(
            invoice_id=invoice_id,
            invoice_type=InvoiceType(raw["InvoiceType"]),
            original_invoice_id=raw.get("OriginalInvoiceId") or None,
            billing_account_id=str(raw.get("AccountId") or self._account_id),
            billing_period_start=start,
            billing_period_end=next_month(start),
            invoice_issuer_name=str((raw.get("Entity") or {}).get("InvoicingEntity") or ""),
            billing_currency=currency,
            billed_cost_before_tax=before_tax,
            tax=tax,
            billed_cost=total,
            issued_at=issued,
            due_date=due.date() if isinstance(due, datetime) else None,
            as_of=issued,
            # A clock behind AWS's would otherwise read the invoice before it was issued.
            collected_at=max(at, issued),
        )

    def _period(self, raw: Any, invoice_id: str) -> date:
        period = raw.get("BillingPeriod") or {}
        try:
            return date(int(period["Year"]), int(period["Month"]), 1)
        except (KeyError, TypeError, ValueError) as failure:
            raise self._drift(f"invoice {invoice_id} has no readable billing period") from failure

    def _amount(self, value: Any, invoice_id: str) -> Decimal:
        if value is None:
            raise self._drift(f"invoice {invoice_id} is missing an amount")
        try:
            return Decimal(str(value))
        except InvalidOperation as failure:
            raise self._drift(f"invoice {invoice_id} has an amount {value!r}") from failure

    def _drift(self, detail: str) -> SchemaDrift:
        return SchemaDrift(scope_key=self._account_id, collector=COLLECTOR, detail=detail)
