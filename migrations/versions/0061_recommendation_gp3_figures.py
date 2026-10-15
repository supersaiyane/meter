"""What gp3 must give a gp2 volume, kept on its recommendation. FEAT-093, TASK-P15-005.

Revision ID: 0061_recommendation_gp3_figures
Revises: 0060_fix_pull_request
Create Date: 2026-10-15

P15 spec section 5.4. The gp2 to gp3 edit sets `iops` and `throughput` where FEAT-074's rule found
the volume needs more than gp3 includes, and the rule's figures were in the rationale's sentence
and nowhere a program could read. Two columns keep them: the IOPS and the MiB/s the priced gp3
gives. A check holds them to the gp2 to gp3 class and to positive figures, constraint 11.

Backward compatible, constraint 12: nullable columns added, which the volume pass fills on its
next run for every gp2 recommendation, since its write is an upsert. The downgrade drops them.
"""

from __future__ import annotations

from alembic import op

revision = "0061_recommendation_gp3_figures"
down_revision = "0060_fix_pull_request"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE recommendation ADD COLUMN IF NOT EXISTS target_iops INTEGER, "
        "ADD COLUMN IF NOT EXISTS target_throughput_mibps INTEGER"
    )
    op.execute(
        "ALTER TABLE recommendation ADD CONSTRAINT ck_recommendation__gp3_figures CHECK ("
        "(target_iops IS NULL AND target_throughput_mibps IS NULL) OR "
        "(waste_class = 'EBS_GP2_TO_GP3' AND target_iops > 0 AND target_throughput_mibps > 0))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE recommendation DROP CONSTRAINT IF EXISTS ck_recommendation__gp3_figures"
    )
    op.execute(
        "ALTER TABLE recommendation DROP COLUMN IF EXISTS target_throughput_mibps, "
        "DROP COLUMN IF EXISTS target_iops"
    )
