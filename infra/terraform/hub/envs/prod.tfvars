# The production hub.
#
# Four values are deliberately absent and are supplied at apply time:
# image_tag, certificate_arn, page_topic_arn and ticket_topic_arn. The last
# three are refused as empty in production by preconditions, so a first apply
# without them fails at plan rather than producing a stack with TLS off and no
# alerting.

env    = "prod"
owner  = "platform"
region = "eu-west-1"

organization_id = "o-prodexample0"

# Set from the output of infra/terraform/management once that stack is applied.
org_reader_role_arn = ""

database_min_capacity = 0.5
database_max_capacity = 4

api_desired_count = 2
web_desired_count = 2
worker_max_count  = 4

# Ninety days, matching the operational retention window in
# docs/09-DATA-CLASSIFICATION.md.
log_retention_days = 90

# The AWS maximum, which is below every table retention window, so a backup
# never resurrects data the policy says was removed.
backup_retention_days = 35

# Every setting this environment's services read that settings.tf does not derive, TASK-P12-006.
# Started from .env.example on 2026-10-12. The CUR export prefix and table name, the Regions to
# collect and the thresholds are the owner's to review before the first deploy.
# prod cannot start yet: the local identity provider is refused in production and no other one is
# built, ISS-280, so METER_IDENTITY_PROVIDER names that rather than pretending to a provider.
settings = {
  METER_LOG_LEVEL                                     = "INFO"
  METER_DB_POOL_SIZE                                  = "5"
  METER_DB_MAX_OVERFLOW                               = "5"
  METER_REGIONS                                       = "eu-west-1,eu-west-2"
  METER_AWS_CONNECT_TIMEOUT_SECONDS                   = "10"
  METER_AWS_READ_TIMEOUT_SECONDS                      = "30"
  METER_AWS_MAX_RETRIES                               = "2"
  METER_GETMETRICDATA_BATCH_SIZE                      = "500"
  METER_CUR_EXPORT_PREFIX                             = "exports/focus"
  METER_CUR_ATHENA_TABLE                              = "focus_daily"
  METER_CONFIG_AGGREGATOR                             = "meter-organization"
  METER_ANOMALY_SENSITIVITY                           = "3.0"
  METER_ANOMALY_FLOOR_USD                             = "5.0"
  METER_RUN_CLAIM_TIMEOUT_MINUTES                     = "30"
  METER_WORKER_CONCURRENCY                            = "8"
  METER_IDENTITY_PROVIDER                             = "unset, no production identity provider exists yet, ISS-280"
  METER_LOCAL_AUTH_FILE                               = "/app/local-auth.yaml"
  METER_LOCAL_TENANT_ID                               = "5eeded00-0000-4000-8000-000000000001"
  METER_SESSION_TTL_HOURS                             = "8"
  METER_ENTITLEMENT_CACHE_TTL_MINUTES                 = "15"
  METER_EXPORT_ROW_LIMIT                              = "100000"
  METER_SEVERITY_CRITICAL_USD                         = "1000"
  METER_SEVERITY_HIGH_USD                             = "100"
  METER_SEVERITY_MEDIUM_USD                           = "20"
  METER_ANOMALY_Z_SCORE                               = "3.0"
  METER_ANOMALY_ABSOLUTE_USD                          = "50"
  METER_ANOMALY_RELATIVE_PERCENT                      = "20"
  METER_ANOMALY_BASELINE_DAYS                         = "30"
  METER_ANOMALY_AUTORESOLVE_DAYS                      = "2"
  METER_RIGHTSIZING_MIN_DAYS                          = "14"
  METER_RIGHTSIZING_PERCENTILE                        = "95"
  METER_RIGHTSIZING_MEMORY_HEADROOM_PERCENT           = "15"
  METER_RIGHTSIZING_MEMORY_HEADROOM_OOMKILLED_PERCENT = "25"
  METER_PARKING_OBSERVATION_DAYS                      = "14"
  METER_PARKING_IDLE_PERCENT                          = "5"
  METER_PARKING_MINIMUM_WEEKS                         = "2"
  METER_PARKING_MINIMUM_WINDOW_HOURS                  = "3"
  METER_COMMITMENT_DISCOUNT_PERCENT                   = "30"
  METER_COMMITMENT_TERM_MONTHS                        = "12"
  METER_COMMITMENT_MINIMUM_MONTHLY_SAVING_USD         = "25"
  METER_IAC_STATE_LOCATIONS                           = ""
  METER_IAC_EXHAUSTIVE_ACCOUNTS                       = ""
  METER_OWNER_TAG_KEYS                                = "team"
  METER_CATALOGUE_OWNER_KEY                           = "owner"
  METER_CREATOR_LOOKUPS_PER_RUN                       = "200"
  METER_AI_REQUEST_METADATA_KEY                       = ""
  METER_GPU_METRICS_NAMESPACE                         = "CWAgent"
  METER_COMMITMENT_RECOMMENDATION_SERVICES            = "Amazon Elastic Compute Cloud - Compute,Amazon Relational Database Service,Amazon ElastiCache,Amazon OpenSearch Service,Amazon Redshift,Amazon MemoryDB"
  METER_BLAST_RADIUS_WIDE_AT                          = "10"
  METER_BLAST_RADIUS_DEPTH                            = "4"
  METER_BUDGET_AT_RISK_MARGIN                         = "0.1"
  METER_MAX_GRAPH_NODES                               = "2000"
  METER_QUERY_LOGS_SCAN_PRICE_PER_GB                  = "0.005"
  METER_QUERY_METRICS_PRICE_PER_1000                  = "0.01"
  METER_QUERY_MANUAL_LOADS_PER_DAY                    = "4.0"
  METER_QUERY_VIEWING_HOURS_PER_DAY                   = "2.0"
  METER_QUERY_METRICS_PER_CALL                        = "1.0"
  METER_QUERY_DEFAULT_INGEST_GB_PER_DAY               = "50.0"
  METER_QUERY_ASSUMED_QUERY_SECONDS                   = "5.0"
  METER_QUERY_REFRESH_WARN_SECONDS                    = "60"
  METER_QUERY_REFRESH_CRIT_SECONDS                    = "30"
  METER_QUERY_TIMERANGE_WARN_HOURS                    = "24"
  METER_QUERY_TIMERANGE_CRIT_HOURS                    = "168"
  METER_QUERY_WRITE_LEVEL                             = "none"
  METER_QUERY_QUOTA_LOGS_CONCURRENT                   = "30"
  METER_QUERY_QUOTA_GETMETRICDATA_TPS                 = "50"
  METER_ASSISTANT_INPUT_USD_PER_MILLION_TOKENS        = "3.00"
  METER_ASSISTANT_OUTPUT_USD_PER_MILLION_TOKENS       = "15.00"
  METER_ASSISTANT_MONTHLY_TOKEN_BUDGET                = "2000000"
  METER_ASSISTANT_MAX_CONCURRENT_QUESTIONS            = "8"
  METER_RETENTION_PRINCIPAL_DAYS                      = "90"
  METER_RETENTION_OPERATIONAL_DAYS                    = "90"
  METER_RETENTION_ASSISTANT_DAYS                      = "90"
  METER_RETENTION_AI_USAGE_DAYS                       = "395"
  METER_RETENTION_PLAN_DAYS                           = "400"
  METER_RETENTION_AUDIT_DAYS                          = "395"
  METER_RETENTION_COST_DAYS                           = "1126"
  METER_FEATURE_MCP_SERVER                            = "false"
  METER_FEATURE_INGESTION                             = "true"
  METER_FEATURE_COLLECTOR_ORG_TREE                    = "true"
  METER_FEATURE_COLLECTOR_ACCOUNT_HEALTH              = "true"
  METER_FEATURE_COLLECTOR_PLATFORM_COST               = "true"
  METER_FEATURE_RETENTION_JOBS                        = "true"
  METER_FEATURE_SCOPE_AUDIT                           = "true"
  METER_FEATURE_LOCAL_AUTH                            = "false"
  METER_FEATURE_PULL_REQUEST_MERGE                    = "true"
}
