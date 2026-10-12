"""The fake payer's invoices, built from the very rows the fake export bills.

FEAT-076, TASK-P10-003. ADR-0022 keeps this out of the production packages.

**Built from the rows, not beside them.** Each closed period's invoice is the sum of the billed
cost its rows carry under that invoice's id, so the comparison TASK-P10-004 makes matches by
construction wherever it should, whatever moment the estate was generated for. The demo seeder
generates its bill for now and these follow it.

**Three states on purpose.** The newest closed period matches, so the front page shows a real
match. The oldest closed period asked for has an invoice higher than its rows by `SURCHARGE`, a
charge on the invoice the export never itemised, so the screen shows a mismatch and its
difference. And a Marketplace invoice in that period names an id no row carries, because
Marketplace charges are invoiced by another entity and a reconciliation that ignored that would
be wrong in every estate that buys anything there. The open period has no invoice at all.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from datetime import time as time_of_day
from decimal import Decimal

from finops_core.domain.cost import CostRecord
from finops_core.domain.invoice import Invoice, InvoiceType
from finops_core.errors import CollectionError
from finops_fakes import cur, fixtures

COLLECTOR = "invoices"

#: What the oldest closed period's invoice carries beyond its rows.
SURCHARGE = Decimal("2.5000")
#: The Marketplace invoice's amount, which no row of the export carries.
MARKETPLACE_AMOUNT = Decimal("40.0000")
MARKETPLACE_ISSUER = "Fake Marketplace"
ISSUER = "Fake"
#: Days after a period ends that its invoice is issued, and then that it is due.
ISSUED_AFTER_DAYS = 2
DUE_AFTER_DAYS = 30
TAX = "Tax"

_Key = tuple[str, date, date]


def marketplace_invoice_id_for(period: date) -> str:
    return f"fake-marketplace-{period:%Y-%m}"


class FakeInvoices:
    """Invoices for the closed periods of the rows given, and every failure asked for."""

    def __init__(
        self,
        rows: Iterable[CostRecord] = cur.ESTATE,
        *,
        failure: type[CollectionError] | None = None,
    ) -> None:
        self._rows = tuple(rows)
        self._failure = failure

    def invoices(self, start: date, end: date) -> Iterable[Invoice]:
        if self._failure is not None:
            raise self._failure(
                scope_key=fixtures.ORGANIZATION_SCOPE,
                collector=COLLECTOR,
                detail="planned by the fake invoice source",
            )
        billed, taxed = self._sums(start, end)
        periods = sorted({period for _, period, _ in billed})
        # The oldest in the window asked for, so a reader of fewer periods than the estate
        # holds still meets the mismatch and the Marketplace invoice.
        oldest = periods[0] if len(periods) > 1 else None
        found: list[Invoice] = []
        for key, before_tax in sorted(billed.items()):
            invoice_id, period, period_end = key
            surcharge = SURCHARGE if period == oldest else Decimal("0")
            found.append(
                _invoice(invoice_id, period, period_end, ISSUER, before_tax + surcharge, taxed[key])
            )
            if period == oldest:
                found.append(
                    _invoice(
                        marketplace_invoice_id_for(period),
                        period,
                        period_end,
                        MARKETPLACE_ISSUER,
                        MARKETPLACE_AMOUNT,
                        Decimal("0"),
                    )
                )
        return tuple(found)

    def _sums(self, start: date, end: date) -> tuple[dict[_Key, Decimal], dict[_Key, Decimal]]:
        billed: dict[_Key, Decimal] = defaultdict(Decimal)
        taxed: dict[_Key, Decimal] = defaultdict(Decimal)
        for row in self._rows:
            if row.invoice_id is None or not start <= row.billing_period_start < end:
                continue
            key = (row.invoice_id, row.billing_period_start, row.billing_period_end)
            if row.charge_category == TAX:
                taxed[key] += row.billed_cost
            else:
                billed[key] += row.billed_cost
        return billed, taxed


def _invoice(
    invoice_id: str,
    period: date,
    period_end: date,
    issuer: str,
    before_tax: Decimal,
    tax: Decimal,
) -> Invoice:
    issued = datetime.combine(
        period_end + timedelta(days=ISSUED_AFTER_DAYS), time_of_day(6, 0), UTC
    )
    return Invoice(
        invoice_id=invoice_id,
        invoice_type=InvoiceType.INVOICE,
        original_invoice_id=None,
        billing_account_id=fixtures.ACCOUNT_IDS[0],
        billing_period_start=period,
        billing_period_end=period_end,
        invoice_issuer_name=issuer,
        billing_currency=cur.CURRENCY,
        billed_cost_before_tax=before_tax,
        tax=tax,
        billed_cost=before_tax + tax,
        issued_at=issued,
        due_date=issued.date() + timedelta(days=DUE_AFTER_DAYS),
        as_of=issued,
        collected_at=max(issued, fixtures.COLLECTED_AT),
    )
