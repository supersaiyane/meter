"""The fake payer's invoices: built from the rows, with a match, a mismatch and an open month.

TASK-P10-003. The states the fake plants are the ones TASK-P10-004's comparison must tell
apart, so each is held here rather than left to be noticed on a screen.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from finops_core.domain.invoice import InvoiceType
from finops_core.errors import AccessDenied
from finops_core.ports.invoice import InvoiceSource
from finops_fakes import cur
from finops_fakes.invoices import (
    MARKETPLACE_ISSUER,
    FakeInvoices,
    marketplace_invoice_id_for,
)

AT = datetime(2026, 10, 7, 6, 0, tzinfo=UTC)
ROWS = cur.estate(at=AT)
EVERYTHING = (date(2000, 1, 1), date(2100, 1, 1))


def billed(invoice_id: str) -> Decimal:
    return sum(
        (row.billed_cost for row in ROWS if row.invoice_id == invoice_id), start=Decimal("0")
    )


def test_it_is_an_invoice_source() -> None:
    assert isinstance(FakeInvoices(ROWS), InvoiceSource)


def test_the_newest_closed_period_matches_its_rows_exactly() -> None:
    found = {i.invoice_id: i for i in FakeInvoices(ROWS).invoices(*EVERYTHING)}
    newest = found[cur.invoice_id_for(date(2026, 9, 1))]
    assert newest.billed_cost_before_tax == billed(newest.invoice_id)
    assert newest.billed_cost == newest.billed_cost_before_tax + newest.tax


def test_the_oldest_closed_period_is_over_its_rows_by_the_surcharge() -> None:
    found = {i.invoice_id: i for i in FakeInvoices(ROWS).invoices(*EVERYTHING)}
    oldest = found[cur.invoice_id_for(date(2026, 8, 1))]
    # A literal, not the fake's own constant: compared with the constant, a surcharge of zero
    # would pass and the demo would show no mismatch at all.
    assert oldest.billed_cost_before_tax - billed(oldest.invoice_id) == Decimal("2.50")


def test_a_marketplace_invoice_names_an_id_no_row_carries() -> None:
    found = {i.invoice_id: i for i in FakeInvoices(ROWS).invoices(*EVERYTHING)}
    marketplace = found[marketplace_invoice_id_for(date(2026, 8, 1))]
    assert marketplace.invoice_issuer_name == MARKETPLACE_ISSUER
    assert all(row.invoice_id != marketplace.invoice_id for row in ROWS)


def test_the_running_month_has_no_invoice() -> None:
    periods = {i.billing_period_start for i in FakeInvoices(ROWS).invoices(*EVERYTHING)}
    assert date(2026, 10, 1) not in periods
    assert all(row.invoice_id is None for row in ROWS if row.billing_period_start.month == 10)


def test_the_window_asked_for_moves_the_planted_mismatch_inside_it() -> None:
    """A reader of fewer periods than the estate holds still meets the mismatch."""
    longer = cur.estate(at=AT, periods=5)
    found = FakeInvoices(longer).invoices(date(2026, 8, 1), date(2026, 11, 1))
    assert {i.billing_period_start for i in found} == {date(2026, 8, 1), date(2026, 9, 1)}
    assert marketplace_invoice_id_for(date(2026, 8, 1)) in {i.invoice_id for i in found}


def test_every_invoice_is_issued_after_its_period_and_read_after_it_is_issued() -> None:
    for found in FakeInvoices(ROWS).invoices(*EVERYTHING):
        assert found.invoice_type is InvoiceType.INVOICE
        assert found.issued_at.date() >= found.billing_period_end
        assert found.collected_at >= found.as_of == found.issued_at


def test_a_failure_asked_for_is_raised_by_type() -> None:
    with pytest.raises(AccessDenied):
        FakeInvoices(ROWS, failure=AccessDenied).invoices(*EVERYTHING)
