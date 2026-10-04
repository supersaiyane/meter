"""The assistant's exchanges: the one row a question writes, and what a month spent.

FEAT-038, TASK-P7-007 and P7 spec section 6.1. Neither operation here reads anybody's
rows back.

**Recording** writes one `assistant_exchange` row per question, whatever came back. The
three outcomes go to the three sets of columns 0023 holds apart, and the citations and the
tool calls are stored as they were made, so an answer can be replayed and every figure in
it traced to the call behind it.

**What a month spent** is a tenant wide sum, read for the budget, and it is the one read of
this table that crosses people. It returns a number and never a row. The budget is per
tenant, so it has to count everybody's spend, and a count is all it needs. Reading one
person's own questions is scoped by principal and arrives with the routes, TASK-P7-010.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from finops_api.db import models
from finops_core.domain.insight import Answer, Citation, Outcome, Refusal
from finops_query.insight import Exchange, ToolCallRecord


def tokens_spent(connection: Connection, tenant_id: UUID, since: datetime) -> int:
    """Every token the tenant's exchanges recorded since `since`. Zero is the truth when
    nothing was asked, which is the one place a sum of nothing means nothing spent."""
    table = models.assistant_exchange
    spent = connection.execute(
        select(func.coalesce(func.sum(table.c.input_tokens + table.c.output_tokens), 0)).where(
            table.c.tenant_id == tenant_id, table.c.asked_at >= since
        )
    ).scalar_one()
    return int(spent)


def record_exchange(
    connection: Connection,
    *,
    tenant_id: UUID,
    principal_id: str,
    exchange: Exchange,
    model_id: str | None,
    est_cost: Decimal,
    asked_at: datetime,
    answered_at: datetime,
) -> UUID:
    """Write the one row a question produces, and return its id."""
    exchange_id = uuid4()
    values: dict[str, Any] = {
        "exchange_id": exchange_id,
        "tenant_id": tenant_id,
        "principal_id": principal_id,
        "question": exchange.question,
        "citations": [],
        "tool_calls": [_call(record) for record in exchange.tool_calls],
        "model_id": model_id,
        "input_tokens": exchange.usage.input_tokens,
        "output_tokens": exchange.usage.output_tokens,
        "est_cost": est_cost,
        "asked_at": asked_at,
        "answered_at": answered_at,
    }
    outcome = exchange.outcome
    if isinstance(outcome, Answer):
        values.update(
            outcome=Outcome.ANSWERED.value,
            answer=outcome.prose,
            citations=[_citation(citation) for citation in outcome.citations],
        )
    elif isinstance(outcome, Refusal):
        values.update(
            outcome=Outcome.REFUSED.value,
            refusal_gap=outcome.gap.value,
            refusal_reason=outcome.reason,
            refusal_screen=outcome.screen,
        )
    else:
        values.update(
            outcome=Outcome.FAILED.value,
            failure_cause=outcome.cause,
            failure_detail=outcome.detail or None,
        )
    connection.execute(models.assistant_exchange.insert().values(**values))
    return exchange_id


def _citation(citation: Citation) -> dict[str, Any]:
    """A figure as text, so a Decimal survives the trip through JSON unrounded."""
    return {
        "placeholder": citation.placeholder,
        "tool": citation.tool,
        "call_id": citation.call_id,
        "field": citation.field,
        "value": str(citation.value),
        "kind": "figure" if citation.is_figure else "label",
        "provenance": citation.provenance.value,
        "as_of": citation.as_of.isoformat(),
    }


def _call(record: ToolCallRecord) -> dict[str, Any]:
    return {
        "call_id": record.call_id,
        "tool": record.tool,
        # Through JSON, so whatever a model passed is stored as the text it was rather
        # than refused for being a type the column cannot hold.
        "arguments": json.loads(json.dumps(dict(record.arguments), default=str)),
        "returned": record.returned,
    }
