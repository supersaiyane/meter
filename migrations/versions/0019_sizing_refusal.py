"""What Meter looked at and decided not to recommend.

Revision ID: 0019_sizing_refusal
Revises: 0018_misconfigured_cause
Create Date: 2026-09-28

FEAT-062, decided in ADR-0027. The argument that produced it is on FEAT-058: Meter has
no performance dimension and cannot honestly gain one, because it cannot verify a
performance finding and verification is its whole claim. What it can do is show that it
looked, which is what the complaint behind the gap was actually about.

**Its own table and not a row in `recommendation`.** A refusal has no saving. Writing it
into `recommendation` would put rows with a zero saving into a table whose every consumer
ranks by money, and ADR-0016 orders that list by exactly that figure, so a zero there
reads as the least valuable action rather than as the absence of one. That is the same
defect as rendering a collection failure as a number, wearing a different hat. The
reasoning is ADR-0025's: a finding inherits the shape of what it is.

**Nothing here is new arithmetic.** `finops_query/waste.py` already computes these, in
`_refused`, with the sentence written for a reader. The collector ended `_judge` with
`return smaller if smaller.is_worth_acting_on else None` and discarded them. This table is
where they go instead.

**The reason cannot be empty, and that is the load bearing constraint.** A refusal is only
as good as its sentence: one that said "did not qualify" would be worse than no feature at
all, because it would teach a reader that the explanations here are empty and they would
stop reading the ones that are not. Constraint 11, and the check is a length rather than a
NOT NULL because an empty string satisfies NOT NULL.
"""

from __future__ import annotations

from alembic import op

revision = "0019_sizing_refusal"
down_revision = "0018_misconfigured_cause"
branch_labels = None
depends_on = None

_UP = (
    """
    CREATE TABLE IF NOT EXISTS sizing_refusal (
        refusal_id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id UUID NOT NULL,
        sub_account_id TEXT NOT NULL,
        region_id TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        waste_class TEXT NOT NULL,
        reason TEXT NOT NULL,
        observation_days INTEGER NOT NULL,
        as_of TIMESTAMPTZ NOT NULL,
        collected_at TIMESTAMPTZ NOT NULL
    )
    """,
    # One row per resource per rule. A resource examined by the sizing rule and by the idle
    # rule was declined by each for its own reason, and collapsing them would lose the half a
    # reader came for.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_sizing_refusal__resource_and_rule
        ON sizing_refusal (tenant_id, resource_id, waste_class)
    """,
    # The sentence is the feature. A refusal with an empty one teaches a reader that the
    # explanations are empty, and they stop reading the ones that are not.
    """
    ALTER TABLE sizing_refusal
        ADD CONSTRAINT ck_sizing_refusal__reason_is_a_sentence
        CHECK (length(trim(reason)) >= 12)
    """,
    # A judgement made over no observation is not a judgement. The rules already refuse under
    # their own history floor and say so, which means a negative here could only be a bug.
    """
    ALTER TABLE sizing_refusal
        ADD CONSTRAINT ck_sizing_refusal__observed_something
        CHECK (observation_days >= 0)
    """,
    # The read is every refusal for an account, which is the only shape the screen asks for.
    """
    CREATE INDEX IF NOT EXISTS ix_sizing_refusal__account
        ON sizing_refusal (tenant_id, sub_account_id)
    """,
)

_DOWN = "DROP TABLE IF EXISTS sizing_refusal"


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    op.execute(_DOWN)
