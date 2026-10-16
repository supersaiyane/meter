"""A Terraform plan as Meter keeps it, and its estimate. FEAT-095, TASK-P16-005.

Revision ID: 0065_plan_estimates
Revises: 0064_fixes_screen
Create Date: 2026-10-16

P16 spec sections 5.2, 5.7, 5.8 and 6. `terraform_plan` is one row per plan received for a pull
request, a folder and a commit, unique on the four, so a plan sent twice is one plan: its status,
`RECEIVED`, `PRICED` or `REFUSED`, and a refusal's reason, which a check requires. No plan is stored
whole: `planned_change` holds only what the reduction kept, spec section 5.2, the address, type,
actions and Region of each change and its priced attributes before and after, with the names of
those Terraform knows only after apply and of those withheld as sensitive.

`plan_estimate` is one per plan priced: its monthly figures before, after and the change, and how
many lines were priced and how many not. `plan_estimate_line` is one per change: its figures, or the
reason it has none, and its notes and components, each component with its unit price, price
identifier and version as figures. A check holds that a line with a reason carries no figure and a
line without one carries at least one, constraint 5: a resource Meter could not price is never
nought.

A plan names no account until it is applied, so all four are payer wide, ADR-0025. The
`plan_estimates` collector's cadence, every ten minutes, is installed for every tenant that exists,
as `DEFAULT_SCHEDULE` installs it for a new one. Backward compatible, constraint 12: new tables
nothing old reads, and a schedule row nothing old runs. The downgrade removes them.
"""

from __future__ import annotations

from alembic import op

revision = "0065_plan_estimates"
down_revision = "0064_fixes_screen"
branch_labels = None
depends_on = None

_BY = "migration 0065_plan_estimates"

_SCHEDULE = {
    "plan_estimates": (
        600,
        (
            "Prices each Terraform plan received from the catalog Meter already holds and writes "
            "its estimate, P16 spec section 7. Every ten minutes, so an estimate is written within "
            "ten minutes of its plan arriving. It reads only Meter's own tables: modelled at 0.00 "
            "USD a run. ADR-0012 and constraint 9."
        ),
        "0.00",
    ),
}

_PLAN = r"""
CREATE TABLE IF NOT EXISTS terraform_plan (
    plan_id            UUID        NOT NULL,
    tenant_id          UUID        NOT NULL REFERENCES tenant(tenant_id),
    repository         TEXT        NOT NULL,
    pull_request       INTEGER     NOT NULL,
    head_sha           TEXT        NOT NULL,
    folder             TEXT        NOT NULL DEFAULT '',
    state_reference    TEXT,
    route              TEXT        NOT NULL,
    status             TEXT        NOT NULL,
    reason             TEXT,
    format_version     TEXT,
    terraform_version  TEXT,
    received_at        TIMESTAMPTZ NOT NULL,
    as_of              TIMESTAMPTZ NOT NULL,
    collected_at       TIMESTAMPTZ NOT NULL,
    CONSTRAINT pk_terraform_plan PRIMARY KEY (plan_id),
    CONSTRAINT uq_terraform_plan__commit
        UNIQUE (tenant_id, repository, pull_request, folder, head_sha),
    CONSTRAINT ck_terraform_plan__repository
        CHECK (repository ~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'),
    CONSTRAINT ck_terraform_plan__pull_request CHECK (pull_request > 0),
    CONSTRAINT ck_terraform_plan__head CHECK (head_sha ~ '^[0-9a-f]{7,64}$'),
    CONSTRAINT ck_terraform_plan__folder CHECK (
        folder = '' OR (folder !~ '^/' AND folder !~ '/$' AND folder !~ '(^|/)\.\.?(/|$)')),
    CONSTRAINT ck_terraform_plan__route CHECK (length(trim(route)) > 0),
    CONSTRAINT ck_terraform_plan__status CHECK (status IN ('RECEIVED', 'PRICED', 'REFUSED')),
    CONSTRAINT ck_terraform_plan__refusal_says_why CHECK (
        status <> 'REFUSED' OR length(trim(coalesce(reason, ''))) > 0),
    CONSTRAINT ck_terraform_plan__read_has_a_format CHECK (
        status = 'REFUSED' OR format_version IS NOT NULL),
    CONSTRAINT ck_terraform_plan__collected_after_true CHECK (collected_at >= as_of)
)
"""

_CHANGE = """
CREATE TABLE IF NOT EXISTS planned_change (
    plan_id        UUID        NOT NULL REFERENCES terraform_plan(plan_id),
    tenant_id      UUID        NOT NULL REFERENCES tenant(tenant_id),
    address        TEXT        NOT NULL,
    resource_type  TEXT        NOT NULL,
    actions        TEXT[]      NOT NULL,
    region         TEXT,
    before         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    after          JSONB       NOT NULL DEFAULT '{}'::jsonb,
    unknown        TEXT[]      NOT NULL DEFAULT '{}',
    withheld       TEXT[]      NOT NULL DEFAULT '{}',
    CONSTRAINT pk_planned_change PRIMARY KEY (plan_id, address),
    CONSTRAINT ck_planned_change__type CHECK (resource_type ~ '^aws_[a-z0-9_]+$'),
    CONSTRAINT ck_planned_change__actions CHECK (
        cardinality(actions) > 0 AND actions <@ ARRAY['create', 'update', 'delete']::text[])
)
"""

_ESTIMATE = """
CREATE TABLE IF NOT EXISTS plan_estimate (
    plan_id         UUID           NOT NULL REFERENCES terraform_plan(plan_id),
    tenant_id       UUID           NOT NULL REFERENCES tenant(tenant_id),
    monthly_before  NUMERIC(20, 6) NOT NULL,
    monthly_after   NUMERIC(20, 6) NOT NULL,
    monthly_change  NUMERIC(20, 6) NOT NULL,
    currency        TEXT           NOT NULL,
    priced_lines    INTEGER        NOT NULL,
    unpriced_lines  INTEGER        NOT NULL,
    priced_at       TIMESTAMPTZ    NOT NULL,
    as_of           TIMESTAMPTZ    NOT NULL,
    collected_at    TIMESTAMPTZ    NOT NULL,
    CONSTRAINT pk_plan_estimate PRIMARY KEY (plan_id),
    CONSTRAINT ck_plan_estimate__currency CHECK (currency = 'USD'),
    CONSTRAINT ck_plan_estimate__lines CHECK (priced_lines >= 0 AND unpriced_lines >= 0),
    CONSTRAINT ck_plan_estimate__change CHECK (monthly_change = monthly_after - monthly_before),
    CONSTRAINT ck_plan_estimate__collected_after_true CHECK (collected_at >= as_of)
)
"""

_LINE = """
CREATE TABLE IF NOT EXISTS plan_estimate_line (
    plan_id         UUID           NOT NULL REFERENCES plan_estimate(plan_id),
    tenant_id       UUID           NOT NULL REFERENCES tenant(tenant_id),
    address         TEXT           NOT NULL,
    resource_type   TEXT           NOT NULL,
    actions         TEXT[]         NOT NULL,
    region          TEXT,
    monthly_before  NUMERIC(20, 6),
    monthly_after   NUMERIC(20, 6),
    reason          TEXT,
    notes           TEXT[]         NOT NULL DEFAULT '{}',
    components      JSONB          NOT NULL DEFAULT '[]'::jsonb,
    CONSTRAINT pk_plan_estimate_line PRIMARY KEY (plan_id, address),
    CONSTRAINT ck_plan_estimate_line__figure_or_reason CHECK (
        (reason IS NULL) = (monthly_before IS NOT NULL OR monthly_after IS NOT NULL)),
    CONSTRAINT ck_plan_estimate_line__reason CHECK (
        reason IS NULL OR length(trim(reason)) > 0),
    CONSTRAINT ck_plan_estimate_line__unpriced_has_no_parts CHECK (
        reason IS NULL OR components = '[]'::jsonb)
)
"""


def _literal(text: str) -> str:
    """A SQL string literal, its apostrophes doubled."""
    return "'" + text.replace("'", "''") + "'"


def upgrade() -> None:
    op.execute(_PLAN)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_terraform_plan__status "
        "ON terraform_plan (tenant_id, status, received_at)"
    )
    op.execute(_CHANGE)
    op.execute(_ESTIMATE)
    op.execute(_LINE)
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
    op.execute("DROP TABLE IF EXISTS plan_estimate_line")
    op.execute("DROP TABLE IF EXISTS plan_estimate")
    op.execute("DROP TABLE IF EXISTS planned_change")
    op.execute("DROP TABLE IF EXISTS terraform_plan")
