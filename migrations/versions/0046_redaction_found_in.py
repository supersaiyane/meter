"""Where redaction found a secret: in the question, or in what a tool returned to the model.

Revision ID: 0046_redaction_found_in
Revises: 0045_ledger_screen
Create Date: 2026-10-12

ISS-085, FEAT-046. The question has been screened since TASK-P7-013, and what the tools return to
the model, Meter's own data, was sent as it was, so a key someone typed into a tag reached the
model. It is screened now too. A hit there is not something the asker typed, so an event says
where it was found, and the asker's list of their own redactions can tell the two apart.

Backward compatible, constraint 12: the column has a default, so the old code's inserts land as
`question`, which is what every one of them was. The downgrade drops it.
"""

from __future__ import annotations

from alembic import op

revision = "0046_redaction_found_in"
down_revision = "0045_ledger_screen"
branch_labels = None
depends_on = None

_UP = (
    "ALTER TABLE redaction_event "
    "ADD COLUMN IF NOT EXISTS found_in TEXT NOT NULL DEFAULT 'question'",
    "ALTER TABLE redaction_event DROP CONSTRAINT IF EXISTS ck_redaction_event__found_in",
    "ALTER TABLE redaction_event ADD CONSTRAINT ck_redaction_event__found_in "
    "CHECK (found_in IN ('question', 'tool_result'))",
)

_DOWN = (
    "ALTER TABLE redaction_event DROP CONSTRAINT IF EXISTS ck_redaction_event__found_in",
    "ALTER TABLE redaction_event DROP COLUMN IF EXISTS found_in",
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
