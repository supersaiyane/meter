"""Saved views: a person's own until shared, and opened in the opener's scope. FEAT-068.

TASK-P8-010's acceptance criteria, each held here:

- the `saved_view` table refuses what the P8 spec's section 6 says it must, as constraints in the
  database rather than conventions in code, constraint 11;
- a private view is its owner's alone, even to a reader of the whole estate, ADR-0032;
- a shared view is opened by the rest of the tenant and changed only by its owner, and a refused
  change leaves an audit row behind;
- opening a view reads the screen it names in the opener's scope and not the saver's, asserted
  with two principals whose scopes differ.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from finops_api.db import models
from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.views import SavedViewRepository
from finops_api.guards import SCOPED_TABLES, OwnedOrShared, ScopeViolationError
from finops_api.identity.session import SessionSigner
from finops_api.main import create_app
from finops_api.routes.views import NO_SUCH_VIEW, NOT_YOURS, VIEWS
from finops_api.screens import SCREEN_PATHS
from finops_core.config import Settings
from finops_core.domain.tenant import Scope
from tests.api.test_query_routes import (
    IN_SCOPE,
    NOW,
    OUT_OF_SCOPE,
    SIGNING_KEY,
    StubEntitlements,
    another_tenant,
    auth,
    everything,
    narrow,
)

pytestmark = pytest.mark.integration

LIBRARY = "/api/v1/reports/views"
ACCOUNTS = "/api/v1/accounts"
CONTEXT = AccessContext(request_id="test")
OWNER = "p-owner"
COLLEAGUE = "p-colleague"
#: The Accounts screen, which reads ACCOUNTS, so opening a view of it can be followed to its data.
SCREEN = "/inventory/accounts"
QUERY: dict[str, str | list[str]] = {"status": "ACTIVE", "sort": ["name", "status"]}

INSERT_ACCOUNT = text(
    "INSERT INTO cloud_account (account_pk, tenant_id, provider, account_id, name, status, "
    "as_of, collected_at) VALUES (:pk, :t, 'aws', :a, :a, 'ACTIVE', :at, :at)"
)
DENIALS = text(
    "SELECT action FROM audit_event WHERE tenant_id = :t AND resource = 'saved_view' "
    "AND outcome = 'DENIED'"
)


def whole(tenant: UUID, person: str | None) -> Scope:
    """A reader of the whole estate, which ADR-0032 says does not widen this table."""
    return replace(everything(tenant), principal_id=person)


def narrowed(tenant: UUID, person: str | None) -> Scope:
    """A reader of one account of the two."""
    return replace(narrow(tenant), principal_id=person)


def saved(engine: Engine, scope: Scope, visibility: str = "PRIVATE") -> UUID:
    with engine.begin() as connection:
        row = SavedViewRepository(connection, CONTEXT).create(
            scope,
            name="Accounts",
            screen_path=SCREEN,
            query=QUERY,
            visibility=visibility,
            at=NOW,
        )
    view_id: UUID = row.view_id
    return view_id


def opened(engine: Engine, scope: Scope) -> list[UUID]:
    with engine.connect() as connection:
        return [row.view_id for row in SavedViewRepository(connection, CONTEXT).views(scope, 100)]


def denials(engine: Engine, tenant: UUID) -> list[str]:
    with engine.connect() as connection:
        return sorted(
            str(action) for action in connection.execute(DENIALS, {"t": tenant}).scalars()
        )


@pytest.fixture
def signer() -> SessionSigner:
    return SessionSigner(SIGNING_KEY, ttl_hours=8, clock=lambda: NOW)


def client(engine: Engine, settings: Settings, signer: SessionSigner, scope: Scope) -> TestClient:
    """An application whose every reader resolves to `scope`, stamped with their own principal."""
    app = create_app(
        engine=engine, entitlements=StubEntitlements(scope), signer=signer, settings=settings
    )
    return TestClient(app, raise_server_exceptions=False)


def as_person(signer: SessionSigner, principal: str, scope: Scope) -> dict[str, str]:
    return auth(signer.issue(principal, f"{principal}@example.local", scope))


def body(**change: Any) -> dict[str, Any]:
    return {"name": "Active accounts", "screen_path": SCREEN, "query": QUERY, **change}


def when(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)


# --- the table ------------------------------------------------------------------------------


class TestTheTable:
    """Constraint 11: every invariant in the spec's section 6 is the database's to refuse."""

    @staticmethod
    def row(tenant: UUID, **change: object) -> dict[str, object]:
        return {
            "view_id": uuid4(),
            "tenant_id": tenant,
            "owner_id": OWNER,
            "name": "Accounts",
            "screen_path": SCREEN,
            "query": QUERY,
            "visibility": "PRIVATE",
            "created_at": NOW,
            "updated_at": NOW,
            **change,
        }

    def test_a_whole_row_is_accepted_so_each_refusal_below_can_fail(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        with engine.begin() as connection:
            connection.execute(models.saved_view.insert().values(**self.row(tenant_id)))

    @pytest.mark.parametrize(
        "change",
        [
            {"visibility": "PUBLIC"},
            {"name": "   "},
            {"name": "x" * 121},
            {"owner_id": " "},
            {"screen_path": "/analyze/nowhere"},
            {"query": ["status", "ACTIVE"]},
            {"query": "status=ACTIVE"},
            {"updated_at": NOW - timedelta(seconds=1)},
        ],
        ids=[
            "visibility",
            "blank-name",
            "long-name",
            "nobody",
            "unknown-screen",
            "array-query",
            "string-query",
            "updated-first",
        ],
    )
    def test_the_table_refuses(
        self, engine: Engine, tenant_id: UUID, change: dict[str, object]
    ) -> None:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(models.saved_view.insert().values(**self.row(tenant_id, **change)))

    def test_the_screen_constraint_admits_the_navigation_exactly(self, engine: Engine) -> None:
        """Read from the migrated database, so a later migration that widens it is held too."""
        with engine.connect() as connection:
            definition = connection.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname = 'ck_saved_view__screen'"
                )
            ).scalar_one()
        admitted = re.findall(r"'([^']*)'::text", str(definition))
        # A parse that found nothing would compare equal to a list that held nothing.
        assert len(admitted) > 20
        assert sorted(admitted) == sorted(SCREEN_PATHS)


# --- the guard ------------------------------------------------------------------------------


class TestTheGuard:
    def test_the_table_is_its_owners_until_shared(self) -> None:
        assert SCOPED_TABLES["saved_view"] == OwnedOrShared("owner_id", "visibility", "SHARED")
        assert {"owner_id", "visibility"} <= set(models.saved_view.columns.keys())

    def test_a_private_view_is_its_owners_alone_even_to_the_whole_estate(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        mine = saved(engine, whole(tenant_id, OWNER))
        assert opened(engine, whole(tenant_id, OWNER)) == [mine]
        assert opened(engine, whole(tenant_id, COLLEAGUE)) == []
        with engine.connect() as connection:
            repository = SavedViewRepository(connection, CONTEXT)
            assert repository.view(whole(tenant_id, COLLEAGUE), mine) is None
            assert repository.count(whole(tenant_id, COLLEAGUE)) == 0

    def test_a_shared_view_is_opened_by_a_colleague_narrowed_to_one_account(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        shared = saved(engine, whole(tenant_id, OWNER), "SHARED")
        assert opened(engine, narrowed(tenant_id, COLLEAGUE)) == [shared]

    def test_a_scope_naming_nobody_opens_nothing_and_saves_nothing(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """Fail closed, as a scope naming no account does."""
        saved(engine, whole(tenant_id, OWNER), "SHARED")
        assert opened(engine, whole(tenant_id, None)) == []
        with engine.begin() as connection, pytest.raises(ScopeViolationError):
            SavedViewRepository(connection, CONTEXT).create(
                whole(tenant_id, None),
                name="Nobody's",
                screen_path=SCREEN,
                query={},
                visibility="PRIVATE",
                at=NOW,
            )

    def test_a_shared_view_stays_in_its_tenant(self, engine: Engine, tenant_id: UUID) -> None:
        saved(engine, whole(tenant_id, OWNER), "SHARED")
        assert opened(engine, whole(another_tenant(engine), OWNER)) == []

    def test_only_the_owner_changes_a_shared_view_and_a_refusal_is_audited(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        shared = saved(engine, whole(tenant_id, OWNER), "SHARED")
        with engine.begin() as connection:
            repository = SavedViewRepository(connection, CONTEXT)
            colleague = whole(tenant_id, COLLEAGUE)
            assert repository.change(colleague, shared, at=NOW, name="Mine now") is None
            assert repository.delete(colleague, shared) is None
        with engine.connect() as connection:
            row = SavedViewRepository(connection, CONTEXT).view(whole(tenant_id, OWNER), shared)
        assert row is not None
        assert row.name == "Accounts"
        assert denials(engine, tenant_id) == ["change", "delete"]


# --- the routes, with two principals ----------------------------------------------------------


class TestTheRoutes:
    def test_saving_answers_with_the_view_and_its_envelope(
        self, engine: Engine, settings: Settings, signer: SessionSigner, tenant_id: UUID
    ) -> None:
        api = client(engine, settings, signer, everything(tenant_id))
        owner = as_person(signer, OWNER, everything(tenant_id))
        response = api.post(LIBRARY, json=body(name="  Active accounts  "), headers=owner)
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["name"] == "Active accounts"
        assert (data["screen_path"], data["query"]) == (SCREEN, QUERY)
        assert (data["visibility"], data["owned"]) == ("PRIVATE", True)
        assert data["created_at"] == data["updated_at"]
        meta = response.json()["meta"]
        assert meta["as_of"] is not None
        assert meta["collected_at"] is not None
        assert meta["scope_coverage"]["unit"] == VIEWS

    def test_the_library_lists_the_readers_own_and_the_shared_latest_changed_first(
        self, engine: Engine, settings: Settings, signer: SessionSigner, tenant_id: UUID
    ) -> None:
        api = client(engine, settings, signer, everything(tenant_id))
        owner = as_person(signer, OWNER, everything(tenant_id))
        colleague = as_person(signer, COLLEAGUE, everything(tenant_id))
        first = api.post(LIBRARY, json=body(name="First"), headers=owner).json()["data"]
        second = api.post(LIBRARY, json=body(name="Second"), headers=owner).json()["data"]
        theirs = api.post(LIBRARY, json=body(name="Theirs"), headers=colleague).json()["data"]
        renamed = api.patch(
            f"{LIBRARY}/{first['view_id']}", json={"name": "First, again"}, headers=owner
        )
        assert renamed.status_code == 200, renamed.text

        listed = api.get(LIBRARY, headers=owner).json()
        assert [view["name"] for view in listed["data"]] == ["First, again", "Second"]
        coverage = listed["meta"]["scope_coverage"]
        assert (coverage["visible"], coverage["total"], coverage["unit"]) == (2, 2, VIEWS)
        assert listed["meta"]["as_of"] is not None

        shared = api.patch(
            f"{LIBRARY}/{second['view_id']}", json={"visibility": "SHARED"}, headers=owner
        )
        assert shared.status_code == 200, shared.text
        seen = {
            view["view_id"]: view["owned"]
            for view in api.get(LIBRARY, headers=colleague).json()["data"]
        }
        assert seen == {second["view_id"]: False, theirs["view_id"]: True}

    def test_a_colleagues_private_view_is_not_found_and_a_shared_one_refuses_their_change(
        self, engine: Engine, settings: Settings, signer: SessionSigner, tenant_id: UUID
    ) -> None:
        api = client(engine, settings, signer, everything(tenant_id))
        owner = as_person(signer, OWNER, everything(tenant_id))
        colleague = as_person(signer, COLLEAGUE, everything(tenant_id))
        private = api.post(LIBRARY, json=body(), headers=owner).json()["data"]["view_id"]
        made = api.post(LIBRARY, json=body(visibility="SHARED"), headers=owner)
        shared = made.json()["data"]["view_id"]

        assert api.get(f"{LIBRARY}/{private}", headers=colleague).status_code == 404
        assert api.get(f"{LIBRARY}/{shared}", headers=colleague).status_code == 200

        hidden = api.patch(f"{LIBRARY}/{private}", json={"name": "Taken"}, headers=colleague)
        assert (hidden.status_code, hidden.json()) == (404, {"detail": NO_SUCH_VIEW})
        refused = api.patch(f"{LIBRARY}/{shared}", json={"name": "Taken"}, headers=colleague)
        assert (refused.status_code, refused.json()) == (403, {"detail": NOT_YOURS})
        assert api.delete(f"{LIBRARY}/{private}", headers=colleague).status_code == 404
        assert api.delete(f"{LIBRARY}/{shared}", headers=colleague).status_code == 403

        # Answered rather than raised, so each refusal's audit row outlived its request.
        assert denials(engine, tenant_id) == ["change", "change", "delete", "delete"]
        names = {view["name"] for view in api.get(LIBRARY, headers=owner).json()["data"]}
        assert names == {"Active accounts"}

    def test_the_owner_renames_shares_unshares_and_deletes(
        self, engine: Engine, settings: Settings, signer: SessionSigner, tenant_id: UUID
    ) -> None:
        api = client(engine, settings, signer, everything(tenant_id))
        owner = as_person(signer, OWNER, everything(tenant_id))
        colleague = as_person(signer, COLLEAGUE, everything(tenant_id))
        created = api.post(LIBRARY, json=body(), headers=owner).json()["data"]
        path = f"{LIBRARY}/{created['view_id']}"

        renamed = api.patch(path, json={"name": "Accounts, active"}, headers=owner).json()["data"]
        assert renamed["name"] == "Accounts, active"
        assert when(renamed["updated_at"]) >= when(created["updated_at"])
        assert renamed["created_at"] == created["created_at"]

        shared = api.patch(path, json={"visibility": "SHARED"}, headers=owner).json()["data"]
        assert shared["visibility"] == "SHARED"
        assert api.get(path, headers=colleague).status_code == 200
        assert api.patch(path, json={"visibility": "PRIVATE"}, headers=owner).status_code == 200
        assert api.get(path, headers=colleague).status_code == 404

        deleted = api.delete(path, headers=owner)
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["data"]["name"] == "Accounts, active"
        assert deleted.json()["meta"]["as_of"] is not None
        assert api.get(path, headers=owner).status_code == 404
        assert denials(engine, tenant_id) == []

    @pytest.mark.parametrize(
        "sent",
        [
            body(screen_path="/analyze/nowhere"),
            body(name="   "),
            body(name="x" * 121),
            body(name="two\nlines"),
            body(visibility="PUBLIC"),
            body(query={"status": 1}),
            body(owner_id=OWNER),
        ],
        ids=["screen", "blank", "long", "lines", "visibility", "query", "owner"],
    )
    def test_a_save_the_spec_refuses_is_refused_before_the_database(
        self,
        engine: Engine,
        settings: Settings,
        signer: SessionSigner,
        tenant_id: UUID,
        sent: dict[str, Any],
    ) -> None:
        api = client(engine, settings, signer, everything(tenant_id))
        owner = as_person(signer, OWNER, everything(tenant_id))
        assert api.post(LIBRARY, json=sent, headers=owner).status_code == 422
        assert api.get(LIBRARY, headers=owner).json()["data"] == []

    @pytest.mark.parametrize(
        "sent",
        [{}, {"query": QUERY}, {"screen_path": SCREEN}, {"name": " "}, {"visibility": "PUBLIC"}],
        ids=["nothing", "query", "screen", "blank", "visibility"],
    )
    def test_a_change_to_nothing_or_to_what_the_view_is_is_refused(
        self,
        engine: Engine,
        settings: Settings,
        signer: SessionSigner,
        tenant_id: UUID,
        sent: dict[str, Any],
    ) -> None:
        api = client(engine, settings, signer, everything(tenant_id))
        owner = as_person(signer, OWNER, everything(tenant_id))
        view_id = api.post(LIBRARY, json=body(), headers=owner).json()["data"]["view_id"]
        assert api.patch(f"{LIBRARY}/{view_id}", json=sent, headers=owner).status_code == 422

    def test_a_view_opens_in_the_openers_scope_and_not_the_savers(
        self, engine: Engine, settings: Settings, signer: SessionSigner, tenant_id: UUID
    ) -> None:
        """The acceptance criterion: one shared view, two principals, two scopes."""
        with engine.begin() as connection:
            for account in (IN_SCOPE, OUT_OF_SCOPE):
                connection.execute(
                    INSERT_ACCOUNT, {"pk": uuid4(), "t": tenant_id, "a": account, "at": NOW}
                )
        saver = client(engine, settings, signer, everything(tenant_id))
        opener = client(engine, settings, signer, narrow(tenant_id))
        saver_headers = as_person(signer, OWNER, everything(tenant_id))
        opener_headers = as_person(signer, COLLEAGUE, narrow(tenant_id))

        created = saver.post(LIBRARY, json=body(visibility="SHARED"), headers=saver_headers)
        assert created.status_code == 201, created.text
        path = f"{LIBRARY}/{created.json()['data']['view_id']}"
        as_saver = saver.get(path, headers=saver_headers).json()["data"]
        as_opener = opener.get(path, headers=opener_headers).json()["data"]

        # The same configuration reaches both, because a view holds nothing that could differ.
        assert {**as_opener, "owned": None} == {**as_saver, "owned": None}
        assert (as_saver["owned"], as_opener["owned"]) == (True, False)

        # Opening it reads the screen it names, each reader through their own scope.
        def accounts(api: TestClient, headers: dict[str, str]) -> tuple[set[str], int, int]:
            response = api.get(ACCOUNTS, params=as_opener["query"], headers=headers)
            assert response.status_code == 200, response.text
            coverage = response.json()["meta"]["scope_coverage"]
            found = {row["account_id"] for row in response.json()["data"]}
            return found, coverage["visible"], coverage["total"]

        assert as_opener["screen_path"] == SCREEN
        assert accounts(saver, saver_headers) == ({IN_SCOPE, OUT_OF_SCOPE}, 2, 2)
        assert accounts(opener, opener_headers) == ({IN_SCOPE}, 1, 2)
