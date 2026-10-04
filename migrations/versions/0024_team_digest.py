"""Weekly digests, composed whether or not anybody can send them.

Revision ID: 0024_team_digest
Revises: 0023_assistant_exchange
Create Date: 2026-10-04

TASK-P7-012 and FEAT-041, P7 spec section 6.2. One row per audience, team and week: a
digest for each team the bill's `team` tag names, and one executive digest for the whole
organization.

**`sent_at` null is a real state, and it says why.** Nothing can send a digest until OPEN-11
decides between email and Slack, so every row is composed and kept, and the reason it was
not sent is required beside a null and forbidden beside a send. The biconditional is the
shape 0020 and 0023 use, for the reason they do: a null with no reason renders as a digest
that silently went nowhere, and a reason beside a send is a sentence about nothing.

**A team digest names its team and an executive one names none.** Audience is a column of
its own rather than a reserved team name, because a tag value is somebody else's text and
one called `organization` would otherwise collide with the executive digest.

**Our own work, so `composed_at` and no `as_of`.** The `as_of` of every cited figure is in
`citations`, beside the figure it dates, as in `assistant_exchange`.

Backward compatible, constraint 12: a new table no earlier release reads or writes. The
downgrade drops it, as 0022 and 0023 do, for the round trip test's sake.
"""

from __future__ import annotations

from alembic import op

revision = "0024_team_digest"
down_revision = "0023_assistant_exchange"
branch_labels = None
depends_on = None


_UP = (
    """
    CREATE TABLE IF NOT EXISTS team_digest (
        digest_id        UUID         PRIMARY KEY,
        tenant_id        UUID         NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id    UUID         NOT NULL,
        audience         TEXT         NOT NULL,
        team             TEXT,
        period_start     DATE         NOT NULL,
        period_end       DATE         NOT NULL,
        prose            TEXT         NOT NULL,
        citations        JSONB        NOT NULL,
        composed_at      TIMESTAMPTZ  NOT NULL,
        sent_at          TIMESTAMPTZ,
        unsent_reason    TEXT
    )
    """,
    """
    ALTER TABLE team_digest DROP CONSTRAINT IF EXISTS ck_team_digest__audience
    """,
    """
    ALTER TABLE team_digest
        ADD CONSTRAINT ck_team_digest__audience
        CHECK (audience IN ('team', 'executive'))
    """,
    """
    ALTER TABLE team_digest DROP CONSTRAINT IF EXISTS ck_team_digest__team_iff_team_audience
    """,
    """
    ALTER TABLE team_digest
        ADD CONSTRAINT ck_team_digest__team_iff_team_audience
        CHECK ((audience = 'team') = (length(trim(coalesce(team, ''))) > 0))
    """,
    # Twelve is REASON_MIN_LENGTH, carried literally because a check cannot read it.
    """
    ALTER TABLE team_digest DROP CONSTRAINT IF EXISTS ck_team_digest__reason_iff_unsent
    """,
    """
    ALTER TABLE team_digest
        ADD CONSTRAINT ck_team_digest__reason_iff_unsent
        CHECK ((sent_at IS NULL) = (length(trim(coalesce(unsent_reason, ''))) >= 12))
    """,
    """
    ALTER TABLE team_digest DROP CONSTRAINT IF EXISTS ck_team_digest__sent_after_composed
    """,
    """
    ALTER TABLE team_digest
        ADD CONSTRAINT ck_team_digest__sent_after_composed
        CHECK (sent_at IS NULL OR sent_at >= composed_at)
    """,
    """
    ALTER TABLE team_digest DROP CONSTRAINT IF EXISTS ck_team_digest__a_week_with_prose
    """,
    """
    ALTER TABLE team_digest
        ADD CONSTRAINT ck_team_digest__a_week_with_prose
        CHECK (
            period_end > period_start
            AND length(trim(prose)) > 0
            AND jsonb_typeof(citations) = 'array'
        )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_team_digest__identity
        ON team_digest (tenant_id, audience, coalesce(team, ''), period_start)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_team_digest__period
        ON team_digest (tenant_id, period_start)
    """,
)


_DOWN = ("DROP TABLE IF EXISTS team_digest",)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
