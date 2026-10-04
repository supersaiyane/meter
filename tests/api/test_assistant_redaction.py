"""Redaction through the service and the routes, and the table that cannot hold a secret.

TASK-P7-013. The unit tests prove the rules. These prove the plumbing: the service screens
before every path, so no path stores a secret, not even the ones that never reach a model;
the event records the rule and the action and nothing that could rebuild the secret; and a
person sees their own events and nobody else's.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import Engine, text

from finops_api.db import models
from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.assistant import RedactionRepository
from finops_api.guards import SCOPED_TABLES, ByPrincipal
from finops_core.config import Settings
from finops_core.domain.tenant import Scope
from finops_fakes.llm import ForbiddenModel, ScriptedModel
from finops_query.redaction import scan
from tests.api.test_assistant_routes import application, as_person, asked
from tests.query.insight.harness import everything, refuse

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("clear_split_gap")]

REDACTIONS = "/api/v1/assistant/redactions"
CONTEXT = AccessContext(request_id="test")

#: Built at run time, so this repository's own secret scan never sees one in this file.
SECRET = "AKIA" + "Z7QW2XK4M6R3TP5B"
TOKEN = (
    "eyJ"
    + "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    + ".eyJ"
    + "zdWIiOiJhLXBlcnNvbiIsIm5hbWUiOiJhLW5hbWUifQ"
    + ".Qm9rT2hNc0pfV2tYcEZ6VjVHZ2RKcG5L"
)
BLOCKED_QUESTION = f"Why did compute cost jump? My key is {SECRET} if you need it."
REDACTED_QUESTION = f"Why did this token stop working? It is {TOKEN} and it expired."


def everything_stored(engine: Engine, tenant: UUID, table: str) -> str:
    """Every column of every row a tenant has in `table`, as one string."""
    with engine.connect() as connection:
        rows = connection.execute(
            text(f"SELECT * FROM {table} WHERE tenant_id = :t"), {"t": tenant}
        ).all()
    return " ".join(str(value) for row in rows for value in row)


def test_a_blocked_question_reaches_no_model_and_no_table_holds_the_secret(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    scope = everything(tenant_id)
    client, signer = application(engine, settings, scope, ForbiddenModel())  # type: ignore[arg-type]

    data = asked(client, as_person(signer, "p2", scope), BLOCKED_QUESTION)["data"]

    assert data["outcome"] == "REFUSED"
    assert data["refusal"]["gap"] == "secret"
    assert SECRET not in data["question"]
    assert SECRET not in everything_stored(engine, tenant_id, "assistant_exchange")
    assert SECRET not in everything_stored(engine, tenant_id, "redaction_event")
    with engine.connect() as connection:
        event = connection.execute(
            text("SELECT rule_id, action FROM redaction_event WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).one()
    assert (event.rule_id, event.action) == ("aws-access-token", "BLOCKED")


def test_with_no_model_configured_a_secret_is_still_never_stored(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The path that never reaches a model is the one a screen in the loop alone would miss."""
    scope = everything(tenant_id)
    client, signer = application(engine, settings, scope)

    data = asked(client, as_person(signer, "p2", scope), BLOCKED_QUESTION)["data"]

    assert data["refusal"]["gap"] == "secret", "blocked before anything says it is not enabled"
    assert SECRET not in everything_stored(engine, tenant_id, "assistant_exchange")


def test_a_redacted_question_is_answered_without_its_secret(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    sent = scan(REDACTED_QUESTION).text
    model = ScriptedModel({sent: (refuse("tool", "No tool explains a token's expiry here."),)})
    scope = everything(tenant_id)
    client, signer = application(engine, settings, scope, model)

    data = asked(client, as_person(signer, "p2", scope), REDACTED_QUESTION)["data"]

    (received,) = model.received
    assert TOKEN not in received.question
    assert "[redacted: jwt]" in received.question
    assert data["refusal"]["gap"] == "tool", "the question was answered, without its token"
    assert TOKEN not in everything_stored(engine, tenant_id, "assistant_exchange")
    with engine.connect() as connection:
        event = connection.execute(
            text("SELECT rule_id, action FROM redaction_event WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).one()
    assert (event.rule_id, event.action) == ("jwt", "REDACTED")


def test_a_person_sees_their_own_redactions_and_nobody_elses(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    scope = everything(tenant_id)
    client, signer = application(engine, settings, scope)
    asked(client, as_person(signer, "p2", scope), BLOCKED_QUESTION)

    mine = client.get(REDACTIONS, headers=as_person(signer, "p2", scope)).json()
    theirs = client.get(REDACTIONS, headers=as_person(signer, "p3", scope)).json()

    assert set(mine) == {"data", "meta"}
    assert [(e["rule_id"], e["action"]) for e in mine["data"]] == [("aws-access-token", "BLOCKED")]
    assert theirs["data"] == []


def test_the_event_table_is_scoped_by_its_principal_before_any_route(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    assert SCOPED_TABLES["redaction_event"] == ByPrincipal("principal_id")
    scope = everything(tenant_id)
    client, signer = application(engine, settings, scope)
    asked(client, as_person(signer, "p2", scope), BLOCKED_QUESTION)

    with engine.connect() as connection:
        repository = RedactionRepository(connection, CONTEXT)
        other = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset(), principal_id="p3")
        assert repository.redactions(other, 10) == []


def test_the_event_table_has_no_column_a_secret_could_go_in() -> None:
    """Not the text, a hash, a position or a length. Spec section 6.3."""
    assert set(models.redaction_event.columns.keys()) == {
        "event_id",
        "tenant_id",
        "exchange_id",
        "principal_id",
        "rule_id",
        "action",
        "occurred_at",
    }
