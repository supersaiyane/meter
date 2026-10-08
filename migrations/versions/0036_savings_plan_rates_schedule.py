"""The Savings Plans rate collector's cadence, for every tenant that already exists.

Revision ID: 0036_savings_plan_rates_schedule
Revises: 0035_instance_catalog_schedule
Create Date: 2026-10-08

TASK-P9-012, FEAT-071, P9 spec section 14.4, ADR-0012 and constraint 9.

`install_default_schedule` gives a tenant onboarded later the same row from
`finops_ingest.registry.DEFAULT_SCHEDULE`; this installs it for the tenants before it, and
`tests/ingest/test_registry.py` holds the two to the same words.

Backward compatible, constraint 12: one new schedule row an old worker has no collector for and
does not run. The downgrade removes it.
"""

from __future__ import annotations

from alembic import op

revision = "0036_savings_plan_rates_schedule"
down_revision = "0035_instance_catalog_schedule"
branch_labels = None
depends_on = None

#: A copy of the `savings_plan_rates` entry in `finops_ingest.registry.DEFAULT_SCHEDULE`.
_CADENCE_SECONDS = 28800
_REASON = (
    "Every 8 hours, with the other catalog collectors, P9 specification section 14.4. Savings "
    "Plans rates carry no published version, so every Region is read each run and a Region whose "
    "rates have not moved is stored as nothing. A run is six relay calls a Region, one per plan "
    "type and payment option, so no answer outgrows the relay; about 180 calls a run across 30 "
    "Regions (modelled), inside the Lambda free allowance, and an S3 write each at 0.005 USD a "
    "thousand, AWS's published rate. ADR-0012, ADR-0035, constraint 9, FEAT-071 and OPEN-19."
)
_COST_PER_RUN = "0.001"
#: The reason as a SQL string literal: it holds apostrophes, which a literal doubles.
_REASON_LITERAL = _REASON.replace("'", "''")

_UP = (
    f"""
    INSERT INTO collector_schedule
        (tenant_id, collector, cadence_seconds, reason, est_cost_per_run, updated_by, runs_in)
    SELECT tenant_id, 'savings_plan_rates', {_CADENCE_SECONDS}, '{_REASON_LITERAL}',
           {_COST_PER_RUN}, 'migration 0036_savings_plan_rates_schedule', 'worker'
    FROM tenant
    ON CONFLICT (tenant_id, collector) DO NOTHING
    """,
)

_DOWN = ("DELETE FROM collector_schedule WHERE collector = 'savings_plan_rates'",)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
