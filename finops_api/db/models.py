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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from finops_api.screens import SCREEN_PATHS
from finops_core.constants import (
    REASON_MIN_LENGTH,
    REPORT_RECIPIENTS_MAX,
    SAVED_VIEW_NAME_MAX_LENGTH,
)
from finops_core.domain.report_schedule import Cadence

metadata = MetaData()

#: The closed error taxonomy, mirrored from `finops_core.errors`. A new cause
#: cannot reach the database without a migration, which is the point: the
#: taxonomy staying closed is what stops every future failure becoming generic.
ERROR_TYPES = (
    "AccessDenied",
    "Throttled",
    "NotOptedIn",
    "NoData",
    "Unreachable",
    "SchemaDrift",
    # The seventh, 0018 and ADR-0026. A value this deployment set that does not exist at the
    # provider, which no retry changes and which SchemaDrift used to absorb under a word that
    # sent an operator looking for an API change.
    "Misconfigured",
)

RUN_STATUSES = ("CLAIMED", "RUNNING", "SUCCEEDED", "FAILED", "PARTIAL")
ACCOUNT_STATUSES = ("ACTIVE", "SUSPENDED", "PENDING", "DEPARTED", "UNKNOWN")
ROLE_HEALTH = ("HEALTHY", "ACCESS_DENIED", "NOT_DEPLOYED", "THROTTLED", "UNKNOWN")
NODE_TYPES = ("ROOT", "OU", "ACCOUNT")

#: P4. The closed sets `topology_node` and `topology_edge` admit, mirrored from
#: `finops_core.domain.topology`.
NODE_KINDS = (
    "VPC",
    "SUBNET",
    "INSTANCE",
    "ENI",
    "SECURITY_GROUP",
    "TARGET_GROUP",
    "LOAD_BALANCER",
    "NAT_GATEWAY",
    "TGW_ATTACHMENT",
    "VPC_ENDPOINT",
    "VOLUME",
    "DB_INSTANCE",
    "FUNCTION",
    "OTHER",
)
EDGE_KINDS = ("CONTAINS", "ATTACHED_TO", "ROUTES_TO", "TARGETS", "PERMITS", "PEERS_WITH", "TRUSTS")
COVERAGE_STATES = ("COMPLETE", "PARTIAL", "UNREAD")
#: The taxonomy plus one. ADR-0023: an UNREAD slice has no cause among the six,
#: because nothing failed. `NotYetAttempted` is that state.
COVERAGE_CAUSES = (*ERROR_TYPES, "NotYetAttempted")
TIERS = ("viewer", "analyst", "owner")
#: P8, 0029, ADR-0033. The processes a cadence row can belong to.
SCHEDULE_RUNNERS = ("worker", "api")


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
    #: P8, 0029, ADR-0033. Which process runs this cadence. The ingest worker runs the
    #: collectors; the API runs the scheduled reports, which render through its own routes.
    Column("runs_in", Text, nullable=False, server_default=text("'worker'")),
    CheckConstraint(
        "cadence_seconds BETWEEN 60 AND 2592000", name="ck_collector_schedule__cadence_sane"
    ),
    CheckConstraint(_in_list("runs_in", SCHEDULE_RUNNERS), name="ck_collector_schedule__runs_in"),
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
    UniqueConstraint("tenant_id", "idempotency_key", name="uq_ingest_run__idempotency_key"),
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
    # Split cost allocation, 0021. Nullable because a charge that is not a pod's
    # charge carries none of them, which is most rows. The measures are a breakdown
    # of money already counted in `billed_cost`, never an addition to it.
    Column("eks_cluster_name", Text),
    Column("eks_namespace", Text),
    Column("eks_workload_name", Text),
    Column("eks_workload_type", Text),
    Column("eks_pod_name", Text),
    Column("split_cost", Numeric(20, 10)),
    Column("split_usage", Numeric(30, 10)),
    Column("split_usage_ratio", Numeric(20, 10)),
    Column("unused_cost", Numeric(20, 10)),
    # FOCUS 1.4's mandatory and invoice columns, migration 0030, ADR-0034.
    Column("billing_account_name", Text),
    Column("billing_currency", Text),
    Column("charge_class", Text),
    Column("pricing_unit", Text),
    Column("service_provider_name", Text),
    Column("host_provider_name", Text),
    Column("invoice_id", Text),
    Column("invoice_detail_id", Text),
    # Which collector wrote the row, and what a line of AI spend bought, migration 0047, P13.
    Column("ingest_source", Text, nullable=False, server_default="aws_export"),
    Column("x_usage_type", Text),
    Column("x_iam_principal", Text),
    Column("x_ai_model", Text),
    Column("x_ai_token_type", Text),
    Column("x_ai_tokens", Numeric(30, 10)),
    postgresql_partition_by="RANGE (billing_period_start)",
)

#: P6, FEAT-036. One row per cluster, so a cluster whose workloads could not be read
#: is listed as unmeasurable rather than being absent from the product.
container_cluster = Table(
    "container_cluster",
    metadata,
    Column("cluster_row_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("sub_account_id", Text, nullable=False),
    Column("region_id", Text, nullable=False),
    Column("cluster_name", Text, nullable=False),
    Column("platform", Text, nullable=False),
    Column("enhanced_observability", Boolean, nullable=False),
    Column("request_unavailable_reason", Text),
    Column("node_count", Integer),
    Column("spot_ratio", Numeric(20, 10)),
    Column("packing_efficiency", Numeric(20, 10)),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)

#: One row per workload, carrying the window aggregate the port returns rather than
#: a daily row. `observation_days` says what the figures cover, and `was_oom_killed`
#: is nullable with a null meaning unobserved, never false. See 0022.
container_usage = Table(
    "container_usage",
    metadata,
    Column("usage_row_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("sub_account_id", Text, nullable=False),
    Column("region_id", Text, nullable=False),
    Column("cluster_name", Text, nullable=False),
    Column("namespace", Text, nullable=False),
    Column("workload", Text, nullable=False),
    Column("workload_kind", Text, nullable=False),
    Column("launch_type", Text, nullable=False),
    Column("cpu_requested_millicores", Numeric(20, 10)),
    Column("cpu_used_p99_millicores", Numeric(20, 10)),
    Column("memory_requested_mib", Numeric(20, 10)),
    Column("memory_used_peak_mib", Numeric(20, 10)),
    Column("was_oom_killed", Boolean),
    Column("observation_days", Integer, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)


# Where retention puts cost data before it drops the line items. See
# docs/09-DATA-CLASSIFICATION.md: 37 months of line items, then a monthly
# aggregate that keeps the trend a year on year comparison needs.
cost_focus_monthly = Table(
    "cost_focus_monthly",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), primary_key=True),
    Column("billing_month", Date, primary_key=True),
    Column("sub_account_id", Text, primary_key=True),
    Column("service_name", Text, primary_key=True),
    Column("region_id", Text, primary_key=True),
    Column("billed_cost", Numeric(20, 10), nullable=False),
    Column("effective_cost", Numeric(20, 10), nullable=False),
    Column("line_items", BigInteger, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    Index("ix_cost_focus_monthly__tenant_month", "tenant_id", "billing_month"),
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

#: The P2 vocabularies. Closed sets, mirrored from the P2 specification section
#: 5, so a new value needs a migration rather than a deploy.
INSTANCE_KINDS = ("AMG", "SELF_HOSTED", "CLOUD")
QUERY_ORIGINS = ("PANEL", "ALERT_RULE")
QUERY_ENGINES = ("LOGS_INSIGHTS", "METRIC_SEARCH", "METRIC_INSIGHTS", "PROMQL", "OTHER")
PROVENANCES = ("measured", "modelled")
ENFORCEMENT_LEVELS = ("ALERT", "THROTTLE", "DENY")
REMEDIATION_KINDS = ("WORKSPACE_FLOOR", "PANEL_REWRITE")

grafana_instance = Table(
    "grafana_instance",
    metadata,
    Column("instance_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("kind", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("endpoint", Text, nullable=False),
    Column("account_id", Text),
    Column("region_id", Text),
    #: A Secrets Manager name. Never a value, so a database dump carries no
    #: credential.
    Column("credential_ref", Text),
    Column("reachable", Boolean, nullable=False, server_default=text("true")),
    Column("unreachable_reason", Text),
    #: Null means the instance enforces no floor at all, which is not zero.
    Column("refresh_floor_seconds", Integer),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("tenant_id", "endpoint", name="uq_grafana_instance__tenant_endpoint"),
    CheckConstraint(_in_list("kind", INSTANCE_KINDS), name="ck_grafana_instance__kind_valid"),
    # AMG rows are discovered and must carry their location. The others are
    # entered by a person and must not pretend to have one.
    CheckConstraint(
        "(kind = 'AMG') = (account_id IS NOT NULL AND region_id IS NOT NULL)",
        name="ck_grafana_instance__amg_located",
    ),
    # The same invariant `SurfaceInstance` enforces in the domain. An
    # unexplained absence is what makes an estate look smaller than it is, and
    # the domain being careful is not a reason for the table not to be.
    CheckConstraint(
        "reachable OR unreachable_reason IS NOT NULL",
        name="ck_grafana_instance__unreachable_has_reason",
    ),
)

query_definition = Table(
    "query_definition",
    metadata,
    Column("query_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column(
        "instance_id",
        UUID(as_uuid=True),
        ForeignKey("grafana_instance.instance_id"),
        nullable=False,
    ),
    Column("origin", Text, nullable=False),
    Column("dashboard_uid", Text),
    Column("dashboard_title", Text),
    Column("folder_uid", Text),
    Column("panel_id", Text),
    Column("ref_id", Text),
    Column("engine", Text, nullable=False),
    Column("query_text", Text, nullable=False),
    #: Normalised, with template variables removed, so a dashboard with a
    #: $region variable is one query and not four. Identifies this definition,
    #: which is why it carries the dashboard and the panel.
    Column("fingerprint", Text, nullable=False),
    #: What the query is, independent of where it is drawn, so two panels
    #: running it on different dashboards share one and measured evidence
    #: attaches to both. Nullable until backfilled, per constraint 12.
    Column("query_key", Text),
    Column("target", JSONB, nullable=False),
    Column("refresh_seconds", Integer),
    Column("range_seconds", Integer, nullable=False),
    Column("last_editor", Text),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "tenant_id", "instance_id", "fingerprint", name="uq_query_definition__fingerprint"
    ),
    CheckConstraint(_in_list("origin", QUERY_ORIGINS), name="ck_query_definition__origin_valid"),
    CheckConstraint(_in_list("engine", QUERY_ENGINES), name="ck_query_definition__engine_valid"),
    # A panel has a refresh interval. An alert rule runs on its own schedule and
    # must not borrow one.
    CheckConstraint(
        "(origin = 'ALERT_RULE') OR (refresh_seconds IS NOT NULL)",
        name="ck_query_definition__panel_has_refresh",
    ),
    Index("ix_query_definition__query_key", "tenant_id", "query_key"),
)

#: FEAT-051. The executions that belong to no panel and no alert rule.
#:
#: It carries its own account and region rather than reaching them through a
#: workspace, because a query somebody typed into the console belongs to none.
#: There is no provenance column: an ad hoc row exists only in the evidence, so
#: there is nothing to model it from and every row is measured by construction.
cost_anomaly = Table(
    "cost_anomaly",
    metadata,
    Column("anomaly_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("sub_account_id", Text, nullable=False),
    Column("service_name", Text, nullable=False),
    Column("day", Date, nullable=False),
    Column("observed", Numeric(20, 10), nullable=False),
    Column("baseline", Numeric(20, 10), nullable=False),
    Column("delta", Numeric(20, 10), nullable=False),
    #: Null when the baseline had not moved. Every departure from an unmoving
    #: baseline is infinitely many deviations, so the column says nothing rather
    #: than something false.
    Column("deviations", Numeric(12, 4)),
    Column("severity", Text, nullable=False),
    #: The working, so a reader can disagree with the verdict.
    Column("why", Text, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)


recommendation = Table(
    "recommendation",
    metadata,
    Column("recommendation_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("sub_account_id", Text, nullable=False),
    #: Which of the three AWS services, or METER for our own. One table, not one
    #: per source, because a lifecycle that works for one and not the other is two.
    Column("source", Text, nullable=False),
    Column("source_reference", Text, nullable=False),
    Column("waste_class", Text, nullable=False),
    Column("resource_id", Text, nullable=False),
    Column("region_id", Text, nullable=False),
    #: Modelled, always. What we think would be saved, never what was saved.
    Column("estimated_monthly_saving", Numeric(20, 10), nullable=False),
    #: From the observation days. Deliberately not from the money.
    Column("confidence", Text, nullable=False),
    #: From the money, ADR-0016. Deliberately not from the observation days.
    Column("severity", Text, nullable=False),
    Column("observation_days", Integer, nullable=False),
    Column("lifecycle", Text, nullable=False),
    #: Null is a reported condition, not a gap. ISS-021: an unowned finding is
    #: never fixed, so the screen says so rather than rendering blank.
    Column("owner", Text),
    Column("ticket_reference", Text),
    Column("rationale", Text, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    #: P9, migration 0033. What the resource is billed at and what it should move to, each a
    #: price from one version of the catalog, held there by a composite foreign key. Null until
    #: TASK-P9-007 names a target.
    Column("current_sku_price_id", Text),
    Column("target_instance_type", Text),
    Column("target_sku_price_id", Text),
    Column("price_version", Text),
    #: An Upsize's added monthly cost, modelled, and nothing else's. Migration 0039.
    Column("added_monthly_cost", Numeric(20, 10)),
    #: What the priced gp3 gives a gp2 volume, for FEAT-093's edit, and nothing else's. 0061.
    Column("target_iops", Integer),
    Column("target_throughput_mibps", Integer),
)


#: Append only. The lifecycle column says where a recommendation is; only this can
#: say that somebody accepted it in March and quietly dismissed it in June.
recommendation_event = Table(
    "recommendation_event",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "recommendation_id",
        UUID(as_uuid=True),
        ForeignKey("recommendation.recommendation_id"),
        nullable=False,
    ),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    #: Null exactly once per recommendation: the row recording that it was found.
    Column("from_lifecycle", Text),
    Column("to_lifecycle", Text, nullable=False),
    Column("actor", Text, nullable=False),
    Column("reason", Text),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)


#: TASK-P9-006, migration 0038. Every target a provider ranked, priced from the catalog or saying
#: why not. Its constraints live in the migration; this mirrors the columns for the schema test.
recommendation_option = Table(
    "recommendation_option",
    metadata,
    Column("option_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column(
        "recommendation_id",
        UUID(as_uuid=True),
        ForeignKey("recommendation.recommendation_id"),
        nullable=False,
    ),
    Column("region", Text, nullable=False),
    Column("rank", SmallInteger, nullable=False),
    Column("instance_type", Text, nullable=False),
    # Null where the source gives no risk, as Meter's own rule does not, migration 0040.
    Column("performance_risk", Numeric(3, 1), nullable=True),
    Column("provider_monthly_saving", Numeric(20, 10)),
    Column("migration_effort", Text),
    Column("platform_differences", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column("sku_price_id", Text),
    Column("price_version", Text),
    Column("hourly_price", Numeric(20, 10)),
    Column("unpriced_reason", Text),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)


#: The measured half, in its own table so it cannot be summed with the estimate by
#: accident. Every tool that inflates identified savings does it by adding a
#: modelled number to a measured one.
realized_saving = Table(
    "realized_saving",
    metadata,
    Column("realized_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "recommendation_id",
        UUID(as_uuid=True),
        ForeignKey("recommendation.recommendation_id"),
        nullable=False,
    ),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("window_before_start", Date, nullable=False),
    Column("window_before_end", Date, nullable=False),
    Column("window_after_start", Date, nullable=False),
    Column("window_after_end", Date, nullable=False),
    #: Measured, from cost_focus_daily.
    Column("cost_before", Numeric(20, 10), nullable=False),
    Column("cost_after", Numeric(20, 10), nullable=False),
    #: The control. Without it a fall in cost cannot be told apart from a fall in
    #: use, and the counterfactual is unobservable.
    Column("usage_before", Numeric(20, 10)),
    Column("usage_after", Numeric(20, 10)),
    #: VERIFIED, REGRESSED or INCONCLUSIVE. The third is expected to be common and
    #: is the evidence this metric is not the vanity number ISS-029 warns about.
    Column("verdict", Text, nullable=False),
    Column("why", Text, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)


#: FEAT-043. The score's components live in their own table, and that is the ship
#: condition rather than a normalization choice: the components of last week's score
#: cannot be recomputed once the findings have changed, so a schema holding only the
#: total makes the decomposition unmeetable forever.
finops_score = Table(
    "finops_score",
    metadata,
    Column("score_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    #: One of these is set and the other is null. An account score and a team score
    #: are read by different people, and a row belonging to neither would appear on
    #: both screens or on nobody's.
    Column("sub_account_id", Text),
    Column("team", Text),
    Column("total", Integer, nullable=False),
    #: Stored rather than derived, so a reader looking at an old row can tell a score
    #: out of sixty from a score out of a hundred.
    Column("available_weight", Integer, nullable=False),
    Column("why", Text, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)


finops_score_component = Table(
    "finops_score_component",
    metadata,
    Column("component_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "score_id",
        UUID(as_uuid=True),
        ForeignKey("finops_score.score_id"),
        nullable=False,
    ),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("name", Text, nullable=False),
    #: Nullable, and the null is not a zero. A component that could not be computed
    #: is excluded from the denominator rather than scored as nought.
    Column("points", Numeric(6, 3)),
    Column("weight", Integer, nullable=False),
    Column("why", Text, nullable=False),
    #: The findings that produced this component. What makes a difference between two
    #: runs a list of things that opened or closed rather than two numbers.
    Column("finding_ids", ARRAY(UUID(as_uuid=True)), nullable=False, server_default=text("'{}'")),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)


commitment_use = Table(
    "commitment_use",
    metadata,
    Column("use_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("commitment_id", Text, nullable=False),
    Column("commitment_type", Text, nullable=False),
    #: QUEUED, ACTIVE or EXPIRED. An expired commitment keeps its row, because
    #: the coverage gap its expiry leaves is the finding.
    Column("status", Text, nullable=False),
    Column("term_start", Date, nullable=False),
    Column("term_end", Date, nullable=False),
    Column("window_start", Date, nullable=False),
    Column("window_end", Date, nullable=False),
    Column("committed", Numeric(20, 10), nullable=False),
    Column("used", Numeric(20, 10), nullable=False),
    #: Carried rather than computed on read, and constrained in the database to be
    #: the difference, so a screen and a file cannot disagree about it.
    Column("wasted", Numeric(20, 10), nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)


#: Coverage, at the only grain a provider reports it. There is deliberately no
#: `commitment_id` here: a dollar of covered spend cannot be attributed to one of
#: several overlapping plans, so a column naming one would be an invention.
commitment_coverage = Table(
    "commitment_coverage",
    metadata,
    Column("coverage_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("commitment_type", Text, nullable=False),
    Column("dimension", Text, nullable=False),
    Column("dimension_value", Text, nullable=False),
    Column("window_start", Date, nullable=False),
    Column("window_end", Date, nullable=False),
    Column("eligible_spend", Numeric(20, 10), nullable=False),
    Column("covered_spend", Numeric(20, 10), nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)


#: TASK-P8-013. One kind of commitment on one day. Per kind and never per commitment, because
#: Cost Explorer reports daily Savings Plans use only as one total across every plan; and the
#: coverage figures share the row because at this grain neither is attributed to a plan.
commitment_day = Table(
    "commitment_day",
    metadata,
    Column("day_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("commitment_type", Text, nullable=False),
    Column("day", Date, nullable=False),
    Column("committed", Numeric(20, 10), nullable=False),
    Column("used", Numeric(20, 10), nullable=False),
    Column("eligible_spend", Numeric(20, 10), nullable=False),
    Column("covered_spend", Numeric(20, 10), nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)


#: FEAT-055. A coverage gap as a finding somebody owns, and payer wide because the coverage
#: it derives from is. See ADR-0025: `recommendation` is scoped by account, and stamping an
#: account on a payer wide figure would disclose the organization's commitment position to
#: whoever held that one account.
commitment_action = Table(
    "commitment_action",
    metadata,
    Column("action_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("commitment_type", Text, nullable=False),
    #: SERVICE or REGION, the two `commitment_coverage` allows. A finding cannot describe a
    #: dimension its own source could never have produced.
    Column("dimension", Text, nullable=False),
    Column("dimension_value", Text, nullable=False),
    Column("window_start", Date, nullable=False),
    Column("window_end", Date, nullable=False),
    #: Measured, from the bill. Stored beside the modelled figures so a reader a year later
    #: can check the arithmetic rather than take it.
    Column("eligible_spend", Numeric(20, 10), nullable=False),
    Column("covered_spend", Numeric(20, 10), nullable=False),
    #: Modelled, from a configured discount rate rather than from a quote.
    Column("estimated_monthly_saving", Numeric(20, 10), nullable=False),
    #: How far usage may fall before the commitment costs more than it saves. The number
    #: that decides whether buying it was a mistake, and the one a coverage chart cannot show.
    Column("usage_floor_percent", Numeric(5, 1), nullable=False),
    Column("term_months", Integer, nullable=False),
    Column("confidence", Text, nullable=False),
    Column("severity", Text, nullable=False),
    #: The same vocabulary `recommendation` uses, held to it by a test. Two lifecycles that
    #: drift is how one screen comes to mean something different by DONE.
    Column("lifecycle", Text, nullable=False),
    Column("owner", Text),
    Column("ticket_reference", Text),
    Column("rationale", Text, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)


#: FEAT-057. Which infrastructure as code address owns a resource, stored only where one was
#: found. Presence and never absence: NOT_DETERMINED is the absence of a row and UNMANAGED is
#: derived at read time from a declaration about our own configuration, never stored, because a
#: stored judgement outlives the configuration it was made under.
sizing_refusal = Table(
    "sizing_refusal",
    metadata,
    #: FEAT-062, 0019. What a sizing rule examined and declined to recommend, with the
    #: sentence that decided it. Its own table and not a row in `recommendation`, because a
    #: refusal has no saving and every consumer of that table ranks by money: a zero there
    #: reads as the least valuable action rather than as the absence of one. ADR-0027.
    Column("refusal_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("sub_account_id", Text, nullable=False),
    Column("region_id", Text, nullable=False),
    #: The resource, or the scaling group where one owns it, which is the same target the
    #: recommendation would have named. A reader comparing the two lists has to see one name.
    Column("resource_id", Text, nullable=False),
    #: Which rule declined. A resource the sizing rule and the idle rule both looked at was
    #: declined by each for its own reason, and one row would lose the half somebody came for.
    Column("waste_class", Text, nullable=False),
    #: The sentence, and the whole feature. A refusal reading "did not qualify" would be worse
    #: than no feature: it teaches a reader the explanations are empty and they stop reading
    #: the ones that are not. The constraint is a length, because an empty string is NOT NULL.
    Column("reason", Text, nullable=False),
    Column("observation_days", Integer, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "tenant_id", "resource_id", "waste_class", name="uq_sizing_refusal__resource_and_rule"
    ),
    CheckConstraint(
        "length(trim(reason)) >= 12",  # allow-hardcoded: the text of a database check
        # constraint, which has to match 0019 character for character or the mirror test
        # fails. A CHECK cannot read settings, and this is not a policy knob: it is the
        # floor below which a reason is not a sentence.
        name="ck_sizing_refusal__reason_is_a_sentence",
    ),
    CheckConstraint("observation_days >= 0", name="ck_sizing_refusal__observed_something"),
)


resource_management = Table(
    "resource_management",
    metadata,
    Column("management_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    #: Resolved from the node the resource joined to, not parsed out of the ARN, so the row
    #: exists only where the account is known rather than where a string looked like one.
    Column("sub_account_id", Text, nullable=False),
    #: The ARN, which is what `topology_node` keys on. No foreign key: Terraform manages
    #: resources Meter has never inventoried, and a key would refuse exactly those.
    Column("provider_id", Text, nullable=False),
    #: `module.network.aws_vpc.main`. FEAT-040 opens a pull request against a block, and a bare
    #: resource name appears in every module that declares one.
    Column("address", Text, nullable=False),
    #: Which state we read it from, so a reader can find the file.
    Column("state_reference", Text, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)


#: FEAT-060. What somebody said this should cost, read from the provider rather than typed
#: in, so it carries a provenance like everything else a screen renders here.
#:
#: Nothing derived is stored: not the actual, not the status, not the percentage. Status
#: depends on where today falls in the period, so a stored one is wrong by the next morning.
budget = Table(
    "budget",
    metadata,
    Column("budget_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    #: The provider's own identifier, stable across periods, which is what lets a budget keep
    #: its identity when its limit is revised.
    Column("budget_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    #: ACCOUNT, SERVICE, ALL or UNSUPPORTED. The last is a budget that exists and cannot be
    #: joined, counted rather than dropped, because an estate with ten budgets over tag
    #: expressions is not an estate with no budgets.
    Column("scope", Text, nullable=False),
    Column("scope_value", Text, nullable=False),
    #: Not `limit`, which is reserved in SQL and would need quoting in every statement
    #: forever, which is a thing somebody forgets exactly once.
    Column("limit_amount", Numeric(20, 10), nullable=False),
    Column("currency", Text, nullable=False),
    Column("period_start", Date, nullable=False),
    Column("period_end", Date, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)


#: FEAT-076, migration 0031. FOCUS 1.4's Billing Period dataset: one row per tenant and month,
#: Closed once an invoice for it has been issued and Open until then. Payer wide, ADR-0025.
billing_period = Table(
    "billing_period",
    metadata,
    Column("billing_period_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("billing_period_start", Date, nullable=False),
    Column("billing_period_end", Date, nullable=False),
    #: Open or Closed, in FOCUS's own capitalisation.
    Column("billing_period_status", Text, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)


#: FEAT-076, migration 0031. FOCUS 1.4's Invoice Detail dataset at the grain AWS gives, one row
#: per whole invoice or credit memo, so `invoice_detail_id` is the `invoice_id`. Stored as read:
#: Meter's own sum and the difference are computed when read, TASK-P10-004. Payer wide.
invoice_detail = Table(
    "invoice_detail",
    metadata,
    Column("invoice_detail_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("invoice_id", Text, nullable=False),
    Column("invoice_detail_id", Text, nullable=False),
    #: INVOICE or CREDIT_MEMO. A credit memo names the invoice it corrects.
    Column("invoice_type", Text, nullable=False),
    Column("original_invoice_id", Text),
    Column("billing_account_id", Text, nullable=False),
    Column("billing_period_start", Date, nullable=False),
    Column("billing_period_end", Date, nullable=False),
    #: Not always AWS: Marketplace charges are invoiced by another entity.
    Column("invoice_issuer_name", Text, nullable=False),
    Column("billing_currency", Text, nullable=False),
    Column("billed_cost_before_tax", Numeric(20, 10), nullable=False),
    Column("tax", Numeric(20, 10), nullable=False),
    Column("billed_cost", Numeric(20, 10), nullable=False),
    Column("issued_at", DateTime(timezone=True), nullable=False),
    Column("due_date", Date),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)


# --- the price catalog, P9, migration 0033 -------------------------------------------------
#
# AWS's own prices and descriptions, per tenant as every table is, under the guard's tenant rule.
# Every invariant is a constraint in the migration; these mirror the columns.

#: One publication of one service's prices in one Region. `as_of` is its publication.
price_list_version = Table(
    "price_list_version",
    metadata,
    Column("version_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("service_code", Text, nullable=False),
    Column("region", Text, nullable=False),
    Column("version", Text, nullable=False),
    Column("row_count", Integer, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)

#: One offer term: on demand, or a reservation of one length, payment option and class. Its
#: recurring price and upfront fee are never both nought, spec section 5.3 as corrected.
price = Table(
    "price",
    metadata,
    Column("price_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("service_code", Text, nullable=False),
    Column("region", Text, nullable=False),
    Column("sku", Text, nullable=False),
    Column("sku_price_id", Text, nullable=False),
    Column("sku_meter", Text, nullable=False),
    Column("pricing_unit", Text, nullable=False),
    Column("pricing_category", Text, nullable=False),
    Column("currency", Text, nullable=False),
    Column("recurring_unit_price", Numeric(20, 10), nullable=False),
    Column("upfront_fee", Numeric(20, 10), nullable=False),
    Column("lease_years", SmallInteger),
    Column("purchase_option", Text),
    Column("offering_class", Text),
    Column("sku_price_details", JSONB, nullable=False),
    Column("effective_date", Date, nullable=False),
    Column("version", Text, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)

#: An instance type as AWS describes it in one Region, for EC2 and the four managed services.
instance_type_spec = Table(
    "instance_type_spec",
    metadata,
    Column("spec_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("service_code", Text, nullable=False),
    Column("region", Text, nullable=False),
    Column("instance_type", Text, nullable=False),
    Column("family", Text, nullable=False),
    Column("current_generation", Boolean, nullable=False),
    Column("architectures", ARRAY(Text), nullable=False),
    Column("burstable", Boolean, nullable=False),
    #: A burstable type's baseline share of a vCPU and its credit ceiling, from the EC2 guide's
    #: table, TASK-P9-005, with where it came from.
    Column("baseline_cpu", Numeric(6, 4)),
    Column("maximum_credits", Numeric(10, 2)),
    Column("baseline_source", Text),
    Column("vcpus", Integer, nullable=False),
    Column("memory_mib", BigInteger, nullable=False),
    Column("network_performance", Text, nullable=False),
    Column("network_baseline_gbps", Numeric(8, 3)),
    Column("network_peak_gbps", Numeric(8, 3)),
    Column("ebs_baseline_mbps", Integer),
    Column("ebs_maximum_mbps", Integer),
    Column("gpu_count", Integer, nullable=False),
    Column("offered", Boolean, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)

#: An EBS volume type's included and maximum performance, with its source.
volume_type_spec = Table(
    "volume_type_spec",
    metadata,
    Column("volume_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("volume_type", Text, nullable=False),
    Column("baseline_iops", Integer),
    Column("baseline_throughput_mibps", Integer),
    Column("maximum_iops", Integer, nullable=False),
    Column("maximum_throughput_mibps", Integer, nullable=False),
    Column("iops_per_gib", Numeric(8, 3)),
    Column("source", Text, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)

#: The latest spot price in each pool, replaced each run, OPEN-18.
spot_price = Table(
    "spot_price",
    metadata,
    Column("spot_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("region", Text, nullable=False),
    Column("availability_zone", Text, nullable=False),
    Column("instance_type", Text, nullable=False),
    Column("product_description", Text, nullable=False),
    Column("price", Numeric(20, 10), nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)

#: Each pool's lowest and highest reading in a day, kept 90 days, OPEN-18.
spot_price_daily = Table(
    "spot_price_daily",
    metadata,
    Column("spot_day_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("region", Text, nullable=False),
    Column("availability_zone", Text, nullable=False),
    Column("instance_type", Text, nullable=False),
    Column("product_description", Text, nullable=False),
    Column("day", Date, nullable=False),
    Column("low", Numeric(20, 10), nullable=False),
    Column("high", Numeric(20, 10), nullable=False),
    Column("readings", Integer, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)

#: Who an estate says owns each resource, one row per resource per source, migration 0041,
#: FEAT-077. A suggestion, never an owner: `recommendation.owner` is a person's to write.
resource_owner = Table(
    "resource_owner",
    metadata,
    Column("owner_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("sub_account_id", Text, nullable=False),
    Column("region_id", Text),
    Column("resource_id", Text, nullable=False),
    Column("source", Text, nullable=False),
    Column("owner", Text, nullable=False),
    Column("owner_kind", Text, nullable=False),
    Column("detail", Text, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)

#: Which resources CloudTrail has been asked about, found or older than its history, so none is
#: asked twice, migration 0042, FEAT-077.
creator_lookup = Table(
    "creator_lookup",
    metadata,
    Column("lookup_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("sub_account_id", Text, nullable=False),
    Column("region_id", Text, nullable=False),
    Column("resource_id", Text, nullable=False),
    Column("outcome", Text, nullable=False),
    Column("history_starts", DateTime(timezone=True)),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)

#: One credit per verified saving, to the owner, team and closer, migration 0043, FEAT-078.
savings_credit = Table(
    "savings_credit",
    metadata,
    Column("credit_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("sub_account_id", Text, nullable=False),
    Column(
        "recommendation_id",
        UUID(as_uuid=True),
        ForeignKey("recommendation.recommendation_id"),
        nullable=False,
    ),
    Column(
        "realized_id",
        UUID(as_uuid=True),
        ForeignKey("realized_saving.realized_id"),
        nullable=False,
        unique=True,
    ),
    Column("owner", Text, nullable=False),
    Column("team", Text),
    Column("closed_by", Text, nullable=False),
    #: Measured: FEAT-029's before window's cost less its after window's, thirty days each.
    Column("verified_monthly_saving", Numeric(20, 10), nullable=False),
    Column("verified_on", Date, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)

#: Each closed month after a credit's saving verified, migration 0044, FEAT-078.
savings_credit_month = Table(
    "savings_credit_month",
    metadata,
    Column("month_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("sub_account_id", Text, nullable=False),
    Column("credit_id", UUID(as_uuid=True), ForeignKey("savings_credit.credit_id"), nullable=False),
    #: The first of the month judged.
    Column("month", Date, nullable=False),
    #: HELD, REGRESSED or UNOBSERVED. Cost and saving are null exactly when UNOBSERVED.
    Column("state", Text, nullable=False),
    #: Measured, from cost_focus_daily.
    Column("cost", Numeric(20, 10)),
    Column("saving", Numeric(20, 10)),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)

query_adhoc = Table(
    "query_adhoc",
    metadata,
    Column("adhoc_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("account_id", Text, nullable=False),
    Column("region_id", Text, nullable=False),
    Column("fingerprint", Text, nullable=False),
    #: Whole, never truncated. A person has to recognise their own query.
    Column("query_text", Text, nullable=False),
    Column("run_date", Date, nullable=False),
    Column("runs", Integer, nullable=False),
    Column("scan_bytes", BigInteger, nullable=False),
    Column("cost_usd", Numeric(12, 4), nullable=False),
    #: Null means CloudTrail did not name who ran it, which is reported as
    #: unattributed rather than hidden.
    Column("principal", Text),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
)


query_finding = Table(
    "query_finding",
    metadata,
    Column("finding_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("query_id", UUID(as_uuid=True), ForeignKey("query_definition.query_id"), nullable=False),
    Column("run_date", Date, nullable=False),
    Column("runs_per_day", Numeric(12, 2), nullable=False),
    Column("scan_bytes_per_run", BigInteger),
    Column("metrics_per_call", Integer),
    Column("cost_month_usd", Numeric(20, 10), nullable=False),
    Column("provenance", Text, nullable=False),
    Column("measured_runs", Integer),
    Column("severity", Text, nullable=False),
    Column("cause", Text),
    Column("owner_email", Text),
    Column("owner_source", Text),
    #: What drives the cost, in words. A ranked number says what to look at; this
    #: is what says what to do about it.
    Column("why", Text, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("tenant_id", "query_id", "run_date", name="uq_query_finding__query_day"),
    CheckConstraint(_in_list("provenance", PROVENANCES), name="ck_query_finding__provenance_valid"),
    # Both directions. A measured row must say how many runs it measured, and a
    # modelled row must not claim to have measured any. A figure that says
    # measured and measured nothing is the lie this product exists to prevent.
    CheckConstraint(
        "(provenance = 'modelled' AND measured_runs IS NULL)"
        " OR (provenance = 'measured' AND measured_runs IS NOT NULL)",
        name="ck_query_finding__measured_has_runs",
    ),
    Index("ix_query_finding__cost", "tenant_id", "run_date", text("cost_month_usd DESC")),
)

folder_team_map = Table(
    "folder_team_map",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), primary_key=True),
    Column(
        "instance_id",
        UUID(as_uuid=True),
        ForeignKey("grafana_instance.instance_id"),
        primary_key=True,
    ),
    Column("folder_uid", Text, primary_key=True),
    Column("owner_email", Text, nullable=False),
    Column("team", Text),
    Column("updated_by", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
)

enforcement_action = Table(
    "enforcement_action",
    metadata,
    Column("action_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("level", Text, nullable=False),
    Column("principal_arn", Text, nullable=False),
    Column("trigger_reason", Text, nullable=False),
    Column("observed_rate", Numeric(12, 2), nullable=False),
    Column("threshold", Numeric(12, 2), nullable=False),
    Column("applied_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("expires_at", DateTime(timezone=True)),
    Column("removed_at", DateTime(timezone=True)),
    Column("removed_by", Text),
    CheckConstraint(
        _in_list("level", ENFORCEMENT_LEVELS), name="ck_enforcement_action__level_valid"
    ),
    # The rule that stops a deny becoming permanent. Here rather than in the
    # service layer because two paths write this table, the control function and
    # the API, and application code is not what holds when that is true.
    CheckConstraint(
        "level = 'ALERT' OR expires_at IS NOT NULL",
        name="ck_enforcement_action__restrictive_expires",
    ),
    Index(
        "ix_enforcement_action__active",
        "tenant_id",
        "expires_at",
        postgresql_where=text("removed_at IS NULL"),
    ),
)

remediation_change = Table(
    "remediation_change",
    metadata,
    Column("change_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("query_id", UUID(as_uuid=True), ForeignKey("query_definition.query_id")),
    Column(
        "instance_id",
        UUID(as_uuid=True),
        ForeignKey("grafana_instance.instance_id"),
        nullable=False,
    ),
    Column("kind", Text, nullable=False),
    #: The undo, and it is NOT NULL. A change that cannot say what it replaced is
    #: a change nobody will dare apply.
    Column("before", JSONB, nullable=False),
    Column("after", JSONB, nullable=False),
    Column("applied_by", Text, nullable=False),
    Column("applied_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("reverted_at", DateTime(timezone=True)),
    Column("reverted_by", Text),
    CheckConstraint(_in_list("kind", REMEDIATION_KINDS), name="ck_remediation_change__kind_valid"),
)


topology_node = Table(
    "topology_node",
    metadata,
    #: Derived from `(tenant_id, provider_id)` by
    #: `finops_core.domain.topology.node_id_for`, not allocated, so an edge can be
    #: written without a round trip to look up the row it points at.
    Column("node_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), ForeignKey("ingest_run.run_id"), nullable=False),
    Column("sub_account_id", Text, nullable=False),
    Column("provider_id", Text, nullable=False),
    Column("node_kind", Text, nullable=False),
    #: The provider's own word for the type, beside the lossy kind. Six AWS types
    #: map to OTHER, and a reader looking at an unfamiliar box needs to know which.
    Column("resource_type", Text, nullable=False),
    #: Null means global rather than regional: an IAM role belongs to an account and
    #: to no region. ISS-196, in a new table.
    Column("region_id", Text),
    #: Null means regional rather than zonal, never that the zone is unknown. An
    #: unknown zone is a PARTIAL row in `graph_coverage`.
    Column("availability_zone", Text),
    Column("name", Text),
    Column("tags", JSONB, nullable=False, server_default=text("'{}'")),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("tenant_id", "provider_id", name="uq_topology_node__provider_id"),
    CheckConstraint(_in_list("node_kind", NODE_KINDS), name="ck_topology_node__kind_known"),
    CheckConstraint(
        "availability_zone IS NULL OR "
        "(region_id IS NOT NULL AND availability_zone LIKE region_id || '%')",
        name="ck_topology_node__zone_within_region",
    ),
    CheckConstraint("collected_at >= as_of", name="ck_topology_node__collected_after_as_of"),
    Index("ix_topology_node__slice", "tenant_id", "sub_account_id", "region_id"),
    Index("ix_topology_node__run", "tenant_id", "ingest_run_id"),
)


#: Directed, and the direction is part of the identity. There is deliberately no
#: foreign key on `to_node_id`: the far end of a cross account TRUSTS edge is
#: routinely a principal in an account Meter does not collect from, and a key
#: there would refuse exactly the rows the blast radius read exists to find.
topology_edge = Table(
    "topology_edge",
    metadata,
    Column("edge_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), ForeignKey("ingest_run.run_id"), nullable=False),
    #: Not cascading. `principal_scope` is the only table here that cascades, and a
    #: cascade would remove edges nothing counted, so a run's `items_removed` would
    #: undercount every departed resource by the size of its neighbourhood.
    Column(
        "from_node_id",
        UUID(as_uuid=True),
        ForeignKey("topology_node.node_id"),
        nullable=False,
    ),
    Column("to_node_id", UUID(as_uuid=True), nullable=False),
    Column("edge_kind", Text, nullable=False),
    #: Materialised, because the cross account question is the expensive one to ask
    #: repeatedly and the interesting one to answer.
    Column("is_cross_account", Boolean, nullable=False),
    #: The API call that produced the edge. An edge whose absence cannot be told
    #: apart from a refused API is the failure this sub project is about.
    Column("source", Text, nullable=False),
    #: The origin's slice, not the edge's. Denormalised so the retraction that
    #: removes a withdrawn edge needs no join to a node row this run may already
    #: have removed.
    Column("sub_account_id", Text, nullable=False),
    Column("region_id", Text),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "tenant_id",
        "from_node_id",
        "to_node_id",
        "edge_kind",
        name="uq_topology_edge__directed",
    ),
    CheckConstraint(_in_list("edge_kind", EDGE_KINDS), name="ck_topology_edge__kind_known"),
    CheckConstraint("length(source) > 0", name="ck_topology_edge__has_source"),
    CheckConstraint(
        "from_node_id <> to_node_id OR edge_kind = 'PERMITS'",
        name="ck_topology_edge__self_edge_only_permits",
    ),
    CheckConstraint("collected_at >= as_of", name="ck_topology_edge__collected_after_as_of"),
    Index("ix_topology_edge__outward", "tenant_id", "from_node_id"),
    Index("ix_topology_edge__inward", "tenant_id", "to_node_id"),
    Index("ix_topology_edge__slice", "tenant_id", "sub_account_id", "region_id"),
    Index(
        "ix_topology_edge__cross_account",
        "tenant_id",
        "from_node_id",
        postgresql_where=text("is_cross_account"),
    ),
)


#: The table P4 exists for. One row per account and region, written on every run
#: including a failed one, because absence of a row and absence of resources are
#: indistinguishable to a consumer and one of them is dangerous.
graph_coverage = Table(
    "graph_coverage",
    metadata,
    Column("coverage_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), ForeignKey("ingest_run.run_id"), nullable=False),
    Column("sub_account_id", Text, nullable=False),
    Column("region_id", Text),
    Column("state", Text, nullable=False),
    Column("cause", Text),
    Column("node_count", Integer, nullable=False),
    Column("edge_count", Integer, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    #: Coalesced in the migration, because a unique index treats nulls as distinct
    #: and two rows for one account's global slice would both be accepted.
    Index(
        "uq_graph_coverage__slice",
        "tenant_id",
        "sub_account_id",
        text("COALESCE(region_id, '')"),
        unique=True,
    ),
    CheckConstraint(_in_list("state", COVERAGE_STATES), name="ck_graph_coverage__state_known"),
    CheckConstraint(
        f"cause IS NULL OR {_in_list('cause', COVERAGE_CAUSES)}",
        name="ck_graph_coverage__cause_known",
    ),
    # Both halves as one rule. A slice that cannot say why it is incomplete shows a
    # banner that sends nobody anywhere, and a complete slice carrying a cause
    # shows a reader a failure over a graph that is whole.
    CheckConstraint(
        "(state = 'COMPLETE') = (cause IS NULL)",
        name="ck_graph_coverage__cause_iff_not_complete",
    ),
    CheckConstraint(
        "state <> 'UNREAD' OR cause = 'NotYetAttempted'",
        name="ck_graph_coverage__unread_is_not_yet_attempted",
    ),
    CheckConstraint(
        "state <> 'UNREAD' OR (node_count = 0 AND edge_count = 0)",
        name="ck_graph_coverage__unread_is_empty",
    ),
    CheckConstraint(
        "node_count >= 0 AND edge_count >= 0", name="ck_graph_coverage__counts_not_negative"
    ),
    CheckConstraint("collected_at >= as_of", name="ck_graph_coverage__collected_after_as_of"),
    Index(
        "ix_graph_coverage__incomplete",
        "tenant_id",
        "sub_account_id",
        "region_id",
        postgresql_where=text("state <> 'COMPLETE'"),
    ),
)

#: The four sources a usage figure can come from, and the absence. Mirrored from
#: `finops_core.domain.quota.UsageSource`, and `tests/db/test_models.py` holds the two
#: equal. NONE is the common case rather than the error path: AWS publishes usage for a
#: minority of its quotas, which is why the screen shows two lists instead of one.
USAGE_SOURCES = ("AWS_USAGE_METRIC", "TRUSTED_ADVISOR", "SERVICE_API", "NONE")

#: AWS's own vocabulary for an increase request, not ours to improve. DENIED is in it
#: because that is the one a product is tempted to hide.
#:
#: A literal rather than a comprehension over `RequestStatus`, for the reason
#: `ERROR_TYPES` is one: deriving it would let a member added to the enum widen this
#: silently, and the friction is the feature. The mirror test in
#: `tests/db/test_models.py` fails instead, naming the vocabulary, and the fix is a
#: migration. Seven values where the P5 spec named five, which is how that test earned
#: its keep the day it was written.
REQUEST_STATUSES = (
    "PENDING",
    "CASE_OPENED",
    "APPROVED",
    "DENIED",
    "CASE_CLOSED",
    "NOT_APPROVED",
    "INVALID_REQUEST",
)


quota_usage = Table(
    "quota_usage",
    metadata,
    #: FEAT-033, 0020. One quota for one account in one region, every run, including the
    #: ones nothing can measure. Those are the majority in a real estate, and rendering
    #: one as zero used tells somebody they have headroom nobody has measured.
    Column("quota_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("sub_account_id", Text, nullable=False),
    #: Null where the quota is global rather than regional. IAM roles per account are
    #: counted once, and a placeholder region would let a screen show one limit five
    #: times and add them up. The unique index is NULLS NOT DISTINCT for that reason.
    Column("region_id", Text),
    Column("service_code", Text, nullable=False),
    Column("quota_code", Text, nullable=False),
    Column("quota_name", Text, nullable=False),
    #: Nullable, because a few quotas publish no limit. Zero is a real and different
    #: value meaning the thing is switched off here.
    Column("limit_value", Numeric(20, 10)),
    #: Nullable, and the null is the point. Never zero as a stand in.
    Column("used_value", Numeric(20, 10)),
    #: Where the figure came from, or NONE. Held equal to `used_value` by a check, so a
    #: figure can never be recorded without its provenance.
    Column("usage_source", Text, nullable=False),
    #: Why nothing could measure it, required where nothing did. A quota in the
    #: unmeasurable list with a blank reason teaches a reader the explanations there are
    #: empty, and they stop reading the ones that are not.
    Column("unmeasurable_reason", Text),
    Column("is_adjustable", Boolean, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "usage_source IN ('AWS_USAGE_METRIC', 'TRUSTED_ADVISOR', 'SERVICE_API', 'NONE')",
        name="ck_quota_usage__usage_source",
    ),
    #: The constraint the sub project exists for, both directions in one expression. A
    #: figure with no source cannot be audited later and renders identically to a
    #: measured one; a source with no figure claims a measurement nobody made.
    CheckConstraint(
        "(used_value IS NULL) = (usage_source = 'NONE')",
        name="ck_quota_usage__source_iff_usage",
    ),
    CheckConstraint(
        "limit_value IS NULL OR used_value IS NULL OR used_value <= limit_value",
        name="ck_quota_usage__used_within_limit",
    ),
    CheckConstraint(
        "limit_value IS NULL OR limit_value >= 0",
        name="ck_quota_usage__limit_not_negative",
    ),
    CheckConstraint(
        "(usage_source = 'NONE') = "
        f"(length(trim(coalesce(unmeasurable_reason, ''))) >= {REASON_MIN_LENGTH})",
        name="ck_quota_usage__reason_iff_unmeasurable",
    ),
    Index("ix_quota_usage__account", "tenant_id", "sub_account_id"),
)


quota_request = Table(
    "quota_request",
    metadata,
    #: FEAT-034, 0020. An increase request Meter reads and never writes. Spec section 6:
    #: `RequestServiceQuotaIncrease` is a write into a member account and constraint 6
    #: says there are none in v1, so this is the tracking half only.
    Column("request_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    #: AWS's own request id, which is what lets a re read update rather than accumulate.
    Column("request_id", Text, nullable=False),
    Column("sub_account_id", Text, nullable=False),
    Column("region_id", Text),
    Column("service_code", Text, nullable=False),
    Column("quota_code", Text, nullable=False),
    #: Stored rather than joined to `quota_usage`. A request outlives the quota it names, so a
    #: join would drop exactly the rows somebody is chasing, and a list of bare codes is
    #: unreadable: `L-1216C47A` says nothing about what was asked for.
    Column("quota_name", Text, nullable=False),
    Column("desired_value", Numeric(20, 10), nullable=False),
    Column("status", Text, nullable=False),
    Column("requested_at", DateTime(timezone=True), nullable=False),
    Column("last_updated_at", DateTime(timezone=True), nullable=False),
    #: Always false, and that is the column's whole job: spec section 6 written into the
    #: schema rather than into a comment. Reversing the decision takes a migration
    #: somebody has to write and defend.
    Column("submitted_by_meter", Boolean, nullable=False, server_default=text("FALSE")),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("tenant_id", "request_id", name="uq_quota_request__request_id"),
    CheckConstraint(
        "status IN ('PENDING', 'CASE_OPENED', 'APPROVED', 'DENIED', "
        "'CASE_CLOSED', 'NOT_APPROVED', 'INVALID_REQUEST')",
        name="ck_quota_request__status",
    ),
    CheckConstraint("desired_value > 0", name="ck_quota_request__desired_is_positive"),
    CheckConstraint(
        "last_updated_at >= requested_at",
        name="ck_quota_request__updated_after_requested",
    ),
    CheckConstraint("submitted_by_meter = FALSE", name="ck_quota_request__meter_never_submits"),
    Index("ix_quota_request__account", "tenant_id", "sub_account_id"),
)


quota_request_history = Table(
    "quota_request_history",
    metadata,
    #: Every status a request has been in. The current status cannot say when it was
    #: approved, and FEAT-034 exists for the increase nobody checked on. It carries no
    #: `as_of`: `changed_at` is AWS's timestamp for the transition, and the request row
    #: beside it holds the pair of timestamps for the read that found it.
    Column("history_pk", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("request_id", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("changed_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("tenant_id", "request_id", "status", name="uq_quota_request_history__status"),
    CheckConstraint(
        "status IN ('PENDING', 'CASE_OPENED', 'APPROVED', 'DENIED', "
        "'CASE_CLOSED', 'NOT_APPROVED', 'INVALID_REQUEST')",
        name="ck_quota_request_history__status",
    ),
    Index("ix_quota_request_history__request", "tenant_id", "request_id", "changed_at"),
)


#: P7, 0023. The two closed vocabularies `assistant_exchange` is checked against, mirrored
#: from `finops_core.domain.insight` the way `ERROR_TYPES` mirrors the error taxonomy, and
#: held equal to the enums by `tests/db/test_p7_constraints.py`.
EXCHANGE_OUTCOMES = ("ANSWERED", "REFUSED", "FAILED")
REFUSAL_GAPS = ("tool", "figure", "scope", "budget", "secret")

assistant_exchange = Table(
    "assistant_exchange",
    metadata,
    #: FEAT-038, 0023. One question, and which of three things came back. Our own work, so
    #: `asked_at` and `answered_at` rather than `as_of`: the `as_of` of every cited figure is
    #: inside `citations`, beside the figure it dates.
    Column("exchange_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    #: The session's identifier and not a foreign key: principals are not persisted yet,
    #: see `finops_api.deps.get_access_context`.
    Column("principal_id", Text, nullable=False),
    #: As typed. Never normalised, because the wording is the evidence when an answer
    #: turns out wrong.
    Column("question", Text, nullable=False),
    Column("outcome", Text, nullable=False),
    Column("answer", Text),
    Column("refusal_gap", Text),
    Column("refusal_reason", Text),
    Column("refusal_screen", Text),
    Column("failure_cause", Text),
    Column("failure_detail", Text),
    Column("citations", JSONB, nullable=False),
    #: In the order they were made, so an answer can be replayed.
    Column("tool_calls", JSONB, nullable=False),
    Column("model_id", Text),
    #: No default on any of the three spend columns. A writer that forgot them would
    #: otherwise record a confident zero.
    Column("input_tokens", Integer, nullable=False),
    Column("output_tokens", Integer, nullable=False),
    Column("est_cost", Numeric(20, 10), nullable=False),
    Column("asked_at", DateTime(timezone=True), nullable=False),
    Column("answered_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(_in_list("outcome", EXCHANGE_OUTCOMES), name="ck_assistant_exchange__outcome"),
    CheckConstraint(
        "(outcome = 'ANSWERED') = (length(trim(coalesce(answer, ''))) > 0)",
        name="ck_assistant_exchange__answer_iff_answered",
    ),
    CheckConstraint(
        "(outcome = 'REFUSED') = "
        f"(length(trim(coalesce(refusal_reason, ''))) >= {REASON_MIN_LENGTH})",
        name="ck_assistant_exchange__reason_iff_refused",
    ),
    CheckConstraint(
        "(outcome = 'REFUSED') = (refusal_gap IS NOT NULL) AND "
        f"(refusal_gap IS NULL OR {_in_list('refusal_gap', REFUSAL_GAPS)})",
        name="ck_assistant_exchange__gap_iff_refused",
    ),
    CheckConstraint(
        "refusal_screen IS NULL OR outcome = 'REFUSED'",
        name="ck_assistant_exchange__screen_only_on_refusal",
    ),
    CheckConstraint(
        "(outcome = 'FAILED') = (failure_cause IS NOT NULL) AND "
        f"(failure_cause IS NULL OR {_in_list('failure_cause', ERROR_TYPES)})",
        name="ck_assistant_exchange__cause_iff_failed",
    ),
    CheckConstraint(
        "failure_detail IS NULL OR outcome = 'FAILED'",
        name="ck_assistant_exchange__detail_only_on_failure",
    ),
    CheckConstraint(
        "jsonb_typeof(citations) = 'array' AND jsonb_typeof(tool_calls) = 'array' "
        "AND (outcome = 'ANSWERED' OR citations = '[]'::jsonb)",
        name="ck_assistant_exchange__citations_only_on_answer",
    ),
    CheckConstraint(
        "input_tokens >= 0 AND output_tokens >= 0 AND est_cost >= 0",
        name="ck_assistant_exchange__spend_not_negative",
    ),
    CheckConstraint(
        "model_id IS NOT NULL OR (input_tokens = 0 AND output_tokens = 0 AND est_cost = 0)",
        name="ck_assistant_exchange__spend_needs_a_model",
    ),
    CheckConstraint("answered_at >= asked_at", name="ck_assistant_exchange__answered_after_asked"),
    CheckConstraint(
        "length(trim(principal_id)) > 0 AND length(trim(question)) > 0",
        name="ck_assistant_exchange__who_and_what_not_blank",
    ),
    Index("ix_assistant_exchange__principal", "tenant_id", "principal_id", "asked_at"),
    Index("ix_assistant_exchange__tenant_month", "tenant_id", "asked_at"),
)


#: P7, 0024. Who a digest is for.
DIGEST_AUDIENCES = ("team", "executive")

team_digest = Table(
    "team_digest",
    metadata,
    #: FEAT-041, 0024. One digest per audience, team and week, composed whether or not
    #: anything can send it. Where it goes is OPEN-11.
    Column("digest_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("audience", Text, nullable=False),
    #: The bill's `team` tag value for a team digest, and null for the executive one.
    Column("team", Text),
    Column("period_start", Date, nullable=False),
    Column("period_end", Date, nullable=False),
    Column("prose", Text, nullable=False),
    Column("citations", JSONB, nullable=False),
    Column("composed_at", DateTime(timezone=True), nullable=False),
    #: Null means composed and not sent, which is a real state, with the reason beside it.
    Column("sent_at", DateTime(timezone=True)),
    Column("unsent_reason", Text),
    CheckConstraint(_in_list("audience", DIGEST_AUDIENCES), name="ck_team_digest__audience"),
    CheckConstraint(
        "(audience = 'team') = (length(trim(coalesce(team, ''))) > 0)",
        name="ck_team_digest__team_iff_team_audience",
    ),
    CheckConstraint(
        f"(sent_at IS NULL) = (length(trim(coalesce(unsent_reason, ''))) >= {REASON_MIN_LENGTH})",
        name="ck_team_digest__reason_iff_unsent",
    ),
    CheckConstraint(
        "sent_at IS NULL OR sent_at >= composed_at", name="ck_team_digest__sent_after_composed"
    ),
    CheckConstraint(
        "period_end > period_start AND length(trim(prose)) > 0 "
        "AND jsonb_typeof(citations) = 'array'",
        name="ck_team_digest__a_week_with_prose",
    ),
    Index("ix_team_digest__period", "tenant_id", "period_start"),
)
Index(
    "uq_team_digest__identity",
    team_digest.c.tenant_id,
    team_digest.c.audience,
    text("coalesce(team, '')"),
    team_digest.c.period_start,
    unique=True,
)


#: P7, 0025. What redaction did on finding a secret, mirrored from `finops_query.redaction`.
REDACTION_ACTIONS = ("BLOCKED", "REDACTED")
#: Where a rule fired: the question the asker typed, or what a tool returned to the model. 0046.
REDACTION_SOURCES = ("question", "tool_result")

redaction_event = Table(
    "redaction_event",
    metadata,
    #: FEAT-046, 0025. The rule that fired and what it did. There is no column the secret
    #: could go in, deliberately: not the text, a hash, a position or a length.
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column(
        "exchange_id",
        UUID(as_uuid=True),
        ForeignKey("assistant_exchange.exchange_id"),
        nullable=False,
    ),
    #: The asker, so the guard can confine the rows to them, ADR-0029.
    Column("principal_id", Text, nullable=False),
    #: A gitleaks rule identifier, such as `aws-access-token`.
    Column("rule_id", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    #: The question, or a tool's result, 0046. A tool's result is the estate's data, not
    #: something the asker typed, ISS-085.
    Column("found_in", Text, nullable=False, server_default="question"),
    CheckConstraint(_in_list("action", REDACTION_ACTIONS), name="ck_redaction_event__action"),
    CheckConstraint(_in_list("found_in", REDACTION_SOURCES), name="ck_redaction_event__found_in"),
    CheckConstraint(
        "length(trim(rule_id)) > 0 AND length(trim(principal_id)) > 0",
        name="ck_redaction_event__named",
    ),
    Index("ix_redaction_event__principal", "tenant_id", "principal_id", "occurred_at"),
)

#: P13, 0048. Tokens and requests per day, model and caller, from every AI source, FEAT-082.
#: Which sources exist is held by the migration's `ck_ai_usage_daily__provider` and not
#: mirrored here: ADR-0028 keeps every vendor's name out of `finops_api`.
ai_usage_daily = Table(
    "ai_usage_daily",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), primary_key=True),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("provider", Text, primary_key=True),
    #: An AWS account, or the provider's organization.
    Column("account_id", Text, primary_key=True),
    Column("usage_date", Date, primary_key=True),
    Column("model", Text, primary_key=True),
    #: An empty string in a key column means the source does not report that dimension.
    Column("workspace", Text, primary_key=True, server_default=""),
    Column("api_key_id", Text, primary_key=True, server_default=""),
    #: An IAM ARN or a provider's user identifier, which can name a person: class P.
    Column("caller", Text, primary_key=True, server_default=""),
    Column("application", Text, primary_key=True, server_default=""),
    Column("input_tokens", BigInteger, nullable=False),
    Column("output_tokens", BigInteger, nullable=False),
    Column("cache_read_tokens", BigInteger, nullable=False),
    Column("cache_write_tokens", BigInteger, nullable=False),
    #: Null where a source counts tokens and not requests, never a zero.
    Column("requests", BigInteger),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("model <> ''", name="ck_ai_usage_daily__model_named"),
    CheckConstraint(
        "input_tokens >= 0 AND output_tokens >= 0 "
        "AND cache_read_tokens >= 0 AND cache_write_tokens >= 0",
        name="ck_ai_usage_daily__tokens_not_negative",
    ),
    CheckConstraint("requests >= 0", name="ck_ai_usage_daily__requests_not_negative"),
    CheckConstraint("collected_at >= as_of", name="ck_ai_usage_daily__collected_after_true"),
    Index("ix_ai_usage_daily__tenant_date", "tenant_id", "usage_date"),
)

#: P13, 0049. The AI provider organizations a tenant connects, FEAT-083. The admin key is never
#: here: `key_secret_name` names a Secrets Manager secret under `meter/<env>/ai/`. Which providers
#: exist is the migration's constraint, ADR-0028 keeping vendors' names out of `finops_api`.
ai_provider_account = Table(
    "ai_provider_account",
    metadata,
    Column("provider", Text, primary_key=True),
    Column("organization_id", Text, primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("name", Text, nullable=False),
    Column("key_secret_name", Text, nullable=False),
    Column("enrolled_at", DateTime(timezone=True), nullable=False),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    CheckConstraint(
        "length(trim(organization_id)) > 0 AND length(trim(name)) > 0",
        name="ck_ai_provider_account__named",
    ),
    CheckConstraint(
        "key_secret_name ~ '^meter/[a-z]+/ai/[A-Za-z0-9/_+=.@-]+$'",
        name="ck_ai_provider_account__key_under_the_ai_path",
    ),
    Index("ix_ai_provider_account__tenant", "tenant_id", "provider"),
)

#: P13, 0052. How busy each GPU instance's accelerators were per day, FEAT-084. An instance that
#: published nothing has no row, which reads as not published and never as nought percent.
gpu_utilization_daily = Table(
    "gpu_utilization_daily",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), primary_key=True),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("account_id", Text, primary_key=True),
    Column("region_id", Text, primary_key=True),
    Column("instance_id", Text, primary_key=True),
    Column("usage_date", Date, primary_key=True),
    Column("gpu_count", Integer, nullable=False),
    Column("average_percent", Numeric(5, 2), nullable=False),
    Column("peak_percent", Numeric(5, 2), nullable=False),
    Column("samples", Integer, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("gpu_count > 0 AND samples > 0", name="ck_gpu_utilization_daily__measured"),
    CheckConstraint(
        "average_percent BETWEEN 0 AND 100 AND peak_percent BETWEEN 0 AND 100",
        name="ck_gpu_utilization_daily__percentages",
    ),
    CheckConstraint(
        "peak_percent >= average_percent", name="ck_gpu_utilization_daily__peak_at_least_average"
    ),
    CheckConstraint("collected_at >= as_of", name="ck_gpu_utilization_daily__collected_after_true"),
)

#: P14, 0054. What each member account holds, from the service that sold it, FEAT-086: a Savings
#: Plan or a reservation with its real term and end. Exactly one of quantity and hourly commitment.
commitment_inventory = Table(
    "commitment_inventory",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), primary_key=True),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("kind", Text, primary_key=True),
    Column("commitment_id", Text, primary_key=True),
    Column("program", Text, nullable=False),
    Column("account_id", Text, nullable=False),
    Column("region_id", Text),
    Column("applies_to", Text),
    Column("quantity", Integer),
    Column("hourly_commitment", Numeric(20, 10)),
    Column("term_months", Integer, nullable=False),
    Column("payment_option", Text, nullable=False),
    Column("upfront_amount", Numeric(20, 10), nullable=False),
    Column("recurring_hourly", Numeric(20, 10), nullable=False),
    Column("currency", Text, nullable=False),
    Column("starts_at", DateTime(timezone=True), nullable=False),
    Column("ends_at", DateTime(timezone=True), nullable=False),
    Column("state", Text, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "kind IN ('savings_plan', 'reservation')", name="ck_commitment_inventory__kind"
    ),
    CheckConstraint(
        "(quantity IS NULL) <> (hourly_commitment IS NULL)",
        name="ck_commitment_inventory__one_measure",
    ),
    CheckConstraint(
        "term_months > 0 AND (quantity IS NULL OR quantity > 0) "
        "AND (hourly_commitment IS NULL OR hourly_commitment > 0) "
        "AND upfront_amount >= 0 AND recurring_hourly >= 0",
        name="ck_commitment_inventory__positive",
    ),
    CheckConstraint("ends_at > starts_at", name="ck_commitment_inventory__ends_after_start"),
    CheckConstraint("collected_at >= as_of", name="ck_commitment_inventory__collected_after_true"),
    Index("ix_commitment_inventory__ends", "tenant_id", "ends_at"),
)

#: P14, 0055. What a tenant's purchase plans aim for, FEAT-088: a row per tenant, the cautious
#: default installed for every one.
commitment_policy = Table(
    "commitment_policy",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), primary_key=True),
    Column("target_coverage", Numeric(4, 3), nullable=False),
    Column("term_years", Integer, nullable=False),
    Column("payment_option", Text, nullable=False),
    Column("ladder_limit", Numeric(5, 4), nullable=False),
    Column("reason", Text, nullable=False),
    Column("updated_by", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    CheckConstraint(
        "target_coverage > 0 AND target_coverage <= 1", name="ck_commitment_policy__coverage"
    ),
    CheckConstraint("term_years IN (1, 3)", name="ck_commitment_policy__term"),
    CheckConstraint(
        "payment_option IN ('No Upfront', 'Partial Upfront', 'All Upfront')",
        name="ck_commitment_policy__payment",
    ),
    CheckConstraint("ladder_limit > 0 AND ladder_limit <= 1", name="ck_commitment_policy__ladder"),
    CheckConstraint("length(trim(reason)) > 0", name="ck_commitment_policy__reason"),
)

#: P14, 0056. AWS's purchase recommendations, FEAT-089: a row per Savings Plans type or reserved
#: service, as AWS last recommended it, or the typed cause it could not be read with.
purchase_recommendation = Table(
    "purchase_recommendation",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), primary_key=True),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("kind", Text, primary_key=True),
    Column("program", Text, primary_key=True),
    Column("term_years", Integer, nullable=False),
    Column("payment_option", Text, nullable=False),
    Column("lookback_days", Integer, nullable=False),
    Column("recommended", Boolean),
    Column("hourly_commitment", Numeric(20, 10)),
    Column("units", Numeric(20, 4)),
    Column("estimated_monthly_savings", Numeric(20, 10)),
    Column("estimated_savings_percent", Numeric(10, 4)),
    Column("upfront_cost", Numeric(20, 10)),
    Column("currency", Text),
    Column("failure_cause", Text),
    Column("failure_detail", Text),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "kind IN ('savings_plan', 'reservation')", name="ck_purchase_recommendation__kind"
    ),
    CheckConstraint(
        "(failure_cause IS NULL AND recommended IS NOT NULL AND estimated_monthly_savings IS NOT "
        "NULL AND upfront_cost IS NOT NULL AND currency IS NOT NULL) OR (failure_cause IS NOT "
        "NULL AND recommended IS NULL AND hourly_commitment IS NULL AND units IS NULL AND "
        "estimated_monthly_savings IS NULL)",
        name="ck_purchase_recommendation__read_or_failed",
    ),
    CheckConstraint(
        "hourly_commitment IS NULL OR kind = 'savings_plan'",
        name="ck_purchase_recommendation__measure_of_its_kind",
    ),
    CheckConstraint(
        "units IS NULL OR kind = 'reservation'",
        name="ck_purchase_recommendation__units_of_its_kind",
    ),
    CheckConstraint(
        "collected_at >= as_of", name="ck_purchase_recommendation__collected_after_true"
    ),
)

#: P14, FEAT-089, migration 0057. Meter's purchase plan, one per tenant per month, its lines and
#: the events of its lifecycle. Payer wide, ADR-0025. The trigger refusing a transition out of
#: order lives in the migration, constraint 11.
PLAN_STATUSES = ("DRAFT", "APPROVED", "BOUGHT", "VERIFIED", "WITHDRAWN", "LAPSED")

purchase_plan = Table(
    "purchase_plan",
    metadata,
    Column("plan_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("ingest_run_id", UUID(as_uuid=True), nullable=False),
    Column("plan_month", Date, nullable=False),
    Column("status", Text, nullable=False, server_default="DRAFT"),
    Column("target_coverage", Numeric(4, 3), nullable=False),
    Column("term_years", Integer, nullable=False),
    Column("payment_option", Text, nullable=False),
    Column("ladder_limit", Numeric(5, 4), nullable=False),
    Column("window_start", Date, nullable=False),
    Column("window_end", Date, nullable=False),
    Column("days_held", Integer, nullable=False),
    Column("steady_hourly", Numeric(20, 4)),
    Column("held_hourly", Numeric(20, 4)),
    Column("target_hourly", Numeric(20, 4)),
    Column("beyond_hourly", Numeric(20, 4)),
    Column("unpriced", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("no_purchase_reason", Text),
    Column("currency", Text, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("tenant_id", "plan_month", name="uq_purchase_plan__month"),
    CheckConstraint(
        "status IN ('DRAFT', 'APPROVED', 'BOUGHT', 'VERIFIED', 'WITHDRAWN', 'LAPSED')",
        name="ck_purchase_plan__status",
    ),
    CheckConstraint("collected_at >= as_of", name="ck_purchase_plan__collected_after_true"),
)

purchase_plan_line = Table(
    "purchase_plan_line",
    metadata,
    Column("plan_id", UUID(as_uuid=True), ForeignKey("purchase_plan.plan_id"), primary_key=True),
    Column("line_no", Integer, primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("program", Text, nullable=False),
    Column("instance_family", Text),
    Column("region_id", Text),
    Column("tranche_month", Date, nullable=False),
    Column("hourly_commitment", Numeric(20, 3), nullable=False),
    Column("discount_percent", Numeric(7, 4), nullable=False),
    Column("covers_hourly", Numeric(20, 4), nullable=False),
    Column("monthly_saving", Numeric(20, 2), nullable=False),
    Column("usage_floor_percent", Numeric(5, 1), nullable=False),
    Column("upfront_cost", Numeric(20, 2), nullable=False),
    Column("matched_commitment_id", Text),
    CheckConstraint("program IN ('Compute', 'EC2Instance')", name="ck_purchase_plan_line__program"),
    CheckConstraint("hourly_commitment > 0", name="ck_purchase_plan_line__buys_something"),
    # Migration 0058, TASK-P14-008: a commitment pays for one line at most.
    Index(
        "uq_purchase_plan_line__matched_once",
        "tenant_id",
        "matched_commitment_id",
        unique=True,
        postgresql_where=text("matched_commitment_id IS NOT NULL"),
    ),
)

purchase_plan_event = Table(
    "purchase_plan_event",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("plan_id", UUID(as_uuid=True), ForeignKey("purchase_plan.plan_id"), nullable=False),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("from_status", Text),
    Column("to_status", Text, nullable=False),
    Column("principal", Text, nullable=False),
    Column("at", DateTime(timezone=True), nullable=False),
    Column("note", Text),
    Index("ix_purchase_plan_event__plan", "plan_id", "at"),
)

#: P8, 0026. The two formats an export is written in, mirrored by the migration's constraint.
REPORT_FORMATS = ("xlsx", "csv")
#: P8, 0029. What became of a run: streamed to whoever pressed Export, rendered and kept, kept
#: and sent, or failed with one of the seven causes.
REPORT_RUN_STATUSES = ("STREAMED", "RENDERED", "SENT", "FAILED")
#: P8, 0029. How often a schedule renders, from the domain's own enumeration.
REPORT_CADENCES = tuple(cadence.value for cadence in Cadence)

report_run = Table(
    "report_run",
    metadata,
    #: FEAT-067, 0026. One row per export file, written in the transaction of the read it
    #: records, so a copy of the estate's figures never leaves without a line saying who took it.
    Column("run_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    #: Who made it, so the guard can confine the rows to them, ADR-0029.
    Column("principal_id", Text, nullable=False),
    #: The route the view reads, and its query without the format.
    Column("view_path", Text, nullable=False),
    Column("view_query", Text, nullable=False),
    #: The scope it was made under: every account, or exactly these.
    Column("scope_global", Boolean, nullable=False),
    Column("scope_accounts", ARRAY(Text), nullable=False),
    Column("format", Text, nullable=False),
    Column("row_count", Integer, nullable=False),
    Column("byte_count", BigInteger, nullable=False),
    #: The workbook stopped at the row limit, which its About sheet says.
    Column("truncated", Boolean, nullable=False),
    Column("made_at", DateTime(timezone=True), nullable=False),
    #: FEAT-069, 0029. The schedule that rendered it, or none for a file somebody exported.
    Column(
        "schedule_id",
        UUID(as_uuid=True),
        ForeignKey("report_schedule.schedule_id", ondelete="SET NULL"),
    ),
    Column("status", Text, nullable=False, server_default=text("'STREAMED'")),
    #: Where a rendered file is kept, under the tenant's prefix in the data bucket.
    Column("storage_key", Text),
    Column("failure_cause", Text),
    Column("failure_detail", Text),
    #: How fresh the file's figures were, from the envelope the export was written from.
    Column("as_of", DateTime(timezone=True)),
    Column("collected_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    CheckConstraint(_in_list("format", REPORT_FORMATS), name="ck_report_run__format"),
    CheckConstraint(_in_list("status", REPORT_RUN_STATUSES), name="ck_report_run__status"),
    CheckConstraint(
        f"(status = 'FAILED') = (failure_cause IS NOT NULL) "
        f"AND (failure_cause IS NULL OR {_in_list('failure_cause', ERROR_TYPES)})",
        name="ck_report_run__failure",
    ),
    CheckConstraint(
        "status NOT IN ('RENDERED', 'SENT') OR storage_key IS NOT NULL",
        name="ck_report_run__stored",
    ),
    CheckConstraint(
        "status <> 'STREAMED' OR (storage_key IS NULL AND schedule_id IS NULL)",
        name="ck_report_run__streamed",
    ),
    CheckConstraint(
        "finished_at IS NULL OR finished_at >= made_at", name="ck_report_run__finished"
    ),
    CheckConstraint("row_count >= 0 AND byte_count >= 0", name="ck_report_run__counts"),
    CheckConstraint(
        "length(trim(principal_id)) > 0 AND view_path LIKE '/%'", name="ck_report_run__named"
    ),
    CheckConstraint(
        "NOT scope_global OR cardinality(scope_accounts) = 0", name="ck_report_run__scope"
    ),
    Index("ix_report_run__principal", "tenant_id", "principal_id", "made_at"),
    Index("ix_report_run__schedule", "schedule_id"),
)

#: P8, 0028. Who besides its owner may open a saved view, mirrored by the migration's constraint.
SAVED_VIEW_VISIBILITIES = ("PRIVATE", "SHARED")

saved_view = Table(
    "saved_view",
    metadata,
    #: FEAT-068, 0028. A screen and its query, named by a person and kept for them or shared
    #: with the tenant. Configuration and never data, P8 spec section 5.6: no figure is stored,
    #: so the screen is read afresh in the opener's own scope.
    Column("view_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    #: Whose it is. Only they rename, share or delete it, and a private one only they open,
    #: ADR-0032.
    Column("owner_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    #: A screen the navigation knows, `finops_api.screens`.
    Column("screen_path", Text, nullable=False),
    #: The screen's query string as an object, each key to one value or a list of them.
    Column("query", JSONB, nullable=False),
    Column("visibility", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        _in_list("visibility", SAVED_VIEW_VISIBILITIES), name="ck_saved_view__visibility"
    ),
    CheckConstraint(
        "length(trim(owner_id)) > 0 AND length(trim(name)) > 0 "
        f"AND length(name) <= {SAVED_VIEW_NAME_MAX_LENGTH}",
        name="ck_saved_view__named",
    ),
    CheckConstraint(_in_list("screen_path", SCREEN_PATHS), name="ck_saved_view__screen"),
    CheckConstraint("jsonb_typeof(query) = 'object'", name="ck_saved_view__query"),
    CheckConstraint("updated_at >= created_at", name="ck_saved_view__times"),
    Index("ix_saved_view__owner", "tenant_id", "owner_id", "updated_at"),
    Index(
        "ix_saved_view__shared",
        "tenant_id",
        "updated_at",
        postgresql_where=text("visibility = 'SHARED'"),
    ),
)

report_schedule = Table(
    "report_schedule",
    metadata,
    #: FEAT-069, 0029. A saved view, one route its screen exports, a format, a cadence and the
    #: people it renders for, each in their own scope. The view must be one the owner can open,
    #: which a trigger in the migration holds because a check cannot read another table.
    Column("schedule_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("owner_id", Text, nullable=False),
    #: Null once the view is deleted: the schedule stays, paused, so its owner sees what happened
    #: rather than finding it gone, and nobody's schedule is deleted by somebody else.
    Column("view_id", UUID(as_uuid=True), ForeignKey("saved_view.view_id", ondelete="SET NULL")),
    #: The route a run renders, with its query and without a format, `/api/v1/...`.
    Column("export_path", Text, nullable=False),
    Column("format", Text, nullable=False),
    Column("cadence", Text, nullable=False),
    #: The principals it renders for, by the identifier their sessions carry.
    Column("recipients", ARRAY(Text), nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("next_run_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(_in_list("format", REPORT_FORMATS), name="ck_report_schedule__format"),
    CheckConstraint(_in_list("cadence", REPORT_CADENCES), name="ck_report_schedule__cadence"),
    CheckConstraint(
        f"cardinality(recipients) BETWEEN 1 AND {REPORT_RECIPIENTS_MAX} "
        "AND NOT ('' = ANY (recipients))",
        name="ck_report_schedule__recipients",
    ),
    CheckConstraint("length(trim(owner_id)) > 0", name="ck_report_schedule__named"),
    CheckConstraint(
        "export_path LIKE '/api/v1/%' AND position('format=' in export_path) = 0",
        name="ck_report_schedule__path",
    ),
    CheckConstraint("updated_at >= created_at", name="ck_report_schedule__times"),
    Index("ix_report_schedule__due", "next_run_at", postgresql_where=text("enabled")),
    Index("ix_report_schedule__owner", "tenant_id", "owner_id", "updated_at"),
    Index("ix_report_schedule__view", "view_id"),
)


#: Every table in the schema. Used by the drift test and by the repository layer.
ALL_TABLES = tuple(metadata.sorted_tables)

#: Tables recording our own work rather than a cloud's. They carry an `as_of` and are
#: deliberately not facts, for the reason `finops_core.domain.fact` gives for `IngestRun`
#: not inheriting from `Fact`: a watermark's `as_of` is how far this collector has read,
#: which is a statement about Meter, so there is nothing for a `collected_at` to mean.
#: Listed by name because each is an argued exception, and a list of exceptions that has
#: to be defended one at a time does not rot the way an inventory of the rule does.
NOT_FACT_TABLES = (
    "ingest_watermark",
    # P8, 0029. A run records Meter's own work, a file made or not, and its `as_of` is the
    # freshness of the figures in that file: absent for a run that made none, and for every row
    # written before 0029, so it cannot be held non null the way a fact's can.
    "report_run",
)

#: Tables holding a fact about a cloud, which must carry both timestamps.
#:
#: Derived rather than listed. It was a hand written tuple of eight names until
#: 2026-09-28, and the schema had grown well past it: `budget`, `sizing_refusal`,
#: `resource_management` and others carry `as_of` and were outside the two tests that
#: read this, so constraint 10 was being asserted of a shrinking fraction of the schema
#: while both tests stayed green. A table with an `as_of` about somebody else's estate is
#: a table claiming when something was true, and that is the whole membership rule, so it
#: is asked of the schema instead of remembered.
FACT_TABLES = tuple(
    table.name
    for table in metadata.sorted_tables
    if "as_of" in table.c and table.name not in NOT_FACT_TABLES
)


#: P15, 0059. The GitHub App a tenant connected, FEAT-091: its id and its key's secret name, never
#: the key. The installation is found from the repository on each request, so it is not here.
code_host_connection = Table(
    "code_host_connection",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), primary_key=True),
    Column("host", Text, nullable=False),
    Column("app_id", Text, nullable=False),
    Column("key_secret_name", Text, nullable=False),
    Column("connected_by", Text, nullable=False),
    Column("connected_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    CheckConstraint("host IN ('github')", name="ck_code_host_connection__host"),
    CheckConstraint("app_id ~ '^[A-Za-z0-9.]+$'", name="ck_code_host_connection__app"),
    CheckConstraint(
        "key_secret_name ~ '^meter/[a-z]+/codehost/[A-Za-z0-9/_+=.@-]+$'",
        name="ck_code_host_connection__key",
    ),
)

#: P15, 0059. Where each Terraform state's fixes go, OPEN-42: keyed by the state reference FEAT-057
#: records in `resource_management`.
repository_mapping = Table(
    "repository_mapping",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), primary_key=True),
    Column("state_reference", Text, primary_key=True),
    Column("repository", Text, nullable=False),
    Column("base_branch", Text, nullable=False),
    #: Relative to the repository's root; empty for the root itself.
    Column("folder", Text, nullable=False, server_default=""),
    Column("set_by", Text, nullable=False),
    Column("set_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    CheckConstraint("length(trim(state_reference)) > 0", name="ck_repository_mapping__state"),
    CheckConstraint(
        "repository ~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'", name="ck_repository_mapping__repository"
    ),
    CheckConstraint("length(trim(base_branch)) > 0", name="ck_repository_mapping__branch"),
    CheckConstraint(
        r"folder = '' OR (folder !~ '^/' AND folder !~ '/$' AND folder !~ '(^|/)\.\.?(/|$)')",
        name="ck_repository_mapping__folder",
    ),
)


#: P15, 0060. A fix a person asked for and its pull request, FEAT-092: one live per recommendation,
#: scoped as the recommendation's account.
fix_pull_request = Table(
    "fix_pull_request",
    metadata,
    Column("fix_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column(
        "recommendation_id",
        UUID(as_uuid=True),
        ForeignKey("recommendation.recommendation_id"),
        nullable=False,
    ),
    Column("sub_account_id", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("repository", Text),
    Column("branch", Text),
    Column("number", Integer),
    Column("url", Text),
    Column("note", Text),
    Column("requested_by", Text, nullable=False),
    Column("requested_at", DateTime(timezone=True), nullable=False),
    Column("merged_by", Text),
    #: When it merged or closed without merging, TASK-P15-006: a reading older proves nothing.
    Column("merged_at", DateTime(timezone=True)),
    Column("closed_at", DateTime(timezone=True)),
    Column("reason", Text),
    Column("failure_cause", Text),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('REQUESTED', 'OPEN', 'MERGED', 'CLOSED', 'NOT_AUTHORED', 'FAILED')",
        name="ck_fix_pull_request__status",
    ),
    CheckConstraint(
        "status NOT IN ('OPEN', 'MERGED', 'CLOSED') OR (repository IS NOT NULL AND branch IS NOT "
        "NULL AND number IS NOT NULL AND url IS NOT NULL)",
        name="ck_fix_pull_request__opened_names_it",
    ),
    CheckConstraint(
        "status NOT IN ('NOT_AUTHORED', 'FAILED') OR length(trim(coalesce(reason, ''))) > 0",
        name="ck_fix_pull_request__none_says_why",
    ),
    CheckConstraint(
        "(status = 'FAILED') = (failure_cause IS NOT NULL)",
        name="ck_fix_pull_request__failure_typed",
    ),
    CheckConstraint(
        "failure_cause IS NULL OR failure_cause IN ('AccessDenied', 'Throttled', 'NotOptedIn', "
        "'NoData', 'Unreachable', 'Misconfigured', 'SchemaDrift')",
        name="ck_fix_pull_request__cause",
    ),
    CheckConstraint("collected_at >= as_of", name="ck_fix_pull_request__collected_after_true"),
    CheckConstraint(
        "(status = 'MERGED') = (merged_at IS NOT NULL)", name="ck_fix_pull_request__merged_when"
    ),
    Index(
        "ux_fix_pull_request__live",
        "tenant_id",
        "recommendation_id",
        unique=True,
        postgresql_where=text("status IN ('REQUESTED', 'OPEN')"),
    ),
    Index("ix_fix_pull_request__status", "tenant_id", "status"),
)

#: P15, 0060. Each step of a fix, append only, with its principal: a person, Meter, or the code
#: host's login of whoever merged or closed it.
fix_pull_request_event = Table(
    "fix_pull_request_event",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("fix_id", UUID(as_uuid=True), ForeignKey("fix_pull_request.fix_id"), nullable=False),
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False),
    Column("sub_account_id", Text, nullable=False),
    Column("from_status", Text),
    Column("to_status", Text, nullable=False),
    Column("principal", Text, nullable=False),
    Column("note", Text),
    Column("at", DateTime(timezone=True), nullable=False),
    CheckConstraint("length(trim(principal)) > 0", name="ck_fix_pull_request_event__principal"),
    Index("ix_fix_pull_request_event__fix", "fix_id", "at"),
)


#: P15, 0062. What the volume pass read of each volume, restated every run, so a gp2 volume moved
#: to gp3 can be seen to have moved. TASK-P15-006.
volume_observation = Table(
    "volume_observation",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), primary_key=True),
    Column("sub_account_id", Text, primary_key=True),
    Column("resource_id", Text, primary_key=True),
    Column("region_id", Text, nullable=False),
    Column("volume_type", Text, nullable=False),
    Column("size_gib", Integer, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("length(trim(volume_type)) > 0", name="ck_volume_observation__type"),
    CheckConstraint("size_gib > 0", name="ck_volume_observation__size"),
    CheckConstraint("collected_at >= as_of", name="ck_volume_observation__collected_after_true"),
)


#: P15, 0063. Which reversible fixes a tenant lets Meter merge, FEAT-094: empty to start, and a
#: check holding each class to the reversible set, ADR-0038.
merge_policy = Table(
    "merge_policy",
    metadata,
    Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), primary_key=True),
    Column("waste_class", Text, primary_key=True),
    Column("reason", Text, nullable=False),
    Column("set_by", Text, nullable=False),
    Column("set_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    CheckConstraint("waste_class IN ('EBS_GP2_TO_GP3')", name="ck_merge_policy__reversible"),
    CheckConstraint("length(trim(reason)) > 0", name="ck_merge_policy__reason"),
)
