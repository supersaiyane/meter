"""Coverage gaps as findings somebody owns, in a table no narrowed reader can see.

Revision ID: 0015_commitment_action
Revises: 0014_topology
Create Date: 2026-09-26

FEAT-055, TASK-P1-022. See ADR-0025 for why this is its own table rather than rows
in `recommendation`.

**The short version, because it is the only reason this revision exists.** A
commitment is bought at the payer and its coverage cannot be apportioned to the
accounts that consumed it, which is why `commitment_coverage` is `PayerWide` in
`finops_api/guards.py`. A finding derived from it is payer wide too. `recommendation`
is `ByAccount`, so writing these rows into it would have meant stamping an account
on a payer wide figure, and whoever held that one account would then read the
organization's commitment position, which is exactly what `PayerWide` exists to
withhold. One table cannot hold two scoping rules, and two implementations of one
authorization rule is how an authorization bug is created, per ADR-0009.

**So the lifecycle columns exist twice, and that is the cost of the decision rather
than an oversight.** The vocabulary is copied from `recommendation` deliberately and
held to it by a test, so the two cannot drift into meaning different things by DONE.

**Unique on the dimension, not the window.** A coverage row arrives per window, and
keying on the window would open a second finding every month and leave last month's
looking abandoned. The upsert updates the one finding somebody is working on.

**Every measured input is stored beside the modelled output.** `eligible_spend` and
`covered_spend` came off the bill; the saving and the usage floor are computed from a
discount rate that is configuration. Storing both is what lets a reader a year later
check the arithmetic rather than take it, which is the same argument ADR-0007 makes.
"""

from __future__ import annotations

from alembic import op

revision = "0015_commitment_action"
down_revision = "0014_topology"
branch_labels = None
depends_on = None

_UP = (
    """
    CREATE TABLE IF NOT EXISTS commitment_action (
        action_id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id UUID NOT NULL,
        commitment_type TEXT NOT NULL,
        dimension TEXT NOT NULL,
        dimension_value TEXT NOT NULL,
        window_start DATE NOT NULL,
        window_end DATE NOT NULL,
        eligible_spend NUMERIC(20, 10) NOT NULL,
        covered_spend NUMERIC(20, 10) NOT NULL,
        estimated_monthly_saving NUMERIC(20, 10) NOT NULL,
        usage_floor_percent NUMERIC(5, 1) NOT NULL,
        term_months INTEGER NOT NULL,
        confidence TEXT NOT NULL,
        severity TEXT NOT NULL,
        lifecycle TEXT NOT NULL,
        owner TEXT,
        ticket_reference TEXT,
        rationale TEXT NOT NULL,
        as_of TIMESTAMPTZ NOT NULL,
        collected_at TIMESTAMPTZ NOT NULL
    )
    """,
    # The dimension, not the window. A second finding per month would leave last month's
    # looking abandoned while somebody was still working it.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_commitment_action__dimension
        ON commitment_action (tenant_id, commitment_type, dimension, dimension_value)
    """,
    # The same two values `commitment_coverage` allows, so a finding cannot describe a
    # dimension its own source could never have produced.
    """
    ALTER TABLE commitment_action
        ADD CONSTRAINT ck_commitment_action__dimension
        CHECK (dimension IN ('SERVICE', 'REGION'))
    """,
    # Copied from ck_recommendation__lifecycle_known on purpose. Two vocabularies that
    # drift is how one screen comes to mean something different by DONE.
    """
    ALTER TABLE commitment_action
        ADD CONSTRAINT ck_commitment_action__lifecycle_known
        CHECK (lifecycle IN (
            'OPEN', 'ACCEPTED', 'IN_PROGRESS', 'DONE', 'VERIFIED', 'REGRESSED', 'DISMISSED'
        ))
    """,
    """
    ALTER TABLE commitment_action
        ADD CONSTRAINT ck_commitment_action__severity_known
        CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW'))
    """,
    """
    ALTER TABLE commitment_action
        ADD CONSTRAINT ck_commitment_action__confidence_known
        CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW'))
    """,
    # A finding with no saving is not a finding. Constraint 11: if application code is the
    # only thing preventing a bad row, the bad row will eventually exist, and a zero here
    # would rank as the least valuable action rather than being absent.
    """
    ALTER TABLE commitment_action
        ADD CONSTRAINT ck_commitment_action__saving_positive
        CHECK (estimated_monthly_saving > 0)
    """,
    # The floor is a percentage of today's usage. Outside nought to a hundred it is not one,
    # and a screen would render it as a sentence telling somebody to sustain 140 percent.
    """
    ALTER TABLE commitment_action
        ADD CONSTRAINT ck_commitment_action__floor_is_a_percentage
        CHECK (usage_floor_percent >= 0 AND usage_floor_percent <= 100)
    """,
    """
    ALTER TABLE commitment_action
        ADD CONSTRAINT ck_commitment_action__window_is_a_window
        CHECK (window_end > window_start)
    """,
    # A commitment cannot be handed back, so the term is what decides how long a wrong
    # decision lasts. Nought months is not a commitment.
    """
    ALTER TABLE commitment_action
        ADD CONSTRAINT ck_commitment_action__term_is_positive
        CHECK (term_months > 0)
    """,
    # The read is worst money first, within a tenant, which is the only order the screen
    # asks for. ADR-0016.
    """
    CREATE INDEX IF NOT EXISTS ix_commitment_action__worst_first
        ON commitment_action (tenant_id, estimated_monthly_saving DESC)
    """,
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS commitment_action")
