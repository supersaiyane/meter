"""One row per kind of commitment per day: committed, used, eligible and covered.

Revision ID: 0027_commitment_day
Revises: 0026_report_run
Create Date: 2026-10-06

TASK-P8-013. The owner chose on 2026-10-06 to collect commitments daily, so utilization and
coverage over time, and the day by day heatmap on the Commitments screen, are drawn from
measured days rather than from successive month windows. Cost Explorer reports daily Savings
Plans use only as one total across every plan, so the grain is a kind of commitment and a
day, never one commitment.

**Every invariant is a constraint.** A day is said once per kind, its money is never
negative, it uses no more than was committed and covers no more than was eligible, and it
was collected after it was true. Application code that forgets any of them is refused by the
database rather than trusted.

Backward compatible, constraint 12: a new table no earlier release reads or writes, and the
downgrade drops it.
"""

from __future__ import annotations

from alembic import op

revision = "0027_commitment_day"
down_revision = "0026_report_run"
branch_labels = None
depends_on = None


_UP = (
    """
    CREATE TABLE IF NOT EXISTS commitment_day (
        day_id          UUID            PRIMARY KEY,
        tenant_id       UUID            NOT NULL REFERENCES tenant (tenant_id),
        ingest_run_id   UUID            NOT NULL,
        commitment_type TEXT            NOT NULL,
        day             DATE            NOT NULL,
        committed       NUMERIC(20, 10) NOT NULL,
        used            NUMERIC(20, 10) NOT NULL,
        eligible_spend  NUMERIC(20, 10) NOT NULL,
        covered_spend   NUMERIC(20, 10) NOT NULL,
        as_of           TIMESTAMPTZ     NOT NULL,
        collected_at    TIMESTAMPTZ     NOT NULL
    )
    """,
    # One row per kind per day. Each run rereads the last month of days and replaces them,
    # which is how a day a late bill changed is corrected rather than counted twice.
    """
    ALTER TABLE commitment_day DROP CONSTRAINT IF EXISTS uq_commitment_day__kind_day
    """,
    """
    ALTER TABLE commitment_day
        ADD CONSTRAINT uq_commitment_day__kind_day UNIQUE (tenant_id, commitment_type, day)
    """,
    """
    ALTER TABLE commitment_day DROP CONSTRAINT IF EXISTS ck_commitment_day__money_is_not_negative
    """,
    """
    ALTER TABLE commitment_day
        ADD CONSTRAINT ck_commitment_day__money_is_not_negative
        CHECK (committed >= 0 AND used >= 0 AND eligible_spend >= 0 AND covered_spend >= 0)
    """,
    # Utilization above one and coverage above one both render as more than a hundred
    # percent, which a reader takes for a bug in the screen, and they would be right.
    """
    ALTER TABLE commitment_day DROP CONSTRAINT IF EXISTS ck_commitment_day__used_within_committed
    """,
    """
    ALTER TABLE commitment_day
        ADD CONSTRAINT ck_commitment_day__used_within_committed CHECK (used <= committed)
    """,
    """
    ALTER TABLE commitment_day
        DROP CONSTRAINT IF EXISTS ck_commitment_day__covered_within_eligible
    """,
    """
    ALTER TABLE commitment_day
        ADD CONSTRAINT ck_commitment_day__covered_within_eligible
        CHECK (covered_spend <= eligible_spend)
    """,
    # Constraint 10. A day is true once it has ended and is fetched after that.
    """
    ALTER TABLE commitment_day DROP CONSTRAINT IF EXISTS ck_commitment_day__collected_after_as_of
    """,
    """
    ALTER TABLE commitment_day
        ADD CONSTRAINT ck_commitment_day__collected_after_as_of CHECK (collected_at >= as_of)
    """,
    # The read is the last month of days, both kinds, oldest first.
    """
    CREATE INDEX IF NOT EXISTS ix_commitment_day__day ON commitment_day (tenant_id, day)
    """,
)


_DOWN = ("DROP TABLE IF EXISTS commitment_day",)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
