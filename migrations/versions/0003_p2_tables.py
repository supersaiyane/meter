"""The six P2 tables, for query cost governance.

Revision ID: 0003_p2_tables
Revises: 0002_cost_monthly
Create Date: 2026-08-30

Faithful to section 5 of the P2 specification, which extends
`docs/07-DATA-MODEL.md` rather than inventing a second set of conventions.

Three constraints here are the feature rather than hygiene, per constraint 11.

`ck_enforcement_action__restrictive_expires` is what stops a deny becoming
permanent. It is a database constraint and not a service level check because two
paths write this table, the control function and the API, and application code
is not what holds when that is true.

`ck_query_finding__measured_has_runs` closes both directions: a modelled row
cannot claim a measured run count, and a measured row cannot omit one. A figure
that says measured and has measured nothing is the exact lie this product exists
to prevent.

`remediation_change.before` is `NOT NULL` because it is the undo. A change that
cannot say what it replaced is a change nobody will dare apply, and TASK-P2-019
depends on every rewrite being reversible.

Additive only, per constraint 12. Nothing is renamed and nothing is dropped, so
the old and new task definitions run against this schema together.
"""

from __future__ import annotations

from alembic import op

revision = "0003_p2_tables"
down_revision = "0002_cost_monthly"
branch_labels = None
depends_on = None

STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE grafana_instance (
        instance_id        UUID PRIMARY KEY,
        tenant_id          UUID        NOT NULL REFERENCES tenant(tenant_id),
        kind               TEXT        NOT NULL,
        name               TEXT        NOT NULL,
        endpoint           TEXT        NOT NULL,
        account_id         TEXT,
        region_id          TEXT,
        credential_ref     TEXT,
        reachable          BOOLEAN     NOT NULL DEFAULT true,
        unreachable_reason TEXT,
        as_of              TIMESTAMPTZ NOT NULL,
        collected_at       TIMESTAMPTZ NOT NULL,
        CONSTRAINT uq_grafana_instance__tenant_endpoint UNIQUE (tenant_id, endpoint),
        CONSTRAINT ck_grafana_instance__kind_valid
            CHECK (kind IN ('AMG', 'SELF_HOSTED', 'CLOUD')),
        CONSTRAINT ck_grafana_instance__amg_located
            CHECK ((kind = 'AMG') = (account_id IS NOT NULL AND region_id IS NOT NULL)),
        CONSTRAINT ck_grafana_instance__unreachable_has_reason
            CHECK (reachable OR unreachable_reason IS NOT NULL)
    )
""",
    """
    CREATE TABLE query_definition (
        query_id        UUID PRIMARY KEY,
        tenant_id       UUID        NOT NULL REFERENCES tenant(tenant_id),
        instance_id     UUID        NOT NULL REFERENCES grafana_instance(instance_id),
        origin          TEXT        NOT NULL,
        dashboard_uid   TEXT,
        dashboard_title TEXT,
        folder_uid      TEXT,
        panel_id        TEXT,
        ref_id          TEXT,
        engine          TEXT        NOT NULL,
        query_text      TEXT        NOT NULL,
        fingerprint     TEXT        NOT NULL,
        target          JSONB       NOT NULL,
        refresh_seconds INTEGER,
        range_seconds   INTEGER     NOT NULL,
        last_editor     TEXT,
        as_of           TIMESTAMPTZ NOT NULL,
        collected_at    TIMESTAMPTZ NOT NULL,
        CONSTRAINT uq_query_definition__fingerprint
            UNIQUE (tenant_id, instance_id, fingerprint),
        CONSTRAINT ck_query_definition__origin_valid
            CHECK (origin IN ('PANEL', 'ALERT_RULE')),
        CONSTRAINT ck_query_definition__engine_valid
            CHECK (engine IN ('LOGS_INSIGHTS', 'METRIC_SEARCH', 'METRIC_INSIGHTS',
                              'PROMQL', 'OTHER')),
        CONSTRAINT ck_query_definition__panel_has_refresh
            CHECK ((origin = 'ALERT_RULE') OR (refresh_seconds IS NOT NULL))
    )
""",
    """
    CREATE TABLE query_finding (
        finding_id         UUID PRIMARY KEY,
        tenant_id          UUID        NOT NULL REFERENCES tenant(tenant_id),
        query_id           UUID        NOT NULL REFERENCES query_definition(query_id),
        run_date           DATE        NOT NULL,
        runs_per_day       NUMERIC(12,2) NOT NULL,
        scan_bytes_per_run BIGINT,
        metrics_per_call   INTEGER,
        cost_month_usd     NUMERIC(20,10) NOT NULL,
        provenance         TEXT        NOT NULL,
        measured_runs      INTEGER,
        severity           TEXT        NOT NULL,
        owner_email        TEXT,
        owner_source       TEXT,
        why                TEXT        NOT NULL,
        as_of              TIMESTAMPTZ NOT NULL,
        collected_at       TIMESTAMPTZ NOT NULL,
        CONSTRAINT uq_query_finding__query_day UNIQUE (tenant_id, query_id, run_date),
        CONSTRAINT ck_query_finding__provenance_valid
            CHECK (provenance IN ('measured', 'modelled')),
        CONSTRAINT ck_query_finding__measured_has_runs
            CHECK ((provenance = 'modelled' AND measured_runs IS NULL)
                   OR (provenance = 'measured' AND measured_runs IS NOT NULL))
    )
""",
    """
    CREATE INDEX ix_query_finding__cost
        ON query_finding (tenant_id, run_date, cost_month_usd DESC)
""",
    """
    CREATE TABLE folder_team_map (
        tenant_id   UUID NOT NULL REFERENCES tenant(tenant_id),
        instance_id UUID NOT NULL REFERENCES grafana_instance(instance_id),
        folder_uid  TEXT NOT NULL,
        owner_email TEXT NOT NULL,
        team        TEXT,
        updated_by  TEXT NOT NULL,
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (tenant_id, instance_id, folder_uid)
    )
""",
    """
    CREATE TABLE enforcement_action (
        action_id      UUID PRIMARY KEY,
        tenant_id      UUID        NOT NULL REFERENCES tenant(tenant_id),
        level          TEXT        NOT NULL,
        principal_arn  TEXT        NOT NULL,
        trigger_reason TEXT        NOT NULL,
        observed_rate  NUMERIC(12,2) NOT NULL,
        threshold      NUMERIC(12,2) NOT NULL,
        applied_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        expires_at     TIMESTAMPTZ,
        removed_at     TIMESTAMPTZ,
        removed_by     TEXT,
        CONSTRAINT ck_enforcement_action__level_valid
            CHECK (level IN ('ALERT', 'THROTTLE', 'DENY')),
        CONSTRAINT ck_enforcement_action__restrictive_expires
            CHECK (level = 'ALERT' OR expires_at IS NOT NULL)
    )
""",
    """
    CREATE INDEX ix_enforcement_action__active
        ON enforcement_action (tenant_id, expires_at) WHERE removed_at IS NULL
""",
    """
    CREATE TABLE remediation_change (
        change_id   UUID PRIMARY KEY,
        tenant_id   UUID        NOT NULL REFERENCES tenant(tenant_id),
        query_id    UUID        REFERENCES query_definition(query_id),
        instance_id UUID        NOT NULL REFERENCES grafana_instance(instance_id),
        kind        TEXT        NOT NULL,
        before      JSONB       NOT NULL,
        after       JSONB       NOT NULL,
        applied_by  TEXT        NOT NULL,
        applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        reverted_at TIMESTAMPTZ,
        reverted_by TEXT,
        CONSTRAINT ck_remediation_change__kind_valid
            CHECK (kind IN ('WORKSPACE_FLOOR', 'PANEL_REWRITE'))
    )
""",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Reverse order, because each drop must not orphan a foreign key.
    for table in (
        "remediation_change",
        "enforcement_action",
        "folder_team_map",
        "query_finding",
        "query_definition",
        "grafana_instance",
    ):
        op.drop_table(table)
