"""Budgets as AWS holds them.

FEAT-060.

**Unproved against a real account**, like every adapter in this package. The shapes below are
read from the AWS Budgets documentation and from nothing else, and the tests answer from a
literal. ISS-211.

**Only monthly cost budgets are joined.** AWS budgets can be monthly, quarterly, annual or a
fixed window, and can measure usage, coverage or utilization rather than cost. This product has
one thing to compare a budget against, which is a billing period's effective cost, so anything
else is read, kept, and marked `UNSUPPORTED`. The alternative is matching a quarterly usage
budget against a month of spend, which produces a number that is wrong and a status that is
green.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.domain.budget import Budget, BudgetScope
from finops_providers.aws.client import translate

COLLECTOR = "budgets"

#: The one time unit this product can compare against, because a billing period is a month.
MONTHLY = "MONTHLY"

#: The one measure that is money. COST is the only budget type whose limit is comparable to a
#: bill; USAGE, RI_UTILIZATION and the rest measure something else entirely.
COST = "COST"

#: How an AWS cost filter maps to something we can join. The key is AWS's, the value is ours.
#: Anything absent from here is a filter we cannot reproduce, which is reported rather than
#: guessed at.
FILTERS: dict[str, BudgetScope] = {
    "LinkedAccount": BudgetScope.ACCOUNT,
    "Service": BudgetScope.SERVICE,
}


def _system_clock() -> datetime:
    return datetime.now(UTC)


def scope_of(budget: Any) -> tuple[BudgetScope, str]:
    """What a budget is drawn around, and what it names.

    A budget with no filters covers everything the payer spends, which is the figure an
    executive view asks for. A budget with exactly one filter we recognise is joinable. A
    budget with two filters is not, because the intersection of an account and a service is a
    slice this product does not compute, and reporting it against either one alone would
    overstate the spend.
    """
    filters = budget.get("CostFilters") or {}
    if not filters:
        return BudgetScope.ALL, ""
    if len(filters) != 1:
        return BudgetScope.UNSUPPORTED, ""
    key, values = next(iter(filters.items()))
    scope = FILTERS.get(key)
    if scope is None or not values:
        return BudgetScope.UNSUPPORTED, ""
    if len(values) != 1:
        # A budget over three accounts is a real thing and its actual is the sum of three
        # slices. Honest to report as unsupported until that sum exists.
        return BudgetScope.UNSUPPORTED, ""
    return scope, str(values[0])


class AwsBudgets:
    """The payer's budgets, read and never written."""

    def __init__(self, *, client: Any, account_id: str, clock: Any = _system_clock) -> None:
        self._client = client
        # The payer, because DescribeBudgets is per account and budgets live at the payer.
        self._account_id = account_id
        self._clock = clock

    def budgets(self) -> Iterable[Budget]:
        at = self._clock()
        try:
            pages = self._client.get_paginator("describe_budgets").paginate(
                AccountId=self._account_id
            )
            found: list[Budget] = []
            for page in pages:
                for raw in page.get("Budgets") or ():
                    built = self._one(raw, at)
                    if built is not None:
                        found.append(built)
            return tuple(found)
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=self._account_id, collector=COLLECTOR) from failure

    def _one(self, raw: Any, at: datetime) -> Budget | None:
        name = str(raw.get("BudgetName") or "").strip()
        if not name:
            # A budget with no name has no stable identity across periods, so it cannot be
            # upserted and would arrive as a new row every run.
            return None

        period = raw.get("TimePeriod") or {}
        start, end = _as_date(period.get("Start")), _as_date(period.get("End"))
        if start is None or end is None:
            return None

        limit_raw = (raw.get("BudgetLimit") or {}).get("Amount")
        try:
            limit = Decimal(str(limit_raw))
        except (InvalidOperation, TypeError):
            # A limit that is not a number is schema drift, and a budget with no limit cannot
            # be compared to anything. Skipped rather than defaulted: a default of zero would
            # render as an estate that has overspent every budget it has.
            return None

        scope, value = scope_of(raw)
        if raw.get("TimeUnit") != MONTHLY or raw.get("BudgetType") != COST:
            # Kept, so the count is right, and marked so nothing joins it to a month of spend.
            scope = BudgetScope.UNSUPPORTED
            value = ""

        return Budget(
            budget_id=name,
            name=name,
            scope=scope,
            scope_value=value,
            limit=limit,
            currency=str((raw.get("BudgetLimit") or {}).get("Unit") or "USD"),
            period_start=start,
            period_end=end,
            as_of=at,
            collected_at=at,
        )


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None
