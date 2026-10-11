"""The adversarial test for ISS-009, and the envelope contract.

Constraint 3 puts scope enforcement in two independent places. The request
dependency is the one a route author remembers. The repository guard is the one
that holds when they do not, and the only way to know it holds is to write the
route that forgets and check that nothing comes back.

The plan says not to delete that test once every route has the dependency. It
exists for the route somebody adds next year, in a hurry, at the end of a
Friday.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from finops_api.db.repositories import AccessContext, AccountRepository
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.identity import SessionSigner
from finops_api.main import ENVELOPE_EXEMPT, EnvelopeContractError, create_app
from finops_api.schemas import CoverageOut, Envelope, Meta
from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.identity import Entitlement, Principal
from finops_core.domain.tenant import Scope

NOW = datetime(2026, 8, 27, 6, 0, tzinfo=UTC)
SIGNING_KEY = "a-test-signing-key"
REGION = "eu-west-1"


class StubEntitlements:
    """Resolves whatever scope the test wants, as the real resolver would."""

    def __init__(self, scope: Scope) -> None:
        self.scope = scope

    def resolve(self, principal: Principal) -> Entitlement:
        return Entitlement(principal=principal, scope=self.scope, as_of=NOW, collected_at=NOW)


def probe_router() -> APIRouter:
    """Two routes: one that scopes properly, and one that forgets."""
    router = APIRouter()

    @router.get("/probe/scoped", response_model=Envelope[list[str]])
    def scoped(
        scope: Scope = Depends(get_scope),
        connection: Connection = Depends(get_connection),
        context: AccessContext = Depends(get_access_context),
    ) -> Envelope[list[str]]:
        rows = AccountRepository(connection, context).list_in_scope(scope)
        names = [str(row.account_id) for row in rows]
        return Envelope(data=names, meta=Meta.build(visible=len(names), total=len(names)))

    @router.get("/probe/forgetful", response_model=Envelope[list[str]])
    def forgetful(
        connection: Connection = Depends(get_connection),
        context: AccessContext = Depends(get_access_context),
    ) -> Envelope[list[str]]:
        # The mistake this whole design exists to survive: a route that reads
        # without ever asking who is asking.
        rows = AccountRepository(connection, context).list_in_scope(None)  # type: ignore[arg-type]
        names = [str(row.account_id) for row in rows]
        return Envelope(data=names, meta=Meta.build(visible=len(names), total=len(names)))

    return router


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


def client_for(engine: Engine, scope: Scope, settings: Settings) -> tuple[TestClient, str]:
    """Settings are passed rather than loaded.

    `get_settings` is cached for the process, which is right in production and
    a trap in a test: whichever test ran first decides what every later one
    sees. Passing them makes each test say what it is running against.
    """
    signer = SessionSigner(SIGNING_KEY, ttl_hours=8, clock=lambda: NOW)
    app = create_app(
        engine=engine,
        entitlements=StubEntitlements(scope),
        signer=signer,
        settings=settings,
        extra_routers=(probe_router(),),
    )
    token = signer.issue("p1", "someone@example.local", scope)
    return TestClient(app, raise_server_exceptions=False), token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- the envelope contract, with no database --------------------------------


def test_the_app_refuses_to_start_with_a_route_that_returns_bare_data(
    settings: Settings,
) -> None:
    """The freshness contract is worth nothing unless it is universal."""
    bare = APIRouter()

    @bare.get("/probe/bare", response_model=list[str])
    def bare_route() -> list[str]:
        return []

    with pytest.raises(EnvelopeContractError, match="/probe/bare"):
        create_app(
            engine=None,  # type: ignore[arg-type]
            entitlements=None,
            signer=None,
            settings=settings,
            extra_routers=(bare,),
        )


def test_the_exemptions_are_named_rather_than_inferred() -> None:
    """An exemption somebody decided on, not a route that slipped through."""
    assert "/healthz" in ENVELOPE_EXEMPT


def test_degraded_is_computed_from_the_three_things_that_make_a_view_untrustworthy() -> None:
    complete = Meta.build(visible=5, total=5, as_of=NOW, collected_at=NOW)
    assert complete.degraded is False

    partial = Meta.build(visible=2, total=5, as_of=NOW, collected_at=NOW)
    assert partial.degraded is True
    assert partial.scope_coverage.is_partial is True

    never_collected = Meta.build(visible=5, total=5)
    assert never_collected.degraded is True


def test_coverage_reports_the_organization_total_not_the_visible_one() -> None:
    """ISS-016 in the response shape itself."""
    assert CoverageOut(visible=2, total=5).is_partial is True
    assert CoverageOut(visible=5, total=5).is_partial is False


def test_a_chosen_account_travels_on_the_coverage() -> None:
    """FEAT-075. A view narrowed on purpose says so, and is not therefore untrustworthy."""
    meta = Meta.build(visible=1, total=1, as_of=NOW, collected_at=NOW, chosen="444455556666")

    assert meta.scope_coverage.chosen == "444455556666"
    assert meta.degraded is False
    assert Meta.build(visible=5, total=5).scope_coverage.chosen is None


# --- against a real database -------------------------------------------------


@pytest.mark.integration
def test_route_without_dependency_cannot_leak(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Spec section 11. The adversarial test for ISS-009.

    Do not delete this because every route has the dependency now. It is here
    for the route somebody adds next year.
    """
    other = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenant (tenant_id, name) VALUES (:id, :name)"),
            {"id": other, "name": f"tenant-{other}"},
        )
    seed(engine, tenant_id, ("111122223333",))
    seed(engine, other, ("999988887777",))

    scope = Scope(
        tenant_id=tenant_id,
        is_global=False,
        accounts=frozenset({AccountKey(provider=Provider.AWS, account_id="111122223333")}),
    )
    client, token = client_for(engine, scope, settings)

    response = client.get("/probe/forgetful", headers=auth(token))
    assert response.status_code == 500
    body = response.text
    assert "999988887777" not in body, "another tenant's account reached the response"
    assert "111122223333" not in body, "the route returned rows despite having no scope"


@pytest.mark.integration
def test_the_scoped_route_returns_only_what_the_scope_permits(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id, ("111122223333", "444455556666"))
    scope = Scope(
        tenant_id=tenant_id,
        is_global=False,
        accounts=frozenset({AccountKey(provider=Provider.AWS, account_id="111122223333")}),
    )
    client, token = client_for(engine, scope, settings)
    response = client.get("/probe/scoped", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["data"] == ["111122223333"]


@pytest.mark.integration
def test_a_chosen_account_narrows_a_route_that_knows_nothing_of_it(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """FEAT-075. The probe never names the choice, so the dependency is what applied it."""
    seed(engine, tenant_id, ("111122223333", "444455556666"))
    client, token = client_for(
        engine, Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset()), settings
    )

    response = client.get(
        "/probe/scoped", params={"chosen_account": "444455556666"}, headers=auth(token)
    )

    assert response.status_code == 200
    assert response.json()["data"] == ["444455556666"]


@pytest.mark.integration
def test_a_chosen_account_never_widens_and_an_absent_one_gets_the_same_answer(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A link naming an account outside the session must not read it, nor confirm it exists."""
    seed(engine, tenant_id, ("111122223333", "444455556666"))
    scope = Scope(
        tenant_id=tenant_id,
        is_global=False,
        accounts=frozenset({AccountKey(provider=Provider.AWS, account_id="111122223333")}),
    )
    client, token = client_for(engine, scope, settings)

    outside = client.get(
        "/probe/scoped", params={"chosen_account": "444455556666"}, headers=auth(token)
    )
    absent = client.get(
        "/probe/scoped", params={"chosen_account": "000000000000"}, headers=auth(token)
    )

    assert outside.status_code == absent.status_code == 404
    assert outside.json()["detail"] == absent.json()["detail"]
    assert "444455556666" not in outside.text


@pytest.mark.integration
def test_a_malformed_choice_is_refused_before_anything_is_read(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    client, token = client_for(
        engine, Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset()), settings
    )

    response = client.get(
        "/probe/scoped", params={"chosen_account": "1111' OR '1'='1"}, headers=auth(token)
    )

    assert response.status_code == 422


@pytest.mark.integration
def test_a_narrowed_view_counts_coverage_against_the_chosen_account(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The owner's decision of 2026-10-06: a choice is stated, never reported as partial."""
    seed(engine, tenant_id, ("111122223333", "444455556666", "777788889999"))
    client, token = client_for(
        engine, Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset()), settings
    )

    body = client.get(
        "/api/v1/accounts", params={"chosen_account": "444455556666"}, headers=auth(token)
    ).json()

    assert [row["account_id"] for row in body["data"]] == ["444455556666"]
    assert body["meta"]["scope_coverage"] == {
        "visible": 1,
        "total": 1,
        "unit": "accounts",
        "is_partial": False,
        "chosen": "444455556666",
    }


@pytest.mark.integration
def test_every_response_carries_meta(engine: Engine, tenant_id: UUID, settings: Settings) -> None:
    """Iterates the registered routes and asserts the envelope."""
    seed(engine, tenant_id, ("111122223333",))
    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    client, token = client_for(engine, scope, settings)

    for route in client.app.routes:  # type: ignore[attr-defined]
        path = getattr(route, "path", "")
        if path in ENVELOPE_EXEMPT or "{" in path or not path.startswith("/probe"):
            continue
        response = client.get(path, headers=auth(token))
        if response.status_code != 200:
            continue
        payload = response.json()
        assert "meta" in payload, path
        assert "scope_coverage" in payload["meta"], path
        assert "degraded" in payload["meta"], path
        assert "as_of" in payload["meta"], path


@pytest.mark.integration
def test_a_request_without_a_token_is_refused(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    client, _ = client_for(engine, scope, settings)
    assert client.get("/probe/scoped").status_code == 401


@pytest.mark.integration
def test_a_forged_token_is_refused(engine: Engine, tenant_id: UUID, settings: Settings) -> None:
    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    client, token = client_for(engine, scope, settings)
    body, _, signature = token.partition(".")
    forged = f"{body[:-2]}xx.{signature}"
    assert client.get("/probe/scoped", headers=auth(forged)).status_code == 401


@pytest.mark.integration
def test_the_request_id_comes_back_and_an_incoming_one_is_kept(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A trace that started at the edge must not be broken here."""
    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    client, token = client_for(engine, scope, settings)

    generated = client.get("/probe/scoped", headers=auth(token))
    assert generated.headers["X-Request-Id"]

    supplied = client.get("/probe/scoped", headers={**auth(token), "X-Request-Id": "from-the-edge"})
    assert supplied.headers["X-Request-Id"] == "from-the-edge"


@pytest.mark.integration
def test_a_read_writes_an_audit_row_carrying_the_request_id(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A fabricated scope is not preventable here, so it has to be visible after."""
    seed(engine, tenant_id, ("111122223333",))
    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    client, token = client_for(engine, scope, settings)
    client.get("/probe/scoped", headers={**auth(token), "X-Request-Id": "traceable"})

    with engine.connect() as connection:
        rows = (
            connection.execute(
                text("SELECT * FROM audit_event WHERE tenant_id = :t"), {"t": tenant_id}
            )
            .mappings()
            .all()
        )
    assert rows
    assert rows[0]["request_id"] == "traceable"
    assert rows[0]["is_global_read"] is True


# --- health ------------------------------------------------------------------


@pytest.mark.integration
def test_healthz_is_not_a_liveness_probe(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Never collected is stale, not healthy. That is the case it exists to surface."""
    from finops_ingest.registry import install_default_schedule

    with engine.begin() as connection:
        install_default_schedule(connection, tenant_id, updated_by="test")

    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    client, _ = client_for(engine, scope, settings)
    payload = client.get("/healthz").json()

    assert payload["database_reachable"] is True
    assert payload["status"] == "degraded"
    assert payload["collectors"]
    assert all(entry["is_stale"] for entry in payload["collectors"])


@pytest.fixture
def scheduled_alone(engine: Engine, tenant_id: UUID) -> Iterator[None]:
    """This tenant's collectors the only ones scheduled while the test runs. ISS-267.

    `/healthz` reports the worst tenant in the database, and the database is shared by the run: a
    tenant another suite left with a schedule and no run made this test degraded, depending only on
    which file pytest reached first. The other tenants' schedules are paused and given back.
    """
    with engine.begin() as connection:
        paused = connection.execute(
            text(
                "UPDATE collector_schedule SET is_enabled = false "
                "WHERE tenant_id <> :t AND is_enabled RETURNING tenant_id, collector"
            ),
            {"t": tenant_id},
        ).all()
    yield
    if paused:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE collector_schedule SET is_enabled = true "
                    "WHERE tenant_id = :t AND collector = :c"
                ),
                [{"t": row.tenant_id, "c": row.collector} for row in paused],
            )


@pytest.mark.integration
@pytest.mark.usefixtures("scheduled_alone")
def test_healthz_reports_a_recent_collection_as_healthy(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    from finops_ingest.registry import DEFAULT_SCHEDULE, install_default_schedule

    with engine.begin() as connection:
        install_default_schedule(connection, tenant_id, updated_by="test")
        # Every scheduled collector, taken from the schedule rather than listed
        # here. A hardcoded list would leave a newly added collector permanently
        # stale and this test asserting health over a tenant that is not healthy.
        for collector in (entry.collector for entry in DEFAULT_SCHEDULE):
            connection.execute(
                text(
                    "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, "
                    "idempotency_key, status, finished_at, as_of_window_start, "
                    "as_of_window_end) VALUES (:run, :tenant, :collector, 'scope', :key, "
                    "'SUCCEEDED', now(), now(), now())"
                ),
                {
                    "run": uuid4(),
                    "tenant": tenant_id,
                    "collector": collector,
                    "key": str(uuid4()),
                },
            )

    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    client, _ = client_for(engine, scope, settings)
    payload = client.get("/healthz").json()
    assert payload["status"] == "ok"
    assert not any(entry["is_stale"] for entry in payload["collectors"])


@pytest.mark.integration
def test_healthz_is_degraded_when_a_collector_has_fallen_behind(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    from finops_ingest.registry import install_default_schedule

    stale_finish = datetime.now(UTC) - timedelta(hours=6)
    with engine.begin() as connection:
        install_default_schedule(connection, tenant_id, updated_by="test")
        connection.execute(
            text(
                "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, "
                "idempotency_key, status, finished_at, as_of_window_start, "
                "as_of_window_end) VALUES (:run, :tenant, 'org_tree', 'scope', :key, "
                "'SUCCEEDED', :finished, :finished, :finished)"
            ),
            {
                "run": uuid4(),
                "tenant": tenant_id,
                "key": str(uuid4()),
                "finished": stale_finish,
            },
        )

    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    client, _ = client_for(engine, scope, settings)
    payload = client.get("/healthz").json()
    org_tree = next(e for e in payload["collectors"] if e["collector"] == "org_tree")
    assert org_tree["is_stale"] is True
    assert payload["status"] == "degraded"
