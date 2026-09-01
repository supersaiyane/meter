"""A key for what a query is, separate from which panel draws it.

Revision ID: 0004_query_key
Revises: 0003_p2_tables
Create Date: 2026-09-01

`query_definition.fingerprint` identifies one definition, and it has to:
`uq_query_definition__fingerprint` makes it the identity of a row, so two panels
sharing one would upsert over each other and a panel would vanish.

`query_key` identifies the query itself, so two panels running the same query on
different dashboards share it. That is what lets a measured execution attach to
both rather than to whichever was looked up first, which TASK-P2-013 needs.

Nullable, per constraint 12. The old task definition writes rows without it
during a rolling deploy, and a NOT NULL here would reject them. Backfill and
tighten in a later release.
"""

from __future__ import annotations

from alembic import op

revision = "0004_query_key"
down_revision = "0003_p2_tables"
branch_labels = None
depends_on = None

STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE query_definition ADD COLUMN query_key TEXT",
    """
    CREATE INDEX ix_query_definition__query_key
        ON query_definition (tenant_id, query_key)
""",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_query_definition__query_key")
    op.execute("ALTER TABLE query_definition DROP COLUMN query_key")
