"""An Upsize states what it adds to the bill, and never reduces a total of savings.

Revision ID: 0039_upsize_added_cost
Revises: 0038_recommendation_option
Create Date: 2026-10-08

TASK-P9-008, P9 spec section 5.7, constraint 11. An instance under pressure is recommended a
larger type as a recommendation of its own kind, `UPSIZE_INSTANCE`, with an added monthly cost.
Its saving is nought and the saving column already refuses a negative, 0010, so no total of
savings can fall because of an Upsize; the added cost is a column of its own, held to the kind:
an Upsize has one above nought, and nothing else has one.

Backward compatible, constraint 12: a nullable column an old writer leaves null, and a check every
row an old writer makes already meets, because no old writer makes an Upsize. The downgrade removes
the Upsizes first, with their options, their events and any realized saving cascading, then the
check and the column: an Upsize without its added cost is a row the check would refuse on the way
back up, and it is not a row the old release can show. The next run writes them again, as 0033's
downgrade relies on for the targets.
"""

from __future__ import annotations

from alembic import op

revision = "0039_upsize_added_cost"
down_revision = "0038_recommendation_option"
branch_labels = None
depends_on = None

_UP = (
    "ALTER TABLE recommendation ADD COLUMN IF NOT EXISTS added_monthly_cost NUMERIC(20, 10)",
    "ALTER TABLE recommendation DROP CONSTRAINT IF EXISTS ck_recommendation__upsize_costs",
    """
    ALTER TABLE recommendation ADD CONSTRAINT ck_recommendation__upsize_costs CHECK (
        (waste_class = 'UPSIZE_INSTANCE') = (added_monthly_cost IS NOT NULL)
        AND (added_monthly_cost IS NULL
             OR (added_monthly_cost > 0 AND estimated_monthly_saving = 0))
    )
    """,
)

_UPSIZES = "SELECT recommendation_id FROM recommendation WHERE waste_class = 'UPSIZE_INSTANCE'"

_DOWN = (
    f"DELETE FROM recommendation_option WHERE recommendation_id IN ({_UPSIZES})",
    "DELETE FROM recommendation WHERE waste_class = 'UPSIZE_INSTANCE'",
    "ALTER TABLE recommendation DROP CONSTRAINT IF EXISTS ck_recommendation__upsize_costs",
    "ALTER TABLE recommendation DROP COLUMN IF EXISTS added_monthly_cost",
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
