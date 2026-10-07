"""The price catalog: AWS's prices, its instance types, volume types and spot prices.

Revision ID: 0033_price_catalog
Revises: 0032_reconciliation_screen
Create Date: 2026-10-08

TASK-P9-003, P9 spec sections 5.3, 5.4, 6 and 14.7, and the correction to 5.3 of 2026-10-08.

**Every invariant a constraint, constraint 11.** A price belongs to a version that was recorded,
by a foreign key. A price is one offer term: its recurring price and its upfront fee are never
negative and never both nought, because AWS's real price list sells All Upfront reservations at
nought an hour beside the fee, and refusing every nought would refuse all of them. A reservation
names its length and how it is paid, and an on demand price has neither and nothing up front. An
instance type has vCPUs and memory, and a burstable one has the baseline it earns credits at, with
its source. A spot pool is one row, and a day's low is never above its high.

**Per tenant, as every table is.** AWS's prices are public, and the spec's table drew them without
a tenant. They carry `tenant_id` anyway, under the guard's tenant rule, because a shared table
would need a new rule in the guard, the one place two implementations of an authorization rule
must never appear, ADR-0009, to save copies a hub with one tenant does not make. A second tenant
on one hub would hold a second copy of the catalog; moving it to shared tables then is a
migration and an ADR, recorded here so it is a decision rather than a discovery.

**The recommendation names its target by price, from one version.** Four nullable columns, and a
composite foreign key from the target to a recorded price in the same Region and version, so a
saving can only be quoted from two prices that exist together. Null until TASK-P9-007 writes them.

Backward compatible, constraint 12: six new tables, and nullable columns nothing old writes whose
constraints admit every row the old code makes. The downgrade drops what this adds.
"""

from __future__ import annotations

from alembic import op

revision = "0033_price_catalog"
down_revision = "0032_reconciliation_screen"
branch_labels = None
depends_on = None

_CURRENCY = "^[A-Z]{3}$"

_UP = (
    # ------------------------------------------------------------------ versions
    """
    CREATE TABLE IF NOT EXISTS price_list_version (
        version_pk    UUID         PRIMARY KEY,
        tenant_id     UUID         NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id UUID         NOT NULL,
        service_code  TEXT         NOT NULL,
        region        TEXT         NOT NULL,
        version       TEXT         NOT NULL,
        row_count     INTEGER      NOT NULL,
        as_of         TIMESTAMPTZ  NOT NULL,
        collected_at  TIMESTAMPTZ  NOT NULL,
        CONSTRAINT uq_price_list_version__identity
            UNIQUE (tenant_id, service_code, region, version),
        CONSTRAINT ck_price_list_version__rows CHECK (row_count >= 0),
        CONSTRAINT ck_price_list_version__collected_after_true CHECK (collected_at >= as_of),
        CONSTRAINT ck_price_list_version__named
            CHECK (length(service_code) > 0 AND length(region) > 0 AND length(version) > 0)
    )
    """,
    # ------------------------------------------------------------------ prices
    f"""
    CREATE TABLE IF NOT EXISTS price (
        price_pk              UUID            PRIMARY KEY,
        tenant_id             UUID            NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id         UUID            NOT NULL,
        service_code          TEXT            NOT NULL,
        region                TEXT            NOT NULL,
        sku                   TEXT            NOT NULL,
        sku_price_id          TEXT            NOT NULL,
        sku_meter             TEXT            NOT NULL,
        pricing_unit          TEXT            NOT NULL,
        pricing_category      TEXT            NOT NULL,
        currency              TEXT            NOT NULL,
        recurring_unit_price  NUMERIC(20, 10) NOT NULL,
        upfront_fee           NUMERIC(20, 10) NOT NULL DEFAULT 0,
        lease_years           SMALLINT,
        purchase_option       TEXT,
        offering_class        TEXT,
        sku_price_details     JSONB           NOT NULL DEFAULT '{{}}'::jsonb,
        effective_date        DATE            NOT NULL,
        version               TEXT            NOT NULL,
        as_of                 TIMESTAMPTZ     NOT NULL,
        collected_at          TIMESTAMPTZ     NOT NULL,
        CONSTRAINT uq_price__identity UNIQUE (tenant_id, region, sku_price_id, version),
        CONSTRAINT fk_price__version FOREIGN KEY (tenant_id, service_code, region, version)
            REFERENCES price_list_version (tenant_id, service_code, region, version),
        CONSTRAINT ck_price__category CHECK (pricing_category IN ('Standard', 'Committed')),
        CONSTRAINT ck_price__currency_iso CHECK (currency ~ '{_CURRENCY}'),
        CONSTRAINT ck_price__never_negative
            CHECK (recurring_unit_price >= 0 AND upfront_fee >= 0),
        CONSTRAINT ck_price__not_both_nought
            CHECK (recurring_unit_price > 0 OR upfront_fee > 0),
        CONSTRAINT ck_price__reservation_named CHECK (
            (pricing_category = 'Committed')
            = (lease_years IS NOT NULL AND purchase_option IS NOT NULL)
        ),
        CONSTRAINT ck_price__on_demand_nothing_up_front
            CHECK (pricing_category = 'Committed' OR upfront_fee = 0),
        CONSTRAINT ck_price__lease CHECK (lease_years IS NULL OR lease_years IN (1, 3)),
        CONSTRAINT ck_price__purchase_option CHECK (
            purchase_option IS NULL
            OR purchase_option IN ('No Upfront', 'Partial Upfront', 'All Upfront')
        ),
        CONSTRAINT ck_price__details_object CHECK (jsonb_typeof(sku_price_details) = 'object'),
        CONSTRAINT ck_price__collected_after_true CHECK (collected_at >= as_of)
    )
    """,
    # The read a downsizing candidate makes: every price of one type in one Region's version.
    """
    CREATE INDEX IF NOT EXISTS ix_price__type
        ON price (tenant_id, region, version, (sku_price_details ->> 'instanceType'))
    """,
    # ------------------------------------------------------------------ instance types
    """
    CREATE TABLE IF NOT EXISTS instance_type_spec (
        spec_pk                UUID         PRIMARY KEY,
        tenant_id              UUID         NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id          UUID         NOT NULL,
        service_code           TEXT         NOT NULL,
        region                 TEXT         NOT NULL,
        instance_type          TEXT         NOT NULL,
        family                 TEXT         NOT NULL,
        current_generation     BOOLEAN      NOT NULL,
        architectures          TEXT[]       NOT NULL,
        burstable              BOOLEAN      NOT NULL,
        baseline_cpu           NUMERIC(6, 4),
        maximum_credits        NUMERIC(10, 2),
        baseline_source        TEXT,
        vcpus                  INTEGER      NOT NULL,
        memory_mib             BIGINT       NOT NULL,
        network_performance    TEXT         NOT NULL,
        network_baseline_gbps  NUMERIC(8, 3),
        network_peak_gbps      NUMERIC(8, 3),
        ebs_baseline_mbps      INTEGER,
        ebs_maximum_mbps       INTEGER,
        gpu_count              INTEGER      NOT NULL DEFAULT 0,
        offered                BOOLEAN      NOT NULL DEFAULT true,
        as_of                  TIMESTAMPTZ  NOT NULL,
        collected_at           TIMESTAMPTZ  NOT NULL,
        CONSTRAINT uq_instance_type_spec__identity
            UNIQUE (tenant_id, service_code, region, instance_type),
        CONSTRAINT ck_instance_type_spec__sized CHECK (vcpus > 0 AND memory_mib > 0),
        CONSTRAINT ck_instance_type_spec__gpus CHECK (gpu_count >= 0),
        CONSTRAINT ck_instance_type_spec__architecture CHECK (cardinality(architectures) > 0),
        CONSTRAINT ck_instance_type_spec__burstable_has_baseline CHECK (
            NOT burstable OR (baseline_cpu IS NOT NULL AND baseline_source IS NOT NULL)
        ),
        CONSTRAINT ck_instance_type_spec__baseline_a_share
            CHECK (baseline_cpu IS NULL OR (baseline_cpu > 0 AND baseline_cpu <= 1)),
        CONSTRAINT ck_instance_type_spec__network_peak CHECK (
            network_peak_gbps IS NULL OR network_baseline_gbps IS NULL
            OR network_peak_gbps >= network_baseline_gbps
        ),
        CONSTRAINT ck_instance_type_spec__ebs_maximum CHECK (
            ebs_maximum_mbps IS NULL OR ebs_baseline_mbps IS NULL
            OR ebs_maximum_mbps >= ebs_baseline_mbps
        ),
        CONSTRAINT ck_instance_type_spec__collected_after_true CHECK (collected_at >= as_of)
    )
    """,
    # ------------------------------------------------------------------ volume types
    """
    CREATE TABLE IF NOT EXISTS volume_type_spec (
        volume_pk                  UUID         PRIMARY KEY,
        tenant_id                  UUID         NOT NULL REFERENCES tenant(tenant_id),
        volume_type                TEXT         NOT NULL,
        baseline_iops              INTEGER,
        baseline_throughput_mibps  INTEGER,
        maximum_iops               INTEGER      NOT NULL,
        maximum_throughput_mibps   INTEGER      NOT NULL,
        iops_per_gib               NUMERIC(8, 3),
        source                     TEXT         NOT NULL,
        as_of                      TIMESTAMPTZ  NOT NULL,
        collected_at               TIMESTAMPTZ  NOT NULL,
        CONSTRAINT uq_volume_type_spec__identity UNIQUE (tenant_id, volume_type),
        CONSTRAINT ck_volume_type_spec__maxima
            CHECK (maximum_iops > 0 AND maximum_throughput_mibps > 0),
        CONSTRAINT ck_volume_type_spec__baseline_within_maximum CHECK (
            (baseline_iops IS NULL OR baseline_iops <= maximum_iops)
            AND (baseline_throughput_mibps IS NULL
                 OR baseline_throughput_mibps <= maximum_throughput_mibps)
        ),
        CONSTRAINT ck_volume_type_spec__sourced CHECK (length(trim(source)) > 0),
        CONSTRAINT ck_volume_type_spec__collected_after_true CHECK (collected_at >= as_of)
    )
    """,
    # ------------------------------------------------------------------ spot, OPEN-18
    """
    CREATE TABLE IF NOT EXISTS spot_price (
        spot_pk              UUID            PRIMARY KEY,
        tenant_id            UUID            NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id        UUID            NOT NULL,
        region               TEXT            NOT NULL,
        availability_zone    TEXT            NOT NULL,
        instance_type        TEXT            NOT NULL,
        product_description  TEXT            NOT NULL,
        price                NUMERIC(20, 10) NOT NULL,
        as_of                TIMESTAMPTZ     NOT NULL,
        collected_at         TIMESTAMPTZ     NOT NULL,
        CONSTRAINT uq_spot_price__pool UNIQUE
            (tenant_id, region, availability_zone, instance_type, product_description),
        CONSTRAINT ck_spot_price__positive CHECK (price > 0),
        CONSTRAINT ck_spot_price__collected_after_true CHECK (collected_at >= as_of)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spot_price_daily (
        spot_day_pk          UUID            PRIMARY KEY,
        tenant_id            UUID            NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id        UUID            NOT NULL,
        region               TEXT            NOT NULL,
        availability_zone    TEXT            NOT NULL,
        instance_type        TEXT            NOT NULL,
        product_description  TEXT            NOT NULL,
        day                  DATE            NOT NULL,
        low                  NUMERIC(20, 10) NOT NULL,
        high                 NUMERIC(20, 10) NOT NULL,
        readings             INTEGER         NOT NULL,
        as_of                TIMESTAMPTZ     NOT NULL,
        collected_at         TIMESTAMPTZ     NOT NULL,
        CONSTRAINT uq_spot_price_daily__pool_day UNIQUE
            (tenant_id, region, availability_zone, instance_type, product_description, day),
        CONSTRAINT ck_spot_price_daily__positive CHECK (low > 0 AND high > 0),
        CONSTRAINT ck_spot_price_daily__low_not_above_high CHECK (low <= high),
        CONSTRAINT ck_spot_price_daily__read CHECK (readings > 0),
        CONSTRAINT ck_spot_price_daily__collected_after_true CHECK (collected_at >= as_of)
    )
    """,
    # ------------------------------------------------------------------ the recommendation
    """
    ALTER TABLE recommendation
        ADD COLUMN IF NOT EXISTS current_sku_price_id TEXT,
        ADD COLUMN IF NOT EXISTS target_instance_type TEXT,
        ADD COLUMN IF NOT EXISTS target_sku_price_id TEXT,
        ADD COLUMN IF NOT EXISTS price_version TEXT
    """,
    "ALTER TABLE recommendation DROP CONSTRAINT IF EXISTS ck_recommendation__target_priced",
    # A target is named with its price and the version it came from, or not at all, and a
    # current price is quoted only from a version.
    """
    ALTER TABLE recommendation ADD CONSTRAINT ck_recommendation__target_priced CHECK (
        (target_instance_type IS NULL) = (target_sku_price_id IS NULL)
        AND (target_sku_price_id IS NULL OR price_version IS NOT NULL)
        AND (current_sku_price_id IS NULL OR price_version IS NOT NULL)
    )
    """,
    "ALTER TABLE recommendation DROP CONSTRAINT IF EXISTS fk_recommendation__target_price",
    """
    ALTER TABLE recommendation ADD CONSTRAINT fk_recommendation__target_price
        FOREIGN KEY (tenant_id, region_id, target_sku_price_id, price_version)
        REFERENCES price (tenant_id, region, sku_price_id, version)
    """,
    "ALTER TABLE recommendation DROP CONSTRAINT IF EXISTS fk_recommendation__current_price",
    """
    ALTER TABLE recommendation ADD CONSTRAINT fk_recommendation__current_price
        FOREIGN KEY (tenant_id, region_id, current_sku_price_id, price_version)
        REFERENCES price (tenant_id, region, sku_price_id, version)
    """,
)

_DOWN = (
    "ALTER TABLE recommendation DROP CONSTRAINT IF EXISTS fk_recommendation__current_price",
    "ALTER TABLE recommendation DROP CONSTRAINT IF EXISTS fk_recommendation__target_price",
    "ALTER TABLE recommendation DROP CONSTRAINT IF EXISTS ck_recommendation__target_priced",
    # Drops rather than refusing, as 0021 does: TASK-P9-007 writes these from the catalog, so the
    # next run after an upgrade puts them back.
    """
    ALTER TABLE recommendation
        DROP COLUMN IF EXISTS price_version,
        DROP COLUMN IF EXISTS target_sku_price_id,
        DROP COLUMN IF EXISTS target_instance_type,
        DROP COLUMN IF EXISTS current_sku_price_id
    """,
    "DROP TABLE IF EXISTS spot_price_daily",
    "DROP TABLE IF EXISTS spot_price",
    "DROP TABLE IF EXISTS volume_type_spec",
    "DROP TABLE IF EXISTS instance_type_spec",
    "DROP TABLE IF EXISTS price",
    "DROP TABLE IF EXISTS price_list_version",
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
