"""Each invoice beside Meter's billed cost, over a real database. FEAT-076, TASK-P10-004.

P10 spec sections 5.4 and 5.5, and the plan's criteria: every state through the route, the tax
apart, a credit memo beside what it corrects, a failed read never shown as a zero, and a
narrowed reader refused by type while a reader of the whole payer reads the same rows.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_api.routes.reconciliation import NOT_READ, PAYER_WIDE
from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.invoice import Invoice, InvoiceType
from finops_core.domain.tenant import Scope
from finops_ingest.collectors.invoices import InvoiceCollector
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext
from tests.api.test_query_routes import auth, client_for

pytestmark = pytest.mark.integration

AT = datetime(2026, 10, 7, 6, 0, tzinfo=UTC)
AUG, SEP, OCT, NOV = date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)
MINE = "111122223333"
PATH = "/api/v1/cost/reconciliation"

INSERT_COST = text(
    "INSERT INTO cost_focus_daily (tenant_id, ingest_run_id, source_fingerprint, as_of, "
    "collected_at, billing_account_id, sub_account_id, billing_period_start, "
    "billing_period_end, charge_period_start, charge_period_end, provider_name, "
    "service_name, region_id, resource_id, charge_category, billed_cost, effective_cost, "
    "list_cost, contracted_cost, tags, billing_currency, invoice_id) "
    "VALUES (:t, :run, :fingerprint, :at, :at, :payer, :a, :period, :period_end, :period, "
    ":period, 'aws', 'AmazonEC2', 'eu-west-1', :resource, :category, :cost, :cost, :cost, "
    ":cost, '{}'::jsonb, :currency, :invoice)"
)
FAILED_READ = text(
    "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, idempotency_key, "
    "started_at, finished_at, status, error_type, error_detail, as_of_window_start, "
    "as_of_window_end) VALUES (:id, :t, 'invoices', 'billing:invoices', :key, :at, :at, "
    "'FAILED', 'AccessDenied', 'not permitted', :at, :at)"
)


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module writes cost rows into monthly partitions, and gives them back. See conftest."""


def everything(tenant: UUID) -> Scope:
    return Scope(tenant_id=tenant, is_global=True, accounts=frozenset())


def only(tenant: UUID, account: str) -> Scope:
    return Scope(
        tenant_id=tenant,
        is_global=False,
        accounts=frozenset({AccountKey(provider=Provider.AWS, account_id=account)}),
    )


def cost(
    engine: Engine,
    tenant: UUID,
    *,
    invoice: str | None,
    amount: str,
    period: date = AUG,
    category: str = "Usage",
    currency: str = "USD",
) -> None:
    end = date(period.year + period.month // 12, period.month % 12 + 1, 1)
    with engine.begin() as connection:
        ensure_partition(connection, "cost_focus_daily", period)
        connection.execute(
            INSERT_COST,
            {
                "t": tenant,
                "run": uuid4(),
                "fingerprint": uuid4().hex,
                "payer": MINE,
                "a": MINE,
                "period": period,
                "period_end": end,
                "resource": f"r-{uuid4().hex[:8]}",
                "category": category,
                "cost": Decimal(amount),
                "currency": currency,
                "invoice": invoice,
                "at": AT,
            },
        )


def invoice(
    invoice_id: str,
    before_tax: str,
    tax: str = "0",
    *,
    period: date = AUG,
    currency: str = "USD",
    kind: InvoiceType = InvoiceType.INVOICE,
    original: str | None = None,
) -> Invoice:
    issued = datetime(period.year, period.month, 28, 6, 0, tzinfo=UTC)
    end = date(period.year + period.month // 12, period.month % 12 + 1, 1)
    return Invoice(
        invoice_id=invoice_id,
        invoice_type=kind,
        original_invoice_id=original,
        billing_account_id=MINE,
        billing_period_start=period,
        billing_period_end=end,
        invoice_issuer_name="Fake",
        billing_currency=currency,
        billed_cost_before_tax=Decimal(before_tax),
        tax=Decimal(tax),
        billed_cost=Decimal(before_tax) + Decimal(tax),
        issued_at=issued,
        due_date=None,
        as_of=issued,
        collected_at=AT,
    )


class Invoices:
    def __init__(self, found: Iterable[Invoice]) -> None:
        self._found = tuple(found)

    def invoices(self, start: date, end: date) -> Iterable[Invoice]:
        return tuple(i for i in self._found if start <= i.billing_period_start < end)


def collect(engine: Engine, tenant: UUID, *found: Invoice) -> None:
    unit = WorkUnit(
        tenant_id=tenant,
        collector="invoices",
        window_start=AT,
        window_end=AT,
        account=None,
        region=None,
    )
    with engine.begin() as connection:
        InvoiceCollector(Invoices(found), clock=lambda: AT)(
            CollectorContext(unit=unit, connection=connection, run_id=uuid4())
        )


def get(
    engine: Engine,
    tenant: UUID,
    settings: Settings,
    period: date | None = None,
    scope: Scope | None = None,
    expect: int = 200,
) -> Any:
    client, token = client_for(engine, scope or everything(tenant), settings)
    query = "" if period is None else f"?period={period.isoformat()}"
    response = client.get(PATH + query, headers=auth(token))
    assert response.status_code == expect, response.text
    return response.json()


def one(body: Any) -> Any:
    found = body["data"]["invoices"]
    assert len(found) == 1, found
    return found[0]


# --- the states -------------------------------------------------------------


def test_an_invoice_its_rows_add_up_to_is_matched(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    cost(engine, tenant_id, invoice="inv-08", amount="60")
    cost(engine, tenant_id, invoice="inv-08", amount="40")
    cost(engine, tenant_id, invoice="inv-08", amount="10", category="Tax")
    collect(engine, tenant_id, invoice("inv-08", "100", "10"))
    body = get(engine, tenant_id, settings, AUG)
    found = one(body)
    assert found["state"] == "Matched"
    assert Decimal(found["meter_before_tax"]) == Decimal("100")
    assert Decimal(found["meter_tax"]) == Decimal("10")
    assert Decimal(found["difference_before_tax"]) == 0
    assert body["data"]["period_status"] == "Closed"
    assert body["data"]["state"] is None
    assert Decimal(body["data"]["tolerance"]) == Decimal("0.0001")


def test_a_mismatch_shows_the_difference_meter_less_invoice(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    cost(engine, tenant_id, invoice="inv-08", amount="97.50")
    collect(engine, tenant_id, invoice("inv-08", "100"))
    found = one(get(engine, tenant_id, settings, AUG))
    assert found["state"] == "Mismatched"
    assert Decimal(found["difference_before_tax"]) == Decimal("-2.50")


def test_tax_is_compared_apart_from_the_amount_before_it(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    cost(engine, tenant_id, invoice="inv-08", amount="105")
    cost(engine, tenant_id, invoice="inv-08", amount="5", category="Tax")
    collect(engine, tenant_id, invoice("inv-08", "100", "10"))
    found = one(get(engine, tenant_id, settings, AUG))
    assert found["state"] == "Mismatched"
    assert Decimal(found["difference_tax"]) == Decimal("-5")


def test_an_invoice_no_row_carries_is_no_rows_with_no_figure(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    cost(engine, tenant_id, invoice=None, amount="40")
    collect(engine, tenant_id, invoice("mp-08", "40"))
    found = one(get(engine, tenant_id, settings, AUG))
    assert found["state"] == "No rows"
    assert found["meter_before_tax"] is None
    assert found["difference_before_tax"] is None


def test_rows_in_another_currency_are_not_converted(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    cost(engine, tenant_id, invoice="inv-08", amount="100", currency="EUR")
    collect(engine, tenant_id, invoice("inv-08", "100"))
    found = one(get(engine, tenant_id, settings, AUG))
    assert found["state"] == "Currency differs"
    assert found["meter_before_tax"] is None


def test_a_credit_memo_is_listed_beside_the_invoice_it_corrects(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    cost(engine, tenant_id, invoice="inv-08", amount="100")
    cost(engine, tenant_id, invoice="cm-08", amount="-5")
    collect(
        engine,
        tenant_id,
        invoice("inv-08", "100"),
        invoice("cm-08", "-5", kind=InvoiceType.CREDIT_MEMO, original="inv-08"),
    )
    found = get(engine, tenant_id, settings, AUG)["data"]["invoices"]
    by_id = {row["invoice_id"]: row for row in found}
    assert by_id["cm-08"]["original_invoice_id"] == "inv-08"
    assert by_id["cm-08"]["invoice_type"] == "CREDIT_MEMO"
    assert {row["state"] for row in found} == {"Matched"}


def test_a_period_with_no_invoice_yet_is_period_open(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    collect(engine, tenant_id, invoice("inv-08", "100"))
    body = get(engine, tenant_id, settings, OCT)
    assert body["data"]["state"] == "Period open"
    assert body["data"]["period_status"] == "Open"
    assert body["data"]["invoices"] == []


def test_a_failed_read_is_not_readable_with_its_cause_and_never_a_zero(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    with engine.begin() as connection:
        connection.execute(
            FAILED_READ, {"id": uuid4(), "t": tenant_id, "key": uuid4().hex, "at": AT}
        )
    body = get(engine, tenant_id, settings, SEP)
    assert body["data"]["state"] == "Not readable"
    assert body["data"]["cause"] == "AccessDenied"
    assert body["data"]["invoices"] == []


def test_a_period_never_read_is_not_found_rather_than_open(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    collect(engine, tenant_id, invoice("inv-08", "100"))
    body = get(engine, tenant_id, settings, NOV, expect=404)
    assert body["detail"] == NOT_READ


def test_with_no_period_asked_it_reads_the_newest_closed_one(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    collect(engine, tenant_id, invoice("inv-08", "100"), invoice("inv-09", "50", period=SEP))
    body = get(engine, tenant_id, settings)
    assert body["data"]["period"] == SEP.isoformat()
    assert one(body)["invoice_id"] == "inv-09"


def test_a_day_inside_a_period_reads_that_period(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    collect(engine, tenant_id, invoice("inv-08", "100"))
    assert get(engine, tenant_id, settings, date(2026, 8, 17))["data"]["period"] == "2026-08-01"


# --- the scope rule ----------------------------------------------------------


def test_a_narrowed_reader_is_refused_by_type_where_the_whole_payer_reads(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Two principals over the same rows. The narrowed one reads no total, not a smaller one."""
    cost(engine, tenant_id, invoice="inv-08", amount="100")
    collect(engine, tenant_id, invoice("inv-08", "100"))
    assert one(get(engine, tenant_id, settings, AUG))["state"] == "Matched"
    refused = get(engine, tenant_id, settings, AUG, scope=only(tenant_id, MINE), expect=403)
    assert refused["detail"] == PAYER_WIDE
    assert "data" not in refused


def test_it_exports_one_row_per_invoice(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    cost(engine, tenant_id, invoice="inv-08", amount="100")
    collect(engine, tenant_id, invoice("inv-08", "100"), invoice("mp-08", "40"))
    client, token = client_for(engine, everything(tenant_id), settings)
    response = client.get(f"{PATH}?period={AUG.isoformat()}&format=csv", headers=auth(token))
    assert response.status_code == 200, response.text
    body = response.text
    assert "inv-08" in body and "mp-08" in body
    assert "No rows" in body and "Matched" in body
