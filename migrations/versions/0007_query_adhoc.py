"""The queries that belong to nobody.

Revision ID: 0007_query_adhoc
Revises: 0006_refresh_floor
Create Date: 2026-09-06

FEAT-051, TASK-P2-026. Every other P2 table hangs off a workspace, because
every other finding starts from something Meter can enumerate: a panel, an
alert rule. A query somebody typed into the console belongs to no workspace and
no folder, so this table carries its own account and region rather than
reaching them through `grafana_instance`.

There is no `provenance` column and that is deliberate. An ad hoc query exists
only in the evidence, so there is no definition to model it from, and a
modelled row here would be an invention rather than an estimate. Every row is
measured by construction, which is why `runs` and `scan_bytes` are both NOT
NULL and why the check below refuses a row claiming zero runs: a row that
observed nothing is not evidence of a query, it is the absence of one.

`principal` is nullable, and null means CloudTrail did not name who ran it.
That is not a defect and the row is not dropped for it, because an expensive
query nobody owns is the case this feature exists for.
"""

from __future__ import annotations

from alembic import op

revision = "0007_query_adhoc"
down_revision = "0006_refresh_floor"
branch_labels = None
depends_on = None

STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE query_adhoc (
        adhoc_id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenant (tenant_id),
        account_id TEXT NOT NULL,
        region_id TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        query_text TEXT NOT NULL,
        run_date DATE NOT NULL,
        runs INTEGER NOT NULL,
        scan_bytes BIGINT NOT NULL,
        cost_usd NUMERIC(12, 4) NOT NULL,
        principal TEXT,
        as_of TIMESTAMPTZ NOT NULL,
        collected_at TIMESTAMPTZ NOT NULL
    )
    """,
    # One row per query per account, region and day. Three runs of the
    # collector in one day leave one row, the rule query_finding follows.
    """
    ALTER TABLE query_adhoc
        ADD CONSTRAINT uq_query_adhoc__day
        UNIQUE (tenant_id, account_id, region_id, fingerprint, run_date)
    """,
    # A row that saw nothing is not a query that ran.
    """
    ALTER TABLE query_adhoc
        ADD CONSTRAINT ck_query_adhoc__runs_positive
        CHECK (runs > 0)
    """,
    # Bytes and cost may be zero, because a query can scan nothing and still
    # have run. They may not be negative, which would be an arithmetic fault
    # rather than a small number.
    """
    ALTER TABLE query_adhoc
        ADD CONSTRAINT ck_query_adhoc__scan_not_negative
        CHECK (scan_bytes >= 0)
    """,
    """
    ALTER TABLE query_adhoc
        ADD CONSTRAINT ck_query_adhoc__cost_not_negative
        CHECK (cost_usd >= 0)
    """,
    # The read is always most expensive first, within a tenant and a day.
    """
    CREATE INDEX ix_query_adhoc__cost
        ON query_adhoc (tenant_id, run_date DESC, cost_usd DESC)
    """,
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS query_adhoc")
