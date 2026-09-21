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
from decimal import Decimal
from pathlib import Path

import pytest

# Loaded by path, not imported as a package, because `scripts/` deliberately is
# not one. `tests/scripts/test_check_index.py` does the same, and importing it
# as `scripts.demo.seed_demo` makes mypy resolve one file under two module names.
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo.py"
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


class Settings:
    """Only the fields the seeded collectors read.

    Loading real settings would make these tests depend on a full environment to
    prove something about SQL.
    """

    # The anomaly detector's two, which it refuses to run without, because its
    # severity boundaries and its sensitivity are configuration and a default would
    # put an invented severity on a screen. Same values as `.env.example`.
    anomaly_sensitivity = 3.0
    anomaly_floor_usd = 5.0
    # And the money boundaries severity comes from, per ADR-0016, so the seeded
    # finding carries the severity a real one would.
    severity_critical_usd = Decimal("1000")
    severity_high_usd = Decimal("100")
    severity_medium_usd = Decimal("20")

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

    seeded = seed_demo.seed(engine, Settings(), seed_demo.datetime.now(seed_demo.UTC))
    assert seeded.instances == 3
    assert seeded.accounts > 0
    assert seeded.rows > 0
    # One run per collector call, and account health runs once per account.
    assert seeded.runs > 4

    with engine.connect() as connection:  # type: ignore[attr-defined]
        for table_name in (
            "query_finding",
            "cloud_account",
            "org_node",
            "platform_cost",
            # TASK-P1-019. The demo has nothing to show on the anomalies or
            # commitments screens unless these are filled, and an empty screen in a
            # demo reads as a product that does not work rather than as an estate
            # with nothing wrong.
            #
            # `cost_anomaly` here is the sharpest assertion in this file: the row
            # exists only because the detector read the seeded estate and judged a
            # day. Nothing writes it directly, so if the estate's spike ever stops
            # clearing the detector's bar, this fails.
            "cost_anomaly",
            "commitment_use",
            "commitment_coverage",
            # TASK-P3-019. The three waste screens are empty without these, and
            # an empty screen in a demo reads as a product that does not work.
            "recommendation",
            "realized_saving",
            "finops_score",
            "finops_score_component",
        ):
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


@pytest.mark.integration
def test_a_seeded_history_rises_rather_than_repeating(engine: object) -> None:
    """Six days seeded, and the estate costs more at the end than at the start.

    The trend screens were built against a history that was flat, because the
    seed wrote the same day three times. Flat is not wrong on its own, a real
    estate can be steady, but it meant nothing on those screens could be told
    apart: a chart drawing the right numbers and a chart drawing one number
    three times look identical.

    Strictly rising is the assertion because the fake estate now grows, so a
    repeated day shows up here as an equality rather than as a plausible line
    nobody checks.
    """
    from sqlalchemy import text as sql

    latest = seed_demo.datetime.now(seed_demo.UTC)
    for offset in (5, 4, 3, 2, 1, 0):
        seed_demo.seed(engine, Settings(), latest - seed_demo.timedelta(days=offset), latest=latest)

    try:
        with engine.connect() as connection:  # type: ignore[attr-defined]
            findings = connection.execute(
                sql(
                    "SELECT run_date, sum(cost_month_usd) FROM query_finding "
                    "WHERE tenant_id = :t GROUP BY run_date ORDER BY run_date"
                ),
                {"t": DEMO_TENANT},
            ).all()
            adhoc = connection.execute(
                sql(
                    "SELECT run_date, sum(cost_usd) FROM query_adhoc "
                    "WHERE tenant_id = :t GROUP BY run_date ORDER BY run_date"
                ),
                {"t": DEMO_TENANT},
            ).all()
    finally:
        seed_demo.remove(engine)

    assert len(findings) == 6, f"six days seeded, {len(findings)} days written"
    costs = [float(row[1]) for row in findings]
    assert costs == sorted(costs), f"the estate does not rise: {costs}"
    assert costs[0] < costs[-1], f"the estate ends where it started: {costs}"
    # Six days reaches back past both dashboard edits, so this also proves the
    # definition history arrives in the database rather than only in the fake.
    # Two thirds of the estate's cost is the one alert whose interval was
    # halved, so a run that lost the history would land well inside this.
    assert costs[-1] > costs[0] * 1.5, f"the steps did not land: {costs}"

    # The ad hoc rows are written from the same observations. A history that
    # moved only the owned queries would leave FEAT-051's screen flat while the
    # findings list rose, and the two would be describing different estates.
    assert len(adhoc) == 6
    unowned = [float(row[1]) for row in adhoc]
    assert unowned == sorted(unowned), f"the ad hoc queries do not rise: {unowned}"
    assert unowned[0] < unowned[-1], f"the ad hoc queries end where they started: {unowned}"


def test_the_test_fixture_accepts_the_same_hosts_the_seed_does() -> None:
    """`tests/conftest.py` copies this list rather than importing it, because
    `scripts/` is deliberately not a package. Copied is fine, drifting is not:
    the two guards protect the same thing, a person's own database, and one of
    them silently accepting a host the other refuses is how that protection
    stops being real.
    """
    from tests.conftest import LOCAL_HOSTS as FIXTURE_HOSTS

    assert FIXTURE_HOSTS == LOCAL_HOSTS


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


@pytest.mark.integration
def test_the_seed_produces_all_three_verdicts(engine: object) -> None:
    """TASK-P3-019, and the sharpest assertion about the demo estate.

    None of these rows is written directly. The seed lays down three finished
    recommendations and the billing rows that followed them, and the real
    collector reads those rows and reaches each verdict. So if the arithmetic
    ever stops distinguishing a saving from a workload that shrank, this fails
    rather than the demo doing it in front of an audience.

    The inconclusive one is the reason the test exists. An estate that only ever
    verifies cannot demonstrate the honesty the screen is built around, and it is
    the verdict a reader is least likely to believe until they see the working.
    """
    from sqlalchemy import text as sql

    seed_demo.seed(engine, Settings(), seed_demo.datetime.now(seed_demo.UTC))
    try:
        with engine.connect() as connection:  # type: ignore[attr-defined]
            verdicts = dict(
                connection.execute(
                    sql(
                        "SELECT verdict, count(*) FROM realized_saving "
                        "WHERE tenant_id = :t GROUP BY verdict"
                    ),
                    {"t": seed_demo.DEMO_TENANT},
                ).all()
            )
            scored = connection.execute(
                sql(
                    "SELECT count(*) FROM finops_score WHERE tenant_id = :t "
                    "AND available_weight >= 75"
                ),
                {"t": seed_demo.DEMO_TENANT},
            ).scalar_one()
            excluded = connection.execute(
                sql(
                    "SELECT count(*) FROM finops_score_component WHERE tenant_id = :t "
                    "AND points IS NULL"
                ),
                {"t": seed_demo.DEMO_TENANT},
            ).scalar_one()
        assert verdicts == {"VERIFIED": 1, "REGRESSED": 1, "INCONCLUSIVE": 1}, verdicts
        # At least one account carrying most of the available weight, so the score
        # screen has a substantial card to show. Not all hundred, and that is the
        # estate being honest rather than the seed being thin: the fourth component
        # needs a decided verdict for that same account, and the three seeded changes
        # are deliberately spread across three accounts so more than one of them has
        # something on the savings screen.
        assert scored >= 1
        # And at least one component that could not be computed, so the screen also
        # shows the absence rendered as an absence rather than as nought.
        assert excluded >= 1
    finally:
        seed_demo.remove(engine)
