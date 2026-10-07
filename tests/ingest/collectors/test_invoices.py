"""Invoices and billing periods stored as read, against a migrated database. TASK-P10-003.

The fake estate is pinned to 2026-10-07, so a run reads August to October: two closed periods,
one of them carrying the planted mismatch and a Marketplace invoice, and October open.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from finops_core.domain.invoice import Invoice, InvoiceType
from finops_core.errors import AccessDenied
from finops_fakes import cur
from finops_fakes.invoices import FakeInvoices
from finops_ingest.collectors.invoices import InvoiceCollector, months_before
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext

AT = datetime(2026, 10, 7, 6, 0, tzinfo=UTC)
ROWS = cur.estate(at=AT)

pytestmark = pytest.mark.integration


def run(engine: Engine, tenant: UUID, source: Any) -> int:
    unit = WorkUnit(
        tenant_id=tenant,
        collector="invoices",
        window_start=AT,
        window_end=AT,
        account=None,
        region=None,
    )
    with engine.begin() as connection:
        outcome = InvoiceCollector(source, clock=lambda: AT)(
            CollectorContext(unit=unit, connection=connection, run_id=uuid4())
        )
    return outcome.items_written


def rows(engine: Engine, tenant: UUID, table: str, order: str) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                text(f"SELECT * FROM {table} WHERE tenant_id = :t ORDER BY {order}"),
                {"t": tenant},
            ).mappings()
        ]


class StubInvoices:
    def __init__(self, invoices: Iterable[Invoice]) -> None:
        self._invoices = tuple(invoices)

    def invoices(self, start: date, end: date) -> Iterable[Invoice]:
        return tuple(i for i in self._invoices if start <= i.billing_period_start < end)


def test_months_before_crosses_a_year() -> None:
    assert months_before(date(2027, 1, 1), 2) == date(2026, 11, 1)
    assert months_before(date(2026, 10, 1), 0) == date(2026, 10, 1)


def test_a_run_needs_at_least_the_current_period() -> None:
    with pytest.raises(ValueError, match="at least the current"):
        InvoiceCollector(FakeInvoices(ROWS), periods=0)


def test_each_invoice_is_stored_as_read(engine: Engine, tenant_id: UUID) -> None:
    assert run(engine, tenant_id, FakeInvoices(ROWS)) == 3
    stored = rows(engine, tenant_id, "invoice_detail", "invoice_id")
    assert [row["invoice_id"] for row in stored] == [
        "fake-invoice-2026-08",
        "fake-invoice-2026-09",
        "fake-marketplace-2026-08",
    ]
    for row in stored:
        assert row["invoice_detail_id"] == row["invoice_id"]
        assert row["billing_currency"] == "USD"
        assert row["collected_at"] >= row["as_of"]
    expected = sum(
        (r.billed_cost for r in ROWS if r.invoice_id == "fake-invoice-2026-09"), Decimal("0")
    )
    assert stored[1]["billed_cost_before_tax"] == expected


def test_a_period_is_closed_by_its_invoice_and_open_without_one(
    engine: Engine, tenant_id: UUID
) -> None:
    run(engine, tenant_id, FakeInvoices(ROWS))
    periods = rows(engine, tenant_id, "billing_period", "billing_period_start")
    assert [(p["billing_period_start"], p["billing_period_status"]) for p in periods] == [
        (date(2026, 8, 1), "Closed"),
        (date(2026, 9, 1), "Closed"),
        (date(2026, 10, 1), "Open"),
    ]
    assert periods[1]["as_of"] == datetime(2026, 10, 3, 6, 0, tzinfo=UTC)
    assert periods[2]["as_of"] == AT


def test_a_second_run_updates_rather_than_doubling(engine: Engine, tenant_id: UUID) -> None:
    run(engine, tenant_id, FakeInvoices(ROWS))
    run(engine, tenant_id, FakeInvoices(ROWS))
    assert len(rows(engine, tenant_id, "invoice_detail", "invoice_id")) == 3
    assert len(rows(engine, tenant_id, "billing_period", "billing_period_start")) == 3


def test_a_credit_memo_is_stored_beside_and_does_not_close_a_period(
    engine: Engine, tenant_id: UUID
) -> None:
    issued = datetime(2026, 9, 20, 6, 0, tzinfo=UTC)
    memo = Invoice(
        invoice_id="cm-1",
        invoice_type=InvoiceType.CREDIT_MEMO,
        original_invoice_id="inv-2026-08",
        billing_account_id="111122223333",
        billing_period_start=date(2026, 8, 1),
        billing_period_end=date(2026, 9, 1),
        invoice_issuer_name="Fake",
        billing_currency="USD",
        billed_cost_before_tax=Decimal("-5"),
        tax=Decimal("0"),
        billed_cost=Decimal("-5"),
        issued_at=issued,
        due_date=None,
        as_of=issued,
        collected_at=AT,
    )
    run(engine, tenant_id, StubInvoices([memo]))
    (stored,) = rows(engine, tenant_id, "invoice_detail", "invoice_id")
    assert stored["original_invoice_id"] == "inv-2026-08"
    statuses = {
        p["billing_period_start"]: p["billing_period_status"]
        for p in rows(engine, tenant_id, "billing_period", "billing_period_start")
    }
    assert statuses[date(2026, 8, 1)] == "Open"


def test_a_failed_read_writes_nothing(engine: Engine, tenant_id: UUID) -> None:
    with pytest.raises(AccessDenied):
        run(engine, tenant_id, FakeInvoices(ROWS, failure=AccessDenied))
    assert rows(engine, tenant_id, "invoice_detail", "invoice_id") == []
    assert rows(engine, tenant_id, "billing_period", "billing_period_start") == []


@pytest.mark.parametrize(
    ("column", "value"),
    [("billing_currency", "usd"), ("invoice_type", "PAYMENT_RECEIPT")],
)
def test_the_database_refuses_what_the_domain_refuses(
    engine: Engine, tenant_id: UUID, column: str, value: str
) -> None:
    values = {
        "pk": uuid4(),
        "t": tenant_id,
        "run": uuid4(),
        "billing_currency": "USD",
        "invoice_type": "INVOICE",
        "at": AT,
    }
    values[column] = value
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO invoice_detail (invoice_detail_pk, tenant_id, ingest_run_id, "
                "invoice_id, invoice_detail_id, invoice_type, billing_account_id, "
                "billing_period_start, billing_period_end, invoice_issuer_name, "
                "billing_currency, billed_cost_before_tax, tax, billed_cost, issued_at, "
                "as_of, collected_at) VALUES (:pk, :t, :run, 'x', 'x', :invoice_type, 'p', "
                "'2026-08-01', '2026-09-01', 'Fake', :billing_currency, 1, 0, 1, :at, :at, :at)"
            ),
            values,
        )


def test_the_database_refuses_a_credit_memo_that_names_nothing(
    engine: Engine, tenant_id: UUID
) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO invoice_detail (invoice_detail_pk, tenant_id, ingest_run_id, "
                "invoice_id, invoice_detail_id, invoice_type, billing_account_id, "
                "billing_period_start, billing_period_end, invoice_issuer_name, "
                "billing_currency, billed_cost_before_tax, tax, billed_cost, issued_at, "
                "as_of, collected_at) VALUES (:pk, :t, :run, 'x', 'x', 'CREDIT_MEMO', 'p', "
                "'2026-08-01', '2026-09-01', 'Fake', 'USD', -1, 0, -1, :at, :at, :at)"
            ),
            {"pk": uuid4(), "t": tenant_id, "run": uuid4(), "at": AT},
        )
