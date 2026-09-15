"""The refresh floor a workspace enforces on itself.

Revision ID: 0006_refresh_floor
Revises: 0005_finding_cause
Create Date: 2026-09-14

FEAT-014. A workspace with no floor accepts a one second refresh from anybody,
and the floor is the single setting that stops the next expensive panel being
created rather than reporting the ones that already exist.

Nullable, and null is not zero. Null means the workspace has no floor at all,
which is the estate worth acting on. Zero would say the workspace permits any
refresh, which is the same claim stated as a measurement.
"""

from __future__ import annotations

from alembic import op

revision = "0006_refresh_floor"
down_revision = "0005_finding_cause"
branch_labels = None
depends_on = None

STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE grafana_instance ADD COLUMN refresh_floor_seconds INTEGER",
    """
    ALTER TABLE grafana_instance
        ADD CONSTRAINT ck_grafana_instance__floor_positive
        CHECK (refresh_floor_seconds IS NULL OR refresh_floor_seconds > 0)
""",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE grafana_instance DROP CONSTRAINT IF EXISTS ck_grafana_instance__floor_positive"
    )
    op.execute("ALTER TABLE grafana_instance DROP COLUMN IF EXISTS refresh_floor_seconds")
