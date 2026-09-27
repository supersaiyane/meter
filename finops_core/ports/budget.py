"""Reading the budgets a provider already holds.

FEAT-060. Read only, constraint 6: nothing here creates, edits or deletes a budget in a
member account, and the provider's own alerting on them is untouched.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from finops_core.domain.budget import Budget


@runtime_checkable
class BudgetSource(Protocol):
    """Reads budgets from the payer."""

    def budgets(self) -> Iterable[Budget]:
        """Every budget the payer holds.

        A budget whose scope this product cannot reproduce is returned with
        `BudgetScope.UNSUPPORTED` rather than dropped. Dropping it would make an estate with
        ten budgets over tag expressions look like an estate with no budgets, and the
        difference between those is the whole question a finance reader arrived with.

        Raises:
            AccessDenied: The session may not read budgets at the payer.
            NotOptedIn: The account has never used the budgets service.
            Throttled: The provider rejected the call rate.
            Unreachable: The endpoint did not answer.
            SchemaDrift: A response held a time unit or a limit this adapter cannot read.
        """
        ...
