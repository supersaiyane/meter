"""Split cost allocation columns on the cost line items.

Revision ID: 0021_split_cost_allocation
Revises: 0020_quotas
Create Date: 2026-10-01

TASK-P6-002. FEAT-035 reads split cost allocation data, and split cost allocation
data arrives in the billing export already being read. It is extra columns on the
rows the cost collector already writes rather than a separate source, so this widens
`cost_focus_daily` instead of adding a table.

**Every column is nullable and nothing is backfilled.** Constraint 12: old and new
task definitions run against the same schema during a rolling deploy, so a column
the previous release never writes has to be acceptable as null. Every existing row
keeps working, and a row written by the old collector mid deploy is a row with nulls
here rather than a row that fails to insert.

**Why there is no constraint tying a measure to a dimension.** The obvious one would
be that a split cost implies a cluster name. It is wrong: AWS reports a cluster's
unallocated remainder on rows carrying `unused_cost` and no workload at all, and that
figure is exactly what makes a cluster reconcile. A constraint demanding a workload
beside a cost would refuse it. The invariant that does hold, that a split figure is
never negative and a ratio is a fraction of one, is here.

**Why `split_cost` is not added to `billed_cost`.** Split cost allocation
re-attributes a charge already on the bill. Folding it into the existing money
columns would double count every clustered EC2 charge, which is the one defect a cost
product cannot ship. These measures are a breakdown of money already counted, and
the reconciliation test asserts that rather than assuming it.

The dimensions are stored as columns although AWS surfaces them as resource tags.
Two reasons. A JSONB lookup per row is a different query plan from a column read, and
this grain is queried on every container screen. And a tag can be renamed by whoever
owns the cluster while a column cannot, so a tag based read would quietly return
fewer clusters after somebody's unrelated tidy up.
"""

from __future__ import annotations

from alembic import op

revision = "0021_split_cost_allocation"
down_revision = "0020_quotas"
branch_labels = None
depends_on = None


_UP = (
    # The grain. Five dimensions, every one nullable: a charge that is not a pod's
    # charge carries none of them, which is most rows in most estates.
    """
    ALTER TABLE cost_focus_daily
        ADD COLUMN IF NOT EXISTS eks_cluster_name TEXT,
        ADD COLUMN IF NOT EXISTS eks_namespace TEXT,
        ADD COLUMN IF NOT EXISTS eks_workload_name TEXT,
        ADD COLUMN IF NOT EXISTS eks_workload_type TEXT,
        ADD COLUMN IF NOT EXISTS eks_pod_name TEXT
    """,
    # `split_usage` takes the wider scale because it is a quantity and the existing
    # quantity columns are NUMERIC(30, 10). The money ones match `billed_cost`, so a
    # sum across them cannot lose a scale.
    """
    ALTER TABLE cost_focus_daily
        ADD COLUMN IF NOT EXISTS split_cost NUMERIC(20, 10),
        ADD COLUMN IF NOT EXISTS split_usage NUMERIC(30, 10),
        ADD COLUMN IF NOT EXISTS split_usage_ratio NUMERIC(20, 10),
        ADD COLUMN IF NOT EXISTS unused_cost NUMERIC(20, 10)
    """,
    """
    ALTER TABLE cost_focus_daily
        DROP CONSTRAINT IF EXISTS ck_cost_focus_daily__split_not_negative
    """,
    """
    ALTER TABLE cost_focus_daily
        ADD CONSTRAINT ck_cost_focus_daily__split_not_negative
        CHECK (
            (split_cost IS NULL OR split_cost >= 0)
            AND (split_usage IS NULL OR split_usage >= 0)
            AND (unused_cost IS NULL OR unused_cost >= 0)
        )
    """,
    """
    ALTER TABLE cost_focus_daily
        DROP CONSTRAINT IF EXISTS ck_cost_focus_daily__split_ratio_is_a_fraction
    """,
    """
    ALTER TABLE cost_focus_daily
        ADD CONSTRAINT ck_cost_focus_daily__split_ratio_is_a_fraction
        CHECK (split_usage_ratio IS NULL OR (split_usage_ratio >= 0 AND split_usage_ratio <= 1))
    """,
    # Partial, because the container screens read only rows carrying a cluster and
    # those are a small minority of a cost table. A full index here would be mostly
    # nulls on the largest table in the schema.
    """
    CREATE INDEX IF NOT EXISTS ix_cost_focus_daily__cluster
        ON cost_focus_daily (tenant_id, billing_period_start, eks_cluster_name)
        WHERE eks_cluster_name IS NOT NULL
    """,
)


_DOWN = (
    "DROP INDEX IF EXISTS ix_cost_focus_daily__cluster",
    """
    ALTER TABLE cost_focus_daily
        DROP CONSTRAINT IF EXISTS ck_cost_focus_daily__split_ratio_is_a_fraction
    """,
    """
    ALTER TABLE cost_focus_daily
        DROP CONSTRAINT IF EXISTS ck_cost_focus_daily__split_not_negative
    """,
    # This drops rather than refusing, unlike 0018. Losing these columns loses the
    # container grain for periods already collected, and the next collection reads it
    # back out of the export, so the loss is bounded and recoverable.
    """
    ALTER TABLE cost_focus_daily
        DROP COLUMN IF EXISTS unused_cost,
        DROP COLUMN IF EXISTS split_usage_ratio,
        DROP COLUMN IF EXISTS split_usage,
        DROP COLUMN IF EXISTS split_cost,
        DROP COLUMN IF EXISTS eks_pod_name,
        DROP COLUMN IF EXISTS eks_workload_type,
        DROP COLUMN IF EXISTS eks_workload_name,
        DROP COLUMN IF EXISTS eks_namespace,
        DROP COLUMN IF EXISTS eks_cluster_name
    """,
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
