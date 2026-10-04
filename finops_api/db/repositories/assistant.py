"""The assistant's exchanges: the one row a question writes, and what a month spent.

FEAT-038, TASK-P7-007, TASK-P7-010 and P7 spec section 6.1. Three operations, and only one
reads rows back: a person's own, through the guard.

**Recording** writes one `assistant_exchange` row per question, whatever came back. The
three outcomes go to the three sets of columns 0023 holds apart, and the citations and the
tool calls are stored as they were made, so an answer can be replayed and every figure in
it traced to the call behind it.

**What a month spent** is a tenant wide sum, read for the budget, and it is the one read of
this table that crosses people. It returns a number and never a row. The budget is per
tenant, so it has to count everybody's spend, and a count is all it needs.

**Reading** is `ExchangeRepository`, and it reads one person's own questions and nobody
else's, by the `ByPrincipal` rule in the guard, ADR-0029.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar, cast
from uuid import UUID, uuid4

from sqlalchemy import Row, Select, Table, func, select
from sqlalchemy.engine import Connection

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_core.domain.insight import Answer, Outcome, Refusal
from finops_core.domain.tenant import Scope
from finops_query.insight import Exchange, ToolCallRecord
from finops_query.redaction import Hit


class ExchangeRepository(ScopedRepository):
    """One person's own exchanges, read through the guard. ADR-0029.

    The guard confines every read here to the principal the scope was resolved for, so a
    route that forgot to filter by person still could not show anyone else's questions.
    """

    table: ClassVar[Table] = models.assistant_exchange
    resource: ClassVar[str] = "assistant_exchange"

    def exchanges(self, scope: Scope, limit: int) -> Sequence[Row[tuple[object, ...]]]:
        """The asker's exchanges, newest first."""
        statement = self.scoped_select(scope).order_by(self.table.c.asked_at.desc()).limit(limit)
        return self.fetch(scope, statement)

    def count(self, scope: Scope) -> int:
        """How many the asker has, so a list cut at its limit says it was cut."""
        # The projection narrows the select's type and `fetch` is declared for the general
        # one, so it is cast here, as the cost repository's `_fetch` does for its counts.
        projected = self.scoped_select(scope).with_only_columns(func.count())
        statement = cast("Select[tuple[object, ...]]", projected)
        return int(self.fetch(scope, statement)[0][0])

    def exchange(self, scope: Scope, exchange_id: UUID) -> Row[tuple[object, ...]] | None:
        """One of the asker's exchanges, or None, which is also what another person's is."""
        statement = self.scoped_select(scope).where(self.table.c.exchange_id == exchange_id)
        rows = self.fetch(scope, statement)
        return rows[0] if rows else None


class DigestRepository(ScopedRepository):
    """The weekly digests, read through the guard. FEAT-041.

    Payer wide: a digest sums spend across accounts, so only a scope that sees the whole
    organization reads one, and a narrowed scope reads nothing rather than another
    reader's totals.
    """

    table: ClassVar[Table] = models.team_digest
    resource: ClassVar[str] = "team_digest"

    def digests(self, scope: Scope, limit: int) -> Sequence[Row[tuple[object, ...]]]:
        """The newest week first, the organization's digest before the teams'."""
        statement = (
            self.scoped_select(scope)
            .order_by(
                self.table.c.period_start.desc(),
                # `executive` sorts before `team`, which puts the organization's first.
                self.table.c.audience,
                self.table.c.team,
            )
            .limit(limit)
        )
        return self.fetch(scope, statement)


class RedactionRepository(ScopedRepository):
    """What redaction found in a person's own questions, read through the guard. FEAT-046.

    Scoped by principal, ADR-0029: the events describe what somebody typed, and are theirs.
    """

    table: ClassVar[Table] = models.redaction_event
    resource: ClassVar[str] = "redaction_event"

    def redactions(self, scope: Scope, limit: int) -> Sequence[Row[tuple[object, ...]]]:
        """The asker's events, newest first."""
        statement = self.scoped_select(scope).order_by(self.table.c.occurred_at.desc()).limit(limit)
        return self.fetch(scope, statement)

    def count(self, scope: Scope) -> int:
        """How many the asker has, so a list cut at its limit says it was cut."""
        projected = self.scoped_select(scope).with_only_columns(func.count())
        statement = cast("Select[tuple[object, ...]]", projected)
        return int(self.fetch(scope, statement)[0][0])


def record_redactions(
    connection: Connection,
    *,
    tenant_id: UUID,
    principal_id: str,
    exchange_id: UUID,
    hits: Sequence[Hit],
    at: datetime,
) -> int:
    """One row per rule that fired. The rule and the action, and nothing of the secret."""
    for hit in hits:
        connection.execute(
            models.redaction_event.insert().values(
                event_id=uuid4(),
                tenant_id=tenant_id,
                exchange_id=exchange_id,
                principal_id=principal_id,
                rule_id=hit.rule_id,
                action=hit.action.value,
                occurred_at=at,
            )
        )
    return len(hits)


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
            citations=[citation.as_record() for citation in outcome.citations],
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


def _call(record: ToolCallRecord) -> dict[str, Any]:
    return {
        "call_id": record.call_id,
        "tool": record.tool,
        # Through JSON, so whatever a model passed is stored as the text it was rather
        # than refused for being a type the column cannot hold.
        "arguments": json.loads(json.dumps(dict(record.arguments), default=str)),
        "returned": record.returned,
    }
