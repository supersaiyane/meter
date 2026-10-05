"""The assistant's routes, in the Assistant group. TASK-P7-010, FEAT-038 and ADR-0020.

All four the spec names: ask, the asker's exchanges, the digests and the asker's
redactions. Each arrived with the table it reads, TASK-P7-010, 012 and 013.

**`POST /assistant/ask` is the only write, and it writes one row,** into Meter's own
database. Constraint 6 forbids a write into a member account, which this is not: it records
what was asked and what came back, the way the recommendation lifecycle records a
transition. It holds no connection while the model works, because a model takes seconds and
the pool is the rest of the API's. The question travels in the body, never in the URL,
where it would be written into every access log on the way.

**Answer, refusal and failure come back as three shapes.** Exactly one is present and it is
the one the outcome names, so a screen cannot draw a refusal as an empty answer or a failure
as a refusal. Spec section 5.3.

**`GET /assistant/exchanges` is the asker's own, by the guard,** ADR-0029. A person reads
their own questions and nobody else's, whatever else their scope reaches.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.engine import Connection

from finops_api import assistant
from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.assistant import (
    DigestRepository,
    ExchangeRepository,
    RedactionRepository,
)
from finops_api.deps import (
    AUTHORIZATION,
    BEARER,
    get_access_context,
    get_connection,
    get_principal,
    get_scope,
)
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import (
    AnswerOut,
    AskIn,
    AssistantRefusalOut,
    CitationOut,
    DigestOut,
    Envelope,
    ExchangeFailureOut,
    ExchangeOut,
    Meta,
    RedactionOut,
    ToolCallOut,
)
from finops_core.domain.identity import Principal
from finops_core.domain.tenant import Scope

router = APIRouter(prefix=API_PREFIX, tags=["assistant"])

#: How many exchanges the list returns, newest first. The coverage says when there are more.
EXCHANGE_LIMIT = 50

EXCHANGES = "exchanges"

#: How many digests the list returns: a quarter of weekly digests for a dozen teams.
DIGEST_LIMIT = 200

#: What a digest's coverage counts. It sums the whole payer, so a scope sees all of it or
#: none of it, and the unit says so rather than counting digests against accounts.
PAYER = "payer"

#: What a person who asked can do about each typed cause, by the name the row stores it
#: under. Written for the assistant rather than taken from each cause's own remediation
#: text, which says to re run a collector, and somebody who asked a question has none to
#: re run. `tests/api/test_assistant_remediation.py` holds that every cause has one.
REMEDIATION = {
    "AccessDenied": (
        "The hub role may not invoke this model. Add it to assistant_model_ids in the hub "
        "stack, then ask again."
    ),
    "Throttled": (
        "Too many questions are being answered at once, by Meter or by the model service. "
        "Ask again in a minute."
    ),
    "NotOptedIn": (
        "Name a model in METER_ASSISTANT_MODEL_ID, enable access to it for the hub account, "
        "and grant it through assistant_model_ids in the hub stack."
    ),
    "NoData": (
        "The tools returned nothing to answer from. Ask about a period or a scope that has "
        "been collected."
    ),
    "Unreachable": (
        "The model service did not answer. Ask again, and if it keeps failing, check the "
        "service's health in the hub account's region."
    ),
    "SchemaDrift": (
        "The answer could not be checked against the tool results, so it is not shown. Ask "
        "again, or ask a narrower question."
    ),
    "Misconfigured": (
        "METER_ASSISTANT_MODEL_ID names a model the hub account is not offered. Correct the "
        "setting."
    ),
}


@router.post("/assistant/ask", response_model=Envelope[ExchangeOut])
def ask(
    body: AskIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[ExchangeOut]:
    """Ask a question, and get an answer, a refusal or a typed failure. Writes one row."""
    token = request.headers.get(AUTHORIZATION, "").removeprefix(BEARER)
    asked = assistant.ask(
        request.app.state.engine,
        request.app.state.assistant,
        tenant_id=scope.tenant_id,
        principal_id=principal.principal_id,
        token=token,
        question=body.question,
        clock=lambda: datetime.now(UTC),
    )
    with request.app.state.engine.begin() as connection:
        row = ExchangeRepository(connection, context).exchange(scope, asked.exchange_id)
        if row is None:
            # Written moments ago under this same scope, so this is a defect, not an answer.
            raise RuntimeError("an exchange could not be read back by the person who asked it")
        out = exchange_out(row)
        meta = _meta(connection, scope, context, out)
    return Envelope(data=out, meta=meta)


@router.get("/assistant/exchanges", response_model=Envelope[list[ExchangeOut]])
def exchanges(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[ExchangeOut]]:
    """What the asker has asked and what came back, newest first. Their own and no one else's."""
    repository = ExchangeRepository(connection, context)
    rows = repository.exchanges(scope, EXCHANGE_LIMIT)
    meta = build_meta(
        connection,
        scope,
        context,
        visible=len(rows),
        coverage=(len(rows), repository.count(scope)),
        coverage_unit=EXCHANGES,
    )
    return Envelope(data=[exchange_out(row) for row in rows], meta=meta)


@router.get("/assistant/digests", response_model=Envelope[list[DigestOut]])
def digests(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[DigestOut]]:
    """The weekly digests, newest first, each saying whether it was sent. FEAT-041.

    Payer wide, so a narrowed reader is shown none and the coverage says the digests need
    organization wide scope, rather than a list that looks empty for no reason.
    """
    out = [
        digest_out(row)
        for row in DigestRepository(connection, context).digests(scope, DIGEST_LIMIT)
    ]
    stamps = [citation.as_of for digest in out for citation in digest.citations]
    whole = 1 if scope.is_global else 0
    meta = build_meta(
        connection,
        scope,
        context,
        visible=whole,
        as_of=min(stamps) if stamps else None,
        collected_at=min(digest.composed_at for digest in out) if stamps else None,
        coverage=(whole, 1),
        coverage_unit=PAYER,
    )
    return Envelope(data=out, meta=meta)


@router.get("/assistant/redactions", response_model=Envelope[list[RedactionOut]])
def redactions(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[list[RedactionOut]]:
    """What was blocked or redacted in the asker's own questions, and by which rule.

    The asker's own and nobody else's, ADR-0029, and never the secret, because no column
    holds it. FEAT-046.
    """
    repository = RedactionRepository(connection, context)
    rows = repository.redactions(scope, EXCHANGE_LIMIT)
    meta = build_meta(
        connection,
        scope,
        context,
        visible=len(rows),
        coverage=(len(rows), repository.count(scope)),
        coverage_unit="redactions",
    )
    return Envelope(
        data=[
            RedactionOut(
                event_id=row.event_id,
                exchange_id=row.exchange_id,
                rule_id=row.rule_id,
                action=row.action,
                occurred_at=row.occurred_at,
            )
            for row in rows
        ],
        meta=meta,
    )


def digest_out(row: Any) -> DigestOut:
    """One stored digest, with its citations and whether it went anywhere."""
    return DigestOut(
        digest_id=row.digest_id,
        audience=row.audience,
        team=row.team,
        period_start=row.period_start,
        period_end=row.period_end,
        prose=row.prose,
        citations=tuple(CitationOut(**citation) for citation in row.citations),
        composed_at=row.composed_at,
        sent_at=row.sent_at,
        unsent_reason=row.unsent_reason,
    )


def _meta(connection: Connection, scope: Scope, context: AccessContext, out: ExchangeOut) -> Meta:
    """An answer is as fresh as its stalest cited figure, and an exchange with no figure
    has no freshness to state."""
    stamps = [citation.as_of for citation in out.answer.citations] if out.answer else []
    as_of = min(stamps) if stamps else None
    return build_meta(
        connection,
        scope,
        context,
        visible=1,
        as_of=as_of,
        collected_at=out.answered_at if as_of is not None else None,
        coverage=(1, 1),
        coverage_unit=EXCHANGES,
    )


def exchange_out(row: Any) -> ExchangeOut:
    """One stored exchange, in the one of three shapes its outcome names."""
    return ExchangeOut(
        exchange_id=row.exchange_id,
        question=row.question,
        outcome=row.outcome,
        answer=(
            AnswerOut(
                prose=row.answer,
                citations=tuple(CitationOut(**citation) for citation in row.citations),
            )
            if row.outcome == "ANSWERED"
            else None
        ),
        refusal=(
            AssistantRefusalOut(
                gap=row.refusal_gap, reason=row.refusal_reason, screen=row.refusal_screen
            )
            if row.outcome == "REFUSED"
            else None
        ),
        failure=(
            ExchangeFailureOut(
                cause=row.failure_cause,
                detail=row.failure_detail,
                remediation=REMEDIATION[row.failure_cause],
            )
            if row.outcome == "FAILED"
            else None
        ),
        tool_calls=tuple(
            ToolCallOut(call_id=call["call_id"], tool=call["tool"], returned=call["returned"])
            for call in row.tool_calls
        ),
        model_id=row.model_id,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        est_cost=row.est_cost,
        asked_at=row.asked_at,
        answered_at=row.answered_at,
    )
