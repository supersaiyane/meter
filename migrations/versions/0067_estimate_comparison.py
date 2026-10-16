"""Each created resource's estimate set against its bill. FEAT-097, TASK-P16-007.

Revision ID: 0067_estimate_comparison
Revises: 0066_plan_comments
Create Date: 2026-10-16

P16 spec section 5.6. `estimate_comparison` is one row per priced line a merged plan created, from
when Meter first sees the resource in the mapped state: `PENDING` while its thirty billed days are
not yet billed, then `WITHIN`, `ABOVE` or `BELOW` at list with list and effective cost scaled to a
month and the variance, or `NOT_COMPARED` with the reason. Checks hold each verdict's facts: a
verdict read from the bill carries its figures and window, one not compared carries a reason and
no figure, so a resource never billed cannot read as an accurate estimate. Payer wide, ADR-0025.

The `estimate_comparison` collector's cadence, daily, and the `retention_plans` job's, daily, are
installed for every tenant that exists. Backward compatible, constraint 12: a new table and
schedule rows nothing old reads. The downgrade removes them.
"""

from __future__ import annotations

from alembic import op

revision = "0067_estimate_comparison"
down_revision = "0066_plan_comments"
branch_labels = None
depends_on = None

_BY = "migration 0067_estimate_comparison"

_SCHEDULE = {
    "estimate_comparison": (
        86400,
        (
            "Sets each resource a merged plan created against thirty billed days once the bill "
            "reaches them, and restates the verdict as the bill is restated, P16 spec section 7. "
            "Daily, as the bill is read. It reads only Meter's own tables: modelled at 0.00 USD a "
            "run. ADR-0012 and constraint 9."
        ),
        "0.00",
    ),
    "retention_plans": (
        86400,
        (
            "Plans, their estimates, comments and comparisons are kept 400 days, P16 spec section "
            "6: the comparison needs sixty days after a merge, and a year of accuracy is what is "
            "published. Daily, so a plan leaves within a day of its window."
        ),
        "0",
    ),
}

_COMPARISON = """
CREATE TABLE IF NOT EXISTS estimate_comparison (
    plan_id            UUID           NOT NULL,
    address            TEXT           NOT NULL,
    tenant_id          UUID           NOT NULL REFERENCES tenant(tenant_id),
    resource_type      TEXT           NOT NULL,
    provider_id        TEXT,
    seen_at            TIMESTAMPTZ,
    window_start       DATE,
    window_end         DATE,
    estimate_monthly   NUMERIC(20, 6) NOT NULL,
    list_monthly       NUMERIC(20, 6),
    effective_monthly  NUMERIC(20, 6),
    variance_percent   NUMERIC(14, 4),
    verdict            TEXT           NOT NULL,
    reason             TEXT,
    judged_at          TIMESTAMPTZ    NOT NULL,
    as_of              TIMESTAMPTZ    NOT NULL,
    collected_at       TIMESTAMPTZ    NOT NULL,
    CONSTRAINT pk_estimate_comparison PRIMARY KEY (plan_id, address),
    CONSTRAINT fk_estimate_comparison__line FOREIGN KEY (plan_id, address)
        REFERENCES plan_estimate_line (plan_id, address),
    CONSTRAINT ck_estimate_comparison__verdict CHECK (
        verdict IN ('PENDING', 'WITHIN', 'ABOVE', 'BELOW', 'NOT_COMPARED')),
    CONSTRAINT ck_estimate_comparison__judged_has_figures CHECK (
        verdict NOT IN ('WITHIN', 'ABOVE', 'BELOW') OR (list_monthly IS NOT NULL
        AND effective_monthly IS NOT NULL AND variance_percent IS NOT NULL
        AND provider_id IS NOT NULL AND seen_at IS NOT NULL AND window_start IS NOT NULL)),
    CONSTRAINT ck_estimate_comparison__unjudged_has_no_figure CHECK (
        verdict IN ('WITHIN', 'ABOVE', 'BELOW') OR (list_monthly IS NULL
        AND effective_monthly IS NULL AND variance_percent IS NULL)),
    CONSTRAINT ck_estimate_comparison__not_compared_says_why CHECK (
        verdict <> 'NOT_COMPARED' OR length(trim(coalesce(reason, ''))) > 0),
    CONSTRAINT ck_estimate_comparison__pending_is_seen CHECK (
        verdict <> 'PENDING' OR (seen_at IS NOT NULL AND window_start IS NOT NULL)),
    CONSTRAINT ck_estimate_comparison__window CHECK (
        (window_start IS NULL) = (window_end IS NULL) AND (window_end IS NULL
        OR window_end > window_start)),
    CONSTRAINT ck_estimate_comparison__collected_after_true CHECK (collected_at >= as_of)
)
"""


def _literal(text: str) -> str:
    """A SQL string literal, its apostrophes doubled."""
    return "'" + text.replace("'", "''") + "'"


def upgrade() -> None:
    op.execute(_COMPARISON)
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
    op.execute("DROP TABLE IF EXISTS estimate_comparison")
