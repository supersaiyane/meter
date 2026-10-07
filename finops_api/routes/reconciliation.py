"""Invoice reconciliation, `GET /cost/reconciliation`. FEAT-076, TASK-P10-004.

Each invoice the payer was issued for a billing period, beside the sum of Meter's billed cost
over the rows carrying its id, before tax and tax apart, P10 spec section 5.4. The rule is
`finops_core.domain.reconciliation`; this module reads the three sides and reports the answer.

**Payer wide, refused by type.** An invoice totals every account under the payer, so a reader
whose scope is narrower is refused with a 403 before anything is read, spec section 5.5. The
guard would hand them no invoices anyway, but the cost rows are scoped by account, and a route
that read them for a narrowed reader would be one edit away from setting a partial sum beside a
whole invoice.

**Nothing here is stored.** The comparison is computed per request from the invoice rows and
the cost rows, so it cannot drift from either.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Final

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.engine import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.ingest import IngestRunRepository
from finops_api.db.repositories.invoices import (
    BillingPeriodRepository,
    InvoicedCostRepository,
    InvoiceRepository,
)
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.exports import ExportSpec, View, exportable, rows_in
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import Envelope, InvoiceComparisonOut, ReconciliationOut
from finops_core.domain.invoice import BillingPeriodStatus
from finops_core.domain.reconciliation import CENT, TOLERANCE, compare, without_invoice
from finops_core.domain.tenant import Scope

router = APIRouter(prefix=API_PREFIX, tags=["cost"])

COLLECTOR: Final = "invoices"
FAILED: Final = "FAILED"

PAYER_WIDE: Final = (
    "Invoice reconciliation needs the whole organization in view. An invoice totals every "
    "account under the payer, so a comparison over fewer accounts would be a different number "
    "under the invoice's name. ADR-0025."
)
NOT_READ: Final = (
    "No invoices have been read for this billing period. The invoices collector reads the last "
    "three periods once a day."
)
BILLED_AS_INVOICED: Final = (
    "Billed Cost, before tax and tax apart, in the invoice's currency, beside the invoice"
)


def _period(view: View) -> str:
    asked = view.query.get("period")
    if asked:
        return f"The billing period starting {asked}"
    return "The newest billing period with an issued invoice"


@router.get("/cost/reconciliation", response_model=Envelope[ReconciliationOut])
@exportable(
    ExportSpec(
        title="Invoice reconciliation",
        row_model=InvoiceComparisonOut,
        rows=rows_in("invoices"),
        period=_period,
        metric=BILLED_AS_INVOICED,
        note=(
            "A difference is Meter's figure less the invoice's. Matched means both before tax "
            "and tax are within 0.01 percent of the invoice or one cent, a modelled tolerance."
        ),
    )
)
def cost_reconciliation(
    period: date | None = Query(
        default=None, description="Billing period. The newest with an invoice if omitted."
    ),
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[ReconciliationOut]:
    """Each invoice for a period beside Meter's billed cost under it, and what the gap means."""
    if not scope.is_global:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PAYER_WIDE)
    periods = BillingPeriodRepository(connection, context)
    resolved = period.replace(day=1) if period is not None else periods.latest(scope)
    last = IngestRunRepository(connection, context).latest_of(scope, COLLECTOR)
    read_failed = last is not None and last.status == FAILED
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_READ)
    stored = periods.one(scope, resolved)
    invoices = InvoiceRepository(connection, context).for_period(scope, resolved)
    if stored is None and not invoices and not read_failed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_READ)

    sums = InvoicedCostRepository(connection, context).sums(scope, resolved) if invoices else {}
    compared = tuple(_compared(row, sums.get(str(row.invoice_id), ())) for row in invoices)
    state = None if compared else without_invoice(read_failed=read_failed)
    cause = str(last.error_type) if state is not None and read_failed and last else None
    data = ReconciliationOut(
        period=resolved,
        period_status=(
            BillingPeriodStatus.OPEN.value if stored is None else str(stored.billing_period_status)
        ),
        state=None if state is None else state.value,
        cause=cause,
        tolerance=TOLERANCE,
        minimum_difference=CENT,
        invoices=compared,
    )
    meta = build_meta(
        connection,
        scope,
        context,
        visible=1,
        rows=invoices if invoices else (() if stored is None else (stored,)),
        coverage=(1, 1),
        coverage_unit="payer",
    )
    return Envelope(data=data, meta=meta)


def _compared(row: Any, sums: Any) -> InvoiceComparisonOut:
    outcome = compare(
        currency=str(row.billing_currency),
        before_tax=row.billed_cost_before_tax,
        tax=row.tax,
        sums=sums,
    )
    return InvoiceComparisonOut(
        invoice_id=str(row.invoice_id),
        invoice_type=str(row.invoice_type),
        original_invoice_id=row.original_invoice_id,
        invoice_issuer_name=str(row.invoice_issuer_name),
        billing_currency=str(row.billing_currency),
        invoice_before_tax=row.billed_cost_before_tax,
        invoice_tax=row.tax,
        invoice_billed_cost=row.billed_cost,
        meter_before_tax=outcome.meter_before_tax,
        meter_tax=outcome.meter_tax,
        difference_before_tax=outcome.difference_before_tax,
        difference_tax=outcome.difference_tax,
        state=outcome.state.value,
        issued_at=row.issued_at,
        as_of=row.as_of,
        collected_at=row.collected_at,
    )
