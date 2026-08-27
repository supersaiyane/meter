"""Monthly cost rollup, so retention can aggregate before it drops.

Revision ID: 0002_cost_monthly
Revises: 0001_initial
Create Date: 2026-08-27

`docs/09-DATA-CLASSIFICATION.md` says cost line items older than 37 months are
aggregated to month, account, service and region, and then dropped. Without
somewhere to put the aggregate, retention would either destroy three years of
trend or never run at all, and both are worse than the migration.

Additive only, per constraint 12. Nothing is renamed and nothing is dropped, so
the old and new task definitions run against this schema together.
"""

from __future__ import annotations

from alembic import op

revision = "0002_cost_monthly"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE cost_focus_monthly (
        tenant_id            UUID           NOT NULL,
        billing_month        DATE           NOT NULL,
        sub_account_id       TEXT,
        service_name         TEXT           NOT NULL,
        region_id            TEXT,
        billed_cost          NUMERIC(20, 10) NOT NULL,
        effective_cost       NUMERIC(20, 10) NOT NULL,
        line_items           BIGINT         NOT NULL,
        as_of                TIMESTAMPTZ    NOT NULL,
        collected_at         TIMESTAMPTZ    NOT NULL,
        PRIMARY KEY (tenant_id, billing_month, sub_account_id, service_name, region_id)
    )
""",
    """
    CREATE INDEX ix_cost_focus_monthly__tenant_month
        ON cost_focus_monthly (tenant_id, billing_month)
""",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("cost_focus_monthly")
