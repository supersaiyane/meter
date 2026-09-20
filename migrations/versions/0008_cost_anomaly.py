"""A day that did not look like the days before it.

Revision ID: 0008_cost_anomaly
Revises: 0007_query_adhoc
Create Date: 2026-09-20

FEAT-023, TASK-P1-014. One row per account, service and day that the detector
called out, written by `finops_ingest/collectors/cost_anomaly.py` from the
arithmetic in `finops_query/anomaly.py`.

`deviations` is nullable and null is meaningful: the baseline was perfectly
flat, so the day is a given number of dollars out and no number of deviations
out at all. Every departure from an unmoving baseline is infinitely many
deviations, which is arithmetically true and useless, so the column says nothing
rather than saying something false.

There is no `provenance` column. An anomaly is derived from measured line items
by arithmetic that is entirely ours, so it is neither measured nor modelled in
the sense the rest of the schema uses, and adding the column would force a wrong
answer. `why` carries the working instead, which is what a reader needs before
they can disagree with it.
"""

from __future__ import annotations

from alembic import op

revision = "0008_cost_anomaly"
down_revision = "0007_query_adhoc"
branch_labels = None
depends_on = None

STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE cost_anomaly (
        anomaly_id      UUID PRIMARY KEY,
        tenant_id       UUID            NOT NULL REFERENCES tenant (tenant_id),
        sub_account_id  TEXT            NOT NULL,
        service_name    TEXT            NOT NULL,
        day             DATE            NOT NULL,
        observed        NUMERIC(20, 10) NOT NULL,
        baseline        NUMERIC(20, 10) NOT NULL,
        delta           NUMERIC(20, 10) NOT NULL,
        deviations      NUMERIC(12, 4),
        severity        TEXT            NOT NULL,
        why             TEXT            NOT NULL,
        as_of           TIMESTAMPTZ     NOT NULL,
        collected_at    TIMESTAMPTZ     NOT NULL
    )
    """,
    # One verdict per pair per day. Re running the detector over a day it has
    # already judged replaces the verdict rather than adding a second one, which
    # is what stops a screen showing the same spike four times because the
    # collector ran four times.
    """
    ALTER TABLE cost_anomaly
        ADD CONSTRAINT uq_cost_anomaly__day
        UNIQUE (tenant_id, sub_account_id, service_name, day)
    """,
    # Only increases are stored. A fall is not this table's business, and a row
    # with a negative delta would mean the detector wrote something it has no
    # screen for and no severity rule for.
    """
    ALTER TABLE cost_anomaly
        ADD CONSTRAINT ck_cost_anomaly__delta_positive
        CHECK (delta > 0)
    """,
    # The arithmetic has to hold. A row whose three numbers disagree is a row
    # somebody will try to reconcile, and application code is not what should be
    # preventing it, per constraint 11.
    """
    ALTER TABLE cost_anomaly
        ADD CONSTRAINT ck_cost_anomaly__delta_is_the_difference
        CHECK (delta = observed - baseline)
    """,
    # The read is always worst first, within a tenant.
    """
    CREATE INDEX ix_cost_anomaly__delta
        ON cost_anomaly (tenant_id, day DESC, delta DESC)
    """,
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cost_anomaly")
