"""The cadences of P13's collectors, and of retention_assistant, for the tenants that exist.

Revision ID: 0050_ai_collector_schedules
Revises: 0049_ai_provider_account
Create Date: 2026-10-12

`install_default_schedule` gives a new tenant every collector in `DEFAULT_SCHEDULE`, and nothing
gives one to a tenant that existed before the collector did, so each new collector installs its
own row, as 0043 did for `savings_ledger`. P13 added three, `bedrock_invocations` and
`retention_ai_usage` in TASK-P13-003 and `openai_usage` in TASK-P13-004, and writing this found
the fourth: `retention_assistant`, added with the erasure fixes on 2026-10-12, CHG-0171, had no
row for an existing tenant either, so it would never have run there, ISS-287.

Each is a copy of its `DEFAULT_SCHEDULE` entry, held to it by
`tests/ingest/test_registry.py`. Backward compatible, constraint 12: rows an old worker has no
collector for and does not run. The downgrade removes the rows this inserted and no other.
"""

from __future__ import annotations

from alembic import op

revision = "0050_ai_collector_schedules"
down_revision = "0049_ai_provider_account"
branch_labels = None
depends_on = None

_BY = "migration 0050_ai_collector_schedules"

#: Copies of the entries in `finops_ingest.registry.DEFAULT_SCHEDULE`: cadence, reason, cost.
_SCHEDULE: dict[str, tuple[int, str, str]] = {
    "retention_assistant": (
        86400,
        "A person's questions to the assistant are kept 90 days, OPEN-14. Daily, so a question "
        "leaves within a day of its window rather than within a week.",
        "0",
    ),
    "bedrock_invocations": (
        86400,
        "Who called which Bedrock model, from the invocation logs, P13 spec section 5.4. Daily, "
        "for the day before: the logs are complete for a day once it has ended, a cost per caller "
        "is modelled from the bill, which is itself daily, and reading more often would scan the "
        "same log events again. The cost is the bytes Logs Insights scans in the member account, "
        "USD 0.005 per GB at the list price, and the logs hold every prompt and response, so a "
        "busy account's day can be gigabytes: modelled at two GB a run, 0.01 USD, and not "
        "measured until an account is read, ISS-002. ADR-0012 and constraint 9.",
        "0.01",
    ),
    "retention_ai_usage": (
        86400,
        "Tokens and requests per caller are kept 13 months, P13 spec section 6, because a caller "
        "can name a person. Daily, so a day's usage leaves within a day of its window.",
        "0",
    ),
    "openai_usage": (
        86400,
        "OpenAI's cost and usage for each connected organization, P13 spec section 5.5. Daily, "
        "rereading the billing period to date: the reports are in daily buckets and OpenAI "
        "revises recent ones, so reading more often adds nothing and reading less often leaves "
        "the month's figure behind the bill. The reports are not billed, so a run costs the NAT "
        "gateway's per GB charge on a few kilobytes. ADR-0012 and constraint 9.",
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
