"""The AI provider organizations a tenant connects, and where each one's admin key is kept.

Revision ID: 0049_ai_provider_account
Revises: 0048_ai_usage_daily
Create Date: 2026-10-12

P13 spec section 5.5, TASK-P13-004, FEAT-083. An OpenAI or Anthropic organization belongs to one
tenant, so the organization is the key and the tenant a column the repository guard filters on.
The admin key itself is never here: `key_secret_name` names a Secrets Manager secret under
`meter/<env>/ai/`, the one path the hub's task role may read for it, and the constraint refuses a
name outside that path so a row cannot point the worker at some other secret. New table only,
constraint 12; the downgrade removes it.
"""

from __future__ import annotations

from alembic import op

revision = "0049_ai_provider_account"
down_revision = "0048_ai_usage_daily"
branch_labels = None
depends_on = None

_UP = (
    """
    CREATE TABLE IF NOT EXISTS ai_provider_account (
        provider         TEXT        NOT NULL,
        organization_id  TEXT        NOT NULL,
        tenant_id        UUID        NOT NULL REFERENCES tenant(tenant_id),
        name             TEXT        NOT NULL,
        key_secret_name  TEXT        NOT NULL,
        enrolled_at      TIMESTAMPTZ NOT NULL,
        active           BOOLEAN     NOT NULL DEFAULT true,
        CONSTRAINT pk_ai_provider_account PRIMARY KEY (provider, organization_id),
        CONSTRAINT ck_ai_provider_account__provider
            CHECK (provider IN ('openai', 'anthropic')),
        CONSTRAINT ck_ai_provider_account__named
            CHECK (length(trim(organization_id)) > 0 AND length(trim(name)) > 0),
        CONSTRAINT ck_ai_provider_account__key_under_the_ai_path
            CHECK (key_secret_name ~ '^meter/[a-z]+/ai/[A-Za-z0-9/_+=.@-]+$')
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_ai_provider_account__tenant "
    "ON ai_provider_account (tenant_id, provider)",
)

_DOWN = ("DROP TABLE IF EXISTS ai_provider_account",)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
