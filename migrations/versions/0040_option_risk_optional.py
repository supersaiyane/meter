"""An option may come from a source that gives no performance risk.

Revision ID: 0040_option_risk_optional
Revises: 0039_upsize_added_cost
Create Date: 2026-10-08

TASK-P9-010, P9 spec section 8. The Alternatives table lists every type Meter's own sizing rule
found to fit, written when the rule judged them, because the demand they were judged against is
not stored and a list rebuilt later could not say which of them fit. They go in
`recommendation_option`, 0038, beside Compute Optimizer's. Compute Optimizer scores each option's
performance risk from 0 to 4; Meter's rule gives no such score, and a nought invented for it would
read as Compute Optimizer's "no risk". So the column may be null, meaning the source gave none,
and the 0 to 4 check still holds every value that is given. OPEN-24.

Backward compatible, constraint 12: dropping NOT NULL refuses nothing an old writer writes. The
downgrade deletes the rows with no risk, which only the new release writes, before restoring NOT
NULL; the next run writes them again.
"""

from __future__ import annotations

from alembic import op

revision = "0040_option_risk_optional"
down_revision = "0039_upsize_added_cost"
branch_labels = None
depends_on = None

_UP = ("ALTER TABLE recommendation_option ALTER COLUMN performance_risk DROP NOT NULL",)

_DOWN = (
    "DELETE FROM recommendation_option WHERE performance_risk IS NULL",
    "ALTER TABLE recommendation_option ALTER COLUMN performance_risk SET NOT NULL",
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
