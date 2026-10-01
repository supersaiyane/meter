"""Container usage, and the clusters nothing could measure.

Revision ID: 0022_container_usage
Revises: 0021_split_cost_allocation
Create Date: 2026-10-01

TASK-P6-006. Two tables, not one, and the second is the point.

`container_usage` is one row per workload per day. `container_cluster` is one row
per cluster, and it exists because a cluster whose workloads could not be read has
no usage rows at all. Without it such a cluster is absent from the product rather
than listed as unmeasurable, which reports a smaller and tidier estate than the one
that exists and hides exactly the cluster worth asking about. Spec section 5.4.

**`was_oom_killed` is nullable and null means unobserved.** Not false. Container
Insights does not reliably publish OOM events, so most readings are null, and a
sizing rule reading null as false would apply the smaller memory margin to the
workloads most likely to have been killed. The domain carries this as a three member
enum for the same reason; the column stays nullable because that is the shape the
provider's answer actually has.

**A request of zero cannot sit beside a positive use.** That pair means the request
was unread rather than zero, and a constraint is the only thing stopping it reaching
a screen: a workload using 400 millicores of a request of zero renders as infinitely
wasteful and sorts to the top of the list meant to find real waste. The honest
representation of an unread request is null, which this permits.

**One row per workload, not one per workload per day.** The first draft of this
migration took the fake estate's daily CSV shape, which was wrong: the port returns
a window aggregate, so a 99th percentile computed over thirty days would have been
stored in a row stamped with a single date. A figure labelled with a day it does not
describe is the kind of error that survives every test and misleads the first person
to read it. Spec section 5.2 had the right shape, and this is it: the aggregate plus
`observation_days` saying what it covers.

`docs/reference/fake-estate-data-dictionary.md` documents a load straight into this
table and says its column names are proposals until a migration fixes them. This
fixes them, and that document's daily CSV no longer matches, which it says to check
for.
"""

from __future__ import annotations

from alembic import op

revision = "0022_container_usage"
down_revision = "0021_split_cost_allocation"
branch_labels = None
depends_on = None


_UP = (
    """
    CREATE TABLE IF NOT EXISTS container_cluster (
        cluster_row_id              UUID         PRIMARY KEY,
        tenant_id                   UUID         NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id               UUID         NOT NULL,
        sub_account_id              TEXT         NOT NULL,
        region_id                   TEXT         NOT NULL,
        cluster_name                TEXT         NOT NULL,
        platform                    TEXT         NOT NULL,
        enhanced_observability      BOOLEAN      NOT NULL,
        request_unavailable_reason  TEXT,
        node_count                  INTEGER,
        spot_ratio                  NUMERIC(20, 10),
        packing_efficiency          NUMERIC(20, 10),
        as_of                       TIMESTAMPTZ  NOT NULL,
        collected_at                TIMESTAMPTZ  NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_container_cluster__identity
        ON container_cluster (tenant_id, sub_account_id, region_id, cluster_name)
    """,
    # A cluster that cannot report requests has to say why, and one that can must
    # not carry a reason it does not need. Both directions, because a reason sitting
    # on a measurable cluster is a sentence a screen would show for nothing.
    """
    ALTER TABLE container_cluster
        DROP CONSTRAINT IF EXISTS ck_container_cluster__reason_iff_unavailable
    """,
    """
    ALTER TABLE container_cluster
        ADD CONSTRAINT ck_container_cluster__reason_iff_unavailable
        CHECK (
            (NOT enhanced_observability)
            = (length(trim(coalesce(request_unavailable_reason, ''))) >= 12)
        )
    """,
    """
    ALTER TABLE container_cluster
        DROP CONSTRAINT IF EXISTS ck_container_cluster__ratios_are_fractions
    """,
    """
    ALTER TABLE container_cluster
        ADD CONSTRAINT ck_container_cluster__ratios_are_fractions
        CHECK (
            (spot_ratio IS NULL OR (spot_ratio >= 0 AND spot_ratio <= 1))
            AND (
                packing_efficiency IS NULL
                OR (packing_efficiency >= 0 AND packing_efficiency <= 1)
            )
        )
    """,
    """
    CREATE TABLE IF NOT EXISTS container_usage (
        usage_row_id                UUID         PRIMARY KEY,
        tenant_id                   UUID         NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id               UUID         NOT NULL,
        sub_account_id              TEXT         NOT NULL,
        region_id                   TEXT         NOT NULL,
        cluster_name                TEXT         NOT NULL,
        namespace                   TEXT         NOT NULL,
        workload                    TEXT         NOT NULL,
        workload_kind               TEXT         NOT NULL,
        launch_type                 TEXT         NOT NULL,
        cpu_requested_millicores    NUMERIC(20, 10),
        cpu_used_p99_millicores     NUMERIC(20, 10),
        memory_requested_mib        NUMERIC(20, 10),
        memory_used_peak_mib        NUMERIC(20, 10),
        was_oom_killed              BOOLEAN,
        observation_days            INTEGER      NOT NULL,
        as_of                       TIMESTAMPTZ  NOT NULL,
        collected_at                TIMESTAMPTZ  NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_container_usage__identity
        ON container_usage (
            tenant_id, sub_account_id, region_id, cluster_name, namespace, workload
        )
    """,
    # The constraint this table exists to carry.
    """
    ALTER TABLE container_usage
        DROP CONSTRAINT IF EXISTS ck_container_usage__zero_request_never_beside_use
    """,
    """
    ALTER TABLE container_usage
        ADD CONSTRAINT ck_container_usage__zero_request_never_beside_use
        CHECK (
            NOT (
                cpu_requested_millicores = 0
                AND cpu_used_p99_millicores IS NOT NULL
                AND cpu_used_p99_millicores > 0
            )
            AND NOT (
                memory_requested_mib = 0
                AND memory_used_peak_mib IS NOT NULL
                AND memory_used_peak_mib > 0
            )
        )
    """,
    """
    ALTER TABLE container_usage
        DROP CONSTRAINT IF EXISTS ck_container_usage__quantities_not_negative
    """,
    """
    ALTER TABLE container_usage
        ADD CONSTRAINT ck_container_usage__quantities_not_negative
        CHECK (
            coalesce(cpu_requested_millicores, 0) >= 0
            AND coalesce(memory_requested_mib, 0) >= 0
            AND coalesce(cpu_used_p99_millicores, 0) >= 0
            AND coalesce(memory_used_peak_mib, 0) >= 0
            AND observation_days >= 0
        )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_container_usage__workload
        ON container_usage (tenant_id, cluster_name, namespace, workload)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_container_usage__account
        ON container_usage (tenant_id, sub_account_id)
    """,
)


_DOWN = (
    "DROP TABLE IF EXISTS container_usage",
    "DROP TABLE IF EXISTS container_cluster",
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
