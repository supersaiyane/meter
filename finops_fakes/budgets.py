"""Budgets for an estate, including the ones nothing can be compared against.

FEAT-060. ADR-0022 keeps this out of the production packages.

**Four budgets and only two of them join.** One over the whole payer, one over an account, one
over a tag expression, and one measuring usage rather than cost. That ratio is deliberate: the
first thing a finance reader wants to know is how many of their budgets this product can
actually track, and a fake where everything joined would leave the answer to that question
rendered by nothing anybody runs.

**One of the two that join is already over.** A demo estate where every budget is green shows
the one state nobody needs a tool for.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal

from finops_core.domain.budget import Budget, BudgetScope

AT = datetime(2026, 9, 26, 6, 0, tzinfo=UTC)
START = date(2026, 9, 1)
END = date(2026, 10, 1)

_BUDGETS: tuple[tuple[str, BudgetScope, str, str], ...] = (
    # The payer wide one, which is the figure an executive view asks for. Set below the
    # estate's actual run rate on purpose, so the demo has something amber to show.
    ("Cloud, all accounts", BudgetScope.ALL, "", "12500"),
    # One account, comfortably inside its limit.
    ("Platform team", BudgetScope.ACCOUNT, "fake-platform-a", "6000"),
    # A tag expression. Read, counted, and never matched to a number, because the intersection
    # it describes is not a slice this product computes.
    ("Cost centre 4471", BudgetScope.UNSUPPORTED, "", "9000"),
    # A usage budget. Its limit is in hours and comparing it to a month of money would produce
    # a status that is green and meaningless.
    ("EC2 hours", BudgetScope.UNSUPPORTED, "", "40000"),
)


class FakeBudgets:
    """The payer's budgets, two joinable and two not."""

    def budgets(self) -> Iterable[Budget]:
        return tuple(
            Budget(
                budget_id=name,
                name=name,
                scope=scope,
                scope_value=value,
                limit=Decimal(limit),
                currency="USD",
                period_start=START,
                period_end=END,
                as_of=AT,
                collected_at=AT,
            )
            for name, scope, value, limit in _BUDGETS
        )
