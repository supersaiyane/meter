"""Invoices, the billing periods they close, and Meter's billed cost under each. FEAT-076.

Three reads for one comparison, TASK-P10-004, each through the audited path. The invoice and
period tables are `PayerWide` in the guard; the cost rows are not, and the route refuses a
narrowed reader before it reaches them, so a sum over some accounts can never be set beside an
invoice over all of them.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any, ClassVar, cast

from sqlalchemy import Row, Select, Table, case, func

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_core.domain.invoice import BillingPeriodStatus
from finops_core.domain.reconciliation import InvoicedSum
from finops_core.domain.tenant import Scope

TAX = "Tax"


def _fetch(
    repository: ScopedRepository, scope: Scope, statement: Any
) -> Sequence[Row[*tuple[Any, ...]]]:
    """A projected read through the audited path, cast once as `cost.py` does."""
    return repository.fetch(scope, cast("Select[*tuple[object, ...]]", statement))


class InvoiceRepository(ScopedRepository):
    """Invoices and credit memos as read from the payer."""

    table: ClassVar[Table] = models.invoice_detail
    resource: ClassVar[str] = "invoice_detail"

    def for_period(self, scope: Scope, period: date) -> Sequence[Row[*tuple[Any, ...]]]:
        """Every invoice issued for a period, by issuer then id, so a credit memo sits near
        what it corrects and each issuer's invoices stay together."""
        statement = (
            self.scoped_select(scope)
            .where(self.table.c.billing_period_start == period)
            .order_by(self.table.c.invoice_issuer_name, self.table.c.invoice_id)
        )
        return _fetch(self, scope, statement)


class BillingPeriodRepository(ScopedRepository):
    """Which months the payer has been invoiced for."""

    table: ClassVar[Table] = models.billing_period
    resource: ClassVar[str] = "billing_period"

    def one(self, scope: Scope, period: date) -> Row[*tuple[Any, ...]] | None:
        statement = self.scoped_select(scope).where(self.table.c.billing_period_start == period)
        found = _fetch(self, scope, statement)
        return found[0] if found else None

    def latest(self, scope: Scope) -> date | None:
        """The newest closed period, which is the newest with an invoice to compare, or the
        newest read at all where none has closed yet."""
        closed = self._newest(scope, closed_only=True)
        return closed if closed is not None else self._newest(scope, closed_only=False)

    def _newest(self, scope: Scope, *, closed_only: bool) -> date | None:
        statement = self.scoped_select(scope).with_only_columns(
            func.max(self.table.c.billing_period_start)
        )
        if closed_only:
            statement = statement.where(
                self.table.c.billing_period_status == BillingPeriodStatus.CLOSED.value
            )
        found = _fetch(self, scope, statement)
        newest: date | None = found[0][0] if found else None
        return newest


class InvoicedCostRepository(ScopedRepository):
    """Meter's billed cost per invoice id, the figure each invoice is compared with."""

    table: ClassVar[Table] = models.cost_focus_daily
    resource: ClassVar[str] = "cost_focus_daily"

    def sums(self, scope: Scope, period: date) -> dict[str, tuple[InvoicedSum, ...]]:
        """Billed cost before tax and tax apart, per invoice id and currency, for one period.

        Grouped by currency as well as by invoice, so rows in two currencies under one invoice
        arrive as two sums and the comparison can say so rather than adding them.
        """
        columns = self.table.c
        is_tax = columns.charge_category == TAX
        statement = (
            self.scoped_select(scope)
            .with_only_columns(
                columns.invoice_id,
                columns.billing_currency,
                func.coalesce(func.sum(case((is_tax, 0), else_=columns.billed_cost)), 0),
                func.coalesce(func.sum(case((is_tax, columns.billed_cost), else_=0)), 0),
            )
            .where(columns.billing_period_start == period)
            .where(columns.invoice_id.is_not(None))
            .group_by(columns.invoice_id, columns.billing_currency)
        )
        found: dict[str, list[InvoicedSum]] = defaultdict(list)
        for invoice_id, currency, before_tax, tax in _fetch(self, scope, statement):
            found[str(invoice_id)].append(
                InvoicedSum(currency=currency, before_tax=Decimal(before_tax), tax=Decimal(tax))
            )
        return {invoice_id: tuple(sums) for invoice_id, sums in found.items()}
