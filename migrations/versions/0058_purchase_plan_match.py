"""A commitment is matched to one plan line at most. FEAT-090, TASK-P14-008.

Revision ID: 0058_purchase_plan_match
Revises: 0057_purchase_plan
Create Date: 2026-10-13

P14 spec section 5.2, OPEN-36. A plan recorded as bought is verified when each of its lines is
matched to a commitment the inventory holds. One commitment paying for two lines would verify a
plan only half bought, so the database refuses it, constraint 11, whatever path writes the match.

An index added to a table no release has written to yet, so backward compatible, constraint 12.
"""

from __future__ import annotations

from alembic import op

revision = "0058_purchase_plan_match"
down_revision = "0057_purchase_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_purchase_plan_line__matched_once "
        "ON purchase_plan_line (tenant_id, matched_commitment_id) "
        "WHERE matched_commitment_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_purchase_plan_line__matched_once")
