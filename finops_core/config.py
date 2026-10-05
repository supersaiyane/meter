"""One typed place for every value the project reads. ADR-0017.

This lands before there is any code to put values in, because doing it
afterwards means finding every literal already written.

Two rules make it work.

Nothing here carries a default except a feature flag. A default in code is a
value that never appears in `.env.example`, and a value that never appears in
`.env.example` is one nobody can find when it is wrong. It is also how a region
or a role name ends up compiled into an image, which is exactly what
`scripts/ci/check_hardcoded.py` refuses.

Nothing outside this module reads `os.environ`. That is the entire point, and
the same check enforces it.

A missing or malformed value stops the process at startup and names the
variable. A service that starts with half a configuration fails later, further
away, and as a wrong number rather than an error.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from finops_core.constants import (
    ASSISTANT_CONCURRENCY_CEILING,
    ENV_PREFIX,
    LOCAL_IDENTITY_PROVIDER,
    PRODUCTION_ENV,
)
from finops_core.domain.query import WriteLevel


class ConfigurationError(RuntimeError):
    """The process cannot start with the configuration it was given."""


class Settings(BaseSettings):
    """Every `METER_` variable in `.env.example`, typed, with no hidden defaults."""

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, extra="ignore", frozen=True)

    # Runtime
    env: Literal["local", "dev", "staging", "prod"]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    # Database
    database_url: str = Field(min_length=1)
    db_pool_size: int = Field(ge=1)
    db_max_overflow: int = Field(ge=0)

    # Cloud reach
    regions: str
    collector_role_name: str = Field(min_length=1)
    org_reader_role_arn: str
    external_id_secret: str = Field(min_length=1)
    aws_connect_timeout_seconds: int = Field(ge=1)
    aws_read_timeout_seconds: int = Field(ge=1)
    aws_max_retries: int = Field(ge=0)
    getmetricdata_batch_size: int = Field(ge=1)

    # The billing export. P1, FEAT-020.
    cur_export_bucket: str = Field(min_length=1)
    cur_export_prefix: str = Field(min_length=1)
    cur_athena_database: str = Field(min_length=1)
    cur_athena_table: str = Field(min_length=1)
    cur_athena_workgroup: str = Field(min_length=1)

    # Anomaly detection. P1, FEAT-023. Both are here rather than in code so
    # meeting a real estate is a change of a number rather than a release.
    anomaly_sensitivity: float = Field(gt=0)
    anomaly_floor_usd: float = Field(ge=0)

    # Ingestion
    queue_url: str = Field(min_length=1)
    run_claim_timeout_minutes: int = Field(ge=1)
    worker_concurrency: int = Field(ge=1)

    # Identity
    identity_provider: str = Field(min_length=1)
    local_auth_file: str = Field(min_length=1)
    #: Which tenant the local provider issues principals for. It exists only
    #: because that provider has no directory to read a tenant from. A real
    #: identity provider carries the tenant in the assertion, and the production
    #: guard already refuses to start with the local provider, so this value can
    #: never decide anything in production.
    local_tenant_id: UUID
    session_ttl_hours: int = Field(ge=1)
    entitlement_cache_ttl_minutes: int = Field(ge=1)

    # Exports, FEAT-067. The most rows an Excel workbook holds, below the sheet maximum of
    # 1,048,576 with its header. The About sheet names it, and the CSV holds every row.
    export_row_limit: int = Field(ge=1, le=1_048_575)
    session_signing_key: str = Field(min_length=1)

    # Severity, in dollars. ADR-0016.
    severity_critical_usd: Decimal
    severity_high_usd: Decimal
    severity_medium_usd: Decimal

    # Anomaly detection
    anomaly_z_score: float
    anomaly_absolute_usd: Decimal
    anomaly_relative_percent: int = Field(ge=1)
    anomaly_baseline_days: int = Field(ge=1)
    anomaly_autoresolve_days: int = Field(ge=1)

    # Rightsizing
    rightsizing_min_days: int = Field(ge=1)
    rightsizing_percentile: int = Field(ge=1, le=99)
    rightsizing_memory_headroom_percent: int = Field(ge=0)
    rightsizing_memory_headroom_oomkilled_percent: int = Field(ge=0)

    # Workload parking, FEAT-054. Every one of these decides what gets flagged on
    # somebody's production schedule, so none of them is a literal in a collector.
    # ADR-0012's argument about cadence applies unchanged: a number in code is a
    # number nobody can argue with.
    parking_observation_days: int = Field(ge=14)
    parking_idle_percent: Decimal
    #: Two is the floor and the reason is in finops_query/parking.py: one week holds
    #: exactly one of each weekday, so one bank holiday is indistinguishable from the
    #: normal shape of the week.
    parking_minimum_weeks: int = Field(ge=2)
    #: Shorter than this is not worth a stop and a start.
    parking_minimum_window_hours: int = Field(ge=1)

    # Commitment coverage as actions, FEAT-055. The discount rate is an assumption about a
    # price nobody has been quoted, and the term decides how long a mistake lasts, so
    # neither is a literal in a collector.
    commitment_discount_percent: Decimal
    commitment_term_months: int = Field(ge=1)
    #: Below this a finding is not produced. Advising somebody to sign a multi year
    #: obligation to save a few dollars a month costs more to act on than it returns.
    commitment_minimum_monthly_saving_usd: Decimal

    # Infrastructure as code state, FEAT-057. Locations are configured because searching for
    # them would mean listing somebody's buckets to see what is in them, which is
    # reconnaissance whatever the intent. Empty by default, so a deployment that has not
    # configured any reads nothing and says so.
    iac_state_locations: str = ""
    #: Accounts whose infrastructure as code the configured backends wholly describe. A
    #: declaration about our own configuration, which is why it cannot be inferred: an operator
    #: who adds a workspace and does not say so would otherwise have every resource in it
    #: reported as unmanaged, confidently and wrongly.
    iac_exhaustive_accounts: str = ""

    # Blast radius, FEAT-044. How many reachable resources count as wide. A number in code
    # deciding what is wide is a number nobody can argue with, which is ADR-0012's argument
    # about cadence applied to a judgement rather than to an interval.
    blast_radius_wide_at: int = Field(ge=1)
    #: How far the walk goes. Separate from max_graph_nodes, which is the cap on what fits: a
    #: radius that stopped at two hops is a different claim from one the cap cut short, and
    #: only the second is a refusal.
    blast_radius_depth: int = Field(ge=1, le=10)

    # Budgets, FEAT-060. How far ahead of pace counts as at risk, as a fraction. At 0.1,
    # eighty percent spent sixty percent of the way through is at risk. A number in code
    # deciding when to warn somebody about their own money is a number nobody can argue
    # with, which is ADR-0012's argument applied to a threshold.
    budget_at_risk_margin: Decimal

    # Topology
    max_graph_nodes: int = Field(ge=1)

    # Query cost governance, P2. Every one of these was a literal in the
    # prototype and every one is a policy decision: a price the tenant is
    # charged, an assumption about how people use a dashboard, or a threshold
    # that decides what gets flagged. ADR-0017 and TASK-P2-002.
    #
    # The prices are list prices and they are modelled, not measured. TASK-P2-020
    # back tests the model against a real bill and publishes the accuracy, which
    # is ISS-093 until it does.
    query_logs_scan_price_per_gb: Decimal
    query_metrics_price_per_1000: Decimal
    #: What a dashboard nobody has open still costs. A panel with no auto
    #: refresh is assumed to be loaded this many times a day.
    query_manual_loads_per_day: float = Field(ge=0)
    #: How long a dashboard is assumed to be open and refreshing. The single
    #: biggest lever on a modelled figure, which is why it is configurable and
    #: why the figure carries the assumption with it.
    query_viewing_hours_per_day: float = Field(ge=0)
    query_metrics_per_call: float = Field(ge=0)
    #: Used when ingestion cannot be measured for a log group. A Logs Insights
    #: scan estimate is this multiplied by the window, so it is the assumption
    #: the whole Logs Insights cost rests on.
    query_default_ingest_gb_per_day: float = Field(ge=0)
    query_assumed_query_seconds: float = Field(ge=0)
    #: Refresh intervals at or below these are flagged. Seconds.
    query_refresh_warn_seconds: int = Field(ge=1)
    query_refresh_crit_seconds: int = Field(ge=1)
    #: Dashboard time ranges at or above these are flagged. Hours.
    query_timerange_warn_hours: float = Field(ge=0)
    query_timerange_crit_hours: float = Field(ge=0)
    #: Service quotas the model measures pressure against, not limits it sets.
    #: How much Meter may change, per FEAT-014 and FEAT-017. Defaults to `none`
    #: everywhere: enabling a write is a decision somebody signs rather than one
    #: they inherit.
    query_write_level: str = "none"

    query_quota_logs_concurrent: int = Field(ge=1)
    query_quota_getmetricdata_tps: int = Field(ge=1)

    # The assistant, P7 and ADR-0028. Which model is configuration, so changing it is a
    # setting and nothing above the providers names one. Empty means none has been chosen,
    # OPEN-10, and the assistant then says it is not enabled rather than answering with
    # silence. The prices are list prices per million tokens and they are modelled: the bill
    # is the measurement, and the platform cost screen reads it by tag. Above zero, because a
    # model that costs nothing does not exist and would report every exchange as free.
    assistant_model_id: str = ""
    #: What the adapter calls, where it is not the model itself: the ARN of the application
    #: inference profile the hub stack makes for the model in use, so the call carries
    #: finops:module onto the bill, ISS-230. Empty calls the model by its identifier, which
    #: is what every test and every deployment without the hub stack does. Exchanges record
    #: the identifier above and never this, because the ARN names an account.
    assistant_inference_profile_arn: str = ""
    assistant_input_usd_per_million_tokens: Decimal = Field(gt=0)
    assistant_output_usd_per_million_tokens: Decimal = Field(gt=0)
    #: Tokens one tenant may spend in a calendar month, TASK-P7-007. A deployment decision
    #: rather than a design one, so it is here and not a constant. Exhausted, the assistant
    #: refuses and says when it resets rather than continuing to spend.
    assistant_monthly_token_budget: int = Field(ge=1)
    #: Questions the assistant answers at once, ISS-225. Past it, a question is answered as
    #: Throttled at once rather than queued, because a queued question would hold a worker
    #: thread while it waited. Capped by the constant, so no deployment can set a figure
    #: that lets questions take the whole pool.
    assistant_max_concurrent_questions: int = Field(ge=1, le=ASSISTANT_CONCURRENCY_CEILING)

    # Retention, in days. docs/09-DATA-CLASSIFICATION.md.
    retention_principal_days: int = Field(ge=1)
    retention_operational_days: int = Field(ge=1)
    retention_audit_days: int = Field(ge=1)
    retention_cost_days: int = Field(ge=1)

    # Feature flags. The only fields that carry a declared default, because a
    # flag has to resolve to something when nothing else answers. Every one is
    # registered in docs/feature-flags.yaml with an owner and an expiry.
    feature_mcp_server: bool = False
    feature_ingestion: bool = True
    feature_collector_org_tree: bool = True
    feature_collector_account_health: bool = True
    feature_collector_platform_cost: bool = True
    feature_retention_jobs: bool = True
    feature_scope_audit: bool = True
    feature_local_auth: bool = True

    @field_validator("query_write_level")
    @classmethod
    def _known_write_level(cls, value: str) -> str:
        allowed = tuple(level.value for level in WriteLevel)
        if value not in allowed:
            # A typo here would otherwise read as `none` and be indistinguishable
            # from a deliberate refusal to write, which is the one thing this
            # flag must never be ambiguous about.
            raise ValueError(f"METER_QUERY_WRITE_LEVEL must be one of {allowed}, not {value!r}")
        return value

    @property
    def iac_locations(self) -> tuple[str, ...]:
        """The configured state locations, split.

        Comma separated on the wire like `regions`, rather than JSON, because an operator sets
        this in a task definition environment variable and a JSON array there is a quoting
        problem waiting to happen. Empty means none configured, which is a real deployment: the
        collector then reads nothing and every resource reads as not determined, which is true.
        """
        return tuple(part.strip() for part in self.iac_state_locations.split(",") if part.strip())

    @property
    def iac_exhaustive(self) -> frozenset[str]:
        """Accounts whose infrastructure as code the configured backends wholly describe.

        A `frozenset` because the only question asked of it is membership, and the only thing
        it is allowed to do is turn an absence into `UNMANAGED`. Empty means Meter can never
        say unmanaged, which is the right default: the claim is about this configuration, and
        nobody has made it.
        """
        return frozenset(
            part.strip() for part in self.iac_exhaustive_accounts.split(",") if part.strip()
        )

    @field_validator("regions")
    @classmethod
    def _at_least_one_region(cls, value: str) -> str:
        if not [part for part in value.split(",") if part.strip()]:
            raise ValueError(
                "METER_REGIONS must list at least one region. A collector with no "
                "region to read returns nothing, and nothing looks like zero."
            )
        return value

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.env == PRODUCTION_ENV and self.identity_provider == LOCAL_IDENTITY_PROVIDER:
            raise ValueError(
                "METER_IDENTITY_PROVIDER cannot be local_config when METER_ENV is prod. "
                "The local provider reads users out of a file with no password and no "
                "directory behind it, so reaching production with it selected is a total "
                "authentication bypass rather than a degraded one. ISS-017."
            )
        if self.env == PRODUCTION_ENV and self.feature_local_auth:
            raise ValueError(
                "METER_FEATURE_LOCAL_AUTH cannot be true when METER_ENV is prod. It is the "
                "other half of the same bypass ISS-017 describes, and a guard that covers "
                "only one of the two ways in is not a guard."
            )
        if self.env == PRODUCTION_ENV and not self.feature_scope_audit:
            raise ValueError(
                "METER_FEATURE_SCOPE_AUDIT cannot be false when METER_ENV is prod. "
                "Scope enforcement is one of the two independent checks in constraint 3, "
                "and turning off its audit in production removes the evidence that the "
                "other one is working."
            )
        return self

    @property
    def region_list(self) -> tuple[str, ...]:
        """`regions` is held as text because a comma separated list from the

        environment is not JSON, and pydantic reads a list field as JSON.
        """
        return tuple(part.strip() for part in self.regions.split(",") if part.strip())


def _describe(error: ValidationError) -> str:
    lines: list[str] = []
    for problem in error.errors():
        location = problem.get("loc") or ()
        if location:
            name = f"{ENV_PREFIX}{str(location[0]).upper()}"
            lines.append(f"  {name}: {problem['msg']}")
        else:
            lines.append(f"  {problem['msg']}")
    return "The process cannot start with this configuration.\n" + "\n".join(lines)


def load_settings() -> Settings:
    """Build the settings, or refuse to start and say which variable is at fault."""
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as error:
        raise ConfigurationError(_describe(error)) from error
