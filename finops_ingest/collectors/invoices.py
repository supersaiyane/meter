"""Invoices and billing periods, read from the payer and never written to it.

FEAT-076, TASK-P10-003. The comparison with the cost rows is TASK-P10-004 and is computed when
it is read; this module stores what the provider issued and which periods it has closed.

**Each run reads the last `PERIODS` billing periods, the current one included.** A credit memo
for an earlier period lands inside that window, and an older period keeps the rows it was last
read with rather than being retracted, because last quarter's invoice is what last quarter's
spend was billed as.

**A period with no invoice is stored Open, not skipped.** The reconciliation needs to say a
period is still open rather than say nothing, and nothing is how a failure would look.

**A failed read fails the run.** The source raises one of the typed causes and the ledger
records it; nothing here writes a period Open because its invoices could not be read.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.invoice import (
    BillingPeriodStatus,
    Invoice,
    InvoiceType,
    months,
    next_month,
)
from finops_core.ports.invoice import InvoiceSource
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "invoices"

#: How many billing periods a run reads, the current one included. Three, because a credit memo
#: is usually issued within two months of the invoice it corrects (modelled, not yet measured
#: against a real payer), and each period read is one more call.
PERIODS = 3

WRITE_INVOICE = text(
    "INSERT INTO invoice_detail (invoice_detail_pk, tenant_id, ingest_run_id, invoice_id, "
    "invoice_detail_id, invoice_type, original_invoice_id, billing_account_id, "
    "billing_period_start, billing_period_end, invoice_issuer_name, billing_currency, "
    "billed_cost_before_tax, tax, billed_cost, issued_at, due_date, as_of, collected_at) "
    "VALUES (:pk, :tenant, :run, :invoice_id, :detail_id, :kind, :original, :account, "
    ":start, :end, :issuer, :currency, :before_tax, :tax, :billed, :issued, :due, :as_of, "
    ":collected) "
    "ON CONFLICT (tenant_id, invoice_id) DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, invoice_type = EXCLUDED.invoice_type, "
    "original_invoice_id = EXCLUDED.original_invoice_id, "
    "billing_account_id = EXCLUDED.billing_account_id, "
    "billing_period_start = EXCLUDED.billing_period_start, "
    "billing_period_end = EXCLUDED.billing_period_end, "
    "invoice_issuer_name = EXCLUDED.invoice_issuer_name, "
    "billing_currency = EXCLUDED.billing_currency, "
    "billed_cost_before_tax = EXCLUDED.billed_cost_before_tax, tax = EXCLUDED.tax, "
    "billed_cost = EXCLUDED.billed_cost, issued_at = EXCLUDED.issued_at, "
    "due_date = EXCLUDED.due_date, as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
)

WRITE_PERIOD = text(
    "INSERT INTO billing_period (billing_period_pk, tenant_id, ingest_run_id, "
    "billing_period_start, billing_period_end, billing_period_status, as_of, collected_at) "
    "VALUES (:pk, :tenant, :run, :start, :end, :status, :as_of, :collected) "
    "ON CONFLICT (tenant_id, billing_period_start) DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, billing_period_end = EXCLUDED.billing_period_end, "
    "billing_period_status = EXCLUDED.billing_period_status, as_of = EXCLUDED.as_of, "
    "collected_at = EXCLUDED.collected_at"
)


def _system_clock() -> datetime:
    return datetime.now(UTC)


Clock = Callable[[], datetime]


def months_before(month: date, count: int) -> date:
    """The first day of the month `count` months before `month`'s."""
    year, index = divmod(month.year * 12 + month.month - 1 - count, 12)
    return date(year, index + 1, 1)


class InvoiceCollector:
    """The payer's invoices and the periods they close, stored as read."""

    def __init__(
        self, source: InvoiceSource, clock: Clock = _system_clock, periods: int = PERIODS
    ) -> None:
        if periods < 1:
            raise ValueError("an invoice read covers at least the current billing period")
        self._source = source
        self._clock = clock
        self._periods = periods

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        now = self._clock()
        current = date(now.year, now.month, 1)
        start, end = months_before(current, self._periods - 1), next_month(current)
        invoices = tuple(self._source.invoices(start, end))
        for invoice in invoices:
            self._write_invoice(context, invoice)
        closed: dict[date, datetime] = {}
        for invoice in invoices:
            if invoice.invoice_type is InvoiceType.INVOICE:
                period = invoice.billing_period_start
                closed[period] = min(closed.get(period, invoice.issued_at), invoice.issued_at)
        for month in months(start, end):
            self._write_period(context, month, closed.get(month), now)
        return CollectorOutcome(items_written=len(invoices))

    def _write_invoice(self, context: CollectorContext, invoice: Invoice) -> None:
        context.connection.execute(
            WRITE_INVOICE,
            {
                "pk": uuid4(),
                "tenant": context.unit.tenant_id,
                "run": context.run_id,
                "invoice_id": invoice.invoice_id,
                "detail_id": invoice.invoice_detail_id,
                "kind": invoice.invoice_type.value,
                "original": invoice.original_invoice_id,
                "account": invoice.billing_account_id,
                "start": invoice.billing_period_start,
                "end": invoice.billing_period_end,
                "issuer": invoice.invoice_issuer_name,
                "currency": invoice.billing_currency,
                "before_tax": invoice.billed_cost_before_tax,
                "tax": invoice.tax,
                "billed": invoice.billed_cost,
                "issued": invoice.issued_at,
                "due": invoice.due_date,
                "as_of": invoice.as_of,
                "collected": invoice.collected_at,
            },
        )

    def _write_period(
        self,
        context: CollectorContext,
        month: date,
        closed_at: datetime | None,
        now: datetime,
    ) -> None:
        status = BillingPeriodStatus.OPEN if closed_at is None else BillingPeriodStatus.CLOSED
        context.connection.execute(
            WRITE_PERIOD,
            {
                "pk": uuid4(),
                "tenant": context.unit.tenant_id,
                "run": context.run_id,
                "start": month,
                "end": next_month(month),
                "status": status.value,
                # Closed from when its first invoice was issued; open as of now. Never after
                # the moment it was read, constraint 10.
                "as_of": now if closed_at is None else min(closed_at, now),
                "collected": now,
            },
        )
