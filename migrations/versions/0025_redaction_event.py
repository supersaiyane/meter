"""What redaction found in a question: the rule and the action, and never the secret.

Revision ID: 0025_redaction_event
Revises: 0024_team_digest
Create Date: 2026-10-04

TASK-P7-013 and FEAT-046, P7 spec section 6.3. One row per rule that fired on a question.

**There is no column the secret could go in.** Not the matched text, not a hash of it, not
its position and not its length. A table of redacted secrets is a worse leak than the prompt
would have been, and the cheapest way to make sure one never exists is to give it nowhere to
live. The question itself is stored in `assistant_exchange` with the secret already
replaced by the rule's name.

**Each row belongs to its exchange and its asker.** The exchange is a foreign key without
a cascade, so an event cannot precede the question it was found in and the question cannot
be deleted from under its events: a record of a redaction is not a cache. The asker is kept
so the guard can confine the rows to the person who typed them, ADR-0029.

Backward compatible, constraint 12: a new table no earlier release reads or writes, and the
downgrade drops it, as 0022 to 0024 do.
"""

from __future__ import annotations

from alembic import op

revision = "0025_redaction_event"
down_revision = "0024_team_digest"
branch_labels = None
depends_on = None


_UP = (
    """
    CREATE TABLE IF NOT EXISTS redaction_event (
        event_id       UUID         PRIMARY KEY,
        tenant_id      UUID         NOT NULL REFERENCES tenant(tenant_id),
        exchange_id    UUID         NOT NULL
                       REFERENCES assistant_exchange(exchange_id),
        principal_id   TEXT         NOT NULL,
        rule_id        TEXT         NOT NULL,
        action         TEXT         NOT NULL,
        occurred_at    TIMESTAMPTZ  NOT NULL
    )
    """,
    """
    ALTER TABLE redaction_event DROP CONSTRAINT IF EXISTS ck_redaction_event__action
    """,
    """
    ALTER TABLE redaction_event
        ADD CONSTRAINT ck_redaction_event__action
        CHECK (action IN ('BLOCKED', 'REDACTED'))
    """,
    """
    ALTER TABLE redaction_event DROP CONSTRAINT IF EXISTS ck_redaction_event__named
    """,
    """
    ALTER TABLE redaction_event
        ADD CONSTRAINT ck_redaction_event__named
        CHECK (length(trim(rule_id)) > 0 AND length(trim(principal_id)) > 0)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_redaction_event__principal
        ON redaction_event (tenant_id, principal_id, occurred_at)
    """,
)


_DOWN = ("DROP TABLE IF EXISTS redaction_event",)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
