"""What the P2 tables refuse.

Every assertion here is about something the database rejects, not about
something the application remembers not to do. Constraint 11: if application
code is the only thing preventing a bad row, the bad row eventually exists, and
the three rules below are each the reason a feature is safe to turn on.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 30, 6, 0, tzinfo=UTC)


def add_instance(
    connection: Connection,
    tenant: UUID,
    *,
    kind: str = "AMG",
    account_id: str | None = "111122223333",
    region_id: str | None = "eu-west-2",
    reachable: bool = True,
    reason: str | None = None,
) -> UUID:
    instance_id = uuid4()
    connection.execute(
        text(
            "INSERT INTO grafana_instance (instance_id, tenant_id, kind, name, endpoint, "
            "account_id, region_id, reachable, unreachable_reason, as_of, collected_at) "
            "VALUES (:id, :tenant, :kind, 'ws', :endpoint, :account, :region, "
            ":reachable, :reason, :now, :now)"
        ),
        {
            "id": instance_id,
            "tenant": tenant,
            "kind": kind,
            "endpoint": f"{instance_id}.example",
            "account": account_id,
            "region": region_id,
            "reachable": reachable,
            "reason": reason,
            "now": NOW,
        },
    )
    return instance_id


def add_definition(
    connection: Connection,
    tenant: UUID,
    instance_id: UUID,
    *,
    origin: str = "PANEL",
    refresh: int | None = 60,
) -> UUID:
    query_id = uuid4()
    connection.execute(
        text(
            "INSERT INTO query_definition (query_id, tenant_id, instance_id, origin, engine, "
            "query_text, fingerprint, target, refresh_seconds, range_seconds, as_of, "
            "collected_at) VALUES (:id, :tenant, :instance, :origin, 'LOGS_INSIGHTS', "
            "'fields @timestamp', :fp, '{}'::jsonb, :refresh, 86400, :now, :now)"
        ),
        {
            "id": query_id,
            "tenant": tenant,
            "instance": instance_id,
            "origin": origin,
            "fp": str(query_id),
            "refresh": refresh,
            "now": NOW,
        },
    )
    return query_id


def add_enforcement(
    connection: Connection, tenant: UUID, level: str, expires_at: datetime | None
) -> None:
    connection.execute(
        text(
            "INSERT INTO enforcement_action (action_id, tenant_id, level, principal_arn, "
            "trigger_reason, observed_rate, threshold, expires_at) "
            "VALUES (:id, :tenant, :level, 'arn:aws:iam::role/r', 'over budget', 10, 5, :expires)"
        ),
        {"id": uuid4(), "tenant": tenant, "level": level, "expires": expires_at},
    )


# --- the deny that cannot become permanent -----------------------------------


def test_deny_requires_expiry(engine: Engine, tenant_id: UUID) -> None:
    """A DENY with no expiry cannot be written at all.

    ISS-092. A control that cuts an engineer off mid incident and never lifts is
    worse than the cost it prevented, and two paths write this table.
    """
    with engine.begin() as connection, pytest.raises(IntegrityError) as raised:
        add_enforcement(connection, tenant_id, "DENY", None)
    assert "ck_enforcement_action__restrictive_expires" in str(raised.value)


def test_throttle_requires_expiry_too(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection, pytest.raises(IntegrityError):
        add_enforcement(connection, tenant_id, "THROTTLE", None)


def test_an_alert_may_have_no_expiry(engine: Engine, tenant_id: UUID) -> None:
    # An alert takes nothing away, so it has nothing to expire. The constraint
    # must not be so broad that it forbids the harmless case.
    with engine.begin() as connection:
        add_enforcement(connection, tenant_id, "ALERT", None)


def test_a_restrictive_action_with_an_expiry_is_accepted(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        add_enforcement(connection, tenant_id, "DENY", NOW + timedelta(hours=1))


# --- a figure cannot claim a provenance it does not have ---------------------


def insert_finding(
    connection: Connection,
    tenant: UUID,
    query_id: UUID,
    provenance: str,
    measured_runs: int | None,
) -> None:
    connection.execute(
        text(
            "INSERT INTO query_finding (finding_id, tenant_id, query_id, run_date, "
            "runs_per_day, cost_month_usd, provenance, measured_runs, severity, why, "
            "as_of, collected_at) VALUES (:id, :tenant, :query, :day, 100, 12.5, "
            ":provenance, :measured, 'high', 'refreshes every 10 seconds', :now, :now)"
        ),
        {
            "id": uuid4(),
            "tenant": tenant,
            "query": query_id,
            "day": date(2026, 8, 30),
            "provenance": provenance,
            "measured": measured_runs,
            "now": NOW,
        },
    )


def test_modelled_cannot_claim_measured(engine: Engine, tenant_id: UUID) -> None:
    """Both directions of the provenance rule.

    A figure that says measured and measured nothing is the exact lie the
    provenance system exists to prevent, and the inverse hides that a
    measurement was taken.
    """
    with engine.begin() as connection:
        instance = add_instance(connection, tenant_id)
        query_id = add_definition(connection, tenant_id, instance)

    with engine.begin() as connection, pytest.raises(IntegrityError) as modelled_claiming:
        insert_finding(connection, tenant_id, query_id, "modelled", 42)
    assert "ck_query_finding__measured_has_runs" in str(modelled_claiming.value)

    with engine.begin() as connection, pytest.raises(IntegrityError) as measured_without:
        insert_finding(connection, tenant_id, query_id, "measured", None)
    assert "ck_query_finding__measured_has_runs" in str(measured_without.value)


def test_each_provenance_is_accepted_in_its_correct_form(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        instance = add_instance(connection, tenant_id)
        modelled = add_definition(connection, tenant_id, instance)
        measured = add_definition(connection, tenant_id, instance)
        insert_finding(connection, tenant_id, modelled, "modelled", None)
        insert_finding(connection, tenant_id, measured, "measured", 42)


# --- a change that cannot be undone --------------------------------------------


def test_remediation_requires_undo(engine: Engine, tenant_id: UUID) -> None:
    """`before` is the undo, and it is NOT NULL.

    TASK-P2-019 requires every rewrite to be reversible, and a change that
    cannot say what it replaced is a change nobody will dare apply.
    """
    with engine.begin() as connection:
        instance = add_instance(connection, tenant_id)

    with engine.begin() as connection, pytest.raises(IntegrityError) as raised:
        connection.execute(
            text(
                "INSERT INTO remediation_change (change_id, tenant_id, instance_id, "
                "kind, before, after, applied_by) VALUES (:id, :tenant, :instance, "
                "'PANEL_REWRITE', NULL, '{}'::jsonb, 'someone')"
            ),
            {"id": uuid4(), "tenant": tenant_id, "instance": instance},
        )
    assert "before" in str(raised.value)


# --- the rest of the vocabulary ------------------------------------------------


def test_an_amg_instance_must_carry_its_location(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection, pytest.raises(IntegrityError):
        add_instance(connection, tenant_id, kind="AMG", account_id=None, region_id=None)


def test_a_non_amg_instance_must_not_pretend_to_have_one(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection, pytest.raises(IntegrityError):
        add_instance(connection, tenant_id, kind="SELF_HOSTED")


def test_an_unreachable_instance_must_name_a_reason(engine: Engine, tenant_id: UUID) -> None:
    # The same invariant the domain enforces. An unexplained absence is what
    # makes an estate look smaller than it is.
    with engine.begin() as connection, pytest.raises(IntegrityError) as raised:
        add_instance(connection, tenant_id, reachable=False, reason=None)
    assert "ck_grafana_instance__unreachable_has_reason" in str(raised.value)


def test_a_panel_must_have_a_refresh_and_an_alert_need_not(engine: Engine, tenant_id: UUID) -> None:
    # An alert rule runs on its own schedule and must not borrow a dashboard's.
    with engine.begin() as connection:
        instance = add_instance(connection, tenant_id)
        add_definition(connection, tenant_id, instance, origin="ALERT_RULE", refresh=None)

    with engine.begin() as connection, pytest.raises(IntegrityError) as raised:
        add_definition(connection, tenant_id, instance, origin="PANEL", refresh=None)
    assert "ck_query_definition__panel_has_refresh" in str(raised.value)


def test_one_finding_per_query_per_day(engine: Engine, tenant_id: UUID) -> None:
    # Two findings for one query on one day means the collector ran twice and
    # the second run should update rather than double count.
    with engine.begin() as connection:
        instance = add_instance(connection, tenant_id)
        query_id = add_definition(connection, tenant_id, instance)
        insert_finding(connection, tenant_id, query_id, "modelled", None)

    with engine.begin() as connection, pytest.raises(IntegrityError) as raised:
        insert_finding(connection, tenant_id, query_id, "modelled", None)
    assert "uq_query_finding__query_day" in str(raised.value)
