"""A repository that cannot return out of scope rows, even when asked carelessly.

Constraint 3 in CLAUDE.md puts scope enforcement in two independent places, and
this is the second one. ISS-009 is why: scoping only in the API layer is
bypassable by any route that forgets the dependency, and routes are added by
people who have never read the guard.

The tests split in two. The ones that need no database assert the guard refuses
what it should, and run in `make test`. The ones marked integration prove that a
real query against a real PostgreSQL returns exactly the permitted rows and
writes the audit row that makes a global read defensible.
"""

from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, select, text

from finops_api.db import models
from finops_api.db.repositories import (
    AccessContext,
    AccountRepository,
    IngestRunRepository,
    OrgRepository,
    ScopedRepository,
    SyncErrorRepository,
)
from finops_api.guards import (
    ScopeViolationError,
    assert_scoped,
    require_scope,
    scope_predicate,
    scoped_select,
)
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.tenant import Scope

NOW = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
CONTEXT = AccessContext(request_id="req-1", principal_id=None)

REPOSITORIES = (
    AccountRepository,
    OrgRepository,
    IngestRunRepository,
    SyncErrorRepository,
)


def keys(*ids: str) -> frozenset[AccountKey]:
    return frozenset(AccountKey(provider=Provider.AWS, account_id=i) for i in ids)


# --- the guard, with no database -------------------------------------------


def test_unscoped_query_raises() -> None:
    """None is almost always a forgotten argument, never a request for everything."""
    with pytest.raises(ScopeViolationError):
        require_scope(None)
    with pytest.raises(ScopeViolationError):
        require_scope("everything")


def test_no_scoped_method_has_a_default_scope() -> None:
    """A default that grants access is the commonest cause of this class of leak."""
    for repository in (*REPOSITORIES, ScopedRepository):
        for name, method in vars(repository).items():
            if name.startswith("_") or not callable(method):
                continue
            parameters = inspect.signature(method).parameters
            if "scope" in parameters:
                assert parameters["scope"].default is inspect.Parameter.empty, (
                    f"{repository.__name__}.{name}"
                )


def test_a_table_nobody_has_decided_how_to_scope_is_refused() -> None:
    scope = Scope(tenant_id=uuid4(), is_global=True, accounts=frozenset())
    with pytest.raises(ScopeViolationError, match="SCOPED_TABLES"):
        scope_predicate(models.metadata.tables["tenant"], scope)


def test_an_adhoc_row_is_confined_to_the_accounts_the_scope_names() -> None:
    """FEAT-051. Ad hoc rows reach no workspace, so they are scoped directly.

    Every other query table inherits its account through `grafana_instance`. A
    query somebody typed into the console belongs to no workspace, so this one
    carries its own account, and getting that wrong would expose one tenant's
    hand run queries, complete with their text, to another account's reader.
    """
    scope = Scope(tenant_id=uuid4(), is_global=False, accounts=keys("111122223333"))
    predicate = scope_predicate(models.query_adhoc, scope)
    rendered = str(predicate.compile(compile_kwargs={"literal_binds": True}))
    assert "tenant_id" in rendered
    assert "111122223333" in rendered
    assert "account_id" in rendered


def test_an_adhoc_read_with_no_accounts_returns_nothing() -> None:
    """Empty means nothing, not everything. The fail closed case."""
    scope = Scope(tenant_id=uuid4(), is_global=False, accounts=frozenset())
    rendered = str(
        scope_predicate(models.query_adhoc, scope).compile(compile_kwargs={"literal_binds": True})
    )
    assert "false" in rendered.lower()


def test_a_hand_rolled_statement_with_no_tenant_filter_is_refused() -> None:
    """The backstop, for a future subclass that builds its own select."""
    with pytest.raises(ScopeViolationError, match="not built by scoped_select"):
        assert_scoped(select(models.cloud_account), models.cloud_account)


def test_a_statement_from_the_guard_passes_the_backstop() -> None:
    scope = Scope(tenant_id=uuid4(), is_global=True, accounts=frozenset())
    assert_scoped(scoped_select(models.cloud_account, scope), models.cloud_account)


def test_the_mark_survives_refinement() -> None:
    """A repository adds ordering and limits, and must not lose the guarantee."""
    scope = Scope(tenant_id=uuid4(), is_global=True, accounts=frozenset())
    refined = (
        scoped_select(models.cloud_account, scope)
        .where(models.cloud_account.c["role_health"] != "HEALTHY")
        .order_by(models.cloud_account.c["account_id"])
        .limit(5)
    )
    assert_scoped(refined, models.cloud_account)


def test_an_empty_scope_still_passes_the_backstop() -> None:
    """The regression this backstop was rewritten for. Fail closed must not fail."""
    scope = Scope(tenant_id=uuid4(), is_global=False, accounts=frozenset())
    assert_scoped(scoped_select(models.cloud_account, scope), models.cloud_account)


def test_an_empty_scope_compiles_to_a_predicate_that_matches_nothing() -> None:
    """Empty means nothing, not everything. This is the fail closed case."""
    scope = Scope(tenant_id=uuid4(), is_global=False, accounts=frozenset())
    rendered = str(scope_predicate(models.cloud_account, scope))
    assert "false" in rendered.lower()


def test_a_global_scope_does_not_filter_by_account() -> None:
    scope = Scope(tenant_id=uuid4(), is_global=True, accounts=frozenset())
    rendered = str(scope_predicate(models.cloud_account, scope))
    assert "tenant_id" in rendered
    assert "account_id" not in rendered


# --- against a real database -------------------------------------------------

pytest_integration = pytest.mark.integration


def seed_accounts(engine: Engine, tenant: UUID, ids: tuple[str, ...]) -> None:
    with engine.begin() as connection:
        for account_id in ids:
            connection.execute(
                text(
                    "INSERT INTO cloud_account (account_pk, tenant_id, provider, "
                    "account_id, name, status, as_of, collected_at) VALUES "
                    "(:pk, :tenant, 'aws', :account, :name, 'ACTIVE', :as_of, :collected)"
                ),
                {
                    "pk": uuid4(),
                    "tenant": tenant,
                    "account": account_id,
                    "name": account_id,
                    "as_of": NOW,
                    "collected": NOW,
                },
            )


def audit_rows(engine: Engine, tenant: UUID) -> list[dict[str, object]]:
    with engine.connect() as connection:
        rows = connection.execute(
            select(models.audit_event).where(models.audit_event.c["tenant_id"] == tenant)
        ).mappings()
        return [dict(row) for row in rows]


@pytest.mark.integration
def test_scope_filters_rows(engine: Engine, tenant_id: UUID) -> None:
    """A principal scoped to two accounts sees exactly those two."""
    seed_accounts(engine, tenant_id, ("acct-a", "acct-b", "acct-c"))
    scope = Scope(tenant_id=tenant_id, is_global=False, accounts=keys("acct-a", "acct-b"))
    with engine.begin() as connection:
        rows = AccountRepository(connection, CONTEXT).list_in_scope(scope)
    assert {row.account_id for row in rows} == {"acct-a", "acct-b"}


@pytest.mark.integration
def test_an_empty_scope_returns_nothing_rather_than_everything(
    engine: Engine, tenant_id: UUID
) -> None:
    seed_accounts(engine, tenant_id, ("acct-a", "acct-b"))
    scope = Scope(tenant_id=tenant_id, is_global=False, accounts=frozenset())
    with engine.begin() as connection:
        rows = AccountRepository(connection, CONTEXT).list_in_scope(scope)
    assert rows == []


@pytest.mark.integration
def test_a_scope_never_reaches_another_tenant(engine: Engine, tenant_id: UUID) -> None:
    """The same account identifier under two tenants must not bleed across."""
    other = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenant (tenant_id, name) VALUES (:id, :name)"),
            {"id": other, "name": f"tenant-{other}"},
        )
    seed_accounts(engine, tenant_id, ("shared-id",))
    seed_accounts(engine, other, ("shared-id",))
    scope = Scope(tenant_id=tenant_id, is_global=False, accounts=keys("shared-id"))
    with engine.begin() as connection:
        rows = AccountRepository(connection, CONTEXT).list_in_scope(scope)
    assert len(rows) == 1
    assert rows[0].tenant_id == tenant_id


@pytest.mark.integration
def test_global_scope_is_audited(engine: Engine, tenant_id: UUID) -> None:
    """What makes the global viewer credential defensible is that it leaves a trace."""
    seed_accounts(engine, tenant_id, ("acct-a", "acct-b"))
    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    with engine.begin() as connection:
        rows = AccountRepository(connection, CONTEXT).list_in_scope(scope)
    assert len(rows) == 2

    events = audit_rows(engine, tenant_id)
    assert len(events) == 1
    assert events[0]["is_global_read"] is True
    assert events[0]["outcome"] == "ALLOWED"
    assert events[0]["resource"] == "cloud_account"
    assert events[0]["request_id"] == "req-1"


@pytest.mark.integration
def test_every_read_writes_an_audit_event(engine: Engine, tenant_id: UUID) -> None:
    scope = Scope(tenant_id=tenant_id, is_global=False, accounts=keys("acct-a"))
    with engine.begin() as connection:
        AccountRepository(connection, CONTEXT).list_in_scope(scope)
        OrgRepository(connection, CONTEXT).list_tree(scope)
        IngestRunRepository(connection, CONTEXT).recent(scope, limit=5)
        SyncErrorRepository(connection, CONTEXT).open_errors(scope)
    resources = sorted(str(event["resource"]) for event in audit_rows(engine, tenant_id))
    assert resources == ["cloud_account", "ingest_run", "org_node", "sync_error"]


@pytest.mark.integration
def test_the_audit_row_records_the_accounts_that_were_evaluated(
    engine: Engine, tenant_id: UUID
) -> None:
    """A year later, "what could this person see" has to have an answer."""
    scope = Scope(tenant_id=tenant_id, is_global=False, accounts=keys("acct-a", "acct-b"))
    with engine.begin() as connection:
        AccountRepository(connection, CONTEXT).list_in_scope(scope)
    evaluated = audit_rows(engine, tenant_id)[0]["scope_evaluated"]
    payload = evaluated if isinstance(evaluated, dict) else json.loads(str(evaluated))
    assert payload["is_global"] is False
    assert payload["accounts"] == ["aws:acct-a", "aws:acct-b"]


@pytest.mark.integration
def test_a_repository_read_without_a_scope_returns_no_rows_at_all(
    engine: Engine, tenant_id: UUID
) -> None:
    """It must raise before the query runs, not filter afterwards."""
    seed_accounts(engine, tenant_id, ("acct-a",))
    with engine.begin() as connection:
        repository = AccountRepository(connection, CONTEXT)
        with pytest.raises(ScopeViolationError):
            repository.list_in_scope(None)  # type: ignore[arg-type]
    assert audit_rows(engine, tenant_id) == []


@pytest.mark.integration
def test_unhealthy_accounts_are_still_confined_to_the_scope(
    engine: Engine, tenant_id: UUID
) -> None:
    seed_accounts(engine, tenant_id, ("acct-a", "acct-b"))
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE cloud_account SET role_health = 'ACCESS_DENIED' WHERE tenant_id = :t"),
            {"t": tenant_id},
        )
    scope = Scope(tenant_id=tenant_id, is_global=False, accounts=keys("acct-a"))
    with engine.begin() as connection:
        rows = AccountRepository(connection, CONTEXT).list_unhealthy(scope)
    assert {row.account_id for row in rows} == {"acct-a"}
