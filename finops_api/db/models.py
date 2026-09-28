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
    postgresql_partition_by="RANGE (billing_period_start)",
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
REQUEST_STATUSES = ("PENDING", "CASE_OPENED", "APPROVED", "DENIED", "CASE_CLOSED")

#: The length below which a reason is not a sentence. The same figure 0019 uses for a
#: sizing refusal and for the same argument: an explanation reading "not measured" would
#: be worse than none, because it teaches a reader the reasons here are empty and they
#: stop reading the ones that are not. A literal rather than a setting because a CHECK
#: constraint cannot read one, and it has to match 0020 character for character.
REASON_FLOOR = 12  # allow-hardcoded: a database check constraint cannot read settings


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
        f"(length(trim(coalesce(unmeasurable_reason, ''))) >= {REASON_FLOOR})",
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
        "status IN ('PENDING', 'CASE_OPENED', 'APPROVED', 'DENIED', 'CASE_CLOSED')",
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
        "status IN ('PENDING', 'CASE_OPENED', 'APPROVED', 'DENIED', 'CASE_CLOSED')",
        name="ck_quota_request_history__status",
    ),
    Index("ix_quota_request_history__request", "tenant_id", "request_id", "changed_at"),
)


#: Every table in the schema. Used by the drift test and by the repository layer.
ALL_TABLES = tuple(metadata.sorted_tables)

#: Tables recording our own work rather than a cloud's. They carry an `as_of` and are
#: deliberately not facts, for the reason `finops_core.domain.fact` gives for `IngestRun`
#: not inheriting from `Fact`: a watermark's `as_of` is how far this collector has read,
#: which is a statement about Meter, so there is nothing for a `collected_at` to mean.
#: Listed by name because each is an argued exception, and a list of exceptions that has
#: to be defended one at a time does not rot the way an inventory of the rule does.
NOT_FACT_TABLES = ("ingest_watermark",)

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
