"""The P5 invariants, watched refusing.

Constraint 11: if application code is the only thing preventing a bad row, the bad row
will eventually exist. A check constraint nobody has watched refuse anything is in the
same position as the code it was meant to back up, because a constraint with a typo in
it accepts everything and looks exactly like one that works.

The case this file exists for is the biconditional. A usage figure with no source is the
row that cannot be audited a year later and that renders identically to a measured one,
and a source with no figure is the row that puts a quota in the measurable list with
nothing to show. `finops_core.domain.quota` refuses both, and this is the other door:
a write that never went through the domain at all.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)
FETCHED = datetime(2026, 9, 28, 6, 5, tzinfo=UTC)
ACCOUNT = "111122223333"
REGION = "eu-west-1"
REASON = "AWS publishes no usage metric for this quota"

INSERT_RUN = text(
    "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, idempotency_key, "
    "status, as_of_window_start, as_of_window_end) "
    "VALUES (:run, :t, 'quotas', :scope, :key, 'SUCCEEDED', :at, :at)"
)

INSERT_QUOTA = text(
    "INSERT INTO quota_usage (quota_pk, tenant_id, ingest_run_id, sub_account_id, "
    "region_id, service_code, quota_code, quota_name, limit_value, used_value, "
    "usage_source, unmeasurable_reason, is_adjustable, as_of, collected_at) "
    "VALUES (:pk, :t, :run, :account, :region, :service, :quota, :name, :limit, :used, "
    ":source, :reason, :adjustable, :as_of, :collected)"
)

INSERT_REQUEST = text(
    "INSERT INTO quota_request (request_pk, tenant_id, ingest_run_id, request_id, "
    "sub_account_id, region_id, service_code, quota_code, quota_name, desired_value, status, "
    "requested_at, last_updated_at, submitted_by_meter, as_of, collected_at) "
    "VALUES (:pk, :t, :run, :request, :account, :region, :service, :quota, :name, :desired, "
    ":status, :requested, :updated, :submitted, :as_of, :collected)"
)

INSERT_HISTORY = text(
    "INSERT INTO quota_request_history (history_pk, tenant_id, request_id, status, "
    "changed_at) VALUES (:pk, :t, :request, :status, :changed)"
)


def a_run(connection: Connection, tenant: UUID) -> UUID:
    run = uuid4()
    connection.execute(
        INSERT_RUN,
        {"run": run, "t": tenant, "scope": f"acct:{ACCOUNT}", "key": str(run), "at": NOW},
    )
    return run


def a_quota(connection: Connection, tenant: UUID, run: UUID, **overrides: object) -> None:
    """One measurable quota at 40 of 100, with any field overridden.

    Written as a valid row plus overrides rather than a literal per case, so a case that
    refuses proves the override was the reason and not a typo somewhere else in the row.
    """
    values: dict[str, object] = {
        "pk": uuid4(),
        "t": tenant,
        "run": run,
        "account": ACCOUNT,
        "region": REGION,
        "service": "ec2",
        "quota": f"L-{uuid4().hex[:8]}",
        "name": "Running On-Demand Standard instances",
        "limit": 100,
        "used": 40,
        "source": "AWS_USAGE_METRIC",
        "reason": None,
        "adjustable": True,
        "as_of": NOW,
        "collected": FETCHED,
    }
    values.update(overrides)
    connection.execute(INSERT_QUOTA, values)


def a_request(connection: Connection, tenant: UUID, run: UUID, **overrides: object) -> None:
    values: dict[str, object] = {
        "pk": uuid4(),
        "t": tenant,
        "run": run,
        "request": f"request-{uuid4().hex[:8]}",
        "account": ACCOUNT,
        "region": REGION,
        "service": "ec2",
        "quota": "L-1216C47A",
        "name": "Running On-Demand Standard instances",
        "desired": 500,
        "status": "PENDING",
        "requested": NOW - timedelta(days=3),
        "updated": NOW,
        "submitted": False,
        "as_of": NOW,
        "collected": FETCHED,
    }
    values.update(overrides)
    connection.execute(INSERT_REQUEST, values)


# --- the biconditional, both directions --------------------------------------


def test_a_usage_figure_with_no_source_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """The row that cannot be audited later and renders as though it were measured."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        with pytest.raises(IntegrityError, match="ck_quota_usage__source_iff_usage"):
            a_quota(connection, tenant_id, run, used=40, source="NONE", reason=REASON)


def test_a_source_with_no_usage_figure_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """The row that joins the measurable list with nothing to show."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        with pytest.raises(IntegrityError, match="ck_quota_usage__source_iff_usage"):
            a_quota(connection, tenant_id, run, used=None, source="TRUSTED_ADVISOR")


def test_an_unmeasurable_quota_is_accepted(engine: Engine, tenant_id: UUID) -> None:
    """The majority case in a real estate, so it must not be caught by the checks above."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        a_quota(connection, tenant_id, run, used=None, source="NONE", reason=REASON)


def test_an_unmeasurable_quota_may_still_have_no_limit(engine: Engine, tenant_id: UUID) -> None:
    """Both absences at once, which is a quota AWS publishes neither figure for."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        a_quota(connection, tenant_id, run, limit=None, used=None, source="NONE", reason=REASON)


# --- the source vocabulary ---------------------------------------------------


def test_a_source_outside_the_four_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """A fifth source is a migration, not a string somebody passed."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        with pytest.raises(IntegrityError, match="ck_quota_usage__usage_source"):
            a_quota(connection, tenant_id, run, source="COMPUTE_OPTIMIZER")


# --- the ceiling -------------------------------------------------------------


def test_a_usage_above_the_limit_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """A quota is the ceiling, so this is a misread, and it renders as negative headroom."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        with pytest.raises(IntegrityError, match="ck_quota_usage__used_within_limit"):
            a_quota(connection, tenant_id, run, limit=100, used=101)


def test_a_usage_at_the_limit_is_accepted(engine: Engine, tenant_id: UUID) -> None:
    """A full quota is the finding, so the check above must not take it with it."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        a_quota(connection, tenant_id, run, limit=100, used=100)


def test_a_usage_above_an_absent_limit_is_accepted(engine: Engine, tenant_id: UUID) -> None:
    """Nothing is known about the ceiling, so nothing about the figure contradicts it."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        a_quota(connection, tenant_id, run, limit=None, used=5000)


def test_a_negative_limit_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """Zero means switched off here and is allowed. Below zero is a misread."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        with pytest.raises(IntegrityError, match="ck_quota_usage__limit_not_negative"):
            a_quota(connection, tenant_id, run, limit=-1, used=None, source="NONE", reason=REASON)


def test_a_limit_of_zero_is_accepted(engine: Engine, tenant_id: UUID) -> None:
    """A quota set to nothing exists and has to be visible, at zero rather than absent."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        a_quota(connection, tenant_id, run, limit=0, used=0)


# --- the reason ---------------------------------------------------------------


def test_an_unmeasurable_quota_with_no_reason_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """A blank reason teaches a reader the explanations are empty. TASK-P5-006."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        with pytest.raises(IntegrityError, match="ck_quota_usage__reason_iff_unmeasurable"):
            a_quota(connection, tenant_id, run, used=None, source="NONE", reason=None)


def test_an_unmeasurable_quota_with_a_blank_reason_is_refused(
    engine: Engine, tenant_id: UUID
) -> None:
    """Which is why the check is a length and not a NOT NULL."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        with pytest.raises(IntegrityError, match="ck_quota_usage__reason_iff_unmeasurable"):
            a_quota(connection, tenant_id, run, used=None, source="NONE", reason="   ")


def test_a_measured_quota_carrying_a_reason_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """The half that stops a stale sentence surviving the day a quota starts publishing."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        with pytest.raises(IntegrityError, match="ck_quota_usage__reason_iff_unmeasurable"):
            a_quota(connection, tenant_id, run, reason=REASON)


# --- identity, including the global quota ------------------------------------


def test_the_same_quota_twice_in_one_slice_is_refused(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        a_quota(connection, tenant_id, run, quota="L-1216C47A")
        with pytest.raises(IntegrityError, match="uq_quota_usage__identity"):
            a_quota(connection, tenant_id, run, quota="L-1216C47A")


def test_a_global_quota_cannot_be_inserted_twice(engine: Engine, tenant_id: UUID) -> None:
    """NULLS NOT DISTINCT, and the reason it is there.

    A global quota carries no region. Under PostgreSQL's default two NULLs never
    conflict, so every collection would add another copy and the screen would show one
    account level limit once per region and a total of five times the truth.
    """
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        a_quota(connection, tenant_id, run, region=None, quota="L-FE177D64")
        with pytest.raises(IntegrityError, match="uq_quota_usage__identity"):
            a_quota(connection, tenant_id, run, region=None, quota="L-FE177D64")


def test_the_same_quota_in_two_regions_is_two_rows(engine: Engine, tenant_id: UUID) -> None:
    """The regional case the clause above must not collapse."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        a_quota(connection, tenant_id, run, quota="L-1216C47A", region="eu-west-1")
        a_quota(connection, tenant_id, run, quota="L-1216C47A", region="eu-west-2")
        count = connection.execute(
            text("SELECT count(*) FROM quota_usage WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar_one()
    assert count == 2


# --- the refusal, in the schema ----------------------------------------------


def test_a_request_meter_claims_to_have_submitted_is_refused(
    engine: Engine, tenant_id: UUID
) -> None:
    """Spec section 6 and constraint 6, in the database rather than in a comment.

    Meter drafts a quota increase and never submits one. If that is ever reversed it will
    be reversed by a migration somebody has to write and defend, which is the point of
    putting a column here that can only hold one value.
    """
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        with pytest.raises(IntegrityError, match="ck_quota_request__meter_never_submits"):
            a_request(connection, tenant_id, run, submitted=True)


def test_a_status_outside_aws_own_vocabulary_is_refused(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        with pytest.raises(IntegrityError, match="ck_quota_request__status"):
            a_request(connection, tenant_id, run, status="REJECTED")


def test_a_denied_request_is_storable(engine: Engine, tenant_id: UUID) -> None:
    """The status a product is tempted to hide. TASK-P5-008 asks for it by name."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        a_request(connection, tenant_id, run, status="DENIED")


def test_a_request_updated_before_it_was_made_is_refused(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        with pytest.raises(IntegrityError, match="ck_quota_request__updated_after_requested"):
            a_request(connection, tenant_id, run, requested=NOW, updated=NOW - timedelta(days=1))


def test_a_request_for_nothing_is_refused(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        with pytest.raises(IntegrityError, match="ck_quota_request__desired_is_positive"):
            a_request(connection, tenant_id, run, desired=0)


def test_the_same_request_read_twice_is_one_row(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        a_request(connection, tenant_id, run, request="request-0001")
        with pytest.raises(IntegrityError, match="uq_quota_request__request_id"):
            a_request(connection, tenant_id, run, request="request-0001")


def test_a_status_cannot_be_recorded_twice_for_one_request(engine: Engine, tenant_id: UUID) -> None:
    """A request read twice must not appear to have been approved twice."""
    with engine.begin() as connection:
        values = {
            "pk": uuid4(),
            "t": tenant_id,
            "request": "request-0001",
            "status": "APPROVED",
            "changed": NOW,
        }
        connection.execute(INSERT_HISTORY, values)
        with pytest.raises(IntegrityError, match="uq_quota_request_history__status"):
            connection.execute(INSERT_HISTORY, {**values, "pk": uuid4()})


def test_the_whole_transition_sequence_is_storable(engine: Engine, tenant_id: UUID) -> None:
    """The point of the table: when it was approved, not only that it is."""
    with engine.begin() as connection:
        for days, status in ((8, "PENDING"), (6, "CASE_OPENED"), (0, "APPROVED")):
            connection.execute(
                INSERT_HISTORY,
                {
                    "pk": uuid4(),
                    "t": tenant_id,
                    "request": "request-0001",
                    "status": status,
                    "changed": NOW - timedelta(days=days),
                },
            )
        rows = connection.execute(
            text(
                "SELECT status FROM quota_request_history WHERE tenant_id = :t ORDER BY changed_at"
            ),
            {"t": tenant_id},
        ).scalars()
    assert list(rows) == ["PENDING", "CASE_OPENED", "APPROVED"]
