"""Anthropic's cadence for the tenants that exist. TASK-P13-005, FEAT-083.

Revision ID: 0051_anthropic_schedule
Revises: 0050_ai_collector_schedules
Create Date: 2026-10-12

As 0050 did for P13's first three collectors: `install_default_schedule` gives a new tenant
`anthropic_usage`, and this gives it to every tenant that existed before it, ISS-287. A copy of the
`DEFAULT_SCHEDULE` entry, held to it by `tests/ingest/test_registry.py`. Backward compatible,
constraint 12: a row an old worker has no collector for and does not run. The downgrade removes
the rows this inserted and no other.
"""

from __future__ import annotations

from alembic import op

revision = "0051_anthropic_schedule"
down_revision = "0050_ai_collector_schedules"
branch_labels = None
depends_on = None

_BY = "migration 0051_anthropic_schedule"

#: Copies of the entries in `finops_ingest.registry.DEFAULT_SCHEDULE`: cadence, reason, cost.
_SCHEDULE: dict[str, tuple[int, str, str]] = {
    "anthropic_usage": (
        86400,
        "Anthropic's cost and usage for each connected organization, P13 spec section 5.5. Daily, "
        "rereading the billing period to date: the cost report is in daily buckets and recent "
        "ones are revised, so reading more often adds nothing and reading less often leaves the "
        "month's figure behind the bill. The Admin API's reports are not billed, so a run costs "
        "the NAT gateway's per GB charge on a few kilobytes. ADR-0012 and constraint 9.",
        "0",
    ),
}


def _literal(text: str) -> str:
    """A SQL string literal, its apostrophes doubled."""
    return "'" + text.replace("'", "''") + "'"


def upgrade() -> None:
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
