"""The bill's AI columns, and which collector wrote each cost row.

Revision ID: 0047_cost_ai_columns
Revises: 0046_redaction_found_in
Create Date: 2026-10-12

P13 spec sections 5.2 and 5.3, TASK-P13-002, FEAT-081. FOCUS has no column for a model or a token
yet, so five `x_` columns carry them, the prefix FOCUS reserves for a producer's own, until FOCUS
1.5 names them, OPEN-34. `ingest_source` says which collector wrote a row, because the cost
collector's restatement removes every row of a period its run did not write, and from P13 the
OpenAI and Anthropic collectors write to the same table.

Backward compatible, constraint 12: every new column is nullable or has a default, so the old
code's inserts land as `aws_export`, which is what every one of them was. The constraints hold
the token columns together: a token count names its type, and a type names its model. The
downgrade drops them all.
"""

from __future__ import annotations

from alembic import op

revision = "0047_cost_ai_columns"
down_revision = "0046_redaction_found_in"
branch_labels = None
depends_on = None

_TABLE = "cost_focus_daily"

_UP = (
    f"ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS ingest_source TEXT NOT NULL "
    "DEFAULT 'aws_export'",
    f"ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS x_usage_type TEXT",
    f"ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS x_iam_principal TEXT",
    f"ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS x_ai_model TEXT",
    f"ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS x_ai_token_type TEXT",
    f"ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS x_ai_tokens NUMERIC(30, 10)",
    f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS ck_cost_focus_daily__ingest_source",
    f"ALTER TABLE {_TABLE} ADD CONSTRAINT ck_cost_focus_daily__ingest_source "
    "CHECK (ingest_source IN ('aws_export', 'openai', 'anthropic'))",
    f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS ck_cost_focus_daily__token_type",
    f"ALTER TABLE {_TABLE} ADD CONSTRAINT ck_cost_focus_daily__token_type "
    "CHECK (x_ai_token_type IN ('input', 'output', 'cache_read', 'cache_write'))",
    f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS ck_cost_focus_daily__tokens_not_negative",
    f"ALTER TABLE {_TABLE} ADD CONSTRAINT ck_cost_focus_daily__tokens_not_negative "
    "CHECK (x_ai_tokens >= 0)",
    f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS ck_cost_focus_daily__tokens_have_a_type",
    f"ALTER TABLE {_TABLE} ADD CONSTRAINT ck_cost_focus_daily__tokens_have_a_type "
    "CHECK (x_ai_tokens IS NULL OR x_ai_token_type IS NOT NULL)",
    f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS ck_cost_focus_daily__token_type_has_a_model",
    f"ALTER TABLE {_TABLE} ADD CONSTRAINT ck_cost_focus_daily__token_type_has_a_model "
    "CHECK (x_ai_token_type IS NULL OR x_ai_model IS NOT NULL)",
)

_DOWN = (
    f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS ck_cost_focus_daily__token_type_has_a_model",
    f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS ck_cost_focus_daily__tokens_have_a_type",
    f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS ck_cost_focus_daily__tokens_not_negative",
    f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS ck_cost_focus_daily__token_type",
    f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS ck_cost_focus_daily__ingest_source",
    f"ALTER TABLE {_TABLE} DROP COLUMN IF EXISTS x_ai_tokens",
    f"ALTER TABLE {_TABLE} DROP COLUMN IF EXISTS x_ai_token_type",
    f"ALTER TABLE {_TABLE} DROP COLUMN IF EXISTS x_ai_model",
    f"ALTER TABLE {_TABLE} DROP COLUMN IF EXISTS x_iam_principal",
    f"ALTER TABLE {_TABLE} DROP COLUMN IF EXISTS x_usage_type",
    f"ALTER TABLE {_TABLE} DROP COLUMN IF EXISTS ingest_source",
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
