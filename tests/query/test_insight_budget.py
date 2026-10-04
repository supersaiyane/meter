"""The budget and the cost of an exchange, as arithmetic. TASK-P7-007.

The integration tests in `tests/api/test_assistant_budget.py` exhaust a real budget. These
pin the sentence a spent budget says and the dates it is counted between, because a
budget that resets on the wrong day is one nobody can plan around.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

from finops_core.domain.insight import Gap
from finops_core.ports.llm import TokenUsage
from finops_query.insight import budget_refusal, estimated_cost, month_start, next_month_start

AT = datetime(2026, 10, 4, 9, 30, tzinfo=UTC)


def test_a_month_with_budget_left_refuses_nothing() -> None:
    assert budget_refusal(spent=1_999_999, budget=2_000_000, at=AT) is None


def test_a_spent_month_refuses_naming_the_ceiling_the_spend_and_the_reset() -> None:
    refusal = budget_refusal(spent=2_000_000, budget=2_000_000, at=AT)

    assert refusal is not None
    assert refusal.gap is Gap.BUDGET
    for said in ("2000000 tokens", "October 2026", "2026-11-01", "METER_ASSISTANT_MONTHLY"):
        assert said in refusal.reason, said


def test_december_resets_on_the_first_of_january() -> None:
    assert next_month_start(datetime(2026, 12, 31, 23, 0, tzinfo=UTC)) == datetime(
        2027, 1, 1, tzinfo=UTC
    )


def test_a_month_is_counted_in_utc_whatever_zone_the_clock_reads_in() -> None:
    """Midnight on the first in a zone ahead of UTC is still the previous month in UTC."""
    ahead = timezone(timedelta(hours=5, minutes=30))
    first_local = datetime(2026, 11, 1, 2, 0, tzinfo=ahead)
    assert month_start(first_local) == datetime(2026, 10, 1, tzinfo=UTC)


def test_the_cost_of_an_exchange_is_priced_per_direction() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=200_000)
    cost = estimated_cost(
        usage, input_per_million=Decimal("3.00"), output_per_million=Decimal("15.00")
    )
    assert cost == Decimal("6.00")
