"""The exchange guard, then the two routes it protects. TASK-P7-010.

The guard first and at the repository, because constraint 3 puts scope in two places and a
route that forgot its dependency must still not read out of scope. ADR-0029 adds the case
this table is the first to need: one person reading another's questions, which is refused
whatever else the reader's scope reaches.

Then the routes, through the real application, a scripted model and the in process
toolbox, so every tool call in these tests goes back through the API as the asker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from finops_api.db import models
from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.assistant import (
    DigestRepository,
    ExchangeRepository,
    record_exchange,
)
from finops_api.guards import SCOPED_TABLES, ByPrincipal, PayerWide
from finops_api.identity.session import SessionSigner
from finops_api.main import create_app, returns_envelope
from finops_api.routes import assistant as assistant_routes
from finops_core.config import Settings
from finops_core.domain.insight import Gap, Refusal
from finops_core.domain.tenant import Scope
from finops_core.ports.llm import Message, TokenUsage
from finops_fakes.llm import ScriptedModel
from finops_ingest.collectors.digests import DigestCollector
from finops_ingest.registry import CollectorContext
from finops_query.insight import Exchange
from tests.api.test_query_routes import NOW, SIGNING_KEY, StubEntitlements, another_tenant, auth
from tests.query.insight.harness import (
    IN_SCOPE,
    OUT_OF_SCOPE,
    answer,
    call,
    everything,
    only,
    seed_bill,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("clear_split_gap")]

ASK = "/api/v1/assistant/ask"
LIST = "/api/v1/assistant/exchanges"
MODEL_ID = "a-configured-model"
QUESTION = "Which service cost the most last month?"
CONTEXT = AccessContext(request_id="test")

#: A tenant's stored citations as a row written before ISS-231 held them, with no unit in any.
STRIP_EXCHANGE_UNITS = text(
    "UPDATE assistant_exchange SET citations = (SELECT COALESCE(jsonb_agg(c - 'unit'), "
    "'[]'::jsonb) FROM jsonb_array_elements(citations) AS c) WHERE tenant_id = :t"
)
STRIP_DIGEST_UNITS = text(
    "UPDATE team_digest SET citations = (SELECT COALESCE(jsonb_agg(c - 'unit'), "
    "'[]'::jsonb) FROM jsonb_array_elements(citations) AS c) WHERE tenant_id = :t"
)


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module seeds the fake bill's month, so it gives it back."""


def scripted(*cases: tuple[str, tuple[Message, ...]]) -> ScriptedModel:
    leading = (
        call("t1", "get_cost_by_service"),
        answer(
            "{{service}} cost the most, at {{cost}}.",
            service=("t1", "data[name=AmazonEC2].name"),
            cost=("t1", "data[name=AmazonEC2].effective_cost"),
        ),
    )
    return ScriptedModel({QUESTION: leading, **dict(cases)})


def application(
    engine: Engine, settings: Settings, scope: Scope, model: ScriptedModel | None = None
) -> tuple[TestClient, SessionSigner]:
    signer = SessionSigner(SIGNING_KEY, ttl_hours=8, clock=lambda: NOW)
    configured = settings.model_copy(update={"assistant_model_id": MODEL_ID if model else ""})
    app = create_app(
        engine=engine,
        entitlements=StubEntitlements(scope),
        signer=signer,
        settings=configured,
        language_model=model,
    )
    return TestClient(app, raise_server_exceptions=False), signer


def as_person(signer: SessionSigner, principal: str, scope: Scope) -> dict[str, str]:
    return auth(signer.issue(principal, f"{principal}@example.local", scope))


def asked(client: TestClient, headers: dict[str, str], question: str = QUESTION) -> dict[str, Any]:
    response = client.post(ASK, json={"question": question}, headers=headers)
    assert response.status_code == 200, response.text
    return dict(response.json())


def rows(engine: Engine, tenant: UUID) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text("SELECT count(*) FROM assistant_exchange WHERE tenant_id = :t"), {"t": tenant}
            ).scalar_one()
        )


def refused_exchange(question: str) -> Exchange:
    return Exchange(
        question=question,
        outcome=Refusal(gap=Gap.TOOL, reason="No tool answers that question here."),
        tool_calls=(),
        usage=TokenUsage(input_tokens=0, output_tokens=0),
    )


def write_for(engine: Engine, tenant: UUID, principal: str) -> UUID:
    with engine.begin() as connection:
        return record_exchange(
            connection,
            tenant_id=tenant,
            principal_id=principal,
            exchange=refused_exchange(f"a question from {principal}"),
            model_id=None,
            est_cost=Decimal(0),
            asked_at=NOW,
            answered_at=NOW,
        )


def everyone(tenant: UUID, principal: str | None) -> Scope:
    """An organization wide scope, which ADR-0029 says does not widen this table."""
    return Scope(tenant_id=tenant, is_global=True, accounts=frozenset(), principal_id=principal)


# --- the guard, before any route ---------------------------------------------------------


class TestTheGuardBeforeAnyRoute:
    def test_the_exchange_table_is_scoped_by_its_principal(self) -> None:
        assert SCOPED_TABLES["assistant_exchange"] == ByPrincipal("principal_id")
        assert "principal_id" in models.metadata.tables["assistant_exchange"].columns

    def test_one_person_cannot_read_anothers_questions_even_organization_wide(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        mine = write_for(engine, tenant_id, "p2")
        with engine.connect() as connection:
            repository = ExchangeRepository(connection, CONTEXT)
            assert [r.exchange_id for r in repository.exchanges(everyone(tenant_id, "p2"), 10)] == [
                mine
            ]
            assert repository.exchanges(everyone(tenant_id, "p3"), 10) == []
            assert repository.exchange(everyone(tenant_id, "p3"), mine) is None

    def test_a_scope_naming_no_person_reads_nothing(self, engine: Engine, tenant_id: UUID) -> None:
        """Fail closed, as a scope naming no account does."""
        write_for(engine, tenant_id, "p2")
        with engine.connect() as connection:
            assert (
                ExchangeRepository(connection, CONTEXT).exchanges(everyone(tenant_id, None), 10)
                == []
            )

    def test_the_same_person_in_another_tenant_reads_nothing(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        write_for(engine, tenant_id, "p2")
        elsewhere = another_tenant(engine)
        with engine.connect() as connection:
            assert (
                ExchangeRepository(connection, CONTEXT).exchanges(everyone(elsewhere, "p2"), 10)
                == []
            )


# --- the routes ------------------------------------------------------------------------------


class TestTheRoutes:
    def test_asking_answers_with_cited_figures_and_writes_one_row(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed_bill(engine, tenant_id, split=False)
        scope = everything(tenant_id)
        client, signer = application(engine, settings, scope, scripted())
        before = rows(engine, tenant_id)

        body = asked(client, as_person(signer, "p2", scope))

        assert set(body) == {"data", "meta"}
        data = body["data"]
        assert (data["outcome"], data["refusal"], data["failure"]) == ("ANSWERED", None, None)
        assert {c["placeholder"]: c["unit"] for c in data["answer"]["citations"]} == {
            "service": None,
            "cost": "usd",
        }, "the unit the tool table declares, carried through the row to the screen"
        assert data["model_id"] == MODEL_ID
        assert data["input_tokens"] > 0
        assert Decimal(data["est_cost"]) > 0
        assert body["meta"]["as_of"] is not None, "an answer is as fresh as its stalest figure"
        assert rows(engine, tenant_id) == before + 1

    def test_a_figure_stored_before_citations_carried_a_unit_is_read_with_none(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """ISS-231. A row written before the unit has none, and the list still reads it,
        sending no unit rather than failing or choosing one for it."""
        seed_bill(engine, tenant_id, split=False)
        scope = everything(tenant_id)
        client, signer = application(engine, settings, scope, scripted())
        mine = as_person(signer, "p2", scope)
        asked(client, mine)
        with engine.begin() as connection:
            connection.execute(STRIP_EXCHANGE_UNITS, {"t": tenant_id})

        response = client.get(LIST, headers=mine)

        assert response.status_code == 200, response.text
        (exchange,) = response.json()["data"]
        assert {
            c["placeholder"]: (c["kind"], c["unit"]) for c in exchange["answer"]["citations"]
        } == {
            "service": ("label", None),
            "cost": ("figure", None),
        }

    def test_a_refusal_comes_back_as_a_refusal_and_nothing_else(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        question = "What will we spend next month?"
        scope = everything(tenant_id)
        client, signer = application(
            engine, settings, scope, scripted((question, (call("t1", "forecast_next_month"),)))
        )

        data = asked(client, as_person(signer, "p2", scope), question)["data"]

        assert (data["outcome"], data["answer"], data["failure"]) == ("REFUSED", None, None)
        assert data["refusal"]["gap"] == "tool"
        assert "forecast_next_month" in data["refusal"]["reason"]

    def test_without_a_model_the_assistant_fails_as_not_enabled_and_says_what_to_do(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        scope = everything(tenant_id)
        client, signer = application(engine, settings, scope)

        data = asked(client, as_person(signer, "p2", scope))["data"]

        assert (data["outcome"], data["answer"], data["refusal"]) == ("FAILED", None, None)
        assert data["failure"]["cause"] == "NotOptedIn"
        assert data["failure"]["remediation"]
        assert (data["model_id"], data["input_tokens"], Decimal(data["est_cost"])) == (
            None,
            0,
            Decimal(0),
        )

    def test_an_out_of_scope_account_is_refused_through_the_route_too(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The in process tool call carries the asker's token, not a better one."""
        seed_bill(engine, tenant_id, split=False)
        question = f"What did {OUT_OF_SCOPE} cost?"
        turns = (
            call("t1", "get_cost_by_account"),
            answer("It cost {{cost}}.", cost=("t1", f"data[name={OUT_OF_SCOPE}].effective_cost")),
        )
        scope = only(tenant_id, IN_SCOPE)
        client, signer = application(engine, settings, scope, scripted((question, turns)))

        data = asked(client, as_person(signer, "p2", scope), question)["data"]

        assert data["outcome"] == "REFUSED"
        assert data["refusal"]["gap"] == "scope"

    def test_the_list_is_the_askers_own_newest_first(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        scope = everything(tenant_id)
        client, signer = application(engine, settings, scope)
        mine = as_person(signer, "p2", scope)
        theirs = as_person(signer, "p3", scope)
        first = asked(client, mine, "first question")["data"]["exchange_id"]
        second = asked(client, mine, "second question")["data"]["exchange_id"]
        asked(client, theirs, "somebody else's question")

        listed = client.get(LIST, headers=mine).json()

        assert [e["exchange_id"] for e in listed["data"]] == [second, first]
        assert listed["meta"]["scope_coverage"]["unit"] == "exchanges"
        assert [e["question"] for e in client.get(LIST, headers=theirs).json()["data"]] == [
            "somebody else's question"
        ]

    def test_reading_the_list_writes_nothing(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        scope = everything(tenant_id)
        client, signer = application(engine, settings, scope)
        asked(client, as_person(signer, "p2", scope))
        before = rows(engine, tenant_id)

        assert client.get(LIST, headers=as_person(signer, "p2", scope)).status_code == 200
        assert rows(engine, tenant_id) == before

    def test_a_question_too_long_is_refused_before_anything_runs(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        scope = everything(tenant_id)
        model = scripted()
        client, signer = application(engine, settings, scope, model)

        response = client.post(
            ASK, json={"question": "x" * 2001}, headers=as_person(signer, "p2", scope)
        )

        assert response.status_code == 422
        assert rows(engine, tenant_id) == 0
        assert model.received == ()


def test_ask_is_the_only_write_and_every_route_returns_the_envelope() -> None:
    routes = [r for r in assistant_routes.router.routes if isinstance(r, APIRoute)]
    assert {r.path: r.methods for r in routes} == {
        ASK: {"POST"},
        LIST: {"GET"},
        DIGESTS: {"GET"},
        REDACTIONS: {"GET"},
    }
    assert all(returns_envelope(r.response_model) for r in routes)


# --- the digests, TASK-P7-012 --------------------------------------------------------------

DIGESTS = "/api/v1/assistant/digests"
REDACTIONS = "/api/v1/assistant/redactions"
#: A Monday in the fake bill's closed month, so a whole billed week lies behind it.
DIGEST_CLOCK = datetime(2026, 7, 20, 6, 0, tzinfo=UTC)


@dataclass(frozen=True)
class _Unit:
    tenant_id: UUID


def digests_for(engine: Engine, tenant: UUID) -> None:
    seed_bill(engine, tenant, split=False)
    with engine.begin() as connection:
        DigestCollector(clock=lambda: DIGEST_CLOCK)(
            CollectorContext(unit=_Unit(tenant_id=tenant), connection=connection, run_id=uuid4())
        )


class TestTheDigests:
    def test_the_digest_table_is_payer_wide(self) -> None:
        """A digest sums every account, so it belongs to none of them."""
        assert SCOPED_TABLES["team_digest"] == PayerWide()

    def test_a_narrowed_reader_reads_no_digest_before_any_route(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        digests_for(engine, tenant_id)
        with engine.connect() as connection:
            repository = DigestRepository(connection, CONTEXT)
            assert repository.digests(only(tenant_id, IN_SCOPE), 50) == []
            assert repository.digests(everything(tenant_id), 50)

    def test_the_route_lists_digests_composed_and_not_sent_saying_why(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        digests_for(engine, tenant_id)
        scope = everything(tenant_id)
        client, signer = application(engine, settings, scope)

        body = client.get(DIGESTS, headers=as_person(signer, "p2", scope)).json()

        assert set(body) == {"data", "meta"}
        assert body["data"][0]["audience"] == "executive", "the organization's comes first"
        assert all(d["sent_at"] is None and "OPEN-11" in d["unsent_reason"] for d in body["data"])
        assert body["meta"]["scope_coverage"] == {
            "visible": 1,
            "total": 1,
            "unit": "payer",
            "is_partial": False,
        }
        cited = [c for digest in body["data"] for c in digest["citations"]]
        assert {(c["kind"], c["unit"]) for c in cited} == {("figure", "usd"), ("label", None)}

    def test_a_digest_stored_before_citations_carried_a_unit_is_read_with_none(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """ISS-231, as for an exchange: read, and sent with no unit rather than a guessed one."""
        digests_for(engine, tenant_id)
        with engine.begin() as connection:
            connection.execute(STRIP_DIGEST_UNITS, {"t": tenant_id})
        scope = everything(tenant_id)
        client, signer = application(engine, settings, scope)

        response = client.get(DIGESTS, headers=as_person(signer, "p2", scope))

        assert response.status_code == 200, response.text
        cited = [c for digest in response.json()["data"] for c in digest["citations"]]
        assert cited, "nothing was read, so this proves nothing"
        assert {c["unit"] for c in cited} == {None}

    def test_a_narrowed_reader_is_shown_that_digests_need_the_whole_payer(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        digests_for(engine, tenant_id)
        scope = only(tenant_id, IN_SCOPE)
        client, signer = application(engine, settings, scope)

        body = client.get(DIGESTS, headers=as_person(signer, "p2", scope)).json()

        assert body["data"] == []
        assert body["meta"]["scope_coverage"]["is_partial"] is True


def test_a_question_is_never_a_query_parameter() -> None:
    """A question can hold anything, and a URL is written into every access log."""
    (route,) = [r for r in assistant_routes.router.routes if getattr(r, "path", "") == ASK]
    assert isinstance(route, APIRoute)
    assert [param.name for param in route.dependant.query_params] == []
    assert [param.name for param in route.dependant.body_params] == ["body"]
