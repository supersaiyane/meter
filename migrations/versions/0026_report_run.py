"""One row per export: who made it, of what view, under which scope, and how big it was.

Revision ID: 0026_report_run
Revises: 0025_redaction_event
Create Date: 2026-10-05

TASK-P8-009 and FEAT-067, P8 spec section 5.5 item 5. Every file an export writes is a copy
of the estate's figures leaving the product, and the record of who took which copy is kept
where nobody can quietly not write it: in the same transaction as the read it records.

**Which scope, exactly.** The accounts the scope named are kept as a list, empty for a global
scope, rather than as a count. A count says how much was taken; the list says what, which is
the question an audit asks.

**Every invariant is a constraint.** The format is one of two, the counts are never negative,
the view is a path, and the person is named. Application code that forgets any of them is
refused by the database rather than trusted.

Backward compatible, constraint 12: a new table no earlier release reads or writes, and the
downgrade drops it.
"""

from __future__ import annotations

from alembic import op

revision = "0026_report_run"
down_revision = "0025_redaction_event"
branch_labels = None
depends_on = None


_UP = (
    """
    CREATE TABLE IF NOT EXISTS report_run (
        run_id          UUID         PRIMARY KEY,
        tenant_id       UUID         NOT NULL REFERENCES tenant(tenant_id),
        principal_id    TEXT         NOT NULL,
        view_path       TEXT         NOT NULL,
        view_query      TEXT         NOT NULL,
        scope_global    BOOLEAN      NOT NULL,
        scope_accounts  TEXT[]       NOT NULL,
        format          TEXT         NOT NULL,
        row_count       INTEGER      NOT NULL,
        byte_count      BIGINT       NOT NULL,
        truncated       BOOLEAN      NOT NULL,
        made_at         TIMESTAMPTZ  NOT NULL
    )
    """,
    """
    ALTER TABLE report_run DROP CONSTRAINT IF EXISTS ck_report_run__format
    """,
    """
    ALTER TABLE report_run
        ADD CONSTRAINT ck_report_run__format CHECK (format IN ('xlsx', 'csv'))
    """,
    """
    ALTER TABLE report_run DROP CONSTRAINT IF EXISTS ck_report_run__counts
    """,
    """
    ALTER TABLE report_run
        ADD CONSTRAINT ck_report_run__counts CHECK (row_count >= 0 AND byte_count >= 0)
    """,
    """
    ALTER TABLE report_run DROP CONSTRAINT IF EXISTS ck_report_run__named
    """,
    """
    ALTER TABLE report_run
        ADD CONSTRAINT ck_report_run__named
        CHECK (length(trim(principal_id)) > 0 AND view_path LIKE '/%')
    """,
    """
    ALTER TABLE report_run DROP CONSTRAINT IF EXISTS ck_report_run__scope
    """,
    """
    ALTER TABLE report_run
        ADD CONSTRAINT ck_report_run__scope
        CHECK (NOT scope_global OR cardinality(scope_accounts) = 0)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_report_run__principal
        ON report_run (tenant_id, principal_id, made_at)
    """,
)


_DOWN = ("DROP TABLE IF EXISTS report_run",)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
