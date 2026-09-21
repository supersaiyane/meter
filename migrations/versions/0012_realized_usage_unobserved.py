"""A usage quantity nobody published, recorded as unknown rather than as zero.

Revision ID: 0012_realized_usage_unobserved
Revises: 0011_realized_saving
Create Date: 2026-09-21

FEAT-029, TASK-P3-013. `0011` made both usage columns NOT NULL, which forces the
collector to invent a figure for a resource whose billing rows carry no
`consumed_quantity`. That column is nullable in `cost_focus_daily` and its sum is
null often enough to matter, so the choice was between writing a zero and widening
these two columns. A zero here is not a small inaccuracy: it is a usage that fell
to nothing, which reads as either a vanished workload or a verified saving
depending on the other numbers, and both are claims nobody measured. Constraint 5.

**The paired constraint is the point.** Making the columns nullable alone would
leave `VERIFIED` reachable with no control behind it, so a check refuses that row
and the rule survives a second writer, which is constraint 11's whole argument.

Backward compatible per constraint 12. Dropping NOT NULL accepts everything the old
definition accepted, and the new check cannot fire on a row an older task
definition writes, because an older one never writes a null.
"""

from __future__ import annotations

from alembic import op

revision = "0012_realized_usage_unobserved"
down_revision = "0011_realized_saving"
branch_labels = None
depends_on = None

STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE realized_saving ALTER COLUMN usage_before DROP NOT NULL",
    "ALTER TABLE realized_saving ALTER COLUMN usage_after DROP NOT NULL",
    # An unobserved control can support INCONCLUSIVE and nothing else. Not
    # VERIFIED, which would be a saving with no control, and not REGRESSED, which
    # is decided on cost alone and so never needs the usage columns at all: a
    # regression written with a null usage is a collector that lost the figure
    # rather than one that never had it.
    """
    ALTER TABLE realized_saving
        ADD CONSTRAINT ck_realized_saving__unobserved_is_never_verified
        CHECK (
            (usage_before IS NOT NULL AND usage_after IS NOT NULL)
            OR verdict = 'INCONCLUSIVE'
        )
    """,
)

#: Reversing this needs the nulls gone before the columns can refuse them again,
#: and there is no figure to put back: the row said the quantity was never
#: published. So the rows that used the widening are removed rather than filled in
#: with the zero this migration exists to prevent.
UNDO: tuple[str, ...] = (
    "ALTER TABLE realized_saving "
    "DROP CONSTRAINT IF EXISTS ck_realized_saving__unobserved_is_never_verified",
    "DELETE FROM realized_saving WHERE usage_before IS NULL OR usage_after IS NULL",
    "ALTER TABLE realized_saving ALTER COLUMN usage_before SET NOT NULL",
    "ALTER TABLE realized_saving ALTER COLUMN usage_after SET NOT NULL",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in UNDO:
        op.execute(statement)
