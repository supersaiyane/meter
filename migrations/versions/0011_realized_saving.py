"""What actually appeared in the bill.

Revision ID: 0011_realized_saving
Revises: 0010_recommendations
Create Date: 2026-09-21

FEAT-029, TASK-P3-013. The north star metric, and the table exists apart from
`recommendation` for one reason: an estimate is modelled and a realization is
measured, and every tool that inflates identified savings does it by adding the two
together. Two tables make that addition something somebody has to write on purpose
rather than something a careless join produces.

**Four money columns and two usage columns.** The usage pair is the control. A
resource that cost 100 before and 60 after did not necessarily save 40; it may have
been used less. The honest counterfactual is unobservable, so the claim is exactly
what the columns hold: cost moved this much, usage moved this much.

**Three verdicts, not two.** `INCONCLUSIVE` is where usage fell by more than cost
did, and the saving cannot be told apart from a workload that shrank on its own. It
is expected to be common, and the inconclusive rows are the evidence that this
metric is not the vanity number ISS-029 warns about.
"""

from __future__ import annotations

from alembic import op

revision = "0011_realized_saving"
down_revision = "0010_recommendations"
branch_labels = None
depends_on = None

STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE realized_saving (
        realized_id         UUID PRIMARY KEY,
        recommendation_id   UUID            NOT NULL
                            REFERENCES recommendation (recommendation_id) ON DELETE CASCADE,
        tenant_id           UUID            NOT NULL REFERENCES tenant (tenant_id),
        window_before_start DATE            NOT NULL,
        window_before_end   DATE            NOT NULL,
        window_after_start  DATE            NOT NULL,
        window_after_end    DATE            NOT NULL,
        cost_before         NUMERIC(20, 10) NOT NULL,
        cost_after          NUMERIC(20, 10) NOT NULL,
        usage_before        NUMERIC(20, 10) NOT NULL,
        usage_after         NUMERIC(20, 10) NOT NULL,
        verdict             TEXT            NOT NULL,
        why                 TEXT            NOT NULL,
        as_of               TIMESTAMPTZ     NOT NULL,
        collected_at        TIMESTAMPTZ     NOT NULL
    )
    """,
    # One verdict per recommendation. A second would be a second claim about the
    # same change, and a screen summing them would double the saving.
    """
    ALTER TABLE realized_saving
        ADD CONSTRAINT uq_realized_saving__recommendation
        UNIQUE (recommendation_id)
    """,
    """
    ALTER TABLE realized_saving
        ADD CONSTRAINT ck_realized_saving__verdict
        CHECK (verdict IN ('VERIFIED', 'REGRESSED', 'INCONCLUSIVE'))
    """,
    # Windows end after they start, and the after window starts no earlier than the
    # before window ends. A pair that overlapped would compare a period with itself.
    """
    ALTER TABLE realized_saving
        ADD CONSTRAINT ck_realized_saving__windows_ordered
        CHECK (
            window_before_end > window_before_start
            AND window_after_end > window_after_start
            AND window_after_start >= window_before_end
        )
    """,
    # Cost and usage are never negative. A negative here is a parse failure that
    # reached the database, and it would subtract from a total reported upward.
    """
    ALTER TABLE realized_saving
        ADD CONSTRAINT ck_realized_saving__money_not_negative
        CHECK (
            cost_before >= 0 AND cost_after >= 0
            AND usage_before >= 0 AND usage_after >= 0
        )
    """,
    # The working is not optional, for the same reason it is not optional on a
    # recommendation: a verdict nobody can argue with is one nobody believes twice.
    """
    ALTER TABLE realized_saving
        ADD CONSTRAINT ck_realized_saving__has_working
        CHECK (length(why) > 0)
    """,
    """
    CREATE INDEX ix_realized_saving__window
        ON realized_saving (tenant_id, window_after_end DESC)
    """,
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS realized_saving")
