"""Which reversible fixes a tenant lets Meter merge. FEAT-094, TASK-P15-007.

Revision ID: 0063_merge_policy
Revises: 0062_fix_followed
Create Date: 2026-10-15

P15 spec section 5.2, OPEN-41, ADR-0038. One row per tenant and class of fix Meter may merge, with
the reason and who set it. It starts empty for every tenant, so nothing is merged until a person
whose scope is the organization names a class. A check holds every class to the reversible set,
`finops_core.domain.fixes.REVERSIBLE`, gp2 to gp3 alone, so a deletion cannot be named by any
path, constraint 11; a test holds the two lists equal.

Backward compatible, constraint 12: a new table nothing old reads. The downgrade removes it.
"""

from __future__ import annotations

from alembic import op

revision = "0063_merge_policy"
down_revision = "0062_fix_followed"
branch_labels = None
depends_on = None

_TABLE = """
CREATE TABLE IF NOT EXISTS merge_policy (
    tenant_id    UUID        NOT NULL REFERENCES tenant(tenant_id),
    waste_class  TEXT        NOT NULL,
    reason       TEXT        NOT NULL,
    set_by       TEXT        NOT NULL,
    set_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_merge_policy PRIMARY KEY (tenant_id, waste_class),
    CONSTRAINT ck_merge_policy__reversible CHECK (waste_class IN ('EBS_GP2_TO_GP3')),
    CONSTRAINT ck_merge_policy__reason CHECK (length(trim(reason)) > 0)
)
"""


def upgrade() -> None:
    op.execute(_TABLE)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS merge_policy")
