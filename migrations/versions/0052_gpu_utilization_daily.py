"""How busy each GPU instance's accelerators were, per day, and the collector's cadence.

Revision ID: 0052_gpu_utilization_daily
Revises: 0051_anthropic_schedule
Create Date: 2026-10-13

P13 spec sections 5.6 and 6, TASK-P13-006, FEAT-084, OPEN-33. The bill says what a GPU instance
cost and for how many hours; this says whether its accelerators did anything, from the CloudWatch
agent's NVIDIA metrics where an instance publishes them. An instance that publishes nothing has no
row, so the screen reads it as not published and never as nought percent; the constraints hold a
row to at least one accelerator and one reading, and its percentages to percentages.

And, as 0050 did for the others, the `gpu_utilization` cadence for every tenant that existed
before it, ISS-287, a copy of its `DEFAULT_SCHEDULE` entry held to it by
`tests/ingest/test_registry.py`. Backward compatible, constraint 12: a new table and rows an old
worker has no collector for. The downgrade removes both.
"""

from __future__ import annotations

from alembic import op

revision = "0052_gpu_utilization_daily"
down_revision = "0051_anthropic_schedule"
branch_labels = None
depends_on = None

_BY = "migration 0052_gpu_utilization_daily"

#: Copies of the entries in `finops_ingest.registry.DEFAULT_SCHEDULE`: cadence, reason, cost.
_SCHEDULE: dict[str, tuple[int, str, str]] = {
    "gpu_utilization": (
        86400,
        "How busy each GPU instance's accelerators were, P13 spec section 5.6. Daily, for the day "
        "before: the table holds a day's average and peak, so reading more often reads the same "
        "day again. The cost is GetMetricData's, USD 0.01 per 1,000 metrics at the list price, "
        "three a day for each accelerator of each GPU instance the bill names: modelled at 0.001 "
        "USD a run for one instance of eight accelerators, and not measured until an account is "
        "read, ISS-002. ADR-0012 and constraint 9.",
        "0.001",
    ),
}

_TABLE = """
CREATE TABLE IF NOT EXISTS gpu_utilization_daily (
    tenant_id        UUID          NOT NULL REFERENCES tenant(tenant_id),
    ingest_run_id    UUID          NOT NULL,
    account_id       TEXT          NOT NULL,
    region_id        TEXT          NOT NULL,
    instance_id      TEXT          NOT NULL,
    usage_date       DATE          NOT NULL,
    gpu_count        INTEGER       NOT NULL,
    average_percent  NUMERIC(5, 2) NOT NULL,
    peak_percent     NUMERIC(5, 2) NOT NULL,
    samples          INTEGER       NOT NULL,
    as_of            TIMESTAMPTZ   NOT NULL,
    collected_at     TIMESTAMPTZ   NOT NULL,
    CONSTRAINT pk_gpu_utilization_daily
        PRIMARY KEY (tenant_id, account_id, region_id, instance_id, usage_date),
    CONSTRAINT ck_gpu_utilization_daily__measured CHECK (gpu_count > 0 AND samples > 0),
    CONSTRAINT ck_gpu_utilization_daily__percentages CHECK (
        average_percent BETWEEN 0 AND 100 AND peak_percent BETWEEN 0 AND 100),
    CONSTRAINT ck_gpu_utilization_daily__peak_at_least_average
        CHECK (peak_percent >= average_percent),
    CONSTRAINT ck_gpu_utilization_daily__collected_after_true CHECK (collected_at >= as_of)
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
    op.execute("DROP TABLE IF EXISTS gpu_utilization_daily")
