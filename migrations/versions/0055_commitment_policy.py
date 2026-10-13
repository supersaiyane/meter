"""What each tenant's purchase plans aim for, and the cautious default. FEAT-088, TASK-P14-005.

Revision ID: 0055_commitment_policy
Revises: 0054_commitment_inventory
Create Date: 2026-10-13

P14 spec sections 5.4 and 6, OPEN-38. One row per tenant, cadence's pattern, constraint 9: the
coverage of the steady baseline to aim for, the term and payment option to plan in, and the ladder
limit, with who changed it, when and why. The constraints hold what the domain holds, so a policy
no plan could follow cannot be stored, constraint 11.

Every tenant that exists gets the cautious default, the owner's answer of 2026-10-13: 80 percent,
one year, no upfront, one twelfth. A new tenant gets it from `install_default_policy`, beside its
schedule. Backward compatible, constraint 12: a new table nothing old reads. The downgrade removes
it.
"""

from __future__ import annotations

from alembic import op

revision = "0055_commitment_policy"
down_revision = "0054_commitment_inventory"
branch_labels = None
depends_on = None

_BY = "migration 0055_commitment_policy"

_TABLE = """
CREATE TABLE IF NOT EXISTS commitment_policy (
    tenant_id        UUID          NOT NULL REFERENCES tenant(tenant_id),
    target_coverage  NUMERIC(4, 3) NOT NULL,
    term_years       INTEGER       NOT NULL,
    payment_option   TEXT          NOT NULL,
    ladder_limit     NUMERIC(5, 4) NOT NULL,
    reason           TEXT          NOT NULL,
    updated_by       TEXT          NOT NULL,
    updated_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT pk_commitment_policy PRIMARY KEY (tenant_id),
    CONSTRAINT ck_commitment_policy__coverage CHECK (
        target_coverage > 0 AND target_coverage <= 1),
    CONSTRAINT ck_commitment_policy__term CHECK (term_years IN (1, 3)),
    CONSTRAINT ck_commitment_policy__payment CHECK (
        payment_option IN ('No Upfront', 'Partial Upfront', 'All Upfront')),
    CONSTRAINT ck_commitment_policy__ladder CHECK (ladder_limit > 0 AND ladder_limit <= 1),
    CONSTRAINT ck_commitment_policy__reason CHECK (length(trim(reason)) > 0)
)
"""

_DEFAULTS = (
    "INSERT INTO commitment_policy (tenant_id, target_coverage, term_years, payment_option, "
    "ladder_limit, reason, updated_by) SELECT tenant_id, 0.800, 1, 'No Upfront', 0.0833, "
    "'The cautious ladder, the owner''s default, OPEN-38', '" + _BY + "' FROM tenant "
    "ON CONFLICT (tenant_id) DO NOTHING"
)


def upgrade() -> None:
    op.execute(_TABLE)
    op.execute(_DEFAULTS)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS commitment_policy")
