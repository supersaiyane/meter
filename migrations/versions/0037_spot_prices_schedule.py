"""The spot price collector's cadence, for every tenant that already exists.

Revision ID: 0037_spot_prices_schedule
Revises: 0036_savings_plan_rates_schedule
Create Date: 2026-10-08

TASK-P9-013, FEAT-071, P9 spec section 14.4, ADR-0012 and constraint 9.

`install_default_schedule` gives a tenant onboarded later the same row from
`finops_ingest.registry.DEFAULT_SCHEDULE`; this installs it for the tenants before it, and
`tests/ingest/test_registry.py` holds the two to the same words.

Backward compatible, constraint 12: one new schedule row an old worker has no collector for and
does not run. The downgrade removes it.
"""

from __future__ import annotations

from alembic import op

revision = "0037_spot_prices_schedule"
down_revision = "0036_savings_plan_rates_schedule"
branch_labels = None
depends_on = None

#: A copy of the `spot_prices` entry in `finops_ingest.registry.DEFAULT_SCHEDULE`.
_CADENCE_SECONDS = 28800
_REASON = (
    "Every 8 hours, with the other catalog collectors, P9 specification section 14.4. Each run "
    "reads every Region's window since its last read, one relay call a Region because "
    "DescribeSpotPriceHistory pages with botocore's own paginator: about 2,700 calls a month "
    "across 30 Regions (modelled), the figure spec section 14.5 gave, inside the Lambda free "
    "allowance and an S3 write each at 0.005 USD a thousand, AWS's published rate. Spot moves "
    "within hours, so a slower cadence would miss the daily low and high OPEN-18 keeps, and a "
    "faster one would only repeat the same prices. ADR-0012, ADR-0035, constraint 9, FEAT-071 "
    "and OPEN-18."
)
_COST_PER_RUN = "0.0002"
#: The reason as a SQL string literal: it holds apostrophes, which a literal doubles.
_REASON_LITERAL = _REASON.replace("'", "''")

_UP = (
    f"""
    INSERT INTO collector_schedule
        (tenant_id, collector, cadence_seconds, reason, est_cost_per_run, updated_by, runs_in)
    SELECT tenant_id, 'spot_prices', {_CADENCE_SECONDS}, '{_REASON_LITERAL}', {_COST_PER_RUN},
           'migration 0037_spot_prices_schedule', 'worker'
    FROM tenant
    ON CONFLICT (tenant_id, collector) DO NOTHING
    """,
)

_DOWN = ("DELETE FROM collector_schedule WHERE collector = 'spot_prices'",)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
