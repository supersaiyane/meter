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
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from finops_core.config import Settings as RealSettings

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


@pytest.fixture(autouse=True)
def _partitions(request: pytest.FixtureRequest) -> None:
    """The seed bills months into partitions, so a test that seeds gives them back. ISS-268.

    Only where the test already has the database: the offline tests in this module must not start
    the container just to clean up after nothing.
    """
    if "engine" in request.fixturenames:
        request.getfixturevalue("partition_sandbox")


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

    # FEAT-054's four, which the parking collector refuses to run without, because each one
    # decides what gets flagged on somebody's production schedule. Same values as
    # `.env.example`, so the seeded finding is the one a real run would produce.
    parking_observation_days = 14
    parking_idle_percent = Decimal("5")
    parking_minimum_weeks = 2
    parking_minimum_window_hours = 3

    # FEAT-055's three, which the commitment collector refuses to run without. The discount is
    # an assumption about a price nobody has been quoted and the term is how long a wrong
    # decision lasts. Same values as `.env.example`.
    commitment_discount_percent = Decimal("30")
    commitment_term_months = 12
    commitment_minimum_monthly_saving_usd = Decimal("25")

    # FEAT-060's margin.
    budget_at_risk_margin = Decimal("0.1")

    # FEAT-057. The seed overrides the locations with the fake's, because the demo has no real
    # backend to name. Nothing is declared exhaustive, so the seeded estate never says unmanaged,
    # which is correct: the fake has one backend that refuses.
    iac_state_locations = ""
    iac_exhaustive_accounts = ""

    @property
    def iac_locations(self) -> tuple[str, ...]:
        return tuple(p.strip() for p in self.iac_state_locations.split(",") if p.strip())

    @property
    def iac_exhaustive(self) -> frozenset[str]:
        return frozenset(p.strip() for p in self.iac_exhaustive_accounts.split(",") if p.strip())

    # FEAT-077's one, which the ownership collector refuses to run without. Same value as
    # `.env.example`; the seed widens it to name the demo's second key.
    owner_tag_keys = "team"
    # TASK-P11-004, the default: the demo estate is far smaller.
    creator_lookups_per_run = 200

    @property
    def owner_tag_key_list(self) -> tuple[str, ...]:
        return tuple(p.strip() for p in self.owner_tag_keys.split(",") if p.strip())

    # FEAT-089, TASK-P14-010. The services AWS's purchase advice is asked for, the real setting's
    # own default, so the stub cannot drift from it.
    commitment_recommendation_services: str = RealSettings.model_fields[
        "commitment_recommendation_services"
    ].default

    @property
    def recommendation_services(self) -> tuple[str, ...]:
        return tuple(
            p.strip() for p in self.commitment_recommendation_services.split(",") if p.strip()
        )

    def model_copy(self, *, update: dict[str, object] | None = None) -> Settings:
        """The stub's own copy, because the seed uses it to override the state locations.

        A real `Settings` is a pydantic model and gets this for free. This stub is a plain class,
        so without it the seed would fail on an attribute error rather than on anything to do
        with what it was testing.
        """
        clone = Settings()
        for key, value in (update or {}).items():
            setattr(clone, key, value)
        return clone


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


def _now() -> datetime:
    """The real clock, nudged past the first of the month. ISS-221.

    A period has billed up to yesterday, so on the first the newest month holds no
    days and the fake estate is a month shorter than it looks. The realized savings
    collector compares a window ending sixty days after a change to one ending before
    it, and the commitment collector needs a usage floor across the window, so on the
    first both find nothing and the assertions below run against empty lists. The
    same defect as ISS-219, which was fixed the same way in the cost route tests.

    Written with `tz=` so the call site rewrite below does not match its own body.
    """
    # Read through the seed module's own clock, typed here because the module is
    # loaded by path and everything read through it is otherwise Any.
    now: datetime = seed_demo.datetime.now(tz=seed_demo.UTC)
    return max(now, datetime(now.year, now.month, 2, tzinfo=UTC))


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

    seeded = seed_demo.seed(engine, Settings(), _now())
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

    latest = _now()
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

    seed_demo.seed(engine, Settings(), _now())
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
            credited = connection.execute(
                sql(
                    "SELECT s.verdict, c.owner, c.verified_monthly_saving "
                    "FROM savings_credit c JOIN realized_saving s ON s.realized_id = c.realized_id "
                    "WHERE c.tenant_id = :t"
                ),
                {"t": seed_demo.DEMO_TENANT},
            ).all()
        assert verdicts == {"VERIFIED": 1, "REGRESSED": 1, "INCONCLUSIVE": 1}, verdicts
        # TASK-P11-006. The verified saving is credited to the owner who closed the work, and
        # the regressed and inconclusive ones earn nothing.
        assert [(row.verdict, row.owner) for row in credited] == [
            ("VERIFIED", "platform@example.local")
        ]
        assert credited[0].verified_monthly_saving > 0
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


def test_the_seeded_estate_has_exactly_one_unread_slice(engine: object) -> None:
    """TASK-P4-011's fourth criterion. An estate where every slice was read cannot show the
    one state P4 exists to distinguish, and an estate where several were not read makes the
    demo about the gap rather than about the product."""
    from sqlalchemy import text as sql

    seed_demo.seed(engine, Settings(), _now())
    with engine.connect() as connection:  # type: ignore[attr-defined]
        rows = connection.execute(
            sql(
                "SELECT sub_account_id, region_id, state, cause FROM graph_coverage "
                "WHERE tenant_id = :t ORDER BY state, sub_account_id"
            ),
            {"t": seed_demo.DEMO_TENANT},
        ).all()
    by_state: dict[str, int] = {}
    for row in rows:
        by_state[row.state] = by_state.get(row.state, 0) + 1
    unread = [row for row in rows if row.state == "UNREAD"]
    assert len(unread) == 1, f"expected one unread slice, got {by_state}"
    assert (unread[0].sub_account_id, unread[0].region_id) == (
        seed_demo.UNREAD_ACCOUNT,
        seed_demo.UNREAD_REGION,
    )
    assert unread[0].cause == "NotYetAttempted"
    # And the estate still has refused slices, which are a different thing: a read
    # happened and fell short. A demo with only one of the two teaches the wrong lesson.
    assert by_state.get("PARTIAL", 0) > 0
    assert by_state.get("COMPLETE", 0) > 0


def test_the_seeded_graph_has_an_edge_leaving_it(engine: object) -> None:
    """The denied account's VPC has no node row, so the attachment pointing at it is an edge
    whose far end Meter has not read. That is the shape the map draws as a boundary, and a
    seeded estate without one cannot exercise it."""
    from sqlalchemy import text as sql

    seed_demo.seed(engine, Settings(), _now())
    with engine.connect() as connection:  # type: ignore[attr-defined]
        dangling = connection.execute(
            sql(
                "SELECT count(*) FROM topology_edge e WHERE e.tenant_id = :t AND NOT EXISTS "
                "(SELECT 1 FROM topology_node n WHERE n.node_id = e.to_node_id "
                "AND n.tenant_id = e.tenant_id)"
            ),
            {"t": seed_demo.DEMO_TENANT},
        ).scalar_one()
        crossing = connection.execute(
            sql("SELECT count(*) FROM topology_edge WHERE tenant_id = :t AND is_cross_account"),
            {"t": seed_demo.DEMO_TENANT},
        ).scalar_one()
    assert int(dangling) >= 1
    assert int(crossing) >= 1


def test_the_seeded_estate_holds_a_parking_finding(engine: object) -> None:
    """FEAT-054. A collector wired into the seed that produces nothing is the hollow green
    signal this project keeps finding: the seed tests pass, `make verify` passes, and the
    screen the feature was built for is empty.

    The estate's development box is busy in business hours and idles at about two percent
    outside them, so a window exists to be found. If this ever fails it is worth reading the
    rationale before changing the threshold: an estate whose quiet hours drifted above five
    percent is a change in the fake, not a change in the rule.
    """
    from sqlalchemy import text as sql

    seed_demo.seed(engine, Settings(), _now())
    with engine.connect() as connection:  # type: ignore[attr-defined]
        rows = connection.execute(
            sql(
                "SELECT resource_id, estimated_monthly_saving, rationale FROM recommendation "
                "WHERE tenant_id = :t AND waste_class = 'PARKABLE_WINDOW'"
            ),
            {"t": seed_demo.DEMO_TENANT},
        ).all()
    assert rows, "the seeded estate produced no parking finding, so the screen would be empty"
    # Every one of them publishes its working and labels the clock, because a window in an
    # unnamed timezone is one nobody can act on. ISS-206.
    for row in rows:
        assert row.estimated_monthly_saving > 0
        assert "UTC" in row.rationale
        assert "observed weeks" in row.rationale


def test_the_seeded_estate_holds_a_commitment_action(engine: object) -> None:
    """FEAT-055. The same lesson as the parking assertion above: a collector wired into the seed
    that produces nothing passes every test and leaves the screen empty.

    The fake estate has eligible spend that no commitment covers, so a gap exists to be found.
    A failure here is worth reading the numbers before changing the floor: an estate whose gaps
    all fell below the minimum saving is a change in the fake, not a change in the rule.
    """
    from sqlalchemy import text as sql

    seed_demo.seed(engine, Settings(), _now())
    with engine.connect() as connection:  # type: ignore[attr-defined]
        rows = connection.execute(
            sql(
                "SELECT dimension, estimated_monthly_saving, usage_floor_percent, rationale "
                "FROM commitment_action WHERE tenant_id = :t"
            ),
            {"t": seed_demo.DEMO_TENANT},
        ).all()
    assert rows, "the seeded estate produced no commitment action, so the screen would be empty"
    for row in rows:
        assert row.dimension in {"SERVICE", "REGION"}
        assert row.estimated_monthly_saving > 0
        # The figure that makes it a decision rather than an observation, and the one a
        # coverage chart cannot show.
        assert 0 < row.usage_floor_percent <= 100
        assert "obligates" in row.rationale


def test_the_seeded_estate_records_what_manages_a_resource(engine: object) -> None:
    """FEAT-057. The third time this assertion has earned its place: a collector wired into the
    seed that writes nothing passes every test and leaves the screen empty.

    The fake state owns three of the estate's resources and one of its three backends refuses, so
    the seeded estate holds both halves of the honest answer: rows for what was found, and a
    `sync_error` row saying why Meter will not call any account unmanaged.
    """
    from sqlalchemy import text as sql

    seed_demo.seed(engine, Settings(), _now())
    with engine.connect() as connection:  # type: ignore[attr-defined]
        rows = connection.execute(
            sql(
                "SELECT provider_id, address, state_reference FROM resource_management "
                "WHERE tenant_id = :t"
            ),
            {"t": seed_demo.DEMO_TENANT},
        ).all()
        refused = connection.execute(
            sql(
                "SELECT scope_key, error_type FROM sync_error "
                "WHERE tenant_id = :t AND collector = 'iac_state' AND error_type <> 'NoData'"
            ),
            {"t": seed_demo.DEMO_TENANT},
        ).all()
    assert rows, "the seeded estate records nothing as managed, so the entity page would be blank"
    for row in rows:
        assert row.address
        assert row.state_reference.startswith("s3://")
    # The refusal, because the fake is partial by default and the whole feature turns on what
    # that prevents: no account can be called unmanaged while a location is unreadable.
    assert refused, "the fake's refusing backend left no record, so the partial path is untested"


def test_the_seeded_estate_holds_budgets_including_ones_it_cannot_join(engine: object) -> None:
    """FEAT-060. Fourth time this assertion has earned its place.

    Two of the four seeded budgets are deliberately unjoinable, because the first thing a
    finance reader asks is how many of their budgets this product can actually track. A seed
    where everything joined would leave that answer rendered by nothing anybody runs.
    """
    from sqlalchemy import text as sql

    seed_demo.seed(engine, Settings(), _now())
    with engine.connect() as connection:  # type: ignore[attr-defined]
        rows = connection.execute(
            sql("SELECT scope, limit_amount FROM budget WHERE tenant_id = :t"),
            {"t": seed_demo.DEMO_TENANT},
        ).all()
    assert rows, "the seeded estate holds no budgets, so the screen would be empty"
    scopes = [row.scope for row in rows]
    assert "ALL" in scopes, "no payer wide budget, which is the figure an executive view asks for"
    assert scopes.count("UNSUPPORTED") == 2, (
        "the seed no longer contains budgets this product cannot join, so the count the screen "
        "shows for them is rendered by nothing"
    )
    for row in rows:
        assert row.limit_amount > 0


@pytest.mark.integration
def test_the_seed_produces_the_container_estate(engine: object) -> None:
    """TASK-P6-011. The clusters, all three OOM states, and a recommendation in P3's list.

    Every assertion is about something a demo would otherwise show as missing. A seed
    without the container grain in the bill would render clusters with no cost at all,
    which is what it did before the fake derived split lines from the bill it exports: it
    filtered lines pinned to 2026-08 by the seed's own months and found nothing. A seed
    where every workload was observed would leave UNOBSERVED, the state most real
    workloads are in, rendered by nothing anybody runs.
    """
    from sqlalchemy import text as sql

    from finops_fakes import containers

    seed_demo.seed(engine, Settings(), _now())
    try:
        with engine.connect() as connection:  # type: ignore[attr-defined]
            tenant = {"t": seed_demo.DEMO_TENANT}
            clusters = {
                row[0]
                for row in connection.execute(
                    sql("SELECT cluster_name FROM container_cluster WHERE tenant_id = :t"), tenant
                )
            }
            states = {
                row[0]
                for row in connection.execute(
                    sql("SELECT was_oom_killed FROM container_usage WHERE tenant_id = :t"), tenant
                )
            }
            recommended = connection.execute(
                sql(
                    "SELECT count(*) FROM recommendation WHERE tenant_id = :t "
                    "AND waste_class = 'CONTAINER_RIGHTSIZE'"
                ),
                tenant,
            ).scalar_one()
            costed = connection.execute(
                sql(
                    "SELECT count(DISTINCT eks_cluster_name) FROM cost_focus_daily "
                    "WHERE tenant_id = :t AND eks_cluster_name IS NOT NULL"
                ),
                tenant,
            ).scalar_one()
        assert clusters == {cluster.name for cluster in containers.CLUSTERS}
        # Killed, not killed, and unobserved: three facts, so three values.
        assert states == {True, False, None}, states
        assert recommended >= 1, "no container recommendation reached P3's list"
        assert costed >= 1, "the seeded bill carries no container grain"
    finally:
        seed_demo.remove(engine)


def test_the_seeded_estate_names_owners_from_its_tags(engine: object) -> None:
    """FEAT-077. Every tagged resource's team, and the planted volume under the second key.

    `fake-product-b` carries no team tag, so its only owner from tags is the volume that carries
    `owner`, which the demo names as its second key.
    """
    from sqlalchemy import text as sql

    seed_demo.seed(engine, Settings(), _now())
    try:
        with engine.connect() as connection:  # type: ignore[attr-defined]
            found = {
                (row.resource_id, row.owner, row.detail)
                for row in connection.execute(
                    sql(
                        "SELECT resource_id, owner, detail FROM resource_owner "
                        "WHERE tenant_id = :t AND source = 'TAG'"
                    ),
                    {"t": DEMO_TENANT},
                )
            }
        assert ("amazonebs/fake-product-b/0001", "data-platform", "owner") in found
        assert ("amazonec2/fake-product-a/0003", "product", "team") in found
        untagged = {one for one in found if "/fake-product-b/" in one[0]}
        assert untagged == {("amazonebs/fake-product-b/0001", "data-platform", "owner")}
        with engine.connect() as connection:  # type: ignore[attr-defined]
            catalogued = {
                (row.resource_id, row.owner, row.detail)
                for row in connection.execute(
                    sql(
                        "SELECT resource_id, owner, detail FROM resource_owner "
                        "WHERE tenant_id = :t AND source = 'CATALOGUE'"
                    ),
                    {"t": DEMO_TENANT},
                )
            }
        # TASK-P11-003. AppRegistry's owners, by the application's tag and by the stack's.
        assert catalogued == {
            ("amazonec2/fake-product-b/0004", "payments", "checkout"),
            ("amazonrds/fake-product-b/0001", "analytics", "reporting"),
        }
        with engine.connect() as connection:  # type: ignore[attr-defined]
            created = {
                (row.resource_id, row.owner, row.owner_kind)
                for row in connection.execute(
                    sql(
                        "SELECT resource_id, owner, owner_kind FROM resource_owner "
                        "WHERE tenant_id = :t AND source = 'CREATOR'"
                    ),
                    {"t": DEMO_TENANT},
                )
            }
            asked = dict(
                connection.execute(
                    sql(
                        "SELECT outcome, count(*) FROM creator_lookup "
                        "WHERE tenant_id = :t GROUP BY outcome"
                    ),
                    {"t": DEMO_TENANT},
                ).all()
            )
        # TASK-P11-004. The two the fake event history saw made, a person and a pipeline; every
        # other unnamed resource is older than the history, and says so.
        assert created == {
            ("amazonec2/fake-product-b/0003", "dev.lead@fake.example", "PERSON"),
            ("amazonvpc/fake-product-b/nat-0001", "deploy-pipeline", "AUTOMATION"),
        }
        assert asked["FOUND"] == 2
        assert asked["BEFORE_HISTORY"] > 0
    finally:
        seed_demo.remove(engine)


@pytest.mark.integration
def test_the_demo_carries_ai_spend_from_every_source(engine: object) -> None:
    """P13, TASK-P13-009: the bill's model lines, both providers, the logs and the GPU agent.

    The AI spend screen on the local stack shows what this seeded, so each source is asserted by
    name, and so are the two absences the screen exists to say: an account whose invocation logs
    go to S3 only, NotOptedIn, and a GPU instance whose agent publishes nothing.
    """
    from sqlalchemy import text as sql

    seed_demo.seed(engine, Settings(), _now())
    tenant = {"t": DEMO_TENANT}
    with engine.connect() as connection:  # type: ignore[attr-defined]
        sources = set(
            connection.execute(
                sql(
                    "SELECT DISTINCT ingest_source FROM cost_focus_daily WHERE tenant_id = :t "
                    "AND (ingest_source <> 'aws_export' OR x_ai_model IS NOT NULL)"
                ),
                tenant,
            ).scalars()
        )
        assert sources == {"aws_export", "openai", "anthropic"}
        usage = set(
            connection.execute(
                sql("SELECT DISTINCT provider FROM ai_usage_daily WHERE tenant_id = :t"), tenant
            ).scalars()
        )
        assert usage == {"bedrock", "openai", "anthropic"}
        published = set(
            connection.execute(
                sql("SELECT DISTINCT instance_id FROM gpu_utilization_daily WHERE tenant_id = :t"),
                tenant,
            ).scalars()
        )
        assert published == {"i-fakegpu0001"}, "the second instance's agent publishes nothing"
        connected = connection.execute(
            sql("SELECT count(*) FROM ai_provider_account WHERE tenant_id = :t AND active"), tenant
        ).scalar_one()
        assert connected == 2
        refused = connection.execute(
            sql(
                "SELECT error_type FROM sync_error WHERE tenant_id = :t "
                "AND collector = 'bedrock_invocations'"
            ),
            tenant,
        ).scalars()
        assert "NotOptedIn" in set(refused)


def test_the_demo_carries_what_is_held_the_rate_the_advice_and_a_plan(engine: object) -> None:
    """P14, TASK-P14-010: the commitments screen on the local stack shows what this seeded.

    The lesson of the parking and commitment action assertions above: a collector wired into the
    seed that produces nothing passes every other test and leaves a panel empty. So each is
    asserted, and so is the absence the inventory exists to say: the refusing account holds no
    rows rather than reading as holding nothing.
    """
    from sqlalchemy import text as sql

    seed_demo.seed(engine, Settings(), _now())
    tenant = {"t": DEMO_TENANT}
    with engine.connect() as connection:  # type: ignore[attr-defined]
        held = dict(
            connection.execute(
                sql(
                    "SELECT commitment_id, account_id FROM commitment_inventory "
                    "WHERE tenant_id = :t"
                ),
                tenant,
            ).all()
        )
        assert "sp-fake-compute-0001" in held
        refused = connection.execute(
            sql(
                "SELECT count(*) FROM ingest_run WHERE tenant_id = :t "
                "AND collector = 'commitment_inventory' AND status = 'FAILED'"
            ),
            tenant,
        ).scalar_one()
        assert refused >= 1, "the refusing account's read is a failed run, not an empty one"
        listed = connection.execute(
            sql(
                "SELECT count(*) FROM cost_focus_daily WHERE tenant_id = :t "
                "AND charge_category = 'Usage' AND list_cost IS NOT NULL"
            ),
            tenant,
        ).scalar_one()
        assert listed > 0, "the savings rate needs usage lines that carry a List Cost"
        advice = connection.execute(
            sql(
                "SELECT recommended FROM purchase_recommendation WHERE tenant_id = :t "
                "AND kind = 'savings_plan' AND program = 'Compute'"
            ),
            tenant,
        ).scalar_one()
        assert advice is True
        plan = connection.execute(
            sql(
                "SELECT plan_id, status, no_purchase_reason FROM purchase_plan "
                "WHERE tenant_id = :t ORDER BY plan_month DESC LIMIT 1"
            ),
            tenant,
        ).one()
        assert (plan.status, plan.no_purchase_reason) == ("DRAFT", None)
        lines = connection.execute(
            sql("SELECT count(*) FROM purchase_plan_line WHERE plan_id = :p"),
            {"p": plan.plan_id},
        ).scalar_one()
        assert lines > 0, "the demo's plan buys nothing, so the plans panel would be empty"
