"""Each estimate's comment, and each pull request's state. FEAT-096, TASK-P16-006.

Revision ID: 0066_plan_comments
Revises: 0065_plan_estimates
Create Date: 2026-10-16

P16 spec sections 5.5 and 7. `plan_estimate` gains what happened to its comment: `WRITTEN`, with the
comment's identifier, link and time; `SUPERSEDED`, when the pull request's head moved on before it
was written, or the pull request closed; or `FAILED`, with the code host's typed cause. Each is held
by a check. An estimate with no status yet is waiting for the next run.

`plan_pull_request` is each pull request a plan came from, as the code host last reported it: open,
merged or closed, its head commit, and when Meter first saw it merged, which the comparison with the
bill reads, TASK-P16-007. Payer wide, ADR-0025, as its plans are.

The `plan_comments` collector's cadence, every ten minutes, is installed for every tenant that
exists. Backward compatible, constraint 12: nullable columns nothing old reads, a new table, and a
schedule row nothing old runs. The downgrade removes them.
"""

from __future__ import annotations

from alembic import op

revision = "0066_plan_comments"
down_revision = "0065_plan_estimates"
branch_labels = None
depends_on = None

_BY = "migration 0066_plan_comments"

_SCHEDULE = {
    "plan_comments": (
        600,
        (
            "Writes or edits each estimate's one comment on its pull request and follows the pull "
            "request until it merges or closes, P16 spec section 7. Every ten minutes, so the "
            "comment follows its estimate within the next run. GitHub's API is free within its "
            "rate limit: modelled at 0.00 USD a run. ADR-0012 and constraint 9."
        ),
        "0.00",
    ),
}

_COLUMNS = (
    "ALTER TABLE plan_estimate ADD COLUMN IF NOT EXISTS comment_status TEXT",
    "ALTER TABLE plan_estimate ADD COLUMN IF NOT EXISTS comment_id TEXT",
    "ALTER TABLE plan_estimate ADD COLUMN IF NOT EXISTS comment_url TEXT",
    "ALTER TABLE plan_estimate ADD COLUMN IF NOT EXISTS commented_at TIMESTAMPTZ",
    "ALTER TABLE plan_estimate ADD COLUMN IF NOT EXISTS comment_reason TEXT",
    "ALTER TABLE plan_estimate ADD COLUMN IF NOT EXISTS comment_failure_cause TEXT",
)

_CHECKS = (
    "ALTER TABLE plan_estimate ADD CONSTRAINT ck_plan_estimate__comment_status CHECK ("
    "comment_status IS NULL OR comment_status IN ('WRITTEN', 'SUPERSEDED', 'FAILED'))",
    "ALTER TABLE plan_estimate ADD CONSTRAINT ck_plan_estimate__written_names_it CHECK ("
    "coalesce(comment_status, '') <> 'WRITTEN' OR (comment_id IS NOT NULL "
    "AND comment_url IS NOT NULL AND commented_at IS NOT NULL))",
    "ALTER TABLE plan_estimate ADD CONSTRAINT ck_plan_estimate__unwritten_says_why CHECK ("
    "coalesce(comment_status, '') NOT IN ('SUPERSEDED', 'FAILED') "
    "OR length(trim(coalesce(comment_reason, ''))) > 0)",
    "ALTER TABLE plan_estimate ADD CONSTRAINT ck_plan_estimate__failure_typed CHECK ("
    "(coalesce(comment_status, '') = 'FAILED') = (comment_failure_cause IS NOT NULL))",
    "ALTER TABLE plan_estimate ADD CONSTRAINT ck_plan_estimate__cause CHECK ("
    "comment_failure_cause IS NULL OR comment_failure_cause IN ("
    "'AccessDenied', 'Misconfigured', 'SchemaDrift'))",
)

_PULL_REQUEST = r"""
CREATE TABLE IF NOT EXISTS plan_pull_request (
    tenant_id       UUID        NOT NULL REFERENCES tenant(tenant_id),
    repository      TEXT        NOT NULL,
    pull_request    INTEGER     NOT NULL,
    state           TEXT        NOT NULL,
    head_sha        TEXT        NOT NULL,
    merged_seen_at  TIMESTAMPTZ,
    as_of           TIMESTAMPTZ NOT NULL,
    collected_at    TIMESTAMPTZ NOT NULL,
    CONSTRAINT pk_plan_pull_request PRIMARY KEY (tenant_id, repository, pull_request),
    CONSTRAINT ck_plan_pull_request__state CHECK (state IN ('OPEN', 'MERGED', 'CLOSED')),
    CONSTRAINT ck_plan_pull_request__merged_seen CHECK (
        (state = 'MERGED') = (merged_seen_at IS NOT NULL)),
    CONSTRAINT ck_plan_pull_request__collected_after_true CHECK (collected_at >= as_of)
)
"""


def _literal(text: str) -> str:
    """A SQL string literal, its apostrophes doubled."""
    return "'" + text.replace("'", "''") + "'"


def upgrade() -> None:
    for statement in _COLUMNS:
        op.execute(statement)
    for statement in _CHECKS:
        op.execute(statement)
    op.execute(_PULL_REQUEST)
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
    op.execute("DROP TABLE IF EXISTS plan_pull_request")
    for name in (
        "cause",
        "failure_typed",
        "unwritten_says_why",
        "written_names_it",
        "comment_status",
    ):
        op.execute(f"ALTER TABLE plan_estimate DROP CONSTRAINT IF EXISTS ck_plan_estimate__{name}")
    for column in (
        "comment_failure_cause",
        "comment_reason",
        "commented_at",
        "comment_url",
        "comment_id",
        "comment_status",
    ):
        op.execute(f"ALTER TABLE plan_estimate DROP COLUMN IF EXISTS {column}")
