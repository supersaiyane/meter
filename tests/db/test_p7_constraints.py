"""The P7 invariants, watched refusing in both directions.

Constraint 11. A check constraint nobody has watched refuse anything is in the same
position as the code it was meant to back up, because a constraint with a typo in it
accepts everything and looks exactly like one that works. 0023 carries three
biconditionals, one per outcome, and a biconditional has two halves that can each be
mistyped on its own, so every one is watched refusing from both sides.

Every row is one valid answered exchange plus the override under test, so a refusal
proves the override was the reason rather than a typo somewhere else in the row.
"""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from finops_api.db import models
from finops_core.constants import REASON_MIN_LENGTH
from finops_core.domain.insight import Gap, Outcome
from finops_query.digest import Audience
from finops_query.redaction import Action

pytestmark = pytest.mark.integration

MIGRATION = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0023_assistant_exchange.py"
)

ASKED = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)
ANSWERED = ASKED + timedelta(seconds=4)
REASON = "There is no tool that forecasts spend."
CITATION = {
    "placeholder": "total",
    "tool": "get_cost_summary",
    "call_id": "t1",
    "field": "data.month_to_date",
    "value": "4123.50",
    "provenance": "measured",
    "as_of": "2026-10-03T00:00:00+00:00",
}
CALL = {"call_id": "t1", "tool": "get_cost_summary", "arguments": {}}

INSERT = text(
    "INSERT INTO assistant_exchange (exchange_id, tenant_id, principal_id, question, outcome, "
    "answer, refusal_gap, refusal_reason, refusal_screen, failure_cause, failure_detail, "
    "citations, tool_calls, model_id, input_tokens, output_tokens, est_cost, asked_at, "
    "answered_at) VALUES (:id, :t, :who, :question, :outcome, :answer, :gap, :reason, "
    ":screen, :cause, :detail, CAST(:citations AS JSONB), CAST(:calls AS JSONB), :model, "
    ":input, :output, :cost, :asked, :answered)"
)

REFUSED: dict[str, Any] = {
    "outcome": "REFUSED",
    "answer": None,
    "gap": "tool",
    "reason": REASON,
    "citations": [],
}
FAILED: dict[str, Any] = {
    "outcome": "FAILED",
    "answer": None,
    "cause": "SchemaDrift",
    "detail": "the prose held a figure no citation placed",
    "citations": [],
}


def an_exchange(connection: Connection, tenant: UUID, **overrides: Any) -> UUID:
    """One answered exchange, with any field overridden."""
    values: dict[str, Any] = {
        "id": uuid4(),
        "t": tenant,
        "who": "principal-a",
        "question": "What did we spend this month?",
        "outcome": "ANSWERED",
        "answer": "This month cost {{total}}.",
        "gap": None,
        "reason": None,
        "screen": None,
        "cause": None,
        "detail": None,
        "citations": [CITATION],
        "calls": [CALL],
        "model": "configured-model",
        "input": 812,
        "output": 64,
        "cost": "0.0031",
        "asked": ASKED,
        "answered": ANSWERED,
    }
    values.update(overrides)
    values["citations"] = json.dumps(values["citations"])
    values["calls"] = json.dumps(values["calls"])
    connection.execute(INSERT, values)
    return UUID(str(values["id"]))


def refused_as(engine: Engine, tenant: UUID, constraint: str, **overrides: Any) -> None:
    with engine.begin() as connection, pytest.raises(IntegrityError, match=constraint):
        an_exchange(connection, tenant, **overrides)


# --- each outcome in its own shape is accepted -------------------------------------


@pytest.mark.parametrize("shape", [{}, REFUSED, FAILED], ids=["answered", "refused", "failed"])
def test_each_outcome_in_its_own_shape_is_accepted(
    engine: Engine, tenant_id: UUID, shape: dict[str, Any]
) -> None:
    """The positive case, so the refusals below cannot all be passing on a typo."""
    with engine.begin() as connection:
        an_exchange(connection, tenant_id, **shape)


# --- the answer, both directions --------------------------------------------------


def test_an_answered_exchange_with_no_answer_is_refused(engine: Engine, tenant_id: UUID) -> None:
    refused_as(engine, tenant_id, "answer_iff_answered", answer=None)
    refused_as(engine, tenant_id, "answer_iff_answered", answer="   ")


def test_an_answer_beside_a_refusal_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """The row two screens would render as two different things."""
    refused_as(engine, tenant_id, "answer_iff_answered", **{**REFUSED, "answer": "It cost {{x}}."})


# --- the refusal, both directions -------------------------------------------------


def test_a_refusal_with_no_reason_is_refused(engine: Engine, tenant_id: UUID) -> None:
    refused_as(engine, tenant_id, "reason_iff_refused", **{**REFUSED, "reason": None})


def test_a_refusal_reason_below_the_shared_floor_is_refused(
    engine: Engine, tenant_id: UUID
) -> None:
    short = "x" * (REASON_MIN_LENGTH - 1)
    refused_as(engine, tenant_id, "reason_iff_refused", **{**REFUSED, "reason": short})


def test_a_reason_on_an_answered_exchange_is_refused(engine: Engine, tenant_id: UUID) -> None:
    refused_as(engine, tenant_id, "reason_iff_refused", reason=REASON)


def test_a_refusal_names_one_of_the_five_gaps(engine: Engine, tenant_id: UUID) -> None:
    refused_as(engine, tenant_id, "gap_iff_refused", **{**REFUSED, "gap": None})
    refused_as(engine, tenant_id, "gap_iff_refused", **{**REFUSED, "gap": "forecast"})
    refused_as(engine, tenant_id, "gap_iff_refused", gap="tool")


def test_a_screen_link_belongs_only_to_a_refusal(engine: Engine, tenant_id: UUID) -> None:
    refused_as(engine, tenant_id, "screen_only_on_refusal", screen="/cost/containers")
    with engine.begin() as connection:
        an_exchange(connection, tenant_id, **REFUSED, screen="/cost/containers")


# --- the failure, both directions -------------------------------------------------


def test_a_failure_with_no_cause_is_refused(engine: Engine, tenant_id: UUID) -> None:
    refused_as(engine, tenant_id, "cause_iff_failed", **{**FAILED, "cause": None})


def test_a_cause_on_an_answered_exchange_is_refused(engine: Engine, tenant_id: UUID) -> None:
    refused_as(engine, tenant_id, "cause_iff_failed", cause="Throttled")


def test_a_generic_cause_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """ISS-015: the moment a catch all exists, every failure becomes it."""
    refused_as(engine, tenant_id, "cause_iff_failed", **{**FAILED, "cause": "Unknown"})


@pytest.mark.parametrize("cause", models.ERROR_TYPES)
def test_every_one_of_the_seven_causes_is_accepted(
    engine: Engine, tenant_id: UUID, cause: str
) -> None:
    with engine.begin() as connection:
        an_exchange(connection, tenant_id, **{**FAILED, "cause": cause})


def test_a_failure_detail_belongs_only_to_a_failure(engine: Engine, tenant_id: UUID) -> None:
    refused_as(engine, tenant_id, "detail_only_on_failure", detail="nothing went wrong")


# --- citations and spend ----------------------------------------------------------


def test_a_citation_beside_a_refusal_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """A figure shown under a sentence saying there was no figure to show."""
    refused_as(
        engine, tenant_id, "citations_only_on_answer", **{**REFUSED, "citations": [CITATION]}
    )


def test_citations_and_tool_calls_are_arrays(engine: Engine, tenant_id: UUID) -> None:
    refused_as(engine, tenant_id, "citations_only_on_answer", citations=CITATION)
    refused_as(engine, tenant_id, "citations_only_on_answer", calls=CALL)


def test_spend_is_never_negative(engine: Engine, tenant_id: UUID) -> None:
    refused_as(engine, tenant_id, "spend_not_negative", input=-1)
    refused_as(engine, tenant_id, "spend_not_negative", cost="-0.01")


def test_spend_with_no_model_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """Spend nobody can attribute is the line the platform cost screen cannot reconcile."""
    refused_as(engine, tenant_id, "spend_needs_a_model", model=None)


def test_an_exchange_that_reached_no_model_spends_nothing(engine: Engine, tenant_id: UUID) -> None:
    """A refusal on budget never reached a model, and its zero is the truth."""
    with engine.begin() as connection:
        an_exchange(
            connection,
            tenant_id,
            **{**REFUSED, "gap": "budget"},
            model=None,
            input=0,
            output=0,
            cost="0",
        )


def test_a_model_that_failed_before_reporting_spend_is_accepted(
    engine: Engine, tenant_id: UUID
) -> None:
    """A throttled call names the model it was sent to and spent nothing."""
    with engine.begin() as connection:
        an_exchange(connection, tenant_id, **{**FAILED, "cause": "Throttled"}, input=0, output=0)


def test_spend_has_no_default_so_a_forgotten_figure_is_not_a_zero(
    engine: Engine, tenant_id: UUID
) -> None:
    forgetful = text(
        "INSERT INTO assistant_exchange (exchange_id, tenant_id, principal_id, question, "
        "outcome, answer, citations, tool_calls, model_id, asked_at, answered_at) VALUES "
        "(:id, :t, 'principal-a', 'q?', 'ANSWERED', 'a', CAST('[]' AS JSONB), "
        "CAST('[]' AS JSONB), 'configured-model', :at, :at)"
    )
    with engine.begin() as connection, pytest.raises(IntegrityError, match="input_tokens"):
        connection.execute(forgetful, {"id": uuid4(), "t": tenant_id, "at": ASKED})


# --- time, and the question --------------------------------------------------------


def test_an_answer_before_its_question_is_refused(engine: Engine, tenant_id: UUID) -> None:
    refused_as(engine, tenant_id, "answered_after_asked", answered=ASKED - timedelta(seconds=1))


def test_a_blank_question_or_asker_is_refused(engine: Engine, tenant_id: UUID) -> None:
    refused_as(engine, tenant_id, "who_and_what_not_blank", question="  ")
    refused_as(engine, tenant_id, "who_and_what_not_blank", who=" ")


def test_the_question_is_stored_exactly_as_typed(engine: Engine, tenant_id: UUID) -> None:
    """The wording is the evidence when an answer turns out wrong."""
    typed = "  what did   EC2 cost?\n"
    with engine.begin() as connection:
        exchange = an_exchange(connection, tenant_id, question=typed)
        stored = connection.execute(
            text("SELECT question FROM assistant_exchange WHERE exchange_id = :id"),
            {"id": exchange},
        ).scalar_one()
    assert stored == typed


# --- the mirrors, and the shape of the migration -----------------------------------


def test_the_stored_outcomes_and_gaps_mirror_the_domain() -> None:
    assert set(models.EXCHANGE_OUTCOMES) == {member.value for member in Outcome}
    assert set(models.REFUSAL_GAPS) == {member.value for member in Gap}


def test_the_migration_touches_nothing_but_its_own_table() -> None:
    """Constraint 12. A new table no earlier release reads or writes is backward compatible
    by construction, and this holds the construction rather than trusting it."""
    spec = importlib.util.spec_from_file_location("migration_0023", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    touched = {
        name
        for statement in module._UP
        for name in re.findall(
            r"\b(?:TABLE(?: IF NOT EXISTS)?|ON)\s+([a-z_]+)", statement, flags=re.IGNORECASE
        )
    }
    assert touched == {"assistant_exchange"}
    assert not any("DROP TABLE" in statement.upper() for statement in module._UP)


# --- team_digest, 0024 ------------------------------------------------------------------

INSERT_DIGEST = text(
    "INSERT INTO team_digest (digest_id, tenant_id, ingest_run_id, audience, team, "
    "period_start, period_end, prose, citations, composed_at, sent_at, unsent_reason) "
    "VALUES (:id, :t, :run, :audience, :team, :start, :end, :prose, "
    "CAST(:citations AS JSONB), :at, :sent, :reason)"
)
UNSENT = "No sender is configured, so it was kept. OPEN-11."


def a_digest(connection: Connection, tenant: UUID, **overrides: Any) -> None:
    """One team digest, composed and not sent, with any field overridden."""
    values: dict[str, Any] = {
        "id": uuid4(),
        "t": tenant,
        "run": uuid4(),
        "audience": "team",
        "team": "payments",
        "start": date(2026, 7, 13),
        "end": date(2026, 7, 19),
        "prose": "In the week to {{week_end}}, {{team}} spent {{spend}}.",
        "citations": "[]",
        "at": ASKED,
        "sent": None,
        "reason": UNSENT,
    }
    values.update(overrides)
    connection.execute(INSERT_DIGEST, values)


def digest_refused_as(engine: Engine, tenant: UUID, constraint: str, **overrides: Any) -> None:
    with engine.begin() as connection, pytest.raises(IntegrityError, match=constraint):
        a_digest(connection, tenant, **overrides)


def test_a_team_digest_and_the_organizations_are_accepted(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        a_digest(connection, tenant_id)
        a_digest(connection, tenant_id, audience="executive", team=None)


def test_a_digest_is_for_a_team_or_the_executive_and_nobody_else(
    engine: Engine, tenant_id: UUID
) -> None:
    digest_refused_as(engine, tenant_id, "ck_team_digest__audience", audience="board")


def test_a_team_digest_names_its_team_and_an_executive_one_names_none(
    engine: Engine, tenant_id: UUID
) -> None:
    digest_refused_as(engine, tenant_id, "team_iff_team_audience", team=None)
    digest_refused_as(engine, tenant_id, "team_iff_team_audience", team="  ")
    digest_refused_as(engine, tenant_id, "team_iff_team_audience", audience="executive")


def test_an_unsent_digest_says_why_and_a_sent_one_does_not(engine: Engine, tenant_id: UUID) -> None:
    digest_refused_as(engine, tenant_id, "reason_iff_unsent", reason=None)
    digest_refused_as(engine, tenant_id, "reason_iff_unsent", reason="x" * (REASON_MIN_LENGTH - 1))
    digest_refused_as(engine, tenant_id, "reason_iff_unsent", sent=ASKED)
    with engine.begin() as connection:
        a_digest(connection, tenant_id, team="sent", sent=ANSWERED, reason=None)


def test_a_digest_cannot_be_sent_before_it_was_composed(engine: Engine, tenant_id: UUID) -> None:
    digest_refused_as(
        engine, tenant_id, "sent_after_composed", sent=ASKED - timedelta(minutes=1), reason=None
    )


def test_a_digest_covers_a_week_and_says_something(engine: Engine, tenant_id: UUID) -> None:
    digest_refused_as(engine, tenant_id, "a_week_with_prose", end=date(2026, 7, 13))
    digest_refused_as(engine, tenant_id, "a_week_with_prose", prose="   ")
    digest_refused_as(engine, tenant_id, "a_week_with_prose", citations='{"not": "a list"}')


def test_one_digest_per_audience_team_and_week(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        a_digest(connection, tenant_id, audience="executive", team=None)
    digest_refused_as(
        engine, tenant_id, "uq_team_digest__identity", audience="executive", team=None
    )


def test_the_stored_audiences_mirror_the_domain() -> None:
    assert set(models.DIGEST_AUDIENCES) == {member.value for member in Audience}


# --- redaction_event, 0025 -------------------------------------------------------------

INSERT_EVENT = text(
    "INSERT INTO redaction_event (event_id, tenant_id, exchange_id, principal_id, rule_id, "
    "action, occurred_at) VALUES (:id, :t, :exchange, :who, :rule, :action, :at)"
)


def an_event(connection: Connection, tenant: UUID, exchange: UUID, **overrides: Any) -> None:
    values: dict[str, Any] = {
        "id": uuid4(),
        "t": tenant,
        "exchange": exchange,
        "who": "principal-a",
        "rule": "aws-access-token",
        "action": "BLOCKED",
        "at": ASKED,
    }
    values.update(overrides)
    connection.execute(INSERT_EVENT, values)


def test_an_event_names_its_rule_and_one_of_two_actions(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        exchange = an_exchange(connection, tenant_id, **REFUSED)
        an_event(connection, tenant_id, exchange)
        an_event(connection, tenant_id, exchange, rule="jwt", action="REDACTED")
    for override, constraint in (
        ({"action": "IGNORED"}, "ck_redaction_event__action"),
        ({"rule": " "}, "ck_redaction_event__named"),
        ({"who": ""}, "ck_redaction_event__named"),
    ):
        with engine.begin() as connection, pytest.raises(IntegrityError, match=constraint):
            an_event(connection, tenant_id, exchange, **override)


def test_an_event_cannot_name_an_exchange_that_does_not_exist(
    engine: Engine, tenant_id: UUID
) -> None:
    with engine.begin() as connection, pytest.raises(IntegrityError, match="exchange_id"):
        an_event(connection, tenant_id, uuid4())


def test_the_stored_actions_mirror_the_domain() -> None:
    assert set(models.REDACTION_ACTIONS) == {member.value for member in Action}
