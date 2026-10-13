"""AWS's purchase recommendations, and the collector's cadence. FEAT-089, TASK-P14-006.

Revision ID: 0056_purchase_recommendation
Revises: 0055_commitment_policy
Create Date: 2026-10-13

P14 spec sections 5.1 and 6, OPEN-35. One row per Savings Plans type or reserved service, as AWS
last recommended it in the tenant's policy's term and payment option, or the typed cause it could
not be read with: a failure is a row with its cause and no figures, never a recommendation of
nought, constraint 5. The constraints hold a figure to a recommendation that was read, and a read
recommendation to a figure that matches its kind.

And the `purchase_recommendation` cadence for every tenant that existed before it, ISS-287, a copy
of its `DEFAULT_SCHEDULE` entry. Backward compatible, constraint 12. The downgrade removes both.
"""

from __future__ import annotations

from alembic import op

revision = "0056_purchase_recommendation"
down_revision = "0055_commitment_policy"
branch_labels = None
depends_on = None

_BY = "migration 0056_purchase_recommendation"

#: A copy of the entry in `finops_ingest.registry.DEFAULT_SCHEDULE`: cadence, reason, cost.
_SCHEDULE: dict[str, tuple[int, str, str]] = {
    "purchase_recommendation": (
        86400,
        (
            "AWS's purchase recommendations, P14 spec section 5.1. Daily: Cost Explorer refreshes "
            "them at least once a day, and a plan is drafted against them daily. Eight requests a "
            "run, two Savings Plans types and six reserved services, at USD 0.01 each at AWS's "
            "published price: modelled at 0.08 USD a run, and not measured until a payer is read, "
            "ISS-002. ADR-0012 and constraint 9."
        ),
        "0.08",
    ),
}

_TABLE = """
CREATE TABLE IF NOT EXISTS purchase_recommendation (
    tenant_id                   UUID            NOT NULL REFERENCES tenant(tenant_id),
    ingest_run_id               UUID            NOT NULL,
    kind                        TEXT            NOT NULL,
    program                     TEXT            NOT NULL,
    term_years                  INTEGER         NOT NULL,
    payment_option              TEXT            NOT NULL,
    lookback_days               INTEGER         NOT NULL,
    recommended                 BOOLEAN,
    hourly_commitment           NUMERIC(20, 10),
    units                       NUMERIC(20, 4),
    estimated_monthly_savings   NUMERIC(20, 10),
    estimated_savings_percent   NUMERIC(10, 4),
    upfront_cost                NUMERIC(20, 10),
    currency                    TEXT,
    failure_cause               TEXT,
    failure_detail              TEXT,
    as_of                       TIMESTAMPTZ     NOT NULL,
    collected_at                TIMESTAMPTZ     NOT NULL,
    CONSTRAINT pk_purchase_recommendation PRIMARY KEY (tenant_id, kind, program),
    CONSTRAINT ck_purchase_recommendation__kind CHECK (kind IN ('savings_plan', 'reservation')),
    CONSTRAINT ck_purchase_recommendation__read_or_failed CHECK (
        (failure_cause IS NULL AND recommended IS NOT NULL AND estimated_monthly_savings IS NOT NULL
            AND upfront_cost IS NOT NULL AND currency IS NOT NULL)
        OR (failure_cause IS NOT NULL AND recommended IS NULL AND hourly_commitment IS NULL
            AND units IS NULL AND estimated_monthly_savings IS NULL)),
    CONSTRAINT ck_purchase_recommendation__measure_of_its_kind CHECK (
        hourly_commitment IS NULL OR kind = 'savings_plan'),
    CONSTRAINT ck_purchase_recommendation__units_of_its_kind CHECK (
        units IS NULL OR kind = 'reservation'),
    CONSTRAINT ck_purchase_recommendation__collected_after_true CHECK (collected_at >= as_of)
)
"""


def _literal(text: str) -> str:
    """A SQL string literal, its apostrophes doubled."""
    return "'" + text.replace("'", "''") + "'"


def upgrade() -> None:
    op.execute(_TABLE)
    for collector, (cadence, reason, cost) in _SCHEDULE.items():
        op.execute(
            "INSERT INTO collector_schedule (tenant_id, collector, cadence_seconds, reason, "
            "est_cost_per_run, updated_by, runs_in) "
            f"SELECT tenant_id, {_literal(collector)}, {cadence}, {_literal(reason)}, {cost}, "
            f"{_literal(_BY)}, 'worker' FROM tenant "
            "ON CONFLICT (tenant_id, collector) DO NOTHING"
        )


def downgrade() -> None:
    op.execute(f"DELETE FROM collector_schedule WHERE updated_by = {_literal(_BY)}")
    op.execute("DROP TABLE IF EXISTS purchase_recommendation")
