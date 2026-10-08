"""The instance catalog collector's cadence, for every tenant that already exists.

Revision ID: 0035_instance_catalog_schedule
Revises: 0034_price_catalog_schedule
Create Date: 2026-10-08

TASK-P9-005, FEAT-072, P9 spec section 14.4, ADR-0012 and constraint 9.

`install_default_schedule` gives a tenant onboarded later the same row from
`finops_ingest.registry.DEFAULT_SCHEDULE`; this installs it for the tenants before it, and
`tests/ingest/test_registry.py` holds the two to the same words.

Backward compatible, constraint 12: one new schedule row an old worker has no collector for and
does not run. The downgrade removes it.
"""

from __future__ import annotations

from alembic import op

revision = "0035_instance_catalog_schedule"
down_revision = "0034_price_catalog_schedule"
branch_labels = None
depends_on = None

#: A copy of the `instance_catalog` entry in `finops_ingest.registry.DEFAULT_SCHEDULE`.
_CADENCE_SECONDS = 28800
_REASON = (
    "Every 8 hours, P9 specification section 14.4, beside the price catalog whose Regions it "
    "places EC2's types in. A run is one DescribeInstanceTypes in the hub's Region, one in the "
    "Region it is compared with, and GetProducts only for a managed service whose price list "
    "changed since its classes were read, so a faster cadence would read the same descriptions "
    "again. A type AWS starts selling is described within 8 hours of being priced. Neither API "
    "makes a charge; the cost is the hub's endpoints processing the pages, modelled at a tenth "
    "of a cent a run. ADR-0012, ADR-0035, constraint 9 and FEAT-072."
)
_COST_PER_RUN = "0.001"
#: The reason as a SQL string literal: it holds apostrophes, which a literal doubles.
_REASON_LITERAL = _REASON.replace("'", "''")

_UP = (
    f"""
    INSERT INTO collector_schedule
        (tenant_id, collector, cadence_seconds, reason, est_cost_per_run, updated_by, runs_in)
    SELECT tenant_id, 'instance_catalog', {_CADENCE_SECONDS}, '{_REASON_LITERAL}', {_COST_PER_RUN},
           'migration 0035_instance_catalog_schedule', 'worker'
    FROM tenant
    ON CONFLICT (tenant_id, collector) DO NOTHING
    """,
)

_DOWN = ("DELETE FROM collector_schedule WHERE collector = 'instance_catalog'",)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
