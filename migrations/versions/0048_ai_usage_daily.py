"""Tokens and requests per day, per model and per caller, from every AI source.

Revision ID: 0048_ai_usage_daily
Revises: 0047_cost_ai_columns
Create Date: 2026-10-12

P13 spec sections 5.4 and 6, TASK-P13-003, FEAT-082. The bill says what a model cost and never who
called it; the invocation logs and the providers' usage reports say who called what, and how many
tokens and requests it took. This holds them, Bedrock's first and OpenAI's and Anthropic's from
TASK-P13-004 and 005.

An empty string in a key column means the source does not report that dimension, which a NULL
cannot say inside a primary key. `caller` can name a person, so the table is class P, kept 13
months by `retention_ai_usage`. New table only, constraint 12; the downgrade removes it.
"""

from __future__ import annotations

from alembic import op

revision = "0048_ai_usage_daily"
down_revision = "0047_cost_ai_columns"
branch_labels = None
depends_on = None

_UP = (
    """
    CREATE TABLE IF NOT EXISTS ai_usage_daily (
        tenant_id          UUID        NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id      UUID        NOT NULL,
        provider           TEXT        NOT NULL,
        account_id         TEXT        NOT NULL,
        usage_date         DATE        NOT NULL,
        model              TEXT        NOT NULL,
        workspace          TEXT        NOT NULL DEFAULT '',
        api_key_id         TEXT        NOT NULL DEFAULT '',
        caller             TEXT        NOT NULL DEFAULT '',
        application        TEXT        NOT NULL DEFAULT '',
        input_tokens       BIGINT      NOT NULL,
        output_tokens      BIGINT      NOT NULL,
        cache_read_tokens  BIGINT      NOT NULL,
        cache_write_tokens BIGINT      NOT NULL,
        requests           BIGINT,
        as_of              TIMESTAMPTZ NOT NULL,
        collected_at       TIMESTAMPTZ NOT NULL,
        CONSTRAINT pk_ai_usage_daily PRIMARY KEY (tenant_id, provider, account_id, usage_date,
            model, workspace, api_key_id, caller, application),
        CONSTRAINT ck_ai_usage_daily__provider
            CHECK (provider IN ('bedrock', 'openai', 'anthropic')),
        CONSTRAINT ck_ai_usage_daily__model_named CHECK (model <> ''),
        CONSTRAINT ck_ai_usage_daily__tokens_not_negative CHECK (
            input_tokens >= 0 AND output_tokens >= 0
            AND cache_read_tokens >= 0 AND cache_write_tokens >= 0
        ),
        CONSTRAINT ck_ai_usage_daily__requests_not_negative CHECK (requests >= 0),
        CONSTRAINT ck_ai_usage_daily__collected_after_true
            CHECK (collected_at >= as_of)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_ai_usage_daily__tenant_date "
    "ON ai_usage_daily (tenant_id, usage_date)",
)

_DOWN = ("DROP TABLE IF EXISTS ai_usage_daily",)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
