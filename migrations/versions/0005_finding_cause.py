"""The cause a finding is grouped by, beside the prose that explains it.

Revision ID: 0005_finding_cause
Revises: 0004_query_key
Create Date: 2026-09-14

ADR-0016 requires findings to be grouped by cause before they are ranked, so
that four hundred findings at 15 USD each surface as one 6,000 USD group rather
than four hundred LOW rows. `why` already carries the explanation, and prose
cannot be grouped on: a reworded sentence would split one systemic problem
across every phrasing the model has ever emitted.

Nullable, per constraint 12. The old task definition writes rows without it
during a rolling deploy and a NOT NULL here would reject them. A row with no
cause groups under the engine's own scan cost, which is true of every priced
query and is therefore the honest default rather than a guess.
"""

from __future__ import annotations

from alembic import op

revision = "0005_finding_cause"
down_revision = "0004_query_key"
branch_labels = None
depends_on = None

STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE query_finding ADD COLUMN cause TEXT",
    # Grouping happens before ranking, so the index leads with the cause and
    # carries the cost, which is what the group sum reads.
    """
    CREATE INDEX ix_query_finding__cause
        ON query_finding (tenant_id, run_date, cause, cost_month_usd DESC)
""",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_query_finding__cause")
    op.execute("ALTER TABLE query_finding DROP COLUMN IF EXISTS cause")
