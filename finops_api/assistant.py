"""Asking the assistant: the budget, the loop, and the one row a question writes.

FEAT-038 and TASK-P7-007. What the route in TASK-P7-010 calls. Kept apart from the route so
the whole of an exchange is testable without HTTP, and so the order the steps run in is
written down in one place, because the order is most of what this module decides:

1. The question is screened for secrets, TASK-P7-013. One that blocks is refused and sent
   nowhere, and every path below keeps only the screened text, so a secret is stored by no
   path, not even the ones that never reach a model.
2. No model configured is a failure saying so, `NotOptedIn` as ADR-0028 asks, and nothing
   is spent or sent. A deployment without the assistant says it is not enabled rather than
   answering with silence. Naming a model is OPEN-10, and a setting.
3. The budget is read from what exchanges recorded and checked before any model is asked,
   so a spent month refuses without spending more.
4. A slot is taken without waiting, ISS-225. Each running question holds two of the API's
   worker threads, so past the configured number a question is throttled at once rather
   than queued, and the slot is given back however the loop ends.
5. The loop runs with no transaction open. A model takes seconds, and a transaction held
   across it holds a connection the rest of the API is waiting for.
6. One row is written whatever came back, with one redaction event per rule that fired, in
   a transaction of its own.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from threading import BoundedSemaphore
from uuid import UUID

from sqlalchemy import Engine

from finops_api.db.repositories.assistant import (
    record_exchange,
    record_redactions,
    tokens_spent,
)
from finops_core.domain.insight import Failure, Gap, Refusal
from finops_core.ports.llm import LlmProvider, TokenUsage
from finops_query import insight, redaction
from finops_query.insight import (
    Exchange,
    Toolbox,
    budget_refusal,
    estimated_cost,
    month_start,
)
from finops_query.redaction import Scan

NOT_ENABLED = (
    "No model is configured for the assistant in this deployment, so the question was sent "
    "nowhere. Choosing one is OPEN-10, and it is the setting METER_ASSISTANT_MODEL_ID."
)

BUSY = (
    "The assistant is already answering as many questions as it runs at once, so this one "
    "was sent nowhere and spent nothing. Ask again in a moment. The limit is the setting "
    "METER_ASSISTANT_MAX_CONCURRENT_QUESTIONS."
)

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class Assistant:
    """Everything a deployment needs to answer a question. None where no model is set."""

    model: LlmProvider
    #: What the row records it was sent to. Configuration, never chosen here.
    model_id: str
    #: The asker's tools, built from the asker's own token.
    toolbox_for: Callable[[str], Toolbox]
    input_per_million: Decimal
    output_per_million: Decimal
    monthly_token_budget: int
    #: One permit per question that may run at once, ISS-225. Shared by every request this
    #: application serves, and taken without waiting.
    slots: BoundedSemaphore


@dataclass(frozen=True)
class Asked:
    """One question, as it was recorded."""

    exchange_id: UUID
    exchange: Exchange
    model_id: str | None
    est_cost: Decimal
    asked_at: datetime
    answered_at: datetime


def ask(
    engine: Engine,
    assistant: Assistant | None,
    *,
    tenant_id: UUID,
    principal_id: str,
    token: str,
    question: str,
    clock: Clock,
) -> Asked:
    """Answer, refuse or fail, and record which, exactly once.

    The question is screened before anything else, TASK-P7-013, so no path below, not the
    one with no model and not a spent budget, ever stores or sends a secret it held.
    """
    asked_at = clock()
    screened = redaction.scan(question)
    exchange, model_id = _exchange(
        engine, assistant, tenant_id=tenant_id, token=token, screened=screened, at=asked_at
    )
    answered_at = max(clock(), asked_at)
    est_cost = Decimal(0)
    if assistant is not None and model_id is not None:
        est_cost = estimated_cost(
            exchange.usage,
            input_per_million=assistant.input_per_million,
            output_per_million=assistant.output_per_million,
        )
    with engine.begin() as connection:
        exchange_id = record_exchange(
            connection,
            tenant_id=tenant_id,
            principal_id=principal_id,
            exchange=exchange,
            model_id=model_id,
            est_cost=est_cost,
            asked_at=asked_at,
            answered_at=answered_at,
        )
        record_redactions(
            connection,
            tenant_id=tenant_id,
            principal_id=principal_id,
            exchange_id=exchange_id,
            hits=screened.hits,
            at=asked_at,
        )
        record_redactions(
            connection,
            tenant_id=tenant_id,
            principal_id=principal_id,
            exchange_id=exchange_id,
            hits=exchange.withheld,
            at=asked_at,
            found_in="tool_result",
        )
    return Asked(
        exchange_id=exchange_id,
        exchange=exchange,
        model_id=model_id,
        est_cost=est_cost,
        asked_at=asked_at,
        answered_at=answered_at,
    )


def _exchange(
    engine: Engine,
    assistant: Assistant | None,
    *,
    tenant_id: UUID,
    token: str,
    screened: Scan,
    at: datetime,
) -> tuple[Exchange, str | None]:
    """The exchange, and the model it was sent to, which is None where it went nowhere."""
    if screened.blocked:
        refusal = Refusal(gap=Gap.SECRET, reason=redaction.blocked_reason(screened))
        return _unsent(screened, refusal), None
    if assistant is None:
        return _unsent(screened, Failure(cause="NotOptedIn", detail=NOT_ENABLED)), None
    with engine.connect() as connection:
        spent = tokens_spent(connection, tenant_id, month_start(at))
    over_budget = budget_refusal(spent=spent, budget=assistant.monthly_token_budget, at=at)
    if over_budget is not None:
        return _unsent(screened, over_budget), None
    if not assistant.slots.acquire(blocking=False):
        return _unsent(screened, Failure(cause="Throttled", detail=BUSY)), None
    try:
        exchange = insight.ask(
            screened.text, model=assistant.model, toolbox=assistant.toolbox_for(token)
        )
    finally:
        assistant.slots.release()
    return exchange, assistant.model_id


def _unsent(screened: Scan, outcome: Failure | Refusal) -> Exchange:
    """An exchange that reached no model, and spent nothing, which is the truth."""
    return Exchange(
        question=screened.text,
        outcome=outcome,
        tool_calls=(),
        usage=TokenUsage(input_tokens=0, output_tokens=0),
        redactions=screened.hits,
    )
