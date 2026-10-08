"""Meter's billed cost beside the invoice the provider issued for it.

FEAT-076, TASK-P10-004, P10 spec section 5.4. Pure: the route reads an invoice and Meter's sums
over the rows carrying its id, and this decides what the difference between them means.

**Before tax and tax apart.** An invoice states both, and a sum that matched in total while the
tax was wrong would be a match nobody should believe. Both must be within the tolerance.

**One currency or none.** Rows billed in a currency other than the invoice's are a state of
their own, never converted: a rate Meter chose would be a figure Meter produced, and the point of
reading the invoice is to hold a figure Meter did not.

**A failure is never a figure.** No rows, another currency and an unreadable read carry no
Meter amount and no difference, so nothing downstream can render one of them as a zero.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Final


class ReconciliationState(StrEnum):
    """The six answers of spec section 5.4, in the words the screen shows."""

    MATCHED = "Matched"
    MISMATCHED = "Mismatched"
    #: The billing period has no issued invoice yet.
    PERIOD_OPEN = "Period open"
    #: An invoice names an id no cost row carries: a Marketplace invoice, or a gap in the bill.
    NO_ROWS = "No rows"
    CURRENCY_DIFFERS = "Currency differs"
    #: The latest read of the invoices failed, and its typed cause says why.
    NOT_READABLE = "Not readable"


#: 0.01 percent of the invoice's amount, modelled rather than measured: rounding between line
#: items and an invoice is expected, and the figure is revisited once a real invoice has been
#: compared, P10 spec section 5.4.
TOLERANCE: Final = Decimal("0.0001")
#: The least difference that counts. An invoice is stated in cents, so a difference under one
#: cent is the invoice's own rounding, and without this floor a zero tax line would demand an
#: exact match from a sum of ten decimal place rows.
CENT: Final = Decimal("0.01")


@dataclass(frozen=True, kw_only=True)
class InvoicedSum:
    """Meter's billed cost on the rows carrying one invoice id, in one currency."""

    #: None where the rows predate FOCUS 1.2's currency column.
    currency: str | None
    before_tax: Decimal
    tax: Decimal


@dataclass(frozen=True, kw_only=True)
class Comparison:
    """One invoice's answer. The differences are Meter's figure less the invoice's."""

    state: ReconciliationState
    meter_before_tax: Decimal | None = None
    meter_tax: Decimal | None = None
    difference_before_tax: Decimal | None = None
    difference_tax: Decimal | None = None


def allowance(amount: Decimal) -> Decimal:
    """How far Meter's figure may differ from an invoice amount and still match it."""
    return max(abs(amount) * TOLERANCE, CENT)


def compare(
    *, currency: str, before_tax: Decimal, tax: Decimal, sums: Sequence[InvoicedSum]
) -> Comparison:
    """An invoice's amounts beside Meter's sums over the rows carrying its id."""
    if not sums:
        return Comparison(state=ReconciliationState.NO_ROWS)
    if any(found.currency != currency for found in sums):
        return Comparison(state=ReconciliationState.CURRENCY_DIFFERS)
    meter_before_tax = sum((found.before_tax for found in sums), Decimal(0))
    meter_tax = sum((found.tax for found in sums), Decimal(0))
    difference_before_tax = meter_before_tax - before_tax
    difference_tax = meter_tax - tax
    within = abs(difference_before_tax) <= allowance(before_tax) and abs(
        difference_tax
    ) <= allowance(tax)
    return Comparison(
        state=ReconciliationState.MATCHED if within else ReconciliationState.MISMATCHED,
        meter_before_tax=meter_before_tax,
        meter_tax=meter_tax,
        difference_before_tax=difference_before_tax,
        difference_tax=difference_tax,
    )


def without_invoice(*, read_failed: bool) -> ReconciliationState:
    """What a period with no invoice to compare says.

    A failed read wins over an open period, because a period whose invoices could not be read
    may well have one, and saying it is open would be a guess presented as a fact.
    """
    return ReconciliationState.NOT_READABLE if read_failed else ReconciliationState.PERIOD_OPEN
