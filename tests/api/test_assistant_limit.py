"""The assistant answers a bounded number of questions at once. ISS-225.

Each question holds two of the API's worker threads while it runs: the ask route's own, and
the one its current tool call needs, because the tool call goes back through the same
application. Unbounded, enough questions at once take every thread and wait on tool calls
that cannot get one, and nothing ends that. The bound is taken without waiting, so a
question past it is answered as Throttled at once and holds nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from threading import BoundedSemaphore
from typing import Any, NoReturn
from uuid import UUID

import anyio
import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, text

from finops_api.assistant import BUSY, Asked, Assistant, ask
from finops_core.config import Settings
from finops_core.constants import ASSISTANT_CONCURRENCY_CEILING
from finops_core.domain.insight import Answer, Failure
from finops_core.ports.llm import Completion, CompletionRequest, ToolSchema
from finops_fakes.llm import ForbiddenModel, ScriptedModel
from tests.query.insight.harness import answer

AT = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
QUESTION = "Where would I see the bill?"
PRICES = {"input_per_million": Decimal("3.00"), "output_per_million": Decimal("15.00")}


class NoTools:
    """Offers nothing, and fails the test if anything is called."""

    def schemas(self) -> tuple[ToolSchema, ...]:
        return ()

    def call(self, name: str, arguments: Mapping[str, Any]) -> NoReturn:
        raise AssertionError(f"no tool should be called, and {name} was, with {dict(arguments)}")


class Defective:
    """A model that fails in a way the loop does not type, as a defect would."""

    def complete(self, request: CompletionRequest) -> Completion:
        raise RuntimeError(f"a defect, not a collection error, asked {request.question!r}")


def assistant(model: Any, slots: BoundedSemaphore) -> Assistant:
    return Assistant(
        model=model,
        model_id="a-configured-model",
        toolbox_for=lambda _token: NoTools(),
        monthly_token_budget=10_000_000,
        slots=slots,
        **PRICES,
    )


def asked(engine: Engine, tenant_id: UUID, helper: Assistant) -> Asked:
    return ask(
        engine,
        helper,
        tenant_id=tenant_id,
        principal_id="p2",
        token="unused",
        question=QUESTION,
        clock=lambda: AT,
    )


# --- the bound, at the service ------------------------------------------------------------


@pytest.mark.integration
def test_a_question_past_the_limit_is_throttled_and_reaches_no_model(
    engine: Engine, tenant_id: UUID
) -> None:
    slots = BoundedSemaphore(1)
    assert slots.acquire(blocking=False), "the one slot is held, as a running question holds it"

    result = asked(engine, tenant_id, assistant(ForbiddenModel(), slots))

    assert result.exchange.outcome == Failure(cause="Throttled", detail=BUSY)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT outcome, failure_cause, model_id, input_tokens, output_tokens, est_cost "
                "FROM assistant_exchange WHERE exchange_id = :id"
            ),
            {"id": result.exchange_id},
        ).one()
    assert tuple(row) == ("FAILED", "Throttled", None, 0, 0, 0)


@pytest.mark.integration
def test_the_slot_is_given_back_after_an_answer(engine: Engine, tenant_id: UUID) -> None:
    slots = BoundedSemaphore(1)
    helper = assistant(
        ScriptedModel({QUESTION: (answer("The bill is on the cost screen."),)}), slots
    )

    first = asked(engine, tenant_id, helper)
    second = asked(engine, tenant_id, helper)

    assert isinstance(first.exchange.outcome, Answer)
    assert isinstance(second.exchange.outcome, Answer), "the first question kept its slot"


@pytest.mark.integration
def test_the_slot_is_given_back_when_the_loop_raises(engine: Engine, tenant_id: UUID) -> None:
    slots = BoundedSemaphore(1)

    with pytest.raises(RuntimeError, match="a defect"):
        asked(engine, tenant_id, assistant(Defective(), slots))

    assert slots.acquire(blocking=False), "a question that ended still holds its slot"


# --- the ceiling, against the pool it protects --------------------------------------------


def test_the_ceiling_keeps_questions_below_half_the_worker_pool() -> None:
    """Read from the installed anyio, so a change to its default fails here rather than
    leaving the constant's comment and the pool disagreeing."""

    async def pool() -> float:
        return anyio.to_thread.current_default_thread_limiter().total_tokens

    assert anyio.run(pool) > 2 * ASSISTANT_CONCURRENCY_CEILING


@pytest.mark.parametrize("limit", [0, ASSISTANT_CONCURRENCY_CEILING + 1])
def test_a_limit_outside_the_bound_is_refused(settings: Settings, limit: int) -> None:
    configured = {**settings.model_dump(), "assistant_max_concurrent_questions": limit}
    with pytest.raises(ValidationError, match="assistant_max_concurrent_questions"):
        Settings.model_validate(configured)
