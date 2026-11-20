"""The seven P0 routes, and the three places they are tempted to flatter the data.

A tree with out of scope branches pruned looks tidy and tells the reader their
organization is smaller than it is. A run that reports a raw exception string
tells whoever wrote the code something and whoever has to fix the account
nothing. A platform cost page without the unallocated bucket under counts, and
under counting is worse than silence because a number on a page is believed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from finops_api.identity import SessionSigner
from finops_api.main import create_app, iter_api_routes, p0_routers
from finops_core.config import Settings
from finops_core.domain.account import AccountHealth, AccountKey, Provider, RoleHealth
from finops_core.domain.identity import Entitlement, Principal
from finops_core.domain.tenant import Scope

NOW = datetime(2026, 8, 27, 6, 0, tzinfo=UTC)
SIGNING_KEY = "a-test-signing-key"
IN_SCOPE = "111122223333"
OUT_OF_SCOPE = "444455556666"
ROOT = "r-root"
UNIT = "ou-platform"

pytestmark = pytest.mark.integration


class StubEntitlements:
    def __init__(self, scope: Scope) -> None:
        self.scope = scope

    def resolve(self, principal: Principal) -> Entitlement:
        return Entitlement(principal=principal, scope=self.scope, as_of=NOW, collected_at=NOW)


class StubHealthCheck:
    def __init__(self, health: RoleHealth = RoleHealth.HEALTHY, error: str = "") -> None:
        self.health = health
        self.error = error
        self.checked: list[str] = []

    def check(self, account: AccountKey, _region: str) -> AccountHealth:
        self.checked.append(account.account_id)
        return AccountHealth(
            key=account, health=self.health, error=self.error, as_of=NOW, collected_at=NOW
        )


def seed(engine: Engine, tenant: UUID) -> None:
    """Two accounts, a two level tree, one broken run and a platform bill."""
    with engine.begin() as connection:
        for account_id, health in ((IN_SCOPE, "HEALTHY"), (OUT_OF_SCOPE, "ACCESS_DENIED")):
            connection.execute(
                text(
                    "INSERT INTO cloud_account (account_pk, tenant_id, provider, account_id, "
                    "name, status, role_health, role_health_error, as_of, collected_at) "
                    "VALUES (:pk, :t, 'aws', :a, :a, 'ACTIVE', :h, :e, :at, :at)"
                ),
                {
                    "pk": uuid4(),
                    "t": tenant,
                    "a": account_id,
                    "h": health,
                    "e": None
                    if health == "HEALTHY"
                    else "the trust policy names another principal",
                    "at": NOW,
                },
            )
        nodes = (
            (ROOT, "ROOT", None, "/r-root", 0),
            (UNIT, "OU", ROOT, "/r-root/ou-platform", 1),
            (IN_SCOPE, "ACCOUNT", UNIT, f"/r-root/ou-platform/{IN_SCOPE}", 2),
            (OUT_OF_SCOPE, "ACCOUNT", UNIT, f"/r-root/ou-platform/{OUT_OF_SCOPE}", 2),
        )
        for node_id, node_type, parent, path, depth in nodes:
            connection.execute(
                text(
                    "INSERT INTO org_node (node_pk, tenant_id, node_id, node_type, "
                    "parent_node_id, name, path, depth, as_of, collected_at) VALUES "
                    "(:pk, :t, :n, :ty, :p, :n, :path, :d, :at, :at)"
                ),
                {
                    "pk": uuid4(),
                    "t": tenant,
                    "n": node_id,
                    "ty": node_type,
                    "p": parent,
                    "path": path,
                    "d": depth,
                    "at": NOW,
                },
            )
        connection.execute(
            text(
                "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, "
                "idempotency_key, status, finished_at, items_written, error_type, "
                "error_detail, as_of_window_start, as_of_window_end) VALUES "
                "(:run, :t, 'account_health', :scope, :key, 'FAILED', :at, 0, 'AccessDenied', "
                ":detail, :at, :at)"
            ),
            {
                "run": uuid4(),
                "t": tenant,
                "scope": f"aws:{OUT_OF_SCOPE}:eu-west-1",
                "key": str(uuid4()),
                "at": NOW,
                "detail": "not authorized. Check the StackSet deployment for this account.",
            },
        )
        connection.execute(
            text(
                "INSERT INTO sync_error (error_id, tenant_id, collector, scope_key, "
                "error_type, detail, remediation) VALUES "
                "(:id, :t, 'account_health', :scope, 'AccessDenied', :detail, :remedy)"
            ),
            {
                "id": uuid4(),
                "t": tenant,
                "scope": f"aws:{OUT_OF_SCOPE}:eu-west-1",
                "detail": "not authorized",
                "remedy": "Check the StackSet deployment, then the trust policy.",
            },
        )
        for module, service, amount in (
            ("ingest", "AmazonECS", "1.50"),
            ("unallocated", "AmazonS3", "0.20"),
        ):
            connection.execute(
                text(
                    "INSERT INTO platform_cost (tenant_id, day, module, service, "
                    "amortized_cost, as_of, collected_at) VALUES "
                    "(:t, :day, :m, :s, :amount, :at, :at)"
                ),
                {
                    "t": tenant,
                    "day": NOW.date(),
                    "m": module,
                    "s": service,
                    "amount": Decimal(amount),
                    "at": NOW,
                },
            )


def client_for(
    engine: Engine, scope: Scope, settings: Settings, checker: object | None = None
) -> tuple[TestClient, str]:
    signer = SessionSigner(SIGNING_KEY, ttl_hours=8, clock=lambda: NOW)
    app = create_app(
        engine=engine,
        entitlements=StubEntitlements(scope),
        signer=signer,
        settings=settings,
        health_check=checker,
    )
    return TestClient(app, raise_server_exceptions=False), signer.issue(
        "p1", "someone@example.local", scope
    )


def narrow(tenant: UUID) -> Scope:
    return Scope(
        tenant_id=tenant,
        is_global=False,
        accounts=frozenset({AccountKey(provider=Provider.AWS, account_id=IN_SCOPE)}),
    )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- the surface -------------------------------------------------------------


def test_all_seven_routes_from_the_specification_exist() -> None:
    paths = {
        (route.path, method) for route in iter_api_routes(p0_routers()) for method in route.methods
    }
    assert ("/api/v1/me", "GET") in paths
    assert ("/api/v1/accounts", "GET") in paths
    assert ("/api/v1/org/tree", "GET") in paths
    assert ("/api/v1/accounts/{account_id}/recheck", "POST") in paths
    assert ("/api/v1/ingest/runs", "GET") in paths
    assert ("/api/v1/health/freshness", "GET") in paths
    assert ("/api/v1/platform/cost", "GET") in paths


def test_every_route_carries_meta(engine: Engine, tenant_id: UUID, settings: Settings) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, narrow(tenant_id), settings)
    for path in (
        "/api/v1/me",
        "/api/v1/accounts",
        "/api/v1/org/tree",
        "/api/v1/ingest/runs",
        "/api/v1/health/freshness",
        "/api/v1/platform/cost",
    ):
        payload = client.get(path, headers=auth(token)).json()
        assert "meta" in payload, path
        assert set(payload["meta"]) >= {
            "as_of",
            "collected_at",
            "scope_coverage",
            "degraded",
            "failures",
        }, path


# --- me ----------------------------------------------------------------------


def test_me_reports_the_principal_and_the_scope(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, narrow(tenant_id), settings)
    payload = client.get("/api/v1/me", headers=auth(token)).json()
    assert payload["data"]["is_global"] is False
    assert payload["data"]["accounts_in_scope"] == 1
    assert payload["meta"]["scope_coverage"] == {"visible": 1, "total": 2, "is_partial": True}


def test_a_global_viewer_is_not_reported_as_seeing_nothing(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A global scope enumerates no accounts, and zero would render as no access."""
    seed(engine, tenant_id)
    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    client, token = client_for(engine, scope, settings)
    payload = client.get("/api/v1/me", headers=auth(token)).json()
    assert payload["data"]["accounts_in_scope"] == 2
    assert payload["meta"]["scope_coverage"]["is_partial"] is False


# --- accounts ----------------------------------------------------------------


def test_accounts_lists_only_what_the_scope_permits(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, narrow(tenant_id), settings)
    payload = client.get("/api/v1/accounts", headers=auth(token)).json()
    assert [row["account_id"] for row in payload["data"]] == [IN_SCOPE]
    assert payload["meta"]["degraded"] is True


def test_an_account_with_a_broken_role_is_still_listed(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Omitting it hides the reason a figure is missing."""
    seed(engine, tenant_id)
    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    client, token = client_for(engine, scope, settings)
    rows = {
        r["account_id"]: r
        for r in client.get("/api/v1/accounts", headers=auth(token)).json()["data"]
    }
    assert rows[OUT_OF_SCOPE]["role_health"] == "ACCESS_DENIED"
    assert "trust policy" in rows[OUT_OF_SCOPE]["role_health_error"]


# --- the tree ----------------------------------------------------------------


def test_org_tree_marks_unreachable_branches_rather_than_hiding_them(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A tree with gaps a user cannot explain reads as broken data."""
    seed(engine, tenant_id)
    client, token = client_for(engine, narrow(tenant_id), settings)
    nodes = {
        n["node_id"]: n for n in client.get("/api/v1/org/tree", headers=auth(token)).json()["data"]
    }

    assert set(nodes) == {ROOT, UNIT, IN_SCOPE, OUT_OF_SCOPE}
    assert nodes[IN_SCOPE]["reachable"] is True
    assert nodes[OUT_OF_SCOPE]["reachable"] is False
    assert nodes[ROOT]["reachable"] is True
    assert nodes[UNIT]["reachable"] is True


def test_the_tree_has_the_same_shape_whatever_the_scope(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    narrow_client, narrow_token = client_for(engine, narrow(tenant_id), settings)
    wide_client, wide_token = client_for(
        engine, Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset()), settings
    )
    narrow_nodes = narrow_client.get("/api/v1/org/tree", headers=auth(narrow_token)).json()["data"]
    wide_nodes = wide_client.get("/api/v1/org/tree", headers=auth(wide_token)).json()["data"]
    assert len(narrow_nodes) == len(wide_nodes)


def test_the_tree_reports_how_many_accounts_are_reachable(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, narrow(tenant_id), settings)
    payload = client.get("/api/v1/org/tree", headers=auth(token)).json()
    assert payload["meta"]["scope_coverage"] == {"visible": 1, "total": 2, "is_partial": True}


# --- runs and freshness ------------------------------------------------------


def test_ingest_runs_returns_typed_errors_with_their_remediation(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    client, token = client_for(engine, scope, settings)
    payload = client.get("/api/v1/ingest/runs", headers=auth(token)).json()

    failed = next(r for r in payload["data"] if r["status"] == "FAILED")
    assert failed["error_type"] == "AccessDenied"
    assert "StackSet" in failed["error_detail"]

    failure = payload["meta"]["failures"][0]
    assert failure["cause"] == "AccessDenied"
    assert failure["remediation"]


def test_a_run_never_returns_a_raw_exception_string(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A traceback tells the author something and the operator nothing."""
    seed(engine, tenant_id)
    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    client, token = client_for(engine, scope, settings)
    body = client.get("/api/v1/ingest/runs", headers=auth(token)).text
    assert "Traceback" not in body
    assert "finops_" not in body


def test_freshness_is_judged_against_each_collector_own_cadence(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    from finops_ingest.registry import install_default_schedule

    seed(engine, tenant_id)
    recent = datetime.now(UTC) - timedelta(minutes=5)
    old = datetime.now(UTC) - timedelta(hours=9)
    with engine.begin() as connection:
        install_default_schedule(connection, tenant_id, updated_by="test")
        for collector, as_of in (("org_tree", recent), ("account_health", old)):
            connection.execute(
                text(
                    "INSERT INTO ingest_watermark (tenant_id, collector, scope_key, as_of) "
                    "VALUES (:t, :c, 'scope', :as_of)"
                ),
                {"t": tenant_id, "c": collector, "as_of": as_of},
            )

    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    client, token = client_for(engine, scope, settings)
    entries = {
        e["collector"]: e
        for e in client.get("/api/v1/health/freshness", headers=auth(token)).json()["data"]
    }
    assert entries["org_tree"]["is_stale"] is False
    assert entries["account_health"]["is_stale"] is True
    assert entries["org_tree"]["cadence_seconds"] == 3600


def test_a_collector_with_no_cadence_is_reported_stale_not_healthy(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """An unknown cadence is not a healthy one."""
    seed(engine, tenant_id)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ingest_watermark (tenant_id, collector, scope_key, as_of) "
                "VALUES (:t, 'unscheduled', 'scope', :as_of)"
            ),
            {"t": tenant_id, "as_of": datetime.now(UTC)},
        )
    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    client, token = client_for(engine, scope, settings)
    entry = next(
        e
        for e in client.get("/api/v1/health/freshness", headers=auth(token)).json()["data"]
        if e["collector"] == "unscheduled"
    )
    assert entry["cadence_seconds"] is None
    assert entry["is_stale"] is True


# --- platform cost -----------------------------------------------------------


def test_platform_cost_includes_the_unallocated_bucket(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Hiding it would make the report tidier and wrong."""
    seed(engine, tenant_id)
    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    client, token = client_for(engine, scope, settings)
    modules = {
        row["module"]
        for row in client.get("/api/v1/platform/cost", headers=auth(token)).json()["data"]
    }
    assert modules == {"ingest", "unallocated"}


# --- recheck -----------------------------------------------------------------


def test_recheck_updates_the_role_health(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    checker = StubHealthCheck(RoleHealth.NOT_DEPLOYED, error="the StackSet never arrived")
    client, token = client_for(engine, narrow(tenant_id), settings, checker=checker)
    response = client.post(f"/api/v1/accounts/{IN_SCOPE}/recheck", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["data"]["role_health"] == "NOT_DEPLOYED"
    assert checker.checked == [IN_SCOPE]


def test_recheck_refuses_an_account_the_scope_does_not_reach(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Out of scope and absent get one answer, so a caller cannot enumerate."""
    seed(engine, tenant_id)
    checker = StubHealthCheck()
    client, token = client_for(engine, narrow(tenant_id), settings, checker=checker)
    response = client.post(f"/api/v1/accounts/{OUT_OF_SCOPE}/recheck", headers=auth(token))
    assert response.status_code == 404
    assert checker.checked == []

    missing = client.post("/api/v1/accounts/000000000000/recheck", headers=auth(token))
    assert missing.status_code == 404
    assert missing.json()["detail"] == response.json()["detail"]


def test_recheck_says_so_when_checking_is_not_configured(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, narrow(tenant_id), settings, checker=None)
    response = client.post(f"/api/v1/accounts/{IN_SCOPE}/recheck", headers=auth(token))
    assert response.status_code == 503
