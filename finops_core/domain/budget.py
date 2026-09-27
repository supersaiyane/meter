"""What somebody said this should cost, and whether it is on course.

FEAT-060. The gap three separate sources named independently: the 2026-09-26 IBM Turbonomic
review has no budget in it either, the FinOpsForge checklist puts budget against actual at the
top of the finance dashboard and a red amber green budget status at the top of the executive
one, and this product had no budget entity at all.

**A budget is collected, not entered.** Everything in Meter is a fact read from a provider and
carries the two timestamps that say when it was true and when we fetched it. A budget typed
into Meter would be the first thing in the product with no provenance, and it would need a
write API, a form, validation and an audit trail: a week of work that changes what this product
is. Reading the provider's own budgets keeps the shape, costs a day, and has the property that
the number Meter shows is the number the provider is already alerting on. The cost is real and
is recorded as ISS-210: an organization that tracks budgets in a spreadsheet has none here.

**Pace, not forecast.** `status_of` compares spend against where the period has got to. Sixty
percent through the month with eighty percent spent is at risk, and that is arithmetic anybody
can check. A forecast would be a better answer and it is FEAT-048, which ADR-0015 constrains
with four conditions, none of which are met. Calling a pace projection a forecast is how a
model nobody validated ends up in a board pack.

**Three states and the middle one is the useful one.** Over is too late to act on and under is
not news. At risk is the only one that asks somebody to do something, so the threshold that
produces it is configuration rather than a constant, for the reason ADR-0012 gives about
cadence: a number in code is a number nobody can argue with.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from finops_core.domain.fact import Fact


class BudgetScope(StrEnum):
    """What a budget is drawn around.

    The provider's own vocabulary, narrowed to what this product can join to. A budget over a
    tag or a filter expression we cannot reproduce is read and reported as UNSUPPORTED rather
    than silently matched against the wrong spend, because a budget compared to the wrong
    actual is worse than a budget nobody shows.
    """

    ACCOUNT = "ACCOUNT"
    SERVICE = "SERVICE"
    #: The whole payer. What an executive view asks about.
    ALL = "ALL"
    #: Read, understood to exist, and not joinable. Never matched to a number.
    UNSUPPORTED = "UNSUPPORTED"


class BudgetStatus(StrEnum):
    """Where a budget stands, as a word.

    `UNKNOWN` is not a fourth colour on a traffic light. It is the answer when the period has
    not started, when no spend has been collected for it, or when the budget's scope is one we
    cannot join, and it exists so that none of those three renders as green.
    """

    UNDER = "UNDER"
    AT_RISK = "AT_RISK"
    OVER = "OVER"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, kw_only=True)
class Budget(Fact):
    """One budget as the provider holds it."""

    #: The provider's identifier, which is the name for AWS Budgets. Stable across a period,
    #: which is what lets a budget keep its identity when its limit is revised.
    budget_id: str
    name: str
    scope: BudgetScope
    #: What the scope names: an account identifier, a service name, or empty for ALL.
    scope_value: str
    limit: Decimal
    currency: str
    period_start: date
    period_end: date


@dataclass(frozen=True)
class BudgetStanding:
    """A budget, the spend against it, and what that means.

    Every derived field is here rather than computed in a template, so the screen and the API
    cannot disagree about whether something is over.
    """

    budget: Budget
    #: Measured, from the bill. None where no cost has been collected for the period, which is
    #: not zero: an estate whose first ingest has not run has not spent nothing.
    actual: Decimal | None
    status: BudgetStatus
    #: How far through the period we are, nought to one. The denominator of the pace rule.
    elapsed: Decimal
    #: Spend as a fraction of the limit. None when there is no actual.
    used: Decimal | None

    @property
    def remaining(self) -> Decimal | None:
        if self.actual is None:
            return None
        return self.budget.limit - self.actual


def status_of(
    *,
    limit: Decimal,
    actual: Decimal | None,
    elapsed: Decimal,
    at_risk_when_ahead_by: Decimal,
    joinable: bool = True,
) -> BudgetStatus:
    """Where a budget stands, from pace rather than from a forecast.

    Args:
        limit: What was budgeted.
        actual: What has been spent, or None where no cost was collected.
        elapsed: How far through the period, nought to one.
        at_risk_when_ahead_by: How far ahead of pace counts as at risk, as a fraction. At 0.1,
            spending eighty percent of a budget sixty percent of the way through is at risk.
            Configuration, because a number in code deciding when to warn somebody about their
            own money is a number nobody can argue with.
        joinable: False where the budget's scope is one we cannot reproduce, in which case
            there is no honest actual to compare and the answer is UNKNOWN rather than green.

    Unknown in four cases and green in none of them: an unjoinable scope, no collected spend, a
    period that has not started, and a limit of zero, which is a budget that cannot be under.
    """
    if not joinable or actual is None or elapsed <= 0 or limit <= 0:
        return BudgetStatus.UNKNOWN
    used = actual / limit
    if used >= 1:
        return BudgetStatus.OVER
    # Ahead of where the calendar says it should be, by more than the configured margin.
    if used - elapsed > at_risk_when_ahead_by:
        return BudgetStatus.AT_RISK
    return BudgetStatus.UNDER


def elapsed_fraction(*, start: date, end: date, today: date) -> Decimal:
    """How far through a period today is, nought to one.

    Clamped at both ends, because a period that has not started is nought rather than negative
    and one that has closed is one rather than more: a pace rule fed a negative denominator
    produces a status that is confidently wrong.
    """
    span = (end - start).days
    if span <= 0:
        return Decimal("0")
    through = (today - start).days
    if through <= 0:
        return Decimal("0")
    if through >= span:
        return Decimal("1")
    return (Decimal(through) / Decimal(span)).quantize(Decimal("0.0001"))
