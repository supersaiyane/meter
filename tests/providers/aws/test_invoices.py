"""The AWS invoice adapter against a stubbed Invoicing client. TASK-P10-003.

P10 spec section 8: pages, a credit memo, AccessDenied and throttling. The response literals
follow the `ListInvoiceSummaries` shape in botocore 1.43.108's service model, API version
2024-12-01, and nothing here has met a real payer, ISS-002 and ISS-003.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from botocore.exceptions import ClientError

from finops_core.domain.invoice import InvoiceType
from finops_core.errors import AccessDenied, SchemaDrift, Throttled
from finops_core.ports.invoice import InvoiceSource
from finops_providers.aws.invoices import AwsInvoices

PAYER = "111122223333"
NOW = datetime(2026, 10, 7, 6, 0, tzinfo=UTC)
ISSUED = datetime(2026, 9, 3, 6, 0, tzinfo=UTC)


def summary(
    invoice_id: str = "inv-2026-08",
    month: int = 8,
    kind: str = "INVOICE",
    before: str | None = "100.00",
    total: str | None = "110.00",
    taxes: str | None = "10.00",
    currency: str = "USD",
    **extra: Any,
) -> dict[str, Any]:
    amount: dict[str, Any] = {
        "TotalAmountBeforeTax": before,
        "TotalAmount": total,
        "CurrencyCode": currency,
    }
    if taxes is not None:
        amount["AmountBreakdown"] = {"Taxes": {"TotalAmount": taxes, "Breakdown": []}}
    return {
        "AccountId": PAYER,
        "InvoiceId": invoice_id,
        "IssuedDate": ISSUED,
        "DueDate": datetime(2026, 10, 3, tzinfo=UTC),
        "Entity": {"InvoicingEntity": "Amazon Web Services, Inc."},
        "BillingPeriod": {"Month": month, "Year": 2026},
        "InvoiceType": kind,
        "BaseCurrencyAmount": amount,
        **extra,
    }


class _Paginator:
    def __init__(self, pages: dict[tuple[int, int], list[list[Any]]], failure: Exception | None):
        self._pages = pages
        self._failure = failure
        self.calls: list[dict[str, Any]] = []

    def paginate(self, **kwargs: Any) -> Iterator[dict[str, Any]]:
        self.calls.append(kwargs)
        if self._failure is not None:
            raise self._failure
        period = kwargs["Filter"]["BillingPeriod"]
        for page in self._pages.get((period["Year"], period["Month"]), []):
            yield {"InvoiceSummaries": page}


class _Client:
    def __init__(
        self,
        pages: dict[tuple[int, int], list[list[Any]]] | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.paginator = _Paginator(pages or {}, failure)

    def get_paginator(self, name: str) -> _Paginator:
        assert name == "list_invoice_summaries"
        return self.paginator


def adapter(client: _Client) -> AwsInvoices:
    return AwsInvoices(client=client, account_id=PAYER, clock=lambda: NOW)


def read(client: _Client) -> tuple[Any, ...]:
    return tuple(adapter(client).invoices(date(2026, 8, 1), date(2026, 10, 1)))


def test_it_is_an_invoice_source() -> None:
    assert isinstance(adapter(_Client()), InvoiceSource)


def test_each_billing_period_is_asked_for_by_its_period_at_the_payer() -> None:
    client = _Client()
    read(client)
    assert [call["Filter"] for call in client.paginator.calls] == [
        {"BillingPeriod": {"Month": 8, "Year": 2026}},
        {"BillingPeriod": {"Month": 9, "Year": 2026}},
    ]
    assert {call["Selector"]["Value"] for call in client.paginator.calls} == {PAYER}


def test_every_page_is_read_and_each_invoice_mapped() -> None:
    client = _Client({(2026, 8): [[summary()], [summary("inv-2026-08-mp", taxes="0")]]})
    found = read(client)
    assert [i.invoice_id for i in found] == ["inv-2026-08", "inv-2026-08-mp"]
    first = found[0]
    assert first.billing_period_start == date(2026, 8, 1)
    assert first.billing_period_end == date(2026, 9, 1)
    assert first.billed_cost_before_tax == Decimal("100.00")
    assert first.tax == Decimal("10.00")
    assert first.billed_cost == Decimal("110.00")
    assert first.billing_currency == "USD"
    assert first.invoice_issuer_name == "Amazon Web Services, Inc."
    assert first.as_of == ISSUED
    assert first.collected_at == NOW
    assert first.due_date == date(2026, 10, 3)


def test_a_credit_memo_keeps_the_invoice_it_corrects() -> None:
    memo = summary("cm-1", kind="CREDIT_MEMO", OriginalInvoiceId="inv-2026-07")
    (found,) = read(_Client({(2026, 8): [[memo]]}))
    assert found.invoice_type is InvoiceType.CREDIT_MEMO
    assert found.original_invoice_id == "inv-2026-07"


def test_a_payment_receipt_is_not_an_invoice_and_is_skipped() -> None:
    receipt = summary("pr-1", kind="PAYMENT_RECEIPT")
    assert read(_Client({(2026, 8): [[receipt]]})) == ()


def test_an_invoice_with_no_tax_breakdown_takes_its_tax_from_its_totals() -> None:
    (found,) = read(_Client({(2026, 8): [[summary(taxes=None)]]}))
    assert found.tax == Decimal("10.00")


def test_a_clock_behind_aws_never_reads_an_invoice_before_it_was_issued() -> None:
    early = AwsInvoices(
        client=_Client({(2026, 8): [[summary()]]}),
        account_id=PAYER,
        clock=lambda: datetime(2026, 9, 1, tzinfo=UTC),
    )
    (found,) = early.invoices(date(2026, 8, 1), date(2026, 9, 1))
    assert found.collected_at == found.as_of == ISSUED


@pytest.mark.parametrize(
    ("broken", "says"),
    [
        (summary(currency="usd"), "ISO 4217"),
        (summary(before=None), "missing an amount"),
        (summary(total="ten"), "has an amount"),
        (summary(InvoiceId=""), "no invoice id"),
        (summary(BillingPeriod={"Month": 13, "Year": 2026}), "billing period"),
        (summary(IssuedDate=None), "issue date"),
    ],
)
def test_what_cannot_be_read_is_schema_drift_and_never_a_zero(
    broken: dict[str, Any], says: str
) -> None:
    with pytest.raises(SchemaDrift, match=says):
        read(_Client({(2026, 8): [[broken]]}))


@pytest.mark.parametrize(
    ("code", "cause"),
    [("AccessDeniedException", AccessDenied), ("ThrottlingException", Throttled)],
)
def test_a_refused_call_is_raised_by_its_cause(code: str, cause: type[Exception]) -> None:
    failure = ClientError({"Error": {"Code": code, "Message": "no"}}, "ListInvoiceSummaries")
    with pytest.raises(cause):
        read(_Client(failure=failure))
