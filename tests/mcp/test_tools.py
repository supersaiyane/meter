"""The facade is tested against the real API, never against a stub of it.

The whole claim of ADR-0009 is that the MCP path enforces exactly what the HTTP
path enforces, because it is the HTTP path. A test that pointed the tools at a
fake would prove the tools call something, which is not the claim. So the
transport here is the API's own TestClient over the real application, the real
scope dependency and the real repository guard, and a scope test failing here
means an authorization bug rather than a mocking mistake.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from finops_api.identity import SessionSigner
from finops_api.main import create_app
from finops_api.tools import TOOLS_BY_NAME
from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.identity import Entitlement, Principal
from finops_core.domain.tenant import Scope
from finops_mcp.api import ApiError, MeterApi
from finops_mcp.server import MissingTokenError, make_handler

NOW = datetime(2026, 8, 27, 6, 0, tzinfo=UTC)
SIGNING_KEY = "a-test-signing-key"


class StubEntitlements:
    def __init__(self, scope: Scope) -> None:
        self.scope = scope

    def resolve(self, principal: Principal) -> Entitlement:
        return Entitlement(principal=principal, scope=self.scope, as_of=NOW, collected_at=NOW)


#: Every test here runs the real application against a real Postgres. The whole
#: claim is that the MCP path enforces what the HTTP path enforces, and a stub
#: would only prove that the tools call something.
pytestmark = pytest.mark.integration


def seed(engine: Engine, tenant: UUID, account_ids: tuple[str, ...]) -> None:
    with engine.begin() as connection:
        for account_id in account_ids:
            connection.execute(
                text(
                    "INSERT INTO cloud_account (account_pk, tenant_id, provider, "
                    "account_id, name, status, as_of, collected_at) VALUES "
                    "(:pk, :tenant, 'aws', :account, :account, 'ACTIVE', :at, :at)"
                ),
                {"pk": uuid4(), "tenant": tenant, "account": account_id, "at": NOW},
            )


def api_for(engine: Engine, scope: Scope, settings: Settings) -> tuple[MeterApi, str]:
    """The transport is the real application, so the tools call the real guard."""
    signer = SessionSigner(SIGNING_KEY, ttl_hours=8, clock=lambda: NOW)
    app = create_app(
        engine=engine,
        entitlements=StubEntitlements(scope),
        signer=signer,
        settings=settings,
    )
    client = TestClient(app)
    return MeterApi("", transport=client), signer.issue("p1", "someone@example.local", scope)


def scoped_to(tenant: UUID, accounts: tuple[str, ...]) -> Scope:
    return Scope(
        tenant_id=tenant,
        is_global=False,
        accounts=frozenset(AccountKey(Provider.AWS, a) for a in accounts),
    )


def test_a_tool_returns_exactly_what_the_caller_is_entitled_to(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The MCP path enforces what the HTTP path enforces, because it is it."""
    seed(engine, tenant_id, ("a-1", "a-2", "a-3", "a-4"))
    api, token = api_for(engine, scoped_to(tenant_id, ("a-1", "a-2")), settings)

    payload = api.get(TOOLS_BY_NAME["list_accounts"].path, token)

    assert {row["account_id"] for row in payload["data"]} == {"a-1", "a-2"}


def test_the_meta_envelope_survives_the_facade(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A model with no coverage figure states a partial total as a complete one,
    confidently. Threat model row I."""
    seed(engine, tenant_id, ("a-1", "a-2", "a-3", "a-4"))
    api, token = api_for(engine, scoped_to(tenant_id, ("a-1", "a-2")), settings)

    meta = api.get(TOOLS_BY_NAME["list_accounts"].path, token)["meta"]

    assert meta["scope_coverage"]["visible"] == 2
    assert meta["scope_coverage"]["total"] == 4, "counted over the organization, not the view"
    assert meta["scope_coverage"]["is_partial"] is True
    assert "as_of" in meta and "collected_at" in meta
    assert meta["degraded"] is True, "two accounts of four is not a complete answer"


class StubContext:
    """Just the one attribute a handler reads.

    The SDK populates `Context.headers` from the transport's request object, and
    building one of those would be testing the SDK. This exercises the exact
    callable `build_server` registers, which is the part that is ours.
    """

    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


def test_the_registered_handler_returns_the_envelope_and_not_just_the_data(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Through the handler, not around it. A handler that unwrapped to `data`
    would pass every other test here and still blind the model to coverage."""
    seed(engine, tenant_id, ("a-1", "a-2"))
    api, token = api_for(engine, scoped_to(tenant_id, ("a-1",)), settings)
    handler = make_handler(TOOLS_BY_NAME["list_accounts"], api)

    result = handler(StubContext({"Authorization": f"Bearer {token}"}))  # type: ignore[arg-type]

    assert set(result) >= {"data", "meta"}
    assert [row["account_id"] for row in result["data"]] == ["a-1"]


def test_a_handler_with_no_caller_token_refuses_before_it_calls_anything(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The facade has no credential of its own to fall back to."""
    api, _ = api_for(engine, scoped_to(tenant_id, ("a-1",)), settings)
    handler = make_handler(TOOLS_BY_NAME["list_accounts"], api)

    with pytest.raises(MissingTokenError):
        handler(StubContext({}))  # type: ignore[arg-type]


def test_an_unauthenticated_call_is_refused_by_the_api_not_by_the_facade(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The facade does not decide who may read. It forwards and reports."""
    api, _ = api_for(engine, scoped_to(tenant_id, ("a-1",)), settings)

    with pytest.raises(ApiError) as raised:
        api.get(TOOLS_BY_NAME["list_accounts"].path, "not-a-real-token")

    assert raised.value.status == 401
