"""The assistant service: the budget it keeps, and the one row every question writes.

TASK-P7-007, and spec section 11's cost test. The budget is exhausted by asking, not by
writing rows by hand, so the figure being counted is what exchanges actually recorded,
which is the plan's third criterion and the whole reason the budget reads the table.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from finops_api.assistant import NOT_ENABLED, Assistant, ask
from finops_api.db.repositories.assistant import tokens_spent
from finops_api.toolbox import ApiToolbox
from finops_core.config import Settings
from finops_core.domain.insight import Answer, Failure, Gap, Refusal
from finops_fakes.llm import ScriptedModel
from finops_query.insight import estimated_cost, month_start
from tests.api.test_query_routes import another_tenant
from tests.query.insight.harness import answer, asker, call, everything, seed_bill

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("clear_split_gap")]

AT = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)
QUESTION = "Which service cost the most last month?"
PRICES = {"input_per_million": Decimal("3.00"), "output_per_million": Decimal("15.00")}


def scripted() -> ScriptedModel:
    return ScriptedModel(
        {
            QUESTION: (
                call("t1", "get_cost_by_service"),
                answer("{{service}} led the bill.", service=("t1", "data[name=AmazonEC2].name")),
            )
        }
    )


def assistant(client: TestClient, model: ScriptedModel, *, budget: int) -> Assistant:
    return Assistant(
        model=model,
        model_id="a-configured-model",
        toolbox_for=lambda token: ApiToolbox(client, token),
        monthly_token_budget=budget,
        **PRICES,
    )


def stored(engine: Engine, exchange_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT * FROM assistant_exchange WHERE exchange_id = :id"), {"id": exchange_id}
        ).one()
    return dict(row._mapping)


def test_a_spent_budget_refuses_the_next_question_and_says_when_it_resets(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed_bill(engine, tenant_id, split=False)
    client, token = asker(engine, settings, everything(tenant_id))
    model = scripted()
    # A ceiling of one token: the first question is under it, and spends past it.
    helper = assistant(client, model, budget=1)

    first = ask(
        engine,
        helper,
        tenant_id=tenant_id,
        principal_id="p2",
        token=token,
        question=QUESTION,
        clock=lambda: AT,
    )
    sent = len(model.received)
    second = ask(
        engine,
        helper,
        tenant_id=tenant_id,
        principal_id="p2",
        token=token,
        question=QUESTION,
        clock=lambda: AT,
    )

    assert isinstance(first.exchange.outcome, Answer)
    refusal = second.exchange.outcome
    assert isinstance(refusal, Refusal), refusal
    assert refusal.gap is Gap.BUDGET
    assert "2026-11-01" in refusal.reason
    assert len(model.received) == sent, "a refused question reaches no model"
    assert (second.exchange.usage.total, second.est_cost, second.model_id) == (
        0,
        Decimal(0),
        None,
    )


def test_the_spend_counted_is_what_the_exchanges_recorded(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed_bill(engine, tenant_id, split=False)
    client, token = asker(engine, settings, everything(tenant_id))

    asked = ask(
        engine,
        assistant(client, scripted(), budget=10_000_000),
        tenant_id=tenant_id,
        principal_id="p2",
        token=token,
        question=QUESTION,
        clock=lambda: AT,
    )

    row = stored(engine, asked.exchange_id)
    with engine.connect() as connection:
        counted = tokens_spent(connection, tenant_id, month_start(AT))
    assert counted == row["input_tokens"] + row["output_tokens"] == asked.exchange.usage.total
    assert counted > 0


def test_another_month_and_another_tenant_spend_nothing_of_this_budget(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed_bill(engine, tenant_id, split=False)
    client, token = asker(engine, settings, everything(tenant_id))
    ask(
        engine,
        assistant(client, scripted(), budget=10_000_000),
        tenant_id=tenant_id,
        principal_id="p2",
        token=token,
        question=QUESTION,
        clock=lambda: AT,
    )

    november = month_start(AT + timedelta(days=31))
    with engine.connect() as connection:
        assert tokens_spent(connection, tenant_id, november) == 0
        assert tokens_spent(connection, another_tenant(engine), month_start(AT)) == 0


def test_an_exchange_that_reached_a_model_records_a_cost_above_zero(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Spec section 11. A self metering product whose newest feature reported a cost of
    zero would be making the exact mistake it was built to catch."""
    seed_bill(engine, tenant_id, split=False)
    client, token = asker(engine, settings, everything(tenant_id))

    asked = ask(
        engine,
        assistant(client, scripted(), budget=10_000_000),
        tenant_id=tenant_id,
        principal_id="p2",
        token=token,
        question=QUESTION,
        clock=lambda: AT,
    )

    row = stored(engine, asked.exchange_id)
    assert row["model_id"] == "a-configured-model"
    assert row["est_cost"] == estimated_cost(asked.exchange.usage, **PRICES) > 0
    assert row["outcome"] == "ANSWERED"


def test_a_deployment_with_no_model_says_so_and_spends_nothing(
    engine: Engine, tenant_id: UUID
) -> None:
    """ADR-0028: not enabled rather than broken, and recorded like any other exchange."""
    asked = ask(
        engine,
        None,
        tenant_id=tenant_id,
        principal_id="p2",
        token="unused",
        question=QUESTION,
        clock=lambda: AT,
    )

    assert asked.exchange.outcome == Failure(cause="NotOptedIn", detail=NOT_ENABLED)
    row = stored(engine, asked.exchange_id)
    assert (row["outcome"], row["failure_cause"], row["model_id"]) == ("FAILED", "NotOptedIn", None)
    assert (row["input_tokens"], row["output_tokens"], row["est_cost"]) == (0, 0, 0)
