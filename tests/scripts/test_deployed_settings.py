"""Every setting reaches every deployed Python task, from SSM Parameter Store. TASK-P12-006.

FEAT-080, ISS-250. `infra/terraform/hub/settings.tf` makes one parameter per setting from three
sources: the names the stack derives, a committed map per environment, and the secret ones. These
hold their union to `Settings.model_fields`, so a setting added without a parameter fails here and
not in a task that refuses to start in AWS; and they hold the task definitions and the execution
role to reading them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from finops_core.config import UNSET_SECRET, Settings
from finops_core.constants import ENV_PREFIX

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / "infra" / "terraform" / "hub"
SETTINGS_TF = (HUB / "settings.tf").read_text()
ENVIRONMENTS = ("dev", "prod")
FIELDS = {ENV_PREFIX + name.upper() for name in Settings.model_fields}
PASSWORD = (
    '{ name = "PGPASSWORD", valueFrom = '
    '"${aws_rds_cluster.hub.master_user_secret[0].secret_arn}:password::" }'
)


def block(text: str, opening: str) -> str:
    """The body of the first `<opening>` block, to its closing brace at the same indent."""
    start = text.index(opening)
    indent = text[text.rindex("\n", 0, start) + 1 : start]
    return text[start : text.index(f"\n{indent}}}", start)]


def derived() -> set[str]:
    body = block(SETTINGS_TF, "derived_settings = {")
    return set(re.findall(r"^\s+(METER_[A-Z0-9_]+)\s+=", body, re.M))


def secret() -> set[str]:
    line = SETTINGS_TF.split("secret_settings")[1].split("\n")[0]
    return set(re.findall(r'"(METER_[A-Z0-9_]+)"', line))


def mapped(environment: str) -> dict[str, str]:
    text = (HUB / "envs" / f"{environment}.tfvars").read_text()
    pairs = re.findall(
        r'^\s+(METER_[A-Z0-9_]+)\s*=\s*(".*")\s*$', block(text, "settings = {"), re.M
    )
    return {name: json.loads(value) for name, value in pairs}


def as_settings(values: dict[str, str]) -> Settings:
    return Settings.model_validate(
        {name.removeprefix(ENV_PREFIX).lower(): value for name, value in values.items()}
    )


def deployed(environment: str, **overrides: str) -> dict[str, str]:
    """The settings a task in `environment` is given, with the derived ones stood in for."""
    values = dict.fromkeys(derived(), "derived") | mapped(environment)
    values |= {
        "METER_ENV": environment,
        "METER_DATABASE_URL": "postgresql+psycopg://meter@db:5432/meter",
        "METER_SESSION_SIGNING_KEY": "a key the owner set",
    }
    return values | overrides


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_every_setting_is_derived_secret_or_in_the_environments_map_exactly_once(
    environment: str,
) -> None:
    sources = (derived(), secret(), set(mapped(environment)))
    assert sources[0] | sources[1] | sources[2] == FIELDS
    assert not (sources[0] & sources[1] or sources[0] & sources[2] or sources[1] & sources[2])


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_each_environments_map_makes_settings_its_environment_accepts(environment: str) -> None:
    assert as_settings(deployed(environment)).env == environment


def test_the_placeholder_terraform_writes_is_the_one_the_settings_refuse() -> None:
    assert f'unset_secret     = "{UNSET_SECRET}"' in SETTINGS_TF
    with pytest.raises(ValidationError, match="METER_SESSION_SIGNING_KEY is still the placeholder"):
        as_settings(deployed("dev", METER_SESSION_SIGNING_KEY=UNSET_SECRET))


@pytest.mark.parametrize(
    ("file", "family"), [("ecs.tf", "api"), ("ecs.tf", "worker"), ("scheduler.tf", "dispatcher")]
)
def test_every_python_task_reads_its_settings_from_the_parameters(file: str, family: str) -> None:
    definition = block(
        (HUB / file).read_text(), f'resource "aws_ecs_task_definition" "{family}" {{'
    )
    assert re.search(r"\bsecrets\s+=\s+local\.setting_secrets\b", definition)
    assert re.search(r"\benvironment\s+=\s+local\.setting_environment\b", definition)
    assert ":METER_DATABASE_URL::" not in definition, "ISS-278: the RDS secret has no such key"


def test_the_database_password_comes_from_the_secret_rds_manages() -> None:
    assert PASSWORD in SETTINGS_TF
    assert "@${aws_rds_cluster.hub.endpoint}" in SETTINGS_TF, "the URL names the host"
    assert ":password@" not in SETTINGS_TF, "and never a password"


def test_the_dispatcher_runs_the_module_its_image_entrypoint_expects() -> None:
    scheduler = (HUB / "scheduler.tf").read_text()
    definition = block(scheduler, 'resource "aws_ecs_task_definition" "dispatcher" {')
    assert re.search(r'command\s+=\s+\["finops_ingest\.dispatcher"\]', definition), "ISS-277"


def test_the_execution_role_reads_only_its_own_environments_parameters() -> None:
    statement = block((HUB / "iam.tf").read_text(), 'sid       = "ReadOwnSettings"')
    assert '["ssm:GetParameters"]' in statement
    assert ":parameter/meter/${var.env}/*" in statement
