"""The price catalog collector's cadence, for every tenant that already exists.

Revision ID: 0034_price_catalog_schedule
Revises: 0033_price_catalog
Create Date: 2026-10-08

TASK-P9-004, FEAT-071, P9 spec section 14.4, ADR-0012 and constraint 9.

`install_default_schedule` gives a tenant onboarded later the same row from
`finops_ingest.registry.DEFAULT_SCHEDULE`; this installs it for the tenants before it, and
`tests/ingest/test_registry.py` holds the two to the same words.

Backward compatible, constraint 12: one new schedule row an old worker has no collector for and
does not run. The downgrade removes it.
"""

from __future__ import annotations

from alembic import op

revision = "0034_price_catalog_schedule"
down_revision = "0033_price_catalog"
branch_labels = None
depends_on = None

#: A copy of the `price_catalog` entry in `finops_ingest.registry.DEFAULT_SCHEDULE`.
_CADENCE_SECONDS = 28800
_REASON = (
    "Every 8 hours, P9 specification section 14.4. A run asks each of five services for "
    "its current price list version in every Region and loads only a version it does not "
    "hold, so a run that finds nothing new is five ListPriceLists calls and writes "
    "nothing, and a faster cadence would only repeat them. A version AWS publishes is "
    "loaded within 8 hours, so a saving is never quoted from superseded prices for longer "
    "than that. The Price List API makes no charge; a load costs the hub's endpoint "
    "processing its pages at 0.01 USD a GB, AWS's published rate, and a full load of all "
    "five services in every Region is modelled at under one GB, so the figure below "
    "bounds a full load and a quiet run costs nothing. ADR-0012, ADR-0035, constraint 9 "
    "and FEAT-071."
)
_COST_PER_RUN = "0.01"
#: The reason as a SQL string literal: it holds apostrophes, which a literal doubles.
_REASON_LITERAL = _REASON.replace("'", "''")

_UP = (
    f"""
    INSERT INTO collector_schedule
        (tenant_id, collector, cadence_seconds, reason, est_cost_per_run, updated_by, runs_in)
    SELECT tenant_id, 'price_catalog', {_CADENCE_SECONDS}, '{_REASON_LITERAL}', {_COST_PER_RUN},
           'migration 0034_price_catalog_schedule', 'worker'
    FROM tenant
    ON CONFLICT (tenant_id, collector) DO NOTHING
    """,
)

_DOWN = ("DELETE FROM collector_schedule WHERE collector = 'price_catalog'",)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
