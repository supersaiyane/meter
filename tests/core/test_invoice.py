"""An invoice as the domain holds it, and the months its periods are made of. TASK-P10-003."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from finops_core.domain.invoice import Invoice, InvoiceType, months, next_month

AT = datetime(2026, 9, 3, 6, 0, tzinfo=UTC)


def invoice(**overrides: Any) -> Invoice:
    fields: dict[str, Any] = {
        "invoice_id": "inv-2026-08",
        "invoice_type": InvoiceType.INVOICE,
        "original_invoice_id": None,
        "billing_account_id": "111122223333",
        "billing_period_start": date(2026, 8, 1),
        "billing_period_end": date(2026, 9, 1),
        "invoice_issuer_name": "Amazon Web Services, Inc.",
        "billing_currency": "USD",
        "billed_cost_before_tax": Decimal("100.00"),
        "tax": Decimal("10.00"),
        "billed_cost": Decimal("110.00"),
        "issued_at": AT,
        "due_date": date(2026, 10, 3),
        "as_of": AT,
        "collected_at": AT,
    }
    return Invoice(**{**fields, **overrides})


def test_an_invoice_is_its_own_detail_at_the_grain_aws_gives() -> None:
    assert invoice().invoice_detail_id == "inv-2026-08"


def test_a_period_that_does_not_end_after_it_starts_is_refused() -> None:
    with pytest.raises(ValueError, match="end after it starts"):
        invoice(billing_period_end=date(2026, 8, 1))


def test_a_credit_memo_names_the_invoice_it_corrects() -> None:
    with pytest.raises(ValueError, match="credit memo"):
        invoice(invoice_type=InvoiceType.CREDIT_MEMO, original_invoice_id=None)
    memo = invoice(invoice_type=InvoiceType.CREDIT_MEMO, original_invoice_id="inv-2026-07")
    assert memo.original_invoice_id == "inv-2026-07"


def test_december_is_followed_by_the_next_january() -> None:
    assert next_month(date(2026, 12, 1)) == date(2027, 1, 1)
    assert next_month(date(2026, 8, 1)) == date(2026, 9, 1)


def test_months_runs_from_the_start_month_up_to_the_end_and_not_including_it() -> None:
    assert list(months(date(2026, 11, 17), date(2027, 2, 1))) == [
        date(2026, 11, 1),
        date(2026, 12, 1),
        date(2027, 1, 1),
    ]
    assert list(months(date(2026, 8, 1), date(2026, 8, 1))) == []
