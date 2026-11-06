"""The schema as SQLAlchemy Core tables, for the repository layer to read.

This file describes the same tables that `migrations/versions/0001_initial.py`
creates, and the two are written separately on purpose. The migration is raw
SQL because PostgreSQL declarative partitioning and constraints like
`num_nonnulls` have no faithful expression in the ORM, and a migration that
only approximates the schema document is worse than none.

Two files describing one schema is a drift risk, so it is tested rather than
trusted. `tests/db/test_schema.py::test_the_models_match_the_migrated_database`
compares this metadata against a real migrated database, and
`tests/db/test_models.py` asserts the invariants here without needing one.

Constraint 11 in CLAUDE.md: an invariant is a database constraint, not a
convention. If application code is the only thing preventing a bad row, the bad
row eventually exists.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

#: The closed error taxonomy, mirrored from `finops_core.errors`. A new cause
#: cannot reach the database without a migration, which is the point: the
#: taxonomy staying closed is what stops every future failure becoming generic.
ERROR_TYPES = ("AccessDenied", "Throttled", "NotOptedIn", "NoData", "Unreachable", "SchemaDrift")

RUN_STATUSES = ("CLAIMED", "RUNNING", "SUCCEEDED", "FAILED", "PARTIAL")
ACCOUNT_STATUSES = ("ACTIVE", "SUSPENDED", "PENDING", "DEPARTED", "UNKNOWN")
ROLE_HEALTH = ("HEALTHY", "ACCESS_DENIED", "NOT_DEPLOYED", "THROTTLED", "UNKNOWN")
NODE_TYPES = ("ROOT", "OU", "ACCOUNT")
TIERS = ("viewer", "analyst", "owner")


def _in_list(column: str, allowed: tuple[str, ...]) -> str:
    values = ", ".join(f"'{value}'" for value in allowed)
    return f"{column} IN ({values})"


NOW = text("now()")

tenant = Table(
    "tenant",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), primary_key=True),
    Column("name", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    UniqueConstraint("name", name="uq_tenant__name"),
)

principal = Table(
    "principal",
    metadata,
    Column("principal_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("subject", Text, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("email", Text),
    Column("tier", Text, nullable=False),
    Column("is_global", Boolean, nullable=False, server_default=text("false")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("last_seen_at", DateTime(timezone=True)),
    UniqueConstraint("tenant_id", "subject", name="uq_principal__tenant_subject"),
    CheckConstraint(_in_list("tier", TIERS), name="ck_principal__tier_valid"),
)

# The one table where ON DELETE CASCADE is correct. It is a cache, and losing it
# costs one resolution. `expires_at` is NOT NULL because an entry without an
# expiry means a revoked user keeps access.
principal_scope = Table(
    "principal_scope",
    metadata,
    # tenant_id is here even though principal_id reaches a tenant by join. This
    # is the authorization cache, so the repository guard has to be able to
    # filter by tenant without one, and a forgotten join is precisely how one
    # tenant reads another tenant's grants.
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column(
        "principal_id",
        UUID(as_uuid=True),
        ForeignKey("principal.principal_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("account_id", Text),
    Column("ou_id", Text),
    Column("granted_via", Text, nullable=False),
    Column("resolved_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("num_nonnulls(account_id, ou_id) = 1", name="ck_principal_scope__one_target"),
    Index("ix_principal_scope__principal_expires", "principal_id", "expires_at"),
)

# No email column. The provider returns the account root email address, which is
# personal data no feature reads. See docs/09-DATA-CLASSIFICATION.md.
cloud_account = Table(
    "cloud_account",
    metadata,
    Column("account_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("provider", Text, nullable=False),
    Column("account_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("payer_account_id", Text),
    Column("joined_at", DateTime(timezone=True)),
    Column("onboarded_at", DateTime(timezone=True)),
    Column("collector_role_arn", Text),
    Column("external_id_ref", Text),
    Column("role_health", Text, nullable=False, server_default=text("'UNKNOWN'")),
    Column("role_health_checked_at", DateTime(timezone=True)),
    Column("role_health_error", Text),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "tenant_id", "provider", "account_id", name="uq_cloud_account__tenant_provider_account"
    ),
    CheckConstraint(_in_list("status", ACCOUNT_STATUSES), name="ck_cloud_account__status_valid"),
    CheckConstraint(
        _in_list("role_health", ROLE_HEALTH), name="ck_cloud_account__role_health_valid"
    ),
    Index("ix_cloud_account__tenant_health", "tenant_id", "role_health"),
)

# `path` and `depth` are denormalised so a subtree filter is an index scan. Both
# are rebuilt in one transaction on every refresh, because a reader hitting a
# half rebuilt tree sees an empty organization, and empty renders as zero cost.
org_node = Table(
    "org_node",
    metadata,
    Column("node_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("node_id", Text, nullable=False),
    Column("node_type", Text, nullable=False),
    Column("parent_node_id", Text),
    Column("name", Text, nullable=False),
    Column("path", Text, nullable=False),
    Column("depth", SmallInteger, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("tenant_id", "node_id", name="uq_org_node__tenant_node"),
    CheckConstraint(_in_list("node_type", NODE_TYPES), name="ck_org_node__type_valid"),
    CheckConstraint(
        "(node_type = 'ROOT') = (parent_node_id IS NULL)",
        name="ck_org_node__root_has_no_parent",
    ),
    # Deferrable so the whole tree can be rebuilt inside one transaction. A
    # reader hitting a half rebuilt tree sees an empty organization, and an
    # empty organization renders as zero cost.
    ForeignKeyConstraint(
        ["tenant_id", "parent_node_id"],
        ["org_node.tenant_id", "org_node.node_id"],
        name="fk_org_node__parent",
        deferrable=True,
        initially="DEFERRED",
    ),
    Index("ix_org_node__tenant_parent", "tenant_id", "parent_node_id"),
)

# ADR-0012. `reason` is NOT NULL because a cadence without a recorded reason is
# a number nobody can safely change later.
collector_schedule = Table(
    "collector_schedule",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), primary_key=True),
    Column("collector", Text, primary_key=True),
    Column("cadence_seconds", Integer, nullable=False),
    Column("reason", Text, nullable=False),
    Column("est_cost_per_run", Numeric(12, 6)),
    Column("is_enabled", Boolean, nullable=False, server_default=text("true")),
    Column("updated_by", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    CheckConstraint(
        "cadence_seconds BETWEEN 60 AND 2592000", name="ck_collector_schedule__cadence_sane"
    ),
)

# `uq_ingest_run__idempotency_key` is what makes re running a collector safe. It
# is a database constraint rather than an application check because that is what
# holds when two workers claim the same unit simultaneously. ISS-008.
ingest_run = Table(
    "ingest_run",
    metadata,
    Column("run_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("collector", Text, nullable=False),
    Column("scope_key", Text, nullable=False),
    Column("idempotency_key", Text, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("finished_at", DateTime(timezone=True)),
    Column("status", Text, nullable=False),
    Column("items_written", Integer, nullable=False, server_default=text("0")),
    Column("bytes_read", BigInteger, nullable=False, server_default=text("0")),
    Column("error_type", Text),
    Column("error_detail", Text),
    Column("as_of_window_start", DateTime(timezone=True), nullable=False),
    Column("as_of_window_end", DateTime(timezone=True), nullable=False),
    UniqueConstraint("idempotency_key", name="uq_ingest_run__idempotency_key"),
    CheckConstraint(_in_list("status", RUN_STATUSES), name="ck_ingest_run__status_valid"),
    CheckConstraint(
        f"error_type IS NULL OR {_in_list('error_type', ERROR_TYPES)}",
        name="ck_ingest_run__error_type_valid",
    ),
    CheckConstraint("as_of_window_end >= as_of_window_start", name="ck_ingest_run__window_ordered"),
    Index("ix_ingest_run__tenant_collector_started", "tenant_id", "collector", "started_at"),
)

ingest_watermark = Table(
    "ingest_watermark",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), primary_key=True),
    Column("collector", Text, primary_key=True),
    Column("scope_key", Text, primary_key=True),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
)

# `remediation` is NOT NULL. An error a user cannot act on without reading logs
# is an error that stays unfixed.
sync_error = Table(
    "sync_error",
    metadata,
    Column("error_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("collector", Text, nullable=False),
    Column("scope_key", Text, nullable=False),
    Column("error_type", Text, nullable=False),
    Column("detail", Text, nullable=False),
    Column("remediation", Text, nullable=False),
    Column("first_seen_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("last_seen_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("occurrences", Integer, nullable=False, server_default=text("1")),
    UniqueConstraint(
        "tenant_id", "collector", "scope_key", "error_type", name="uq_sync_error__scope"
    ),
    CheckConstraint(_in_list("error_type", ERROR_TYPES), name="ck_sync_error__type_valid"),
)

# Partitioned by range on billing_period_start. A missing partition must raise
# rather than route to a default, because a default partition turns a scheduling
# bug into silently misfiled cost.
cost_focus_daily = Table(
    "cost_focus_daily",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), primary_key=True),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("source_fingerprint", Text, primary_key=True),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    Column("billing_account_id", Text, nullable=False),
    Column("sub_account_id", Text),
    Column("billing_period_start", Date, primary_key=True),
    Column("billing_period_end", Date, nullable=False),
    Column("charge_period_start", DateTime(timezone=True), nullable=False),
    Column("charge_period_end", DateTime(timezone=True), nullable=False),
    Column("provider_name", Text, nullable=False),
    Column("publisher_name", Text),
    Column("invoice_issuer_name", Text),
    Column("service_name", Text, nullable=False),
    Column("service_category", Text),
    Column("resource_id", Text),
    Column("resource_name", Text),
    Column("region_id", Text),
    Column("availability_zone", Text),
    Column("charge_category", Text, nullable=False),
    Column("charge_description", Text),
    Column("sku_id", Text),
    Column("pricing_quantity", Numeric(30, 10)),
    Column("consumed_quantity", Numeric(30, 10)),
    Column("consumed_unit", Text),
    Column("billed_cost", Numeric(20, 10), nullable=False),
    Column("effective_cost", Numeric(20, 10), nullable=False),
    Column("list_cost", Numeric(20, 10)),
    Column("contracted_cost", Numeric(20, 10)),
    Column("commitment_discount_id", Text),
    Column("commitment_discount_type", Text),
    Column("commitment_discount_status", Text),
    Column("tags", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    postgresql_partition_by="RANGE (billing_period_start)",
)

cost_provider_extra = Table(
    "cost_provider_extra",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), primary_key=True),
    Column("billing_period_start", Date, primary_key=True),
    Column("source_fingerprint", Text, primary_key=True),
    Column("provider_fields", JSONB, nullable=False),
    postgresql_partition_by="RANGE (billing_period_start)",
)

# `module` uses the literal 'unallocated' for untagged cost rather than null,
# because a null is easy to filter out by accident and a self metering report
# that quietly under counts is worse than none.
platform_cost = Table(
    "platform_cost",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), primary_key=True),
    Column("day", Date, primary_key=True),
    Column("module", Text, primary_key=True),
    Column("service", Text, primary_key=True),
    Column("amortized_cost", Numeric(20, 10), nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)

audit_event = Table(
    "audit_event",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("principal_id", UUID(as_uuid=True), ForeignKey("principal.principal_id")),
    Column("action", Text, nullable=False),
    Column("resource", Text, nullable=False),
    Column("scope_evaluated", JSONB, nullable=False),
    Column("is_global_read", Boolean, nullable=False, server_default=text("false")),
    Column("outcome", Text, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("request_id", Text, nullable=False),
    CheckConstraint("outcome IN ('ALLOWED', 'DENIED')", name="ck_audit_event__outcome_valid"),
    Index("ix_audit_event__tenant_occurred", "tenant_id", "occurred_at"),
)

#: Every table in the schema. Used by the drift test and by the repository layer.
ALL_TABLES = tuple(metadata.sorted_tables)

#: Tables holding a fact about a cloud, which must carry both timestamps.
FACT_TABLES = (
    "cloud_account",
    "org_node",
    "cost_focus_daily",
    "platform_cost",
)
