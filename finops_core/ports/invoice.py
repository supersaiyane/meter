"""Reading the invoices a provider issued to the payer.

FEAT-076. Read only, constraint 6: nothing here pays, disputes or changes an invoice.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Protocol, runtime_checkable

from finops_core.domain.invoice import Invoice


@runtime_checkable
class InvoiceSource(Protocol):
    """Reads the payer's invoices for a span of billing periods."""

    def invoices(self, start: date, end: date) -> Iterable[Invoice]:
        """Every invoice and credit memo issued for billing periods from `start` up to `end`.

        A period with no invoice yet returns nothing for it, which is not a failure: it is a
        period still open, and the comparison says so.

        Raises:
            AccessDenied: The session may not read invoices at the payer.
            Throttled: The provider rejected the call rate.
            Unreachable: The endpoint did not answer.
            SchemaDrift: A response held an amount, a currency or a date this cannot read.
        """
        ...
