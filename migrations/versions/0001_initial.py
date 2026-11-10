"""The initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-24

Written as raw SQL rather than as `op.create_table` calls, deliberately.
PostgreSQL declarative partitioning and constraints such as `num_nonnulls` have
no faithful expression through the ORM helpers, and a migration that only
approximates `docs/07-DATA-MODEL.md` is worse than none: it produces a database
that passes review and then fails the invariant.

`finops_api/db/models.py` describes the same tables for the repository layer.
The two cannot drift, because
`tests/db/test_schema.py::test_the_models_match_the_migrated_database` compares
this migration against that metadata on a real PostgreSQL.

The partitioned tables are created here without partitions, on purpose. A
missing partition raises on insert, which is the wanted behaviour: a default
partition would turn a scheduling bug into silently misfiled cost. TASK-P0-032
adds the job that creates them a month ahead.
"""

from __future__ import annotations

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE tenant (
        tenant_id       UUID PRIMARY KEY,
        name            TEXT        NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_tenant__name UNIQUE (name)
    )
""",
    """
    CREATE TABLE principal (
        principal_id    UUID PRIMARY KEY,
        tenant_id       UUID        NOT NULL REFERENCES tenant(tenant_id),
        subject         TEXT        NOT NULL,
        display_name    TEXT        NOT NULL,
        email           TEXT,
        tier            TEXT        NOT NULL,
        is_global       BOOLEAN     NOT NULL DEFAULT false,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_seen_at    TIMESTAMPTZ,
        CONSTRAINT uq_principal__tenant_subject UNIQUE (tenant_id, subject),
        CONSTRAINT ck_principal__tier_valid
            CHECK (tier IN ('viewer', 'analyst', 'owner'))
    )
""",
    """
    CREATE TABLE principal_scope (
        tenant_id       UUID        NOT NULL REFERENCES tenant(tenant_id),
        principal_id    UUID        NOT NULL
                        REFERENCES principal(principal_id) ON DELETE CASCADE,
        account_id      TEXT,
        ou_id           TEXT,
        granted_via     TEXT        NOT NULL,
        resolved_at     TIMESTAMPTZ NOT NULL,
        expires_at      TIMESTAMPTZ NOT NULL,
        CONSTRAINT ck_principal_scope__one_target
            CHECK (num_nonnulls(account_id, ou_id) = 1)
    )
""",
    """
    CREATE INDEX ix_principal_scope__principal_expires
        ON principal_scope (principal_id, expires_at)
""",
    """
    CREATE TABLE cloud_account (
        account_pk              UUID PRIMARY KEY,
        tenant_id               UUID        NOT NULL REFERENCES tenant(tenant_id),
        provider                TEXT        NOT NULL,
        account_id              TEXT        NOT NULL,
        name                    TEXT        NOT NULL,
        status                  TEXT        NOT NULL,
        payer_account_id        TEXT,
        joined_at               TIMESTAMPTZ,
        onboarded_at            TIMESTAMPTZ,
        collector_role_arn      TEXT,
        external_id_ref         TEXT,
        role_health             TEXT        NOT NULL DEFAULT 'UNKNOWN',
        role_health_checked_at  TIMESTAMPTZ,
        role_health_error       TEXT,
        as_of                   TIMESTAMPTZ NOT NULL,
        collected_at            TIMESTAMPTZ NOT NULL,
        CONSTRAINT uq_cloud_account__tenant_provider_account
            UNIQUE (tenant_id, provider, account_id),
        CONSTRAINT ck_cloud_account__status_valid
            CHECK (status IN ('ACTIVE', 'SUSPENDED', 'PENDING', 'DEPARTED', 'UNKNOWN')),
        CONSTRAINT ck_cloud_account__role_health_valid
            CHECK (role_health IN ('HEALTHY', 'ACCESS_DENIED', 'NOT_DEPLOYED',
                                   'THROTTLED', 'UNKNOWN'))
    )
""",
    """
    CREATE INDEX ix_cloud_account__tenant_health
        ON cloud_account (tenant_id, role_health)
""",
    """
    CREATE TABLE org_node (
        node_pk         UUID PRIMARY KEY,
        tenant_id       UUID        NOT NULL REFERENCES tenant(tenant_id),
        node_id         TEXT        NOT NULL,
        node_type       TEXT        NOT NULL,
        parent_node_id  TEXT,
        name            TEXT        NOT NULL,
        path            TEXT        NOT NULL,
        depth           SMALLINT    NOT NULL,
        as_of           TIMESTAMPTZ NOT NULL,
        collected_at    TIMESTAMPTZ NOT NULL,
        CONSTRAINT uq_org_node__tenant_node UNIQUE (tenant_id, node_id),
        CONSTRAINT ck_org_node__type_valid
            CHECK (node_type IN ('ROOT', 'OU', 'ACCOUNT')),
        CONSTRAINT ck_org_node__root_has_no_parent
            CHECK ((node_type = 'ROOT') = (parent_node_id IS NULL)),
        CONSTRAINT fk_org_node__parent
            FOREIGN KEY (tenant_id, parent_node_id)
            REFERENCES org_node (tenant_id, node_id)
            DEFERRABLE INITIALLY DEFERRED
    )
""",
    """
    CREATE INDEX ix_org_node__tenant_parent ON org_node (tenant_id, parent_node_id)
""",
    """
    CREATE INDEX ix_org_node__tenant_path
        ON org_node (tenant_id, path text_pattern_ops)
""",
    """
    CREATE TABLE collector_schedule (
        tenant_id           UUID        NOT NULL REFERENCES tenant(tenant_id),
        collector           TEXT        NOT NULL,
        cadence_seconds     INTEGER     NOT NULL,
        reason              TEXT        NOT NULL,
        est_cost_per_run    NUMERIC(12, 6),
        is_enabled          BOOLEAN     NOT NULL DEFAULT true,
        updated_by          TEXT        NOT NULL,
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (tenant_id, collector),
        CONSTRAINT ck_collector_schedule__cadence_sane
            CHECK (cadence_seconds BETWEEN 60 AND 2592000)
    )
""",
    """
    CREATE TABLE ingest_run (
        run_id              UUID PRIMARY KEY,
        tenant_id           UUID        NOT NULL REFERENCES tenant(tenant_id),
        collector           TEXT        NOT NULL,
        scope_key           TEXT        NOT NULL,
        idempotency_key     TEXT        NOT NULL,
        started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        finished_at         TIMESTAMPTZ,
        status              TEXT        NOT NULL,
        items_written       INTEGER     NOT NULL DEFAULT 0,
        bytes_read          BIGINT      NOT NULL DEFAULT 0,
        error_type          TEXT,
        error_detail        TEXT,
        as_of_window_start  TIMESTAMPTZ NOT NULL,
        as_of_window_end    TIMESTAMPTZ NOT NULL,
        CONSTRAINT uq_ingest_run__idempotency_key UNIQUE (tenant_id, idempotency_key),
        CONSTRAINT ck_ingest_run__status_valid
            CHECK (status IN ('CLAIMED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'PARTIAL')),
        CONSTRAINT ck_ingest_run__error_type_valid
            CHECK (error_type IS NULL OR error_type IN
                  ('AccessDenied','Throttled','NotOptedIn','NoData','Unreachable','SchemaDrift')),
        CONSTRAINT ck_ingest_run__window_ordered
            CHECK (as_of_window_end >= as_of_window_start)
    )
""",
    """
    CREATE INDEX ix_ingest_run__tenant_collector_started
        ON ingest_run (tenant_id, collector, started_at DESC)
""",
    """
    CREATE INDEX ix_ingest_run__stale_claims
        ON ingest_run (status, started_at) WHERE status IN ('CLAIMED', 'RUNNING')
""",
    """
    CREATE TABLE ingest_watermark (
        tenant_id       UUID        NOT NULL REFERENCES tenant(tenant_id),
        collector       TEXT        NOT NULL,
        scope_key       TEXT        NOT NULL,
        as_of           TIMESTAMPTZ NOT NULL,
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (tenant_id, collector, scope_key)
    )
""",
    """
    CREATE TABLE sync_error (
        error_id        UUID PRIMARY KEY,
        tenant_id       UUID        NOT NULL REFERENCES tenant(tenant_id),
        collector       TEXT        NOT NULL,
        scope_key       TEXT        NOT NULL,
        error_type      TEXT        NOT NULL,
        detail          TEXT        NOT NULL,
        remediation     TEXT        NOT NULL,
        first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        occurrences     INTEGER     NOT NULL DEFAULT 1,
        CONSTRAINT uq_sync_error__scope
            UNIQUE (tenant_id, collector, scope_key, error_type),
        CONSTRAINT ck_sync_error__type_valid
            CHECK (error_type IN
                  ('AccessDenied','Throttled','NotOptedIn','NoData','Unreachable','SchemaDrift'))
    )
""",
    """
    CREATE TABLE cost_focus_daily (
        tenant_id                   UUID           NOT NULL,
        ingest_run_id               UUID           NOT NULL,
        source_fingerprint          TEXT           NOT NULL,
        as_of                       TIMESTAMPTZ    NOT NULL,
        collected_at                TIMESTAMPTZ    NOT NULL,
        billing_account_id          TEXT           NOT NULL,
        sub_account_id              TEXT,
        billing_period_start        DATE           NOT NULL,
        billing_period_end          DATE           NOT NULL,
        charge_period_start         TIMESTAMPTZ    NOT NULL,
        charge_period_end           TIMESTAMPTZ    NOT NULL,
        provider_name               TEXT           NOT NULL,
        publisher_name              TEXT,
        invoice_issuer_name         TEXT,
        service_name                TEXT           NOT NULL,
        service_category            TEXT,
        resource_id                 TEXT,
        resource_name               TEXT,
        region_id                   TEXT,
        availability_zone           TEXT,
        charge_category             TEXT           NOT NULL,
        charge_description          TEXT,
        sku_id                      TEXT,
        pricing_quantity            NUMERIC(30, 10),
        consumed_quantity           NUMERIC(30, 10),
        consumed_unit               TEXT,
        billed_cost                 NUMERIC(20, 10) NOT NULL,
        effective_cost              NUMERIC(20, 10) NOT NULL,
        list_cost                   NUMERIC(20, 10),
        contracted_cost             NUMERIC(20, 10),
        commitment_discount_id      TEXT,
        commitment_discount_type    TEXT,
        commitment_discount_status  TEXT,
        tags                        JSONB          NOT NULL DEFAULT '{}'::jsonb,
        PRIMARY KEY (tenant_id, billing_period_start, source_fingerprint)
    ) PARTITION BY RANGE (billing_period_start)
""",
    """
    CREATE INDEX ix_cost_focus_daily__account_period
        ON cost_focus_daily (tenant_id, sub_account_id, billing_period_start)
""",
    """
    CREATE INDEX ix_cost_focus_daily__service_period
        ON cost_focus_daily (tenant_id, service_name, billing_period_start)
""",
    """
    CREATE INDEX ix_cost_focus_daily__resource
        ON cost_focus_daily (tenant_id, resource_id) WHERE resource_id IS NOT NULL
""",
    """
    CREATE INDEX ix_cost_focus_daily__tags
        ON cost_focus_daily USING GIN (tags jsonb_path_ops)
""",
    """
    CREATE TABLE cost_provider_extra (
        tenant_id            UUID  NOT NULL,
        billing_period_start DATE  NOT NULL,
        source_fingerprint   TEXT  NOT NULL,
        provider_fields      JSONB NOT NULL,
        PRIMARY KEY (tenant_id, billing_period_start, source_fingerprint)
    ) PARTITION BY RANGE (billing_period_start)
""",
    """
    CREATE TABLE platform_cost (
        tenant_id       UUID           NOT NULL REFERENCES tenant(tenant_id),
        day             DATE           NOT NULL,
        module          TEXT           NOT NULL,
        service         TEXT           NOT NULL,
        amortized_cost  NUMERIC(20, 10) NOT NULL,
        as_of           TIMESTAMPTZ    NOT NULL,
        collected_at    TIMESTAMPTZ    NOT NULL,
        PRIMARY KEY (tenant_id, day, module, service)
    )
""",
    """
    CREATE TABLE audit_event (
        event_id        UUID PRIMARY KEY,
        tenant_id       UUID        NOT NULL REFERENCES tenant(tenant_id),
        principal_id    UUID        REFERENCES principal(principal_id),
        action          TEXT        NOT NULL,
        resource        TEXT        NOT NULL,
        scope_evaluated JSONB       NOT NULL,
        is_global_read  BOOLEAN     NOT NULL DEFAULT false,
        outcome         TEXT        NOT NULL,
        occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        request_id      TEXT        NOT NULL,
        CONSTRAINT ck_audit_event__outcome_valid CHECK (outcome IN ('ALLOWED', 'DENIED'))
    )
""",
    """
    CREATE INDEX ix_audit_event__tenant_occurred
        ON audit_event (tenant_id, occurred_at DESC)
""",
    """
    CREATE INDEX ix_audit_event__global_reads
        ON audit_event (tenant_id, occurred_at DESC) WHERE is_global_read
""",
)

#: Reverse dependency order, and no CASCADE. Constraint 12 in CLAUDE.md is
#: about staying forward compatible during a rolling deploy, not about
#: refusing to go back: a downgrade that does not work is a migration nobody
#: dares apply. Leaving CASCADE out means this order has to be right, and the
#: integration test proves it is rather than papering over it.
TEARDOWN_ORDER: tuple[str, ...] = (
    "audit_event",
    "platform_cost",
    "cost_provider_extra",
    "cost_focus_daily",
    "sync_error",
    "ingest_watermark",
    "ingest_run",
    "collector_schedule",
    "org_node",
    "cloud_account",
    "principal_scope",
    "principal",
    "tenant",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table in TEARDOWN_ORDER:
        op.drop_table(table)
