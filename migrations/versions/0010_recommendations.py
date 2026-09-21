"""One thing worth changing, whatever found it.

Revision ID: 0010_recommendations
Revises: 0009_commitment_coverage
Create Date: 2026-09-21

FEAT-025 and FEAT-028, TASK-P3-003.

**One table, not one per source.** Compute Optimizer, Cost Optimization Hub,
Trusted Advisor and our own collectors all write here, distinguished by a `source`
column. A lifecycle that works for a Compute Optimizer recommendation and not for
an unattached volume is two lifecycles, and the second is the one nobody maintains.

**Severity and confidence are separate columns and neither is derived from the
other.** Severity comes from the money, per ADR-0016. Confidence comes from
`observation_days`. A ten thousand dollar finding resting on three weeks of data is
CRITICAL and LOW, and a schema storing one blended score could not say so.

**`recommendation_event` is append only.** The `lifecycle` column says where a
recommendation is; it cannot say that somebody accepted it in March, nothing
happened, and it was quietly dismissed in June. ISS-028 says recommendations
without a workflow are ignored every time, and the event log is the only way to
watch that happening.
"""

from __future__ import annotations

from alembic import op

revision = "0010_recommendations"
down_revision = "0009_commitment_coverage"
branch_labels = None
depends_on = None

STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE recommendation (
        recommendation_id        UUID PRIMARY KEY,
        tenant_id                UUID            NOT NULL REFERENCES tenant (tenant_id),
        sub_account_id           TEXT            NOT NULL,
        source                   TEXT            NOT NULL,
        source_reference         TEXT            NOT NULL,
        waste_class              TEXT            NOT NULL,
        resource_id              TEXT            NOT NULL,
        region_id                TEXT            NOT NULL,
        estimated_monthly_saving NUMERIC(20, 10) NOT NULL,
        confidence               TEXT            NOT NULL,
        severity                 TEXT            NOT NULL,
        observation_days         INTEGER         NOT NULL,
        lifecycle                TEXT            NOT NULL,
        owner                    TEXT,
        ticket_reference         TEXT,
        rationale                TEXT            NOT NULL,
        as_of                    TIMESTAMPTZ     NOT NULL,
        collected_at             TIMESTAMPTZ     NOT NULL
    )
    """,
    # One row per finding per source. A re read of an unchanged estate updates
    # rather than duplicating, which is what stops a screen showing the same
    # oversized instance once per collection.
    """
    ALTER TABLE recommendation
        ADD CONSTRAINT uq_recommendation__source
        UNIQUE (tenant_id, source, source_reference)
    """,
    # The floor, in the database as well as in the entity. Below fourteen days a
    # new instance looks exactly like an idle one, and the row should not exist at
    # all rather than existing with a low confidence.
    """
    ALTER TABLE recommendation
        ADD CONSTRAINT ck_recommendation__observation_floor
        CHECK (observation_days >= 14)
    """,
    # A saving is never negative. A cost increase is not a recommendation, and a
    # negative here would subtract from a total somebody reports upward.
    """
    ALTER TABLE recommendation
        ADD CONSTRAINT ck_recommendation__saving_not_negative
        CHECK (estimated_monthly_saving >= 0)
    """,
    """
    ALTER TABLE recommendation
        ADD CONSTRAINT ck_recommendation__source_known
        CHECK (source IN (
            'COMPUTE_OPTIMIZER', 'COST_OPTIMIZATION_HUB', 'TRUSTED_ADVISOR', 'METER'
        ))
    """,
    """
    ALTER TABLE recommendation
        ADD CONSTRAINT ck_recommendation__confidence_known
        CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW'))
    """,
    """
    ALTER TABLE recommendation
        ADD CONSTRAINT ck_recommendation__severity_known
        CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW'))
    """,
    """
    ALTER TABLE recommendation
        ADD CONSTRAINT ck_recommendation__lifecycle_known
        CHECK (lifecycle IN (
            'OPEN', 'ACCEPTED', 'IN_PROGRESS', 'DONE', 'VERIFIED', 'REGRESSED', 'DISMISSED'
        ))
    """,
    # The working is not optional. A recommendation a reader cannot argue with is
    # one they take on trust, and nobody takes a cost recommendation on trust twice.
    """
    ALTER TABLE recommendation
        ADD CONSTRAINT ck_recommendation__has_working
        CHECK (length(rationale) > 0)
    """,
    # The read is worst money first, within a tenant.
    """
    CREATE INDEX ix_recommendation__saving
        ON recommendation (tenant_id, estimated_monthly_saving DESC)
    """,
    # And by lifecycle, because every screen filters on it.
    """
    CREATE INDEX ix_recommendation__lifecycle
        ON recommendation (tenant_id, lifecycle)
    """,
    """
    CREATE TABLE recommendation_event (
        event_id          UUID PRIMARY KEY,
        recommendation_id UUID        NOT NULL
                          REFERENCES recommendation (recommendation_id) ON DELETE CASCADE,
        tenant_id         UUID        NOT NULL REFERENCES tenant (tenant_id),
        from_lifecycle    TEXT,
        to_lifecycle      TEXT        NOT NULL,
        actor             TEXT        NOT NULL,
        reason            TEXT,
        occurred_at       TIMESTAMPTZ NOT NULL,
        as_of             TIMESTAMPTZ NOT NULL,
        collected_at      TIMESTAMPTZ NOT NULL
    )
    """,
    # `from_lifecycle` is null exactly once per recommendation: the row recording
    # that it was found. Every later transition names where it came from, so the
    # log can be replayed rather than merely listed.
    """
    ALTER TABLE recommendation_event
        ADD CONSTRAINT ck_recommendation_event__first_has_no_from
        CHECK ((from_lifecycle IS NULL) = (to_lifecycle = 'OPEN'))
    """,
    # A dismissal without a reason is a dismissal nobody can review. The one
    # transition where the reason is the entire point.
    """
    ALTER TABLE recommendation_event
        ADD CONSTRAINT ck_recommendation_event__dismissal_has_a_reason
        CHECK (to_lifecycle <> 'DISMISSED' OR (reason IS NOT NULL AND length(reason) > 0))
    """,
    """
    CREATE INDEX ix_recommendation_event__recommendation
        ON recommendation_event (recommendation_id, occurred_at)
    """,
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recommendation_event")
    op.execute("DROP TABLE IF EXISTS recommendation")
