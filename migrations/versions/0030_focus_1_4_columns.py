"""FOCUS 1.4's mandatory and invoice columns on the cost row.

Revision ID: 0030_focus_1_4_columns
Revises: 0029_report_schedule
Create Date: 2026-10-07

TASK-P10-002, FEAT-004, ADR-0034, P10 spec sections 4 to 6.

Six columns FOCUS 1.4 makes mandatory that the row lacked, and the two that tie a row to its
invoice. Every one nullable: AWS's FOCUS 1.2 export carries five of them and an older export
none, and a null is what Meter knows rather than a value it guessed. `billing_currency` is held
to the form FOCUS 1.4 mandates, an ISO 4217 code of three capital letters, constraint 11.

`service_provider_name` is the column FOCUS 1.3 introduced to replace `provider_name`, and
`host_provider_name` must equal it unless a host is exposed, so the backfill copies
`provider_name` into both. `provider_name` and `publisher_name`, which FOCUS 1.4 removes, stay
and stay readable until a release after P10 drops them.

Backward compatible, constraint 12: nullable columns the old code never writes, a constraint
that refuses only a value the old code cannot produce, a backfill of columns nothing old reads,
and an index nothing old needs. The backfill is the one statement that touches every row; in
an estate with a long history it is the slow one. The downgrade drops what this adds.
"""

from __future__ import annotations

from alembic import op

revision = "0030_focus_1_4_columns"
down_revision = "0029_report_schedule"
branch_labels = None
depends_on = None


_UP = (
    """
    ALTER TABLE cost_focus_daily
        ADD COLUMN IF NOT EXISTS billing_account_name TEXT,
        ADD COLUMN IF NOT EXISTS billing_currency TEXT,
        ADD COLUMN IF NOT EXISTS charge_class TEXT,
        ADD COLUMN IF NOT EXISTS pricing_unit TEXT,
        ADD COLUMN IF NOT EXISTS service_provider_name TEXT,
        ADD COLUMN IF NOT EXISTS host_provider_name TEXT,
        ADD COLUMN IF NOT EXISTS invoice_id TEXT,
        ADD COLUMN IF NOT EXISTS invoice_detail_id TEXT
    """,
    """
    ALTER TABLE cost_focus_daily
        DROP CONSTRAINT IF EXISTS ck_cost_focus_daily__billing_currency_iso
    """,
    """
    ALTER TABLE cost_focus_daily
        ADD CONSTRAINT ck_cost_focus_daily__billing_currency_iso
        CHECK (billing_currency IS NULL OR billing_currency ~ '^[A-Z]{3}$')
    """,
    """
    UPDATE cost_focus_daily
        SET service_provider_name = provider_name,
            host_provider_name = provider_name
        WHERE service_provider_name IS NULL
    """,
    # Partial, for the reconciliation's sum over one invoice's rows, TASK-P10-004. Most rows of
    # an export older than FOCUS 1.2 carry no invoice id, and a full index would be mostly nulls.
    """
    CREATE INDEX IF NOT EXISTS ix_cost_focus_daily__invoice
        ON cost_focus_daily (tenant_id, invoice_id)
        WHERE invoice_id IS NOT NULL
    """,
)


_DOWN = (
    "DROP INDEX IF EXISTS ix_cost_focus_daily__invoice",
    """
    ALTER TABLE cost_focus_daily
        DROP CONSTRAINT IF EXISTS ck_cost_focus_daily__billing_currency_iso
    """,
    # Drops rather than refusing, as 0021 does: the next collection reads every one of these
    # back out of the export, so the loss is bounded and recoverable.
    """
    ALTER TABLE cost_focus_daily
        DROP COLUMN IF EXISTS invoice_detail_id,
        DROP COLUMN IF EXISTS invoice_id,
        DROP COLUMN IF EXISTS host_provider_name,
        DROP COLUMN IF EXISTS service_provider_name,
        DROP COLUMN IF EXISTS pricing_unit,
        DROP COLUMN IF EXISTS charge_class,
        DROP COLUMN IF EXISTS billing_currency,
        DROP COLUMN IF EXISTS billing_account_name
    """,
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
