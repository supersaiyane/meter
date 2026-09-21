"""A score stored with its parts, because a total on its own explains nothing.

Revision ID: 0013_finops_score
Revises: 0012_realized_usage_unobserved
Create Date: 2026-09-21

FEAT-043, TASK-P3-016. Two tables rather than one, and the second is the feature.

FEAT-043 was adopted over an objection, and the objection became the ship condition:
a composite number nobody can decompose tells a reader nothing about what to do. A
schema storing only `total` would satisfy the screen on its first day and make the
condition unmeetable forever, because the components of last week's score cannot be
recomputed once the findings have changed.

So each run stores its components, and each component stores the findings that
produced it. That is what makes a difference between two runs explainable as a list
of findings that opened or closed rather than as two numbers a reader has to take on
trust.

**`points` is nullable, and the null is not a zero.** A component that could not be
computed is excluded from the score's denominator, which is why `available_weight`
is a stored column rather than a derived one: a reader looking at an old row has to
be able to tell a score out of sixty from a score out of a hundred.

**A row is about an account or a team, never both and never neither.** The
biconditional is a constraint because the two kinds of score are read by different
people and a row belonging to neither would appear on both screens or on nobody's.
"""

from __future__ import annotations

from alembic import op

revision = "0013_finops_score"
down_revision = "0012_realized_usage_unobserved"
branch_labels = None
depends_on = None

STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE finops_score (
        score_id         UUID PRIMARY KEY,
        tenant_id        UUID        NOT NULL REFERENCES tenant (tenant_id),
        sub_account_id   TEXT,
        team             TEXT,
        total            INTEGER     NOT NULL,
        available_weight INTEGER     NOT NULL,
        why              TEXT        NOT NULL,
        as_of            TIMESTAMPTZ NOT NULL,
        collected_at     TIMESTAMPTZ NOT NULL
    )
    """,
    # An account score or a team score, never both. A row belonging to neither would
    # appear on both screens or on nobody's, and nobody would notice which.
    """
    ALTER TABLE finops_score
        ADD CONSTRAINT ck_finops_score__account_xor_team
        CHECK ((sub_account_id IS NOT NULL) <> (team IS NOT NULL))
    """,
    """
    ALTER TABLE finops_score
        ADD CONSTRAINT ck_finops_score__total_in_range
        CHECK (total >= 0 AND total <= 100)
    """,
    # A score computed from no available weight cannot exist, because the query
    # returns no score at all in that case. A row with zero here would be a hundred
    # out of nothing, which is the output FEAT-043's failure behaviour forbids.
    """
    ALTER TABLE finops_score
        ADD CONSTRAINT ck_finops_score__weight_in_range
        CHECK (available_weight > 0 AND available_weight <= 100)
    """,
    """
    ALTER TABLE finops_score
        ADD CONSTRAINT ck_finops_score__has_working
        CHECK (length(why) > 0)
    """,
    # One score per subject per run. Coalesced because a unique constraint treats
    # nulls as distinct, so without this two rows for the same team at the same
    # instant would both be accepted and the history would double.
    """
    CREATE UNIQUE INDEX uq_finops_score__subject_at
        ON finops_score (tenant_id, COALESCE(sub_account_id, ''), COALESCE(team, ''), as_of)
    """,
    # The read is newest first per subject, for the trend on the screen.
    """
    CREATE INDEX ix_finops_score__history
        ON finops_score (tenant_id, as_of DESC)
    """,
    """
    CREATE TABLE finops_score_component (
        component_id UUID PRIMARY KEY,
        score_id     UUID        NOT NULL
                     REFERENCES finops_score (score_id) ON DELETE CASCADE,
        tenant_id    UUID        NOT NULL REFERENCES tenant (tenant_id),
        name         TEXT        NOT NULL,
        points       NUMERIC(6, 3),
        weight       INTEGER     NOT NULL,
        why          TEXT        NOT NULL,
        finding_ids  UUID[]      NOT NULL DEFAULT '{}',
        as_of        TIMESTAMPTZ NOT NULL,
        collected_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    ALTER TABLE finops_score_component
        ADD CONSTRAINT ck_finops_score_component__name_known
        CHECK (name IN ('waste', 'coverage', 'responsiveness', 'verification'))
    """,
    # Points never exceed the weight, and are never negative. Either would let one
    # dimension carry a score somewhere the weights say it cannot go, and a total
    # above a hundred or below nought is a number no reader would believe twice.
    """
    ALTER TABLE finops_score_component
        ADD CONSTRAINT ck_finops_score_component__points_within_weight
        CHECK (points IS NULL OR (points >= 0 AND points <= weight))
    """,
    """
    ALTER TABLE finops_score_component
        ADD CONSTRAINT ck_finops_score_component__weight_positive
        CHECK (weight > 0)
    """,
    # The working is not optional here either. A component that moved a score and
    # cannot say why is the decomposition failing at the only level that matters.
    """
    ALTER TABLE finops_score_component
        ADD CONSTRAINT ck_finops_score_component__has_working
        CHECK (length(why) > 0)
    """,
    """
    ALTER TABLE finops_score_component
        ADD CONSTRAINT uq_finops_score_component__name
        UNIQUE (score_id, name)
    """,
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS finops_score_component")
    op.execute("DROP TABLE IF EXISTS finops_score")
