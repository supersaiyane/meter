"""What the three evaluation sets run against: the fake model, the fake bill, the real API.

P7 spec section 11 and TASK-P7-005. These sets were written before the loop they judge,
and that is the whole of their value. A refusal set written afterwards is a description
of what the implementation happens to do, and the pressure on every assistant is to
answer more, one reasonable looking softening at a time. Here a softening is a diff
somebody reviews.

**Every tool call goes through the API's own routes with the asker's own token,** so the
scope cases are decided by the same dependency and the same guard as the screens, and by
nothing in this harness. The model is scripted, because an evaluation run against a
sampling model measures the sampler. The script plays a model that does exactly what a
case needs, adversarial where the case is an attack, and the sets judge what the loop does
with it: whether the figures it shows are the screen's figures, and whether what it
refuses, it refuses for the right reason.

**The loop arrives with TASK-P7-006.** Until then every case skips naming that task, so
the commit between the two is coherent rather than red, and the skip disappears with the
import it is waiting for.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.insight import Answer, bare_figures
from finops_core.domain.tenant import Scope
from finops_core.ports.llm import Message, Role, ToolCall
from finops_fakes.cur import CLOSED_PERIOD, ESTATE, FakeCostExport
from finops_fakes.llm import ScriptedModel
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.registry import CollectorContext
from tests.api.test_query_routes import auth, client_for

#: The fake bill's clock, so its closed month is closed. As `tests/api/test_cost_routes.py`.
NOW = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
CLOSED = tuple(row for row in ESTATE if row.billing_period_start == CLOSED_PERIOD)

IN_SCOPE = "fake-platform-a"
OUT_OF_SCOPE = "fake-product-a"

LOOP = "TASK-P7-006 builds the loop these sets judge"


@dataclass(frozen=True)
class _Unit:
    tenant_id: UUID


def seed_bill(engine: Engine, tenant: UUID, *, split: bool) -> None:
    """The closed month of the fake bill, through the real cost collector.

    `split` is whether the export carries split cost allocation data. Without it the
    collector records the gap as a typed failure, which is what the refusal set reads.
    """
    with engine.begin() as connection:
        ensure_partition(connection, "cost_focus_daily", CLOSED_PERIOD)
        CostFocusCollector(FakeCostExport(rows=CLOSED, split=split), clock=lambda: NOW)(
            CollectorContext(unit=_Unit(tenant_id=tenant), connection=connection, run_id=uuid4())
        )


def everything(tenant: UUID) -> Scope:
    return Scope(tenant_id=tenant, is_global=True, accounts=frozenset())


def only(tenant: UUID, account: str) -> Scope:
    return Scope(
        tenant_id=tenant,
        is_global=False,
        accounts=frozenset({AccountKey(provider=Provider.AWS, account_id=account)}),
    )


def asker(engine: Engine, settings: Settings, scope: Scope) -> tuple[TestClient, str]:
    """A client of the real application, and a token for somebody holding `scope`."""
    return client_for(engine, scope, settings)


def screen(client: TestClient, token: str, path: str) -> dict[str, Any]:
    """What a screen is shown for `path`, read with the same token the assistant uses."""
    response = client.get(f"/api/v1{path}", headers=auth(token))
    assert response.status_code == 200, response.text
    return dict(response.json())


# --- the model's turns ------------------------------------------------------------


def call(call_id: str, tool: str, **arguments: Any) -> Message:
    """The model asking for one tool."""
    return Message(
        role=Role.ASSISTANT,
        tool_calls=(ToolCall(call_id=call_id, name=tool, arguments=arguments),),
    )


def answer(prose: str, **citations: tuple[str, str]) -> Message:
    """The model's last turn: prose with placeholders, and where each value is.

    Each citation names a placeholder, the call whose result holds the value, and the
    path to it. The model names where a figure is and never what it is: the loop reads
    the value out of the result it received.
    """
    references = [
        {"placeholder": name, "call_id": call_id, "path": path}
        for name, (call_id, path) in citations.items()
    ]
    return Message(
        role=Role.ASSISTANT,
        tool_calls=(
            ToolCall(
                call_id="final", name="answer", arguments={"prose": prose, "citations": references}
            ),
        ),
    )


def refuse(gap: str, reason: str) -> Message:
    """The model declining, in its own words, naming the kind of thing missing."""
    return Message(
        role=Role.ASSISTANT,
        tool_calls=(
            ToolCall(call_id="final", name="refuse", arguments={"gap": gap, "reason": reason}),
        ),
    )


# --- asking, and what every answer must satisfy -----------------------------------


def ask_as(
    client: TestClient, token: str, question: str, *turns: Message
) -> tuple[Any, ScriptedModel]:
    """Ask the loop as the holder of `token`, with a model playing `turns`."""
    insight = pytest.importorskip("finops_query.insight", reason=LOOP)
    toolbox = pytest.importorskip("finops_api.toolbox", reason=LOOP)
    model = ScriptedModel({question: turns})
    exchange = insight.ask(question, model=model, toolbox=toolbox.ApiToolbox(client, token))
    return exchange, model


def assert_cited_from_real_results(exchange: Any) -> Answer:
    """Spec section 11's provenance test, over one answer.

    No bare numeral, every placeholder cited, which the entity already refuses to break,
    and every citation resolving to a tool call that actually returned.
    """
    outcome = exchange.outcome
    assert isinstance(outcome, Answer), outcome
    assert bare_figures(outcome.prose) == ()
    returned = {record.call_id for record in exchange.tool_calls if record.returned}
    for citation in outcome.citations:
        assert citation.call_id in returned, (
            f"{citation.placeholder} cites a call that never returned"
        )
    return outcome


def everything_the_model_read(model: ScriptedModel) -> str:
    """Every tool result the model was handed, as one string, for asserting an absence."""
    return "".join(
        result.content
        for request in model.received
        for message in request.messages
        for result in message.tool_results
    )
