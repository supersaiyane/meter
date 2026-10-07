"""The refusal set. Questions the assistant must decline, and the reason it must give.

P7 spec section 11, set two, and the one that matters most. A product that answers these
is the product this one exists not to be.

Every case asserts the gap and the words naming what is missing, not only the outcome,
because a refusal for the wrong reason is a wrong answer. Telling somebody they lack
access when the truth is that a setting is off sends them to the wrong person, and the
setting stays off.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import Engine

from finops_core.config import Settings
from finops_core.domain.insight import Gap, Refusal
from finops_fakes.containers import PLATFORM_EKS
from tests.query.insight.harness import (
    IN_SCOPE,
    OUT_OF_SCOPE,
    answer,
    ask_as,
    asker,
    call,
    everything,
    everything_the_model_read,
    only,
    refuse,
    seed_bill,
)

pytestmark = pytest.mark.integration


def test_a_cluster_without_split_cost_allocation_is_refused_naming_the_setting(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Spec section 5.3's own example of a useful refusal."""
    seed_bill(engine, tenant_id, split=False)
    client, token = asker(engine, settings, everything(tenant_id))

    exchange, _ = ask_as(
        client,
        token,
        "What did the platform cluster's workloads cost last month?",
        call("t1", "get_container_cost"),
        answer(
            "The platform cluster cost {{total}}.",
            total=("t1", f"data.clusters[cluster_name={PLATFORM_EKS.name}].total"),
        ),
    )

    refusal = exchange.outcome
    assert isinstance(refusal, Refusal), refusal
    assert refusal.gap is Gap.FIGURE
    assert "split cost allocation" in refusal.reason.lower()
    assert refusal.screen == "/analyze/kubernetes-cost"


def test_an_account_outside_the_askers_scope_is_refused_as_not_visible(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed_bill(engine, tenant_id, split=False)
    client, token = asker(engine, settings, only(tenant_id, IN_SCOPE))

    exchange, model = ask_as(
        client,
        token,
        f"What did {OUT_OF_SCOPE} cost last month?",
        call("t1", "get_cost_by_account"),
        answer(
            "That account cost {{cost}}.",
            cost=("t1", f"data[name={OUT_OF_SCOPE}].effective_cost"),
        ),
    )

    refusal = exchange.outcome
    assert isinstance(refusal, Refusal), refusal
    assert refusal.gap is Gap.SCOPE
    assert OUT_OF_SCOPE in refusal.reason
    # And the guard is why, not the loop: the result the model read never held it.
    assert OUT_OF_SCOPE not in everything_the_model_read(model)


def test_a_question_needing_a_tool_that_does_not_exist_is_refused_naming_it(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed_bill(engine, tenant_id, split=False)
    client, token = asker(engine, settings, everything(tenant_id))

    exchange, _ = ask_as(
        client,
        token,
        "What is our Savings Plans utilization by hour?",
        call("t1", "get_savings_plan_utilization_by_hour"),
    )

    refusal = exchange.outcome
    assert isinstance(refusal, Refusal), refusal
    assert refusal.gap is Gap.TOOL
    assert "get_savings_plan_utilization_by_hour" in refusal.reason
    # Recorded, so the exchange can be replayed, and never sent anywhere.
    assert [(r.tool, r.returned) for r in exchange.tool_calls] == [
        ("get_savings_plan_utilization_by_hour", False)
    ]


def test_next_months_cost_is_refused_because_nothing_here_forecasts(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Spec section 3 and ADR-0015. Saying what this month is costing is allowed; a figure
    for next month is not, and no tool exists that could produce one."""
    seed_bill(engine, tenant_id, split=False)
    client, token = asker(engine, settings, everything(tenant_id))

    exchange, _ = ask_as(
        client,
        token,
        "What will we spend next month?",
        call("t1", "forecast_next_month"),
    )

    refusal = exchange.outcome
    assert isinstance(refusal, Refusal), refusal
    assert refusal.gap is Gap.TOOL
    assert "forecast_next_month" in refusal.reason


def test_a_refusal_in_the_models_own_words_keeps_its_gap_and_reason(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed_bill(engine, tenant_id, split=False)
    client, token = asker(engine, settings, everything(tenant_id))
    reason = "No tool attributes spend to a person, so the product cannot answer this."

    exchange, _ = ask_as(
        client, token, "Which engineer wastes the most money?", refuse("tool", reason)
    )

    assert exchange.outcome == Refusal(gap=Gap.TOOL, reason=reason)
    assert exchange.tool_calls == ()
