"""Retention is tested because nobody watches it succeed.

A collector that stops is noticed, because a number on a screen stops moving. A
retention job that stops is noticed by a regulator, years later. So the tests
here are about the two failure modes that are otherwise invisible: removing
something that should have survived, and surviving something that should have
been removed.

Two of them exist only to hold the boundary. `retention_principal` must never
reduce the row count, and an erasure must never reduce the audit count, because
both of those are one WHERE clause away from being true and neither would fail
anything else in the suite.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_ingest.collectors.partitions import (
    MONTHS_AHEAD,
    PARTITIONED_TABLES,
    detach_partitions_before,
    ensure_partition,
    existing_partitions,
    partition_maintenance,
    partition_name,
)
from finops_ingest.collectors.retention import (
    TOMBSTONE,
    retention_assistant,
    retention_audit,
    retention_cost,
    retention_operational,
    retention_principal,
    retention_scope_cache,
)
from finops_ingest.registry import CollectorContext
from tests.db.test_p7_constraints import an_exchange

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "erase_principal", ROOT / "scripts" / "ops" / "erase_principal.py"
)
assert _spec is not None and _spec.loader is not None
erase_principal = importlib.util.module_from_spec(_spec)
# Registered before executing, because `dataclass` resolves its own module out of
# sys.modules and a script loaded by path is not there yet.
sys.modules[_spec.name] = erase_principal
_spec.loader.exec_module(erase_principal)

AT = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


def at() -> datetime:
    return AT


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


def context(connection: Any, tenant: UUID, settings: Settings) -> CollectorContext:
    return CollectorContext(unit=Unit(tenant), connection=connection, settings=settings)


#: Every test here needs a real Postgres: partitioning, jsonb and date_trunc
#: are the behaviour under test, so a stub would be testing the stub.
pytestmark = pytest.mark.integration


def test_the_partitioned_tables_are_the_ones_we_think(engine: Engine) -> None:
    """Asked of the database, so a third partitioned table cannot be forgotten."""
    with engine.connect() as connection:
        reported = connection.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_partitioned_table p "
                "ON p.partrelid = c.oid ORDER BY c.relname"
            )
        ).scalars()
    assert tuple(reported) == tuple(sorted(PARTITIONED_TABLES))


def test_maintenance_creates_the_months_and_is_then_a_no_op(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    with engine.begin() as connection:
        first = partition_maintenance(context(connection, tenant_id, settings), clock=at)
        again = partition_maintenance(context(connection, tenant_id, settings), clock=at)
        names = existing_partitions(connection, "cost_focus_daily")

    assert first.items_written == (MONTHS_AHEAD + 1) * len(PARTITIONED_TABLES)
    assert again.items_written == 0
    assert partition_name("cost_focus_daily", date(2026, 8, 1)) in names


def insert_cost(connection: Any, tenant: UUID, day: date, amount: str, service: str) -> None:
    connection.execute(
        text(
            "INSERT INTO cost_focus_daily (tenant_id, ingest_run_id, source_fingerprint, "
            "as_of, collected_at, billing_account_id, sub_account_id, billing_period_start, "
            "billing_period_end, charge_period_start, charge_period_end, provider_name, "
            "service_name, region_id, charge_category, billed_cost, effective_cost) VALUES "
            "(:tenant, :run, :fingerprint, :at, :at, 'billing-1', 'sub-1', :day, :day, "
            ":at, :at, 'aws', :service, 'region-1', 'Usage', :amount, :amount)"
        ),
        {
            "tenant": tenant,
            "run": uuid4(),
            "fingerprint": f"{service}-{day}-{uuid4()}",
            "at": AT,
            "day": day,
            "service": service,
            "amount": Decimal(amount),
        },
    )


def test_a_cost_row_can_be_written_once_the_partition_exists(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The reason this job exists. Without it the insert fails outright."""
    with engine.begin() as connection:
        partition_maintenance(context(connection, tenant_id, settings), clock=at)
        insert_cost(connection, tenant_id, date(2026, 8, 4), "1.50", "compute")
        written = connection.execute(
            text("SELECT count(*) FROM cost_focus_daily WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).scalar_one()
    assert written == 1


def test_cost_is_aggregated_before_its_partition_is_removed(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    old = date(2023, 5, 4)
    with engine.begin() as connection:
        partition_maintenance(context(connection, tenant_id, settings), clock=at)
        for parent in PARTITIONED_TABLES:
            ensure_partition(connection, parent, old)
        insert_cost(connection, tenant_id, old, "10.00", "compute")
        insert_cost(connection, tenant_id, old.replace(day=9), "5.00", "compute")
        insert_cost(connection, tenant_id, date(2026, 8, 4), "1.00", "compute")

        outcome = retention_cost(context(connection, tenant_id, settings), clock=at)

        rolled_rows = connection.execute(
            text(
                "SELECT billing_month, billed_cost, line_items FROM cost_focus_monthly "
                "WHERE tenant_id = :t"
            ),
            {"t": tenant_id},
        ).all()
        rolled = [tuple(row) for row in rolled_rows]
        surviving = connection.execute(
            text("SELECT count(*) FROM cost_focus_daily WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).scalar_one()
        names = existing_partitions(connection, "cost_focus_daily")

    assert outcome.items_written == 1
    assert rolled == [(date(2023, 5, 1), Decimal("15.0000000000"), 2)]
    assert surviving == 1, "the recent month must survive"
    assert partition_name("cost_focus_daily", old) not in names
    assert partition_name("cost_focus_daily", date(2026, 8, 1)) in names


def test_a_partition_holding_any_day_inside_the_window_survives(engine: Engine) -> None:
    """Strictly before, on a month boundary. Otherwise live data goes with it."""
    with engine.begin() as connection:
        ensure_partition(connection, "cost_focus_daily", date(2026, 7, 1))
        removed = detach_partitions_before(connection, "cost_focus_daily", date(2026, 7, 20))
    assert removed == ()


def insert_principal(
    connection: Any, tenant: UUID, seen: datetime | None, name: str = "A Person"
) -> UUID:
    principal = uuid4()
    connection.execute(
        text(
            "INSERT INTO principal (principal_id, tenant_id, subject, display_name, email, "
            "tier, last_seen_at) VALUES (:id, :tenant, :subject, :name, :email, 'analyst', :seen)"
        ),
        {
            "id": principal,
            "tenant": tenant,
            "subject": f"idp|{principal}",
            "name": name,
            "email": f"{principal}@example.invalid",
            "seen": seen,
        },
    )
    return principal


def test_a_principal_past_the_window_is_anonymised_and_never_removed(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The row survives so audit joins do not dangle."""
    with engine.begin() as connection:
        stale = insert_principal(connection, tenant_id, AT - timedelta(days=200))
        fresh = insert_principal(connection, tenant_id, AT - timedelta(days=2))

        outcome = retention_principal(context(connection, tenant_id, settings), clock=at)

        rows = connection.execute(
            text(
                "SELECT principal_id, display_name, email, subject FROM principal "
                "WHERE tenant_id = :t ORDER BY display_name"
            ),
            {"t": tenant_id},
        ).all()

    assert outcome.items_written == 1
    assert len(rows) == 2, "anonymised, not removed"
    retired = next(row for row in rows if row.principal_id == stale)
    kept = next(row for row in rows if row.principal_id == fresh)
    assert (retired.display_name, retired.email) == (TOMBSTONE, None)
    assert str(stale) not in retired.subject, "the subject must not still identify anyone"
    assert kept.display_name == "A Person"


def test_anonymising_twice_changes_nothing_the_second_time(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Without the guard the subject would be re-hashed every night forever."""
    with engine.begin() as connection:
        insert_principal(connection, tenant_id, AT - timedelta(days=200))
        first = retention_principal(context(connection, tenant_id, settings), clock=at)
        second = retention_principal(context(connection, tenant_id, settings), clock=at)
    assert (first.items_written, second.items_written) == (1, 0)


def test_a_principal_never_seen_is_left_alone(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A NULL last_seen_at is an invited account, not an abandoned one."""
    with engine.begin() as connection:
        insert_principal(connection, tenant_id, None)
        outcome = retention_principal(context(connection, tenant_id, settings), clock=at)
    assert outcome.items_written == 0


def insert_run(connection: Any, tenant: UUID, started: datetime) -> None:
    connection.execute(
        text(
            "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, idempotency_key, "
            "started_at, status, as_of_window_start, as_of_window_end) VALUES "
            "(:id, :tenant, 'org_tree', 'scope', :key, :started, 'SUCCEEDED', :started, :started)"
        ),
        {"id": uuid4(), "tenant": tenant, "key": str(uuid4()), "started": started},
    )


def insert_error(connection: Any, tenant: UUID, seen: datetime, scope: str) -> None:
    connection.execute(
        text(
            "INSERT INTO sync_error (error_id, tenant_id, collector, scope_key, error_type, "
            "detail, remediation, first_seen_at, last_seen_at) VALUES "
            "(:id, :tenant, 'org_tree', :scope, 'AccessDenied', 'd', 'r', :seen, :seen)"
        ),
        {"id": uuid4(), "tenant": tenant, "scope": scope, "seen": seen},
    )


def insert_watermark(connection: Any, tenant: UUID, scope: str, updated: datetime) -> None:
    connection.execute(
        text(
            "INSERT INTO ingest_watermark (tenant_id, collector, scope_key, as_of, updated_at) "
            "VALUES (:tenant, 'org_tree', :scope, :updated, :updated)"
        ),
        {"tenant": tenant, "scope": scope, "updated": updated},
    )


def test_operational_history_past_the_window_goes(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Runs, errors and dead watermarks, which is what the classification says."""
    with engine.begin() as connection:
        insert_run(connection, tenant_id, AT - timedelta(days=200))
        insert_run(connection, tenant_id, AT - timedelta(days=1))
        insert_error(connection, tenant_id, AT - timedelta(days=200), "old")
        insert_error(connection, tenant_id, AT - timedelta(days=1), "new")
        insert_watermark(connection, tenant_id, "closed-account", AT - timedelta(days=200))
        insert_watermark(connection, tenant_id, "live-account", AT - timedelta(days=1))

        outcome = retention_operational(context(connection, tenant_id, settings), clock=at)

        counts = tuple(
            connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"),
                {"t": tenant_id},
            ).scalar_one()
            for table in ("ingest_run", "sync_error", "ingest_watermark")
        )
        surviving_scope = connection.execute(
            text("SELECT scope_key FROM ingest_watermark WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).scalar_one()

    assert outcome.items_written == 3
    assert counts == (1, 1, 1)
    assert surviving_scope == "live-account", "a live scope must keep its resume point"


def insert_audit(connection: Any, tenant: UUID, principal: UUID, occurred: datetime) -> None:
    connection.execute(
        text(
            "INSERT INTO audit_event (event_id, tenant_id, principal_id, action, resource, "
            "scope_evaluated, outcome, occurred_at, request_id) VALUES "
            "(:id, :tenant, :principal, 'read', 'accounts', '{}'::jsonb, 'ALLOWED', "
            ":occurred, 'req-1')"
        ),
        {"id": uuid4(), "tenant": tenant, "principal": principal, "occurred": occurred},
    )


def test_audit_events_go_only_at_their_own_window(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    with engine.begin() as connection:
        principal = insert_principal(connection, tenant_id, AT)
        insert_audit(connection, tenant_id, principal, AT - timedelta(days=500))
        insert_audit(connection, tenant_id, principal, AT - timedelta(days=100))

        outcome = retention_audit(context(connection, tenant_id, settings), clock=at)

        left = connection.execute(
            text("SELECT count(*) FROM audit_event WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar_one()

    assert (outcome.items_written, left) == (1, 1)


def insert_scope(connection: Any, tenant: UUID, principal: UUID, expires: datetime) -> None:
    connection.execute(
        text(
            "INSERT INTO principal_scope (tenant_id, principal_id, account_id, granted_via, "
            "resolved_at, expires_at) VALUES (:tenant, :principal, :account, 'group', :at, :exp)"
        ),
        {
            "tenant": tenant,
            "principal": principal,
            "account": f"acct-{uuid4()}",
            "at": AT,
            "exp": expires,
        },
    )


def test_only_expired_entitlement_rows_go(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    with engine.begin() as connection:
        principal = insert_principal(connection, tenant_id, AT)
        insert_scope(connection, tenant_id, principal, AT - timedelta(hours=2))
        insert_scope(connection, tenant_id, principal, AT + timedelta(hours=2))

        outcome = retention_scope_cache(context(connection, tenant_id, settings), clock=at)

        left = connection.execute(
            text("SELECT count(*) FROM principal_scope WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar_one()

    assert (outcome.items_written, left) == (1, 1)


def test_no_job_reaches_into_another_tenant(engine: Engine, settings: Settings) -> None:
    """One filter missing here is a cross tenant deletion, so it is held explicitly."""
    mine, theirs = uuid4(), uuid4()
    with engine.begin() as connection:
        for tenant in (mine, theirs):
            connection.execute(
                text("INSERT INTO tenant (tenant_id, name) VALUES (:id, :name)"),
                {"id": tenant, "name": f"tenant-{tenant}"},
            )
            principal = insert_principal(connection, tenant, AT - timedelta(days=200))
            insert_run(connection, tenant, AT - timedelta(days=200))
            insert_error(connection, tenant, AT - timedelta(days=200), "old")
            insert_audit(connection, tenant, principal, AT - timedelta(days=500))
            insert_scope(connection, tenant, principal, AT - timedelta(hours=2))

        for job in (
            retention_principal,
            retention_operational,
            retention_audit,
            retention_scope_cache,
        ):
            job(context(connection, mine, settings), clock=at)

        survivors = {
            table: connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"),
                {"t": theirs},
            ).scalar_one()
            for table in ("ingest_run", "sync_error", "audit_event", "principal_scope")
        }
        name = connection.execute(
            text("SELECT display_name FROM principal WHERE tenant_id = :t"), {"t": theirs}
        ).scalar_one()

    assert survivors == {
        "ingest_run": 1,
        "sync_error": 1,
        "audit_event": 1,
        "principal_scope": 1,
    }
    assert name == "A Person"


# --- erasure -----------------------------------------------------------------


def test_an_erasure_anonymises_and_leaves_the_audit_trail_intact(
    engine: Engine, tenant_id: UUID
) -> None:
    """The whole point. An erasure that removed audit rows would pass every other
    test in this file."""
    with engine.begin() as connection:
        principal = insert_principal(connection, tenant_id, AT)
        insert_audit(connection, tenant_id, principal, AT - timedelta(days=1))
        insert_scope(connection, tenant_id, principal, AT + timedelta(hours=2))
        connection.execute(
            text(
                "INSERT INTO collector_schedule (tenant_id, collector, cadence_seconds, reason, "
                "updated_by) VALUES (:t, 'org_tree', 3600, 'because', :who)"
            ),
            {"t": tenant_id, "who": str(principal)},
        )
        connection.execute(
            text(
                "INSERT INTO commitment_policy (tenant_id, target_coverage, term_years, "
                "payment_option, ladder_limit, reason, updated_by) VALUES (:t, 0.8, 1, "
                "'No Upfront', 0.0833, 'steady usage', :who)"
            ),
            {"t": tenant_id, "who": str(principal)},
        )

        report = erase_principal.erase(
            connection, tenant_id, principal, "operator-1", "ticket-9", clock=at
        )

        row = connection.execute(
            text("SELECT display_name, email, subject FROM principal WHERE principal_id = :p"),
            {"p": principal},
        ).one()
        audits = connection.execute(
            text("SELECT action FROM audit_event WHERE tenant_id = :t ORDER BY action"),
            {"t": tenant_id},
        ).scalars()
        scopes = connection.execute(
            text("SELECT count(*) FROM principal_scope WHERE principal_id = :p"),
            {"p": principal},
        ).scalar_one()
        attributed = connection.execute(
            text("SELECT updated_by FROM collector_schedule WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).scalar_one()
        policy = connection.execute(
            text("SELECT updated_by, reason FROM commitment_policy WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).one()

    assert report.principals_anonymised == 1
    assert report.scope_rows_removed == 1
    assert report.schedule_rows_reattributed == 1
    assert report.audit_events_removed == 0
    assert (row.display_name, row.email) == (TOMBSTONE, None)
    assert str(principal) not in row.subject
    assert list(audits) == ["erasure.completed", "erasure.requested", "read"], (
        "the pre-existing read must survive alongside the two erasure records"
    )
    assert (scopes, attributed) == (0, TOMBSTONE)
    # The policy stays the tenant's decision; only the name on it goes. TASK-P14-005.
    assert (report.policies_reattributed, policy.updated_by, policy.reason) == (
        1,
        TOMBSTONE,
        "steady usage",
    )


def test_an_erasure_keeps_a_plans_steps_and_takes_the_name_off_them(
    engine: Engine, tenant_id: UUID
) -> None:
    """TASK-P14-008. A plan's history is the payer's record of a commitment; the person goes."""
    plan = uuid4()
    with engine.begin() as connection:
        principal = insert_principal(connection, tenant_id, AT)
        connection.execute(
            text(
                "INSERT INTO purchase_plan (plan_id, tenant_id, ingest_run_id, plan_month, "
                "target_coverage, term_years, payment_option, ladder_limit, window_start, "
                "window_end, days_held, currency, as_of, collected_at) VALUES (:plan, :t, :plan, "
                "'2026-10-01', 0.8, 1, 'No Upfront', 0.0833, '2026-09-13', '2026-10-13', 30, "
                "'USD', :at, :at)"
            ),
            {"plan": plan, "t": tenant_id, "at": AT},
        )
        connection.execute(
            text(
                "INSERT INTO purchase_plan_event (event_id, plan_id, tenant_id, from_status, "
                "to_status, principal, at, note) VALUES (:event, :plan, :t, 'DRAFT', 'APPROVED', "
                ":who, :at, 'within the ladder')"
            ),
            {"event": uuid4(), "plan": plan, "t": tenant_id, "who": str(principal), "at": AT},
        )
        report = erase_principal.erase(
            connection, tenant_id, principal, "operator-1", "ticket-9", clock=at
        )
        step = connection.execute(
            text("SELECT principal, note FROM purchase_plan_event WHERE plan_id = :plan"),
            {"plan": plan},
        ).one()

    assert report.plan_steps_reattributed == 1
    assert (step.principal, step.note) == (TOMBSTONE, "within the ladder")


def test_an_erasure_keeps_where_fixes_go_and_takes_the_name_off(
    engine: Engine, tenant_id: UUID
) -> None:
    """TASK-P15-003. The connection and the mapping are the organization's; the person goes."""
    with engine.begin() as connection:
        principal = insert_principal(connection, tenant_id, AT)
        who = {"t": tenant_id, "who": str(principal), "at": AT}
        connection.execute(
            text(
                "INSERT INTO code_host_connection (tenant_id, host, app_id, key_secret_name, "
                "connected_by, connected_at) VALUES (:t, 'github', '1001', "
                "'meter/dev/codehost/github-app', :who, :at)"
            ),
            who,
        )
        connection.execute(
            text(
                "INSERT INTO repository_mapping (tenant_id, state_reference, repository, "
                "base_branch, folder, set_by, set_at) VALUES (:t, 's3://state/storage.tfstate', "
                "'acme/infra', 'main', 'storage', :who, :at)"
            ),
            who,
        )
        connection.execute(
            text(
                "INSERT INTO merge_policy (tenant_id, waste_class, reason, set_by, set_at) "
                "VALUES (:t, 'EBS_GP2_TO_GP3', 'reversible', :who, :at)"
            ),
            who,
        )
        report = erase_principal.erase(
            connection, tenant_id, principal, "operator-1", "ticket-9", clock=at
        )
        connected = connection.execute(
            text("SELECT connected_by, app_id FROM code_host_connection WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).one()
        mapped = connection.execute(
            text("SELECT set_by, repository FROM repository_mapping WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).one()

    assert (report.code_host_reattributed, report.mappings_reattributed) == (1, 1)
    assert report.merge_policies_reattributed == 1
    assert tuple(connected) == (TOMBSTONE, "1001")
    assert tuple(mapped) == (TOMBSTONE, "acme/infra")


def test_an_erasure_keeps_the_fixes_a_person_asked_for_and_takes_the_name_off(
    engine: Engine, tenant_id: UUID
) -> None:
    """TASK-P15-004. A fix's history is the tenant's record of a change; the person goes."""
    recommendation, fix = uuid4(), uuid4()
    with engine.begin() as connection:
        principal = insert_principal(connection, tenant_id, AT)
        who = {"t": tenant_id, "who": str(principal), "at": AT, "id": recommendation, "fix": fix}
        connection.execute(
            text(
                "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, source, "
                "source_reference, waste_class, resource_id, region_id, "
                "estimated_monthly_saving, confidence, severity, observation_days, lifecycle, "
                "rationale, as_of, collected_at) VALUES (:id, :t, 'acct', 'METER', 'ref-fix', "
                "'EBS_UNATTACHED', 'vol-1', 'eu-west-1', 1, 'HIGH', 'HIGH', 30, 'ACCEPTED', "
                "'unattached', :at, :at)"
            ),
            who,
        )
        connection.execute(
            text(
                "INSERT INTO fix_pull_request (fix_id, tenant_id, recommendation_id, "
                "sub_account_id, status, note, requested_by, requested_at, as_of, collected_at) "
                "VALUES (:fix, :t, :id, 'acct', 'REQUESTED', 'agreed', :who, :at, :at, :at)"
            ),
            who,
        )
        connection.execute(
            text(
                "INSERT INTO fix_pull_request_event (event_id, fix_id, tenant_id, sub_account_id, "
                "to_status, principal, note, at) VALUES (gen_random_uuid(), :fix, :t, 'acct', "
                "'REQUESTED', :who, 'agreed', :at)"
            ),
            who,
        )
        report = erase_principal.erase(
            connection, tenant_id, principal, "operator-1", "ticket-9", clock=at
        )
        asked = connection.execute(
            text("SELECT requested_by, note FROM fix_pull_request WHERE fix_id = :fix"),
            {"fix": fix},
        ).one()
        step = connection.execute(
            text("SELECT principal, note FROM fix_pull_request_event WHERE fix_id = :fix"),
            {"fix": fix},
        ).one()

    assert (report.fixes_reattributed, report.fix_steps_reattributed) == (1, 1)
    assert tuple(asked) == (TOMBSTONE, "agreed")
    assert tuple(step) == (TOMBSTONE, "agreed")


def test_the_report_says_out_loud_that_nothing_was_removed_from_the_audit_log() -> None:
    report = erase_principal.ErasureReport(uuid4(), 1, 0, 0, 2)
    assert any("never removed, by design" in line for line in report.lines())


# --- the kill switch ---------------------------------------------------------


def all_on(_: str) -> bool:
    return True


def retention_off(key: str) -> bool:
    from finops_ingest.registry import RETENTION_FLAG

    return key != RETENTION_FLAG


def test_the_flag_stops_every_retention_job_and_nothing_else(
    engine: Engine, tenant_id: UUID
) -> None:
    """An unenforced kill switch is worse than none: an operator would believe
    they had turned retention off."""
    from finops_ingest.registry import due_collectors, install_default_schedule

    with engine.begin() as connection:
        install_default_schedule(connection, tenant_id, updated_by="test")
        everything = due_collectors(connection, tenant_id, all_on, AT)
        without = due_collectors(connection, tenant_id, retention_off, AT)

    assert set(everything) - set(without) == {
        "retention_principal",
        "retention_operational",
        "retention_assistant",
        "retention_ai_usage",
        "retention_plans",
        "retention_audit",
        "retention_cost",
        "retention_scope_cache",
        "partition_maintenance",
    }
    # Exhaustive on purpose, which is why adding cost_focus to the default
    # schedule failed here rather than anywhere else.
    assert set(without) == {
        "org_tree",
        "account_health",
        "platform_cost",
        "query_audit",
        "cost_focus",
        # P6, TASK-P6-006. In the default schedule and not a retention job.
        "container_usage",
        # P13, TASK-P13-003. Who called which Bedrock model, daily.
        "bedrock_invocations",
        # P13, TASK-P13-004 and 005. OpenAI's and Anthropic's cost and usage, daily.
        "openai_usage",
        "anthropic_usage",
        # P13, TASK-P13-006. How busy each GPU instance was, daily.
        "gpu_utilization",
        # P1 and P3. All six were missing from the default schedule until
        # 2026-09-21, which meant the dispatcher never returned them and none of
        # them ever ran. ISS-190.
        "cost_anomaly",
        "commitment",
        # P14, FEAT-086.
        "commitment_inventory",
        # P14, FEAT-089.
        "purchase_recommendation",
        "purchase_plan",
        "recommendations",
        "waste_compute",
        "waste_cloudwatch",
        "realized_savings",
        "finops_score",
        # P4, FEAT-030 and FEAT-031. Added with the collector in TASK-P4-006, and this
        # list is where it had to be declared, which is the point of it being exhaustive
        # rather than a subset.
        "inventory",
        # FEAT-054, added with the collector in TASK-P3-021. Declared here for the same
        # reason: this list is exhaustive, so a collector with a schedule row and no
        # declaration fails here rather than reaching a dispatcher nobody was watching.
        "waste_parking",
        # FEAT-055, added with the collector in TASK-P1-022. Declared here for the same reason
        # the two above it are: the list is exhaustive, so a collector with a schedule row and
        # no declaration fails here rather than reaching a dispatcher nobody was watching.
        "commitment_actions",
        # FEAT-057, added with the collector in TASK-P4-013.
        "iac_state",
        # FEAT-060, added with the collector.
        "budgets",
        # FEAT-076, added with the collector in TASK-P10-003.
        "invoices",
        # FEAT-071, added with the collector in TASK-P9-004. Eight hourly, and never run, so it is
        # due at `AT`.
        "price_catalog",
        # FEAT-072, added with the collector in TASK-P9-005.
        "instance_catalog",
        # FEAT-071, added with the collector in TASK-P9-012.
        "savings_plan_rates",
        # FEAT-071, added with the collector in TASK-P9-013.
        "spot_prices",
        # FEAT-033 and FEAT-034, added with the collector in TASK-P5-004. Twelve hourly, so it
        # is due at `AT` like everything else here. Declared for the same reason as the four
        # above: the list is exhaustive, so a collector with a schedule row and no declaration
        # fails here rather than reaching a dispatcher nobody was watching.
        "quotas",
        # FEAT-041, added with the collector in TASK-P7-012. Weekly, and never run, so it is
        # due at `AT`. Missed when the collector landed and caught here by the full suite.
        "team_digests",
        # FEAT-077, added with the collector in TASK-P11-002. Daily, and never run, so due at
        # `AT`; declared here because the list is exhaustive.
        "ownership",
        "savings_ledger",
        # FEAT-092, added with the collector in TASK-P15-004. Every ten minutes, and never run,
        # so due at `AT`; declared here because the list is exhaustive.
        "fix_pull_requests",
        # FEAT-095, added with the collector in TASK-P16-005. Every ten minutes, and never run,
        # so due at `AT`; declared here because the list is exhaustive.
        "plan_estimates",
        # FEAT-096, added with the collector in TASK-P16-006. Every ten minutes, and never run,
        # so due at `AT`; declared here because the list is exhaustive.
        "plan_comments",
        # FEAT-097, added with the collector in TASK-P16-007. Daily, and never run, so due at
        # `AT`; declared here because the list is exhaustive.
        "estimate_comparison",
    }


def test_a_collector_inside_its_cadence_is_not_due(engine: Engine, tenant_id: UUID) -> None:
    from finops_ingest.registry import due_collectors, install_default_schedule

    with engine.begin() as connection:
        install_default_schedule(connection, tenant_id, updated_by="test")
        connection.execute(
            text(
                "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, "
                "idempotency_key, status, finished_at, as_of_window_start, as_of_window_end) "
                "VALUES (:run, :tenant, 'org_tree', 'scope', :key, 'SUCCEEDED', :recent, "
                ":recent, :recent)"
            ),
            {
                "run": uuid4(),
                "tenant": tenant_id,
                "key": str(uuid4()),
                "recent": AT - timedelta(minutes=5),
            },
        )
        due = due_collectors(connection, tenant_id, all_on, AT)

    assert "org_tree" not in due, "hourly, and it ran five minutes ago"
    assert "account_health" in due, "never run, so due"


def test_a_disabled_schedule_row_is_never_due(engine: Engine, tenant_id: UUID) -> None:
    from finops_ingest.registry import due_collectors, install_default_schedule

    with engine.begin() as connection:
        install_default_schedule(connection, tenant_id, updated_by="test")
        connection.execute(
            text(
                "UPDATE collector_schedule SET is_enabled = false "
                "WHERE tenant_id = :t AND collector = 'platform_cost'"
            ),
            {"t": tenant_id},
        )
        due = due_collectors(connection, tenant_id, all_on, AT)

    assert "platform_cost" not in due


# --- the person's questions, exports, views and schedules, ISS-226, ISS-249, ISS-255, ISS-256 ---


def a_redaction(connection: Any, tenant: UUID, exchange: UUID, who: str, at: datetime) -> None:
    connection.execute(
        text(
            "INSERT INTO redaction_event (event_id, tenant_id, exchange_id, principal_id, rule_id, "
            "action, occurred_at) VALUES (:e, :t, :x, :w, 'aws-access-token', 'BLOCKED', :at)"
        ),
        {"e": uuid4(), "t": tenant, "x": exchange, "w": who, "at": at},
    )


def an_export(connection: Any, tenant: UUID, who: str) -> None:
    connection.execute(
        text(
            "INSERT INTO report_run (run_id, tenant_id, principal_id, view_path, view_query, "
            "scope_global, scope_accounts, format, row_count, byte_count, truncated, made_at) "
            "VALUES (:r, :t, :w, '/', '', true, ARRAY[]::text[], 'csv', 1, 10, false, :at)"
        ),
        {"r": uuid4(), "t": tenant, "w": who, "at": AT},
    )


def a_view(connection: Any, tenant: UUID, owner: str, visibility: str) -> UUID:
    view = uuid4()
    connection.execute(
        text(
            "INSERT INTO saved_view (view_id, tenant_id, owner_id, name, screen_path, query, "
            "visibility, created_at, updated_at) "
            "VALUES (:v, :t, :o, 'Month to date', '/', CAST('{}' AS JSONB), :vis, :at, :at)"
        ),
        {"v": view, "t": tenant, "o": owner, "vis": visibility, "at": AT},
    )
    return view


def a_schedule(connection: Any, tenant: UUID, owner: str, recipients: list[str]) -> UUID:
    schedule = uuid4()
    connection.execute(
        text(
            "INSERT INTO report_schedule (schedule_id, tenant_id, owner_id, view_id, export_path, "
            "format, cadence, recipients, enabled, next_run_at, created_at, updated_at) VALUES "
            "(:s, :t, :o, NULL, '/api/v1/cost/summary', 'csv', 'WEEKLY', :r, true, :at, :at, :at)"
        ),
        {"s": schedule, "t": tenant, "o": owner, "r": recipients, "at": AT},
    )
    return schedule


def test_an_erasure_reaches_the_persons_questions_exports_views_and_schedules(
    engine: Engine, tenant_id: UUID
) -> None:
    """As the owner decided on 2026-10-12: questions and exports tombstoned and kept, private
    views removed and shared ones left unowned, the person's schedules paused, and their name
    off every recipient list."""
    other = "someone-else"
    with engine.begin() as connection:
        principal = insert_principal(connection, tenant_id, AT)
        who = str(principal)
        answered = an_exchange(
            connection, tenant_id, who=who, question="What did Priya's team spend?"
        )
        an_exchange(
            connection,
            tenant_id,
            who=who,
            question="Forecast Priya's spend",
            outcome="REFUSED",
            answer=None,
            gap="tool",
            reason="There is no tool that forecasts spend.",
            citations=[],
        )
        a_redaction(connection, tenant_id, answered, who, AT)
        an_export(connection, tenant_id, who)
        private = a_view(connection, tenant_id, who, "PRIVATE")
        shared = a_view(connection, tenant_id, who, "SHARED")
        theirs = a_schedule(connection, tenant_id, who, [who, other])
        only_them = a_schedule(connection, tenant_id, other, [who])
        among = a_schedule(connection, tenant_id, other, [other, who])

        report = erase_principal.erase(
            connection, tenant_id, principal, "operator-1", "ticket-10", clock=at
        )

        def rows(sql: str) -> list[Any]:
            return list(connection.execute(text(sql), {"t": tenant_id}).all())

        exchanges = rows(
            "SELECT principal_id, question, answer, refusal_reason, input_tokens "
            "FROM assistant_exchange WHERE tenant_id = :t"
        )
        views = {
            row.view_id: row.owner_id
            for row in rows("SELECT view_id, owner_id FROM saved_view WHERE tenant_id = :t")
        }
        schedules = {
            row.schedule_id: row
            for row in rows(
                "SELECT schedule_id, owner_id, recipients, enabled FROM report_schedule "
                "WHERE tenant_id = :t"
            )
        }
        mentions = sum(
            connection.execute(text(sql), {"t": tenant_id, "w": who}).scalar_one()
            for sql in (
                "SELECT count(*) FROM assistant_exchange "
                "WHERE tenant_id = :t AND principal_id = :w",
                "SELECT count(*) FROM redaction_event WHERE tenant_id = :t AND principal_id = :w",
                "SELECT count(*) FROM report_run WHERE tenant_id = :t AND principal_id = :w",
                "SELECT count(*) FROM saved_view WHERE tenant_id = :t AND owner_id = :w",
                "SELECT count(*) FROM report_schedule WHERE tenant_id = :t "
                "AND (owner_id = :w OR :w = ANY(recipients))",
            )
        )

    assert (
        report.exchanges_tombstoned,
        report.redactions_tombstoned,
        report.exports_tombstoned,
        report.private_views_removed,
        report.shared_views_unowned,
        report.schedules_paused,
        report.recipient_lists_changed,
    ) == (2, 1, 1, 1, 1, 1, 3)
    assert mentions == 0, "nothing names the person"
    assert len(exchanges) == 2, "kept, so the month's token spend stays true"
    assert sum(row.input_tokens for row in exchanges) == 2 * 812
    assert not any("Priya" in str(value) for row in exchanges for value in row)
    assert private not in views and shared in views
    assert (schedules[theirs].enabled, list(schedules[theirs].recipients)) == (False, [other])
    assert (schedules[only_them].enabled, list(schedules[only_them].recipients)) == (False, [other])
    assert (schedules[among].enabled, list(schedules[among].recipients)) == (True, [other])


def test_a_question_past_ninety_days_goes_with_its_redactions_and_a_newer_one_stays(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """OPEN-14, 90 days, ISS-226."""
    assert settings.retention_assistant_days == 90
    with engine.begin() as connection:
        old = an_exchange(
            connection,
            tenant_id,
            asked=AT - timedelta(days=91),
            answered=AT - timedelta(days=91),
        )
        recent = an_exchange(
            connection,
            tenant_id,
            asked=AT - timedelta(days=89),
            answered=AT - timedelta(days=89),
        )
        a_redaction(connection, tenant_id, old, "principal-a", AT - timedelta(days=91))
        outcome = retention_assistant(context(connection, tenant_id, settings), clock=at)
        kept = set(
            connection.execute(
                text("SELECT exchange_id FROM assistant_exchange WHERE tenant_id = :t"),
                {"t": tenant_id},
            ).scalars()
        )
        redactions = connection.execute(
            text("SELECT count(*) FROM redaction_event WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar_one()

    assert kept == {recent}
    assert redactions == 0
    assert outcome.items_written == 2


# --- the script as an operator runs it -------------------------------------------------------


def run_erasure(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tenant: UUID,
    principal: UUID,
    *extra: str,
) -> int:
    url = engine.url.render_as_string(hide_password=False)
    monkeypatch.setenv("METER_DATABASE_URL", url)
    status: int = erase_principal.main(
        [
            "--tenant",
            str(tenant),
            "--principal",
            str(principal),
            "--requested-by",
            "operator-1",
            "--request-id",
            "ticket-11",
            *extra,
        ]
    )
    return status


def display_name(engine: Engine, principal: UUID) -> str:
    with engine.connect() as connection:
        found: str = connection.execute(
            text("SELECT display_name FROM principal WHERE principal_id = :p"), {"p": principal}
        ).scalar_one()
    return found


def test_without_a_database_url_the_script_refuses(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("METER_DATABASE_URL", raising=False)
    status = erase_principal.main(
        [
            "--tenant",
            str(uuid4()),
            "--principal",
            str(uuid4()),
            "--requested-by",
            "o",
            "--request-id",
            "t",
        ]
    )
    assert status == 2
    assert "METER_DATABASE_URL is not set" in capsys.readouterr().err


def test_a_dry_run_reports_every_table_and_changes_nothing(
    engine: Engine,
    tenant_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with engine.begin() as connection:
        principal = insert_principal(connection, tenant_id, AT)
    assert run_erasure(engine, monkeypatch, tenant_id, principal) == 0
    shown = capsys.readouterr().out
    assert "assistant questions tombstoned" in shown and "recipient lists changed" in shown
    assert "dry run, rolled back" in shown
    assert display_name(engine, principal) == "A Person"


def test_with_commit_the_erasure_is_applied(
    engine: Engine, tenant_id: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    with engine.begin() as connection:
        principal = insert_principal(connection, tenant_id, AT)
    assert run_erasure(engine, monkeypatch, tenant_id, principal, "--commit") == 0
    assert display_name(engine, principal) == TOMBSTONE


def test_a_person_the_tenant_does_not_have_is_said_so_and_nothing_is_kept(
    engine: Engine,
    tenant_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run_erasure(engine, monkeypatch, tenant_id, uuid4(), "--commit") == 3
    assert "no principal" in capsys.readouterr().err
