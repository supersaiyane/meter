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

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from finops_core.constants import ENV_PREFIX, PRODUCTION_ENV


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

    # Ingestion
    queue_url: str = Field(min_length=1)
    run_claim_timeout_minutes: int = Field(ge=1)
    worker_concurrency: int = Field(ge=1)

    # Identity
    identity_provider: str = Field(min_length=1)
    local_auth_file: str = Field(min_length=1)
    session_ttl_hours: int = Field(ge=1)
    entitlement_cache_ttl_minutes: int = Field(ge=1)
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

    # Topology
    max_graph_nodes: int = Field(ge=1)

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
