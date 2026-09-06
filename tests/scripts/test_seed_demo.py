"""The seed script's refusal, which is the only dangerous part of it.

Everything else in `seed_demo` is convenience. This file is about the one
property that matters: it must be impossible to fill a real database with a fake
estate by running the wrong command in the wrong terminal.

The refusal is an allow list rather than a deny list on purpose. A deny list of
production hostnames is a list somebody has to remember to extend, and the first
host nobody thought of is the one that gets seeded.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Loaded by path, not imported as a package, because `scripts/` deliberately is
# not one. `tests/scripts/test_check_index.py` does the same, and importing it
# as `scripts.ops.seed_demo` makes mypy resolve one file under two module names.
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "seed_demo.py"
_spec = importlib.util.spec_from_file_location("seed_demo", SCRIPT)
assert _spec is not None and _spec.loader is not None
seed_demo = importlib.util.module_from_spec(_spec)
sys.modules["seed_demo"] = seed_demo
_spec.loader.exec_module(seed_demo)

DEMO_TENANT = seed_demo.DEMO_TENANT
LOCAL_HOSTS = seed_demo.LOCAL_HOSTS
NotLocalError = seed_demo.NotLocalError
main = seed_demo.main
require_local = seed_demo.require_local

REMOTE = "postgresql+psycopg://meter:secret@meter-prod.eu-west-2.rds.amazonaws.com:5432/meter"


class TestItRefusesAnythingNotLocalError:
    def test_a_remote_host_is_refused(self) -> None:
        with pytest.raises(NotLocalError):
            require_local(REMOTE)

    def test_the_refusal_names_the_host_it_refused(self) -> None:
        # An operator who sees this needs to know which database it read, not
        # only that something was wrong.
        with pytest.raises(NotLocalError, match="meter-prod"):
            require_local(REMOTE)

    @pytest.mark.parametrize("host", sorted(LOCAL_HOSTS - {""}))
    def test_every_allowed_host_is_accepted(self, host: str) -> None:
        require_local(f"postgresql+psycopg://meter:secret@{host}:5432/meter")

    def test_a_host_that_merely_contains_localhost_is_still_refused(self) -> None:
        # The check compares the parsed hostname, not a substring, so a host
        # named to look local does not pass.
        with pytest.raises(NotLocalError):
            require_local("postgresql+psycopg://u:p@localhost.evil.example/meter")

    def test_a_url_with_no_host_is_treated_as_local(self) -> None:
        # A socket or a relative URL has no hostname to check and cannot reach a
        # remote database.
        require_local("postgresql+psycopg:///meter")


def test_the_guard_runs_before_anything_connects(monkeypatch: pytest.MonkeyPatch) -> None:
    """A refusal must happen before an engine exists, not after.

    If the guard ran after `create_engine`, a mistyped command would already
    have opened a connection to the database it was refusing to touch.
    """
    opened: list[str] = []

    class Settings:
        database_url = REMOTE

    monkeypatch.setattr(seed_demo, "load_settings", Settings)
    monkeypatch.setattr(seed_demo, "create_engine", lambda url, **_kwargs: opened.append(url))

    assert main([]) == 2
    assert opened == []


def test_the_demo_tenant_is_fixed_so_removal_is_exact() -> None:
    # Removal is a delete by tenant. A generated identifier would mean the only
    # record of what to remove lived in the terminal that created it.
    assert str(DEMO_TENANT) == "5eeded00-0000-4000-8000-000000000001"


@pytest.mark.integration
def test_seed_then_remove_leaves_nothing_behind(engine: object) -> None:
    """The round trip, against a real migrated database.

    The request was to seed now and clear it later. Later is when nobody
    remembers which tables were touched, so the removal is proven here rather
    than described in a document.
    """
    from sqlalchemy import text as sql

    # Only the fields `rates_from` reads. Loading real settings would make this
    # test depend on a full environment to prove something about SQL.
    class Settings:
        query_logs_scan_price_per_gb = 0.005
        query_metrics_price_per_1000 = 0.01
        query_manual_loads_per_day = 4.0
        query_viewing_hours_per_day = 8.0
        query_metrics_per_call = 10.0
        query_default_ingest_gb_per_day = 10.0
        query_assumed_query_seconds = 3.0
        query_refresh_warn_seconds = 60
        query_refresh_crit_seconds = 15
        query_timerange_warn_hours = 168.0
        query_timerange_crit_hours = 720.0
        query_quota_logs_concurrent = 30
        query_quota_getmetricdata_tps = 50
        run_claim_timeout_minutes = 15

    seeded = seed_demo.seed(engine, Settings(), seed_demo.datetime.now(seed_demo.UTC))
    assert seeded.instances == 3
    assert seeded.accounts > 0
    assert seeded.rows > 0
    # One run per collector call, and account health runs once per account.
    assert seeded.runs > 4

    with engine.connect() as connection:  # type: ignore[attr-defined]
        for table_name in ("query_finding", "cloud_account", "org_node", "platform_cost"):
            rows = connection.execute(
                sql(f"SELECT count(*) FROM {table_name} WHERE tenant_id = :t"),
                {"t": DEMO_TENANT},
            ).scalar_one()
            assert rows > 0, f"{table_name} was not seeded"

        # The estate is worth developing against only if it contains the states
        # the screens exist to tell apart. An all healthy estate would let the
        # accounts screen look finished while rendering one of four cases.
        health = (
            connection.execute(
                sql(
                    "SELECT DISTINCT role_health FROM cloud_account "
                    "WHERE tenant_id = :t AND role_health IS NOT NULL"
                ),
                {"t": DEMO_TENANT},
            )
            .scalars()
            .all()
        )
    assert len(set(health)) > 1, f"every account reports the same health: {health}"

    cleared = seed_demo.remove(engine)
    assert cleared["tenant"] == 1

    with engine.connect() as connection:  # type: ignore[attr-defined]
        for table_name in seed_demo.DEMO_TABLES:
            left = connection.execute(
                sql(f"SELECT count(*) FROM {table_name} WHERE tenant_id = :t"),
                {"t": DEMO_TENANT},
            ).scalar_one()
            assert left == 0, f"{table_name} still holds demo rows"


def test_every_tenant_scoped_table_is_in_the_teardown() -> None:
    """A table that references the tenant and is not in DEMO_TABLES makes
    `make unseed` fail on the foreign key rather than remove the estate.

    That is exactly what happened when query_adhoc was added in TASK-P2-026 and
    missed here, and it was found by running unseed rather than by any test.
    Derived from the model metadata rather than restated, so a table added
    tomorrow is caught the day it is added.
    """
    from finops_api.db import models

    tenant_scoped = {
        table.name
        for table in models.metadata.tables.values()
        if "tenant_id" in table.c and table.name != "tenant"
    }
    # Tables the seed deliberately never writes. Listed rather than filtered
    # out, so adding a table forces a decision about it: either the seed writes
    # it and the teardown removes it, or it appears here with a reason.
    never_seeded = {
        # P1 owns these and P1 has not been built.
        "cost_focus_daily",
        "cost_focus_monthly",
        "cost_provider_extra",
        # Identity, which the local stack resolves from local-auth.yaml rather
        # than from rows.
        "principal",
        "principal_scope",
    }
    missing = tenant_scoped - set(seed_demo.DEMO_TABLES) - never_seeded
    assert not missing, (
        f"these tables reference the tenant, are not torn down, and are not "
        f"declared unseeded: {sorted(missing)}. Unseed will fail on the foreign key."
    )
