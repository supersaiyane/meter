"""What was committed, what it consumed, and what it covered.

Revision ID: 0009_commitment_coverage
Revises: 0008_cost_anomaly
Create Date: 2026-09-20

FEAT-024, TASK-P1-016. Two tables, written by
`finops_ingest/collectors/commitment.py` from the `CommitmentReport` port.

**Two tables rather than one, and not for tidiness.** The plan for this task put
utilization and coverage on the same row. That row would have carried a number
nobody measured: a provider reports utilization per commitment and coverage per
service or region, because a dollar of covered spend cannot be attributed to one
of three overlapping plans. A `covered_spend` column on `commitment_use` would
have been an invention, and summing it across commitments would have counted the
same eligible dollar once per plan.

Money columns, never percentages. A schema that stored the two ratios would have
thrown away the numbers a reader needs to disagree with them, and would have made
the two collapsible into one, which is the mistake these tables exist to prevent:
a fully utilized commitment covering a tenth of the estate is a buy signal, and a
half utilized one covering everything is a sizing mistake.

`wasted` is stored and constrained rather than computed on read, so a screen, a
file and a report cannot disagree about it. The constraint is what makes that
safe: application code is not the only thing keeping the three numbers
consistent, per constraint 11.
"""

from __future__ import annotations

from alembic import op

revision = "0009_commitment_coverage"
down_revision = "0008_cost_anomaly"
branch_labels = None
depends_on = None

STATEMENTS: tuple[str, ...] = (
    # Utilization, per commitment.
    """
    CREATE TABLE commitment_use (
        use_id          UUID PRIMARY KEY,
        tenant_id       UUID            NOT NULL REFERENCES tenant (tenant_id),
        ingest_run_id   UUID            NOT NULL,
        commitment_id   TEXT            NOT NULL,
        commitment_type TEXT            NOT NULL,
        status          TEXT            NOT NULL,
        term_start      DATE            NOT NULL,
        term_end        DATE            NOT NULL,
        window_start    DATE            NOT NULL,
        window_end      DATE            NOT NULL,
        committed       NUMERIC(20, 10) NOT NULL,
        used            NUMERIC(20, 10) NOT NULL,
        wasted          NUMERIC(20, 10) NOT NULL,
        as_of           TIMESTAMPTZ     NOT NULL,
        collected_at    TIMESTAMPTZ     NOT NULL
    )
    """,
    # One row per commitment per window. Re running the collector over a window it
    # has already reported replaces that row rather than adding a second, which is
    # what stops a screen summing the same wasted dollar twice.
    """
    ALTER TABLE commitment_use
        ADD CONSTRAINT uq_commitment_use__window
        UNIQUE (tenant_id, commitment_id, window_start)
    """,
    # The three money columns have to agree. A row whose subtraction is wrong is a
    # row somebody will try to reconcile against an invoice.
    """
    ALTER TABLE commitment_use
        ADD CONSTRAINT ck_commitment_use__wasted_is_the_difference
        CHECK (wasted = committed - used)
    """,
    # Nothing here is ever negative. A negative commitment is a parse failure that
    # reached the database.
    """
    ALTER TABLE commitment_use
        ADD CONSTRAINT ck_commitment_use__money_is_not_negative
        CHECK (committed >= 0 AND used >= 0)
    """,
    # Exclusive ends, like every other period in this schema.
    """
    ALTER TABLE commitment_use
        ADD CONSTRAINT ck_commitment_use__term_ends_after_it_starts
        CHECK (term_end > term_start)
    """,
    """
    ALTER TABLE commitment_use
        ADD CONSTRAINT ck_commitment_use__window_ends_after_it_starts
        CHECK (window_end > window_start)
    """,
    # Three states, and expired is one of them. A commitment whose term has ended
    # keeps its row, because the coverage gap the expiry leaves is the finding.
    """
    ALTER TABLE commitment_use
        ADD CONSTRAINT ck_commitment_use__status
        CHECK (status IN ('QUEUED', 'ACTIVE', 'EXPIRED'))
    """,
    # The read is worst waste first, within a window.
    """
    CREATE INDEX ix_commitment_use__wasted
        ON commitment_use (tenant_id, window_start DESC, wasted DESC)
    """,
    # Coverage, per dimension. Deliberately not keyed by commitment: see the module
    # docstring and `CommitmentCoverage`.
    """
    CREATE TABLE commitment_coverage (
        coverage_id     UUID PRIMARY KEY,
        tenant_id       UUID            NOT NULL REFERENCES tenant (tenant_id),
        ingest_run_id   UUID            NOT NULL,
        commitment_type TEXT            NOT NULL,
        dimension       TEXT            NOT NULL,
        dimension_value TEXT            NOT NULL,
        window_start    DATE            NOT NULL,
        window_end      DATE            NOT NULL,
        eligible_spend  NUMERIC(20, 10) NOT NULL,
        covered_spend   NUMERIC(20, 10) NOT NULL,
        as_of           TIMESTAMPTZ     NOT NULL,
        collected_at    TIMESTAMPTZ     NOT NULL
    )
    """,
    """
    ALTER TABLE commitment_coverage
        ADD CONSTRAINT uq_commitment_coverage__slice
        UNIQUE (tenant_id, commitment_type, dimension, dimension_value, window_start)
    """,
    # A commitment cannot cover more than was eligible for it. Coverage above one
    # renders as more than a hundred percent, which a reader reads as a bug in the
    # screen rather than in the data, and they are right.
    """
    ALTER TABLE commitment_coverage
        ADD CONSTRAINT ck_commitment_coverage__covered_within_eligible
        CHECK (covered_spend <= eligible_spend)
    """,
    """
    ALTER TABLE commitment_coverage
        ADD CONSTRAINT ck_commitment_coverage__money_is_not_negative
        CHECK (eligible_spend >= 0 AND covered_spend >= 0)
    """,
    """
    ALTER TABLE commitment_coverage
        ADD CONSTRAINT ck_commitment_coverage__window_ends_after_it_starts
        CHECK (window_end > window_start)
    """,
    # Two dimensions today. A third would be a migration, which is the point: a
    # free text dimension is one a screen cannot label.
    """
    ALTER TABLE commitment_coverage
        ADD CONSTRAINT ck_commitment_coverage__dimension
        CHECK (dimension IN ('SERVICE', 'REGION'))
    """,
    # The read is least covered first, within a window.
    """
    CREATE INDEX ix_commitment_coverage__window
        ON commitment_coverage (tenant_id, window_start DESC, dimension, dimension_value)
    """,
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS commitment_coverage")
    op.execute("DROP TABLE IF EXISTS commitment_use")
