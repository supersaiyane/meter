"""What somebody said this should cost.

Revision ID: 0017_budget
Revises: 0016_resource_management
Create Date: 2026-09-27

FEAT-060. The gap three independent sources named: the IBM Turbonomic review has no
budget in it either, the FinOpsForge checklist puts budget against actual at the top
of the finance dashboard and a red amber green status at the top of the executive
one, and this product had no budget entity at all.

**Collected, not entered, which is why this table looks like every other one here.**
It carries `ingest_run_id` and the two timestamps because a budget read from a
provider is a fact with a provenance, and everything in Meter that a screen renders
has one. A budget typed into Meter would be the first thing in the product with
none, and it would need a write API, a form, validation and an audit trail. The cost
of the decision is real and is ISS-210: an organization that tracks budgets in a
spreadsheet has none here.

**Nothing derived is stored.** Not the actual, not the status, not the percentage.
Status depends on where today falls in the period, so a stored one is wrong by the
next morning, and a stored actual would be a second copy of a number
`cost_focus_daily` already holds. All three are computed per request from the two
facts that are stored.

**`limit_amount`, not `limit`.** LIMIT is reserved in SQL and a column called that
has to be quoted in every statement that touches it forever, which is a thing
somebody forgets exactly once.

**Payer wide, per ADR-0025.** A budget is set at the payer and the API that reports
it is a payer API, so the guard scopes this the way it scopes `commitment_coverage`:
a narrowed reader reads nothing rather than a number that is not theirs. That costs
something real, which ISS-212 records: an account scoped budget is invisible to the
team that owns the account, and closing it properly means the same per class rule
ADR-0025 already refused once.
"""

from __future__ import annotations

from alembic import op

revision = "0017_budget"
down_revision = "0016_resource_management"
branch_labels = None
depends_on = None

_UP = (
    """
    CREATE TABLE IF NOT EXISTS budget (
        budget_pk UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id UUID NOT NULL,
        budget_id TEXT NOT NULL,
        name TEXT NOT NULL,
        scope TEXT NOT NULL,
        scope_value TEXT NOT NULL,
        limit_amount NUMERIC(20, 10) NOT NULL,
        currency TEXT NOT NULL,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        as_of TIMESTAMPTZ NOT NULL,
        collected_at TIMESTAMPTZ NOT NULL
    )
    """,
    # One current row per budget per period. A budget whose limit is revised mid month
    # updates rather than doubling, and a budget that runs every month keeps one row per
    # month rather than one row forever that silently forgets last month's limit.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_budget__identity
        ON budget (tenant_id, budget_id, period_start)
    """,
    # The four the domain allows. UNSUPPORTED is a real value and not an error: a budget
    # over a tag expression exists, is counted, and is never matched to a number.
    """
    ALTER TABLE budget
        ADD CONSTRAINT ck_budget__scope
        CHECK (scope IN ('ACCOUNT', 'SERVICE', 'ALL', 'UNSUPPORTED'))
    """,
    # A scope that names something has to name it, and one that does not must not pretend
    # to. Without this a budget could claim ACCOUNT scope with an empty account and would
    # then be compared against every account or none, depending on how the join was
    # written.
    """
    ALTER TABLE budget
        ADD CONSTRAINT ck_budget__scope_value_iff_narrow
        CHECK (
            (scope IN ('ACCOUNT', 'SERVICE')) = (length(trim(scope_value)) > 0)
        )
    """,
    # A budget of nothing is not a budget. Constraint 11: if application code is the only
    # thing preventing a bad row, the bad row will eventually exist, and a limit of zero
    # renders as an estate that has overspent everything it has.
    """
    ALTER TABLE budget
        ADD CONSTRAINT ck_budget__limit_is_positive
        CHECK (limit_amount > 0)
    """,
    """
    ALTER TABLE budget
        ADD CONSTRAINT ck_budget__period_is_a_period
        CHECK (period_end > period_start)
    """,
    # The read is every budget for a period, worst first, which is the only shape the
    # screen asks for.
    """
    CREATE INDEX IF NOT EXISTS ix_budget__period
        ON budget (tenant_id, period_start)
    """,
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS budget")
