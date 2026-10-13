"""Configuration is one typed place, and the two files that describe it cannot drift.

ADR-0017. The point of doing this before there is any code to put values in is
that afterwards means finding every literal already written.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from finops_api.flags import UNKNOWN_FLAG_DEFAULT, FlagResolver
from finops_core.config import ConfigurationError, Settings, load_settings

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_EXAMPLE = ROOT / ".env.example"
VARIABLE = re.compile(r"^METER_([A-Z0-9_]+)=", re.MULTILINE)


def declared_in_env_example() -> set[str]:
    return {m.lower() for m in VARIABLE.findall(ENV_EXAMPLE.read_text(encoding="utf-8"))}


def complete_environment() -> dict[str, str]:
    """Every variable at the value .env.example documents."""
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if line.startswith("METER_") and "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
    return values


def apply(monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str] | None = None) -> None:
    for key in list(complete_environment()):
        monkeypatch.delenv(key, raising=False)
    for key, value in {**complete_environment(), **(overrides or {})}.items():
        monkeypatch.setenv(key, value)


def test_env_example_matches_settings() -> None:
    """Neither file can drift from the other."""
    assert declared_in_env_example() == set(Settings.model_fields)


def test_the_documented_environment_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    apply(monkeypatch)
    settings = load_settings()
    assert settings.env == "local"


def test_missing_required_refuses_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    apply(monkeypatch)
    monkeypatch.delenv("METER_DATABASE_URL")
    with pytest.raises(ConfigurationError) as caught:
        load_settings()
    assert "METER_DATABASE_URL" in str(caught.value)


def test_malformed_value_refuses_startup_and_names_the_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply(monkeypatch, {"METER_DB_POOL_SIZE": "not-a-number"})
    with pytest.raises(ConfigurationError) as caught:
        load_settings()
    assert "METER_DB_POOL_SIZE" in str(caught.value)


def test_an_unknown_environment_name_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    apply(monkeypatch, {"METER_ENV": "preprod"})
    with pytest.raises(ConfigurationError) as caught:
        load_settings()
    assert "METER_ENV" in str(caught.value)


PRODUCTION_READY = {
    "METER_ENV": "prod",
    "METER_IDENTITY_PROVIDER": "oidc",
    "METER_FEATURE_LOCAL_AUTH": "false",
}


def test_the_local_identity_provider_cannot_reach_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider with no directory behind it is a total bypass. ISS-017."""
    apply(monkeypatch, {**PRODUCTION_READY, "METER_IDENTITY_PROVIDER": "local_config"})
    with pytest.raises(ConfigurationError) as caught:
        load_settings()
    assert "METER_IDENTITY_PROVIDER" in str(caught.value)


def test_the_local_auth_flag_cannot_be_on_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of the same bypass. A guard covering one way in is not a guard."""
    apply(monkeypatch, {**PRODUCTION_READY, "METER_FEATURE_LOCAL_AUTH": "true"})
    with pytest.raises(ConfigurationError) as caught:
        load_settings()
    assert "METER_FEATURE_LOCAL_AUTH" in str(caught.value)


def test_a_production_configuration_without_the_local_provider_loads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply(monkeypatch, PRODUCTION_READY)
    assert load_settings().env == "prod"


def test_scope_audit_cannot_be_off_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    """The one flag with no legitimate off state in production."""
    apply(monkeypatch, {**PRODUCTION_READY, "METER_FEATURE_SCOPE_AUDIT": "false"})
    with pytest.raises(ConfigurationError) as caught:
        load_settings()
    assert "METER_FEATURE_SCOPE_AUDIT" in str(caught.value)


def test_scope_audit_may_be_off_outside_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    apply(monkeypatch, {"METER_ENV": "local", "METER_FEATURE_SCOPE_AUDIT": "false"})
    assert load_settings().feature_scope_audit is False


def test_regions_are_parsed_into_a_list(monkeypatch: pytest.MonkeyPatch) -> None:
    apply(monkeypatch, {"METER_REGIONS": "eu-west-1, eu-west-2 ,us-east-1"})
    assert load_settings().region_list == ("eu-west-1", "eu-west-2", "us-east-1")


def test_the_services_asked_for_purchase_advice_are_parsed_into_a_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = "Amazon Redshift , ,Amazon MemoryDB"
    apply(monkeypatch, {"METER_COMMITMENT_RECOMMENDATION_SERVICES": services})
    assert load_settings().recommendation_services == ("Amazon Redshift", "Amazon MemoryDB")


def test_an_empty_region_list_refuses_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    apply(monkeypatch, {"METER_REGIONS": "  "})
    with pytest.raises(ConfigurationError) as caught:
        load_settings()
    assert "METER_REGIONS" in str(caught.value)


# --- flag resolution ---------------------------------------------------------


def settings_for(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> Settings:
    apply(monkeypatch, dict(overrides))
    return load_settings()


def test_unknown_flag_returns_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo must not take a service down."""
    resolver = FlagResolver(settings_for(monkeypatch))
    assert resolver.is_enabled("ingesstion") is UNKNOWN_FLAG_DEFAULT


def test_environment_default_is_used_when_there_is_no_tenant_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = FlagResolver(settings_for(monkeypatch, METER_FEATURE_MCP_SERVER="true"))
    assert resolver.is_enabled("mcp_server") is True


def test_a_tenant_override_beats_the_environment_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = FlagResolver(
        settings_for(monkeypatch, METER_FEATURE_MCP_SERVER="false"),
        overrides=lambda _tenant: {"mcp_server": True},
    )
    assert resolver.is_enabled("mcp_server", tenant_id="t1") is True
    assert resolver.is_enabled("mcp_server") is False


def test_a_tenant_override_is_cached_for_sixty_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    now = [0.0]

    def lookup(tenant: str) -> dict[str, bool]:
        calls.append(tenant)
        return {"mcp_server": True}

    resolver = FlagResolver(settings_for(monkeypatch), overrides=lookup, clock=lambda: now[0])
    resolver.is_enabled("mcp_server", tenant_id="t1")
    now[0] = 59.0
    resolver.is_enabled("mcp_server", tenant_id="t1")
    assert len(calls) == 1
    now[0] = 61.0
    resolver.is_enabled("mcp_server", tenant_id="t1")
    assert len(calls) == 2


def test_a_failing_override_lookup_falls_back_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flag table being unreachable must not take the API down with it."""

    def broken(_tenant: str) -> dict[str, bool]:
        raise RuntimeError("no database")

    resolver = FlagResolver(
        settings_for(monkeypatch, METER_FEATURE_INGESTION="true"), overrides=broken
    )
    assert resolver.is_enabled("ingestion", tenant_id="t1") is True


def test_every_flag_in_the_register_has_a_settings_field() -> None:
    import yaml

    register = yaml.safe_load((ROOT / "docs" / "feature-flags.yaml").read_text(encoding="utf-8"))
    for flag in register["flags"]:
        assert f"feature_{flag['key']}" in Settings.model_fields
