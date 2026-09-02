"""The migration, run against a real PostgreSQL, is the only proof that counts.

`tests/db/test_models.py` asserts what the metadata promises. This file asserts
that the migration actually delivers it, and the drift test joins the two: if
the hand written SQL and the declarative tables ever disagree, this fails.

Constraint 11 in CLAUDE.md. Every assertion here is about something the
database refuses, not about something the application remembers not to do.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError, IntegrityError

from finops_api.db import models
from tests.conftest import alembic_config

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent.parent
NOW = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)


# --- the two descriptions of the schema agree --------------------------------


def test_the_models_match_the_migrated_database(engine: Engine) -> None:
    """Two files describe one schema, so the agreement is tested rather than trusted."""
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
            )
        ).all()
    in_database: dict[str, set[str]] = {}
    for table_name, column_name in rows:
        in_database.setdefault(table_name, set()).add(column_name)

    in_models = {name: set(table.c.keys()) for name, table in models.metadata.tables.items()}
    assert set(in_database) == set(in_models)
    for name, columns in in_models.items():
        assert in_database[name] == columns, name


def test_every_specified_table_exists(engine: Engine) -> None:
    with engine.connect() as connection:
        present = {
            row[0]
            for row in connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        }
    assert set(models.metadata.tables) <= present


# --- the invariants the database enforces ------------------------------------


def insert_run(connection: Connection, tenant: UUID, key: str, status: str = "SUCCEEDED") -> None:
    connection.execute(
        text(
            "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, "
            "idempotency_key, status, as_of_window_start, as_of_window_end) "
            "VALUES (:run, :tenant, 'org_tree', 'scope', :key, :status, :start, :end)"
        ),
        {
            "run": uuid4(),
            "tenant": tenant,
            "key": key,
            "status": status,
            "start": NOW,
            "end": NOW,
        },
    )


def test_idempotency_key_is_unique(engine: Engine, tenant_id: UUID) -> None:
    """This is what holds when two workers claim the same unit at once. ISS-008."""
    with engine.begin() as connection:
        insert_run(connection, tenant_id, "the-same-key")
    with pytest.raises(IntegrityError), engine.begin() as connection:
        insert_run(connection, tenant_id, "the-same-key")


def test_as_of_is_not_nullable(engine: Engine, tenant_id: UUID) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO cloud_account (account_pk, tenant_id, provider, account_id, "
                "name, status, as_of, collected_at) VALUES "
                "(:pk, :tenant, 'aws', 'a-1', 'n', 'ACTIVE', NULL, :collected)"
            ),
            {"pk": uuid4(), "tenant": tenant_id, "collected": NOW},
        )


def test_an_unknown_error_type_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """The taxonomy staying closed is what stops every future failure becoming generic."""
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO sync_error (error_id, tenant_id, collector, scope_key, "
                "error_type, detail, remediation) VALUES "
                "(:id, :tenant, 'org_tree', 'scope', 'SomethingNew', 'd', 'r')"
            ),
            {"id": uuid4(), "tenant": tenant_id},
        )


def test_a_run_window_cannot_end_before_it_starts(engine: Engine, tenant_id: UUID) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, "
                "idempotency_key, status, as_of_window_start, as_of_window_end) VALUES "
                "(:run, :tenant, 'c', 's', :key, 'SUCCEEDED', :start, :end)"
            ),
            {
                "run": uuid4(),
                "tenant": tenant_id,
                "key": str(uuid4()),
                "start": NOW,
                "end": datetime(2026, 8, 23, tzinfo=UTC),
            },
        )


# --- the organization tree ---------------------------------------------------


def insert_node(
    connection: Connection,
    tenant: UUID,
    node_id: str,
    node_type: str,
    parent: str | None,
    depth: int,
) -> None:
    connection.execute(
        text(
            "INSERT INTO org_node (node_pk, tenant_id, node_id, node_type, parent_node_id, "
            "name, path, depth, as_of, collected_at) VALUES "
            "(:pk, :tenant, :node, :type, :parent, :name, :path, :depth, :as_of, :collected)"
        ),
        {
            "pk": uuid4(),
            "tenant": tenant,
            "node": node_id,
            "type": node_type,
            "parent": parent,
            "name": node_id,
            "path": f"/{node_id}",
            "depth": depth,
            "as_of": NOW,
            "collected": NOW,
        },
    )


def test_org_tree_recursive_query(engine: Engine, tenant_id: UUID) -> None:
    """Four levels, resolved by the recursive CTE the read path will use."""
    with engine.begin() as connection:
        insert_node(connection, tenant_id, "root", "ROOT", None, 0)
        insert_node(connection, tenant_id, "ou-1", "OU", "root", 1)
        insert_node(connection, tenant_id, "ou-2", "OU", "ou-1", 2)
        insert_node(connection, tenant_id, "acct-1", "ACCOUNT", "ou-2", 3)

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "WITH RECURSIVE subtree AS ("
                "  SELECT node_id, parent_node_id, depth FROM org_node"
                "   WHERE tenant_id = :tenant AND node_id = :start"
                "  UNION ALL"
                "  SELECT c.node_id, c.parent_node_id, c.depth FROM org_node c"
                "   JOIN subtree p ON c.parent_node_id = p.node_id"
                "  WHERE c.tenant_id = :tenant"
                ") SELECT node_id, depth FROM subtree ORDER BY depth"
            ),
            {"tenant": tenant_id, "start": "root"},
        ).all()
    assert [row[0] for row in rows] == ["root", "ou-1", "ou-2", "acct-1"]
    assert [row[1] for row in rows] == [0, 1, 2, 3]


def test_a_root_with_a_parent_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """A root with a parent means two roots, and a walk over the tree does not end."""
    with engine.begin() as connection:
        insert_node(connection, tenant_id, "root", "ROOT", None, 0)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        insert_node(connection, tenant_id, "bad-root", "ROOT", "root", 1)


def test_a_node_naming_a_parent_that_does_not_exist_is_refused(
    engine: Engine,
    tenant_id: UUID,
) -> None:
    """Without this, a dropped parent leaves a subtree nothing reports as missing."""
    with pytest.raises(IntegrityError), engine.begin() as connection:
        insert_node(connection, tenant_id, "orphan", "OU", "no-such-parent", 1)


# --- partitioning ------------------------------------------------------------


def cost_row(connection: Connection, tenant: UUID, period: date) -> None:
    connection.execute(
        text(
            "INSERT INTO cost_focus_daily (tenant_id, ingest_run_id, source_fingerprint, "
            "as_of, collected_at, billing_account_id, billing_period_start, "
            "billing_period_end, charge_period_start, charge_period_end, provider_name, "
            "service_name, charge_category, billed_cost, effective_cost) VALUES "
            "(:tenant, :run, :fp, :as_of, :collected, 'payer', :start, :end, "
            ":cstart, :cend, 'AWS', 'svc', 'Usage', 1.0, 1.0)"
        ),
        {
            "tenant": tenant,
            "run": uuid4(),
            "fp": str(uuid4()),
            "as_of": NOW,
            "collected": NOW,
            "start": period,
            "end": date(period.year, period.month, 28),
            "cstart": NOW,
            "cend": NOW,
        },
    )


def test_a_missing_partition_raises_rather_than_misfiling_the_cost(
    engine: Engine,
    tenant_id: UUID,
) -> None:
    """A default partition would turn a scheduling bug into silently misfiled cost."""
    with pytest.raises(DBAPIError), engine.begin() as connection:
        cost_row(connection, tenant_id, date(2031, 1, 1))


def test_a_row_lands_once_the_partition_exists(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS cost_focus_daily_p2026_08 "
                "PARTITION OF cost_focus_daily "
                "FOR VALUES FROM ('2026-08-01') TO ('2026-09-01')"
            )
        )
        cost_row(connection, tenant_id, date(2026, 8, 1))
    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM cost_focus_daily WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).scalar_one()
    assert count == 1


# --- the migration goes back as well as forward ------------------------------


def test_downgrade_removes_every_table_and_upgrade_restores_them(engine: Engine) -> None:
    """A downgrade that does not work is a migration nobody dares apply."""
    config = alembic_config(str(engine.url.render_as_string(hide_password=False)))
    command.downgrade(config, "base")
    with engine.connect() as connection:
        remaining = {
            row[0]
            for row in connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        }
    assert not (set(models.metadata.tables) & remaining)

    command.upgrade(config, "head")
    with engine.connect() as connection:
        restored = {
            row[0]
            for row in connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        }
    assert set(models.metadata.tables) <= restored
