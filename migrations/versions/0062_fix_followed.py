"""When a fix merged or closed, and what each volume is. FEAT-092, TASK-P15-006.

Revision ID: 0062_fix_followed
Revises: 0061_recommendation_gp3_figures
Create Date: 2026-10-15

P15 spec section 5.6, merged is not done. A merged fix's recommendation is DONE when the inventory
sees the change, so the time it merged is kept, `merged_at`, beside `closed_at` for one closed
without merging: a reading older than the merge proves nothing.

A removal is seen when the inventory no longer lists the resource. A gp2 volume moved to gp3 is
seen when the volume reads gp3, and nothing kept a volume's type: the volume pass read it each run
and kept only the gp2 ones. `volume_observation` keeps what it read of every volume, its type and
size, one row each, restated every run.

Backward compatible, constraint 12: nullable columns and a new table nothing old reads. The
downgrade removes them.
"""

from __future__ import annotations

from alembic import op

revision = "0062_fix_followed"
down_revision = "0061_recommendation_gp3_figures"
branch_labels = None
depends_on = None

_OBSERVATION = """
CREATE TABLE IF NOT EXISTS volume_observation (
    tenant_id       UUID        NOT NULL REFERENCES tenant(tenant_id),
    sub_account_id  TEXT        NOT NULL,
    resource_id     TEXT        NOT NULL,
    region_id       TEXT        NOT NULL,
    volume_type     TEXT        NOT NULL,
    size_gib        INTEGER     NOT NULL,
    as_of           TIMESTAMPTZ NOT NULL,
    collected_at    TIMESTAMPTZ NOT NULL,
    CONSTRAINT pk_volume_observation PRIMARY KEY (tenant_id, sub_account_id, resource_id),
    CONSTRAINT ck_volume_observation__type CHECK (length(trim(volume_type)) > 0),
    CONSTRAINT ck_volume_observation__size CHECK (size_gib > 0),
    CONSTRAINT ck_volume_observation__collected_after_true CHECK (collected_at >= as_of)
)
"""


def upgrade() -> None:
    op.execute(
        "ALTER TABLE fix_pull_request ADD COLUMN IF NOT EXISTS merged_at TIMESTAMPTZ, "
        "ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE fix_pull_request ADD CONSTRAINT ck_fix_pull_request__merged_when CHECK ("
        "(status = 'MERGED') = (merged_at IS NOT NULL))"
    )
    op.execute(_OBSERVATION)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS volume_observation")
    op.execute(
        "ALTER TABLE fix_pull_request DROP CONSTRAINT IF EXISTS ck_fix_pull_request__merged_when"
    )
    op.execute(
        "ALTER TABLE fix_pull_request DROP COLUMN IF EXISTS closed_at, "
        "DROP COLUMN IF EXISTS merged_at"
    )
