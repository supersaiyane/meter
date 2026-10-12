"""Connecting an AI provider organization, only once its key has read its costs. TASK-P13-004.

The script records an organization for a tenant after one day of costs is read with the key from
the secret it names, refuses a secret outside this environment's AI path, and never takes an
organization another tenant holds.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.ai import AiUsage, ProviderAccount
from finops_core.domain.cost import CostRecord
from finops_core.errors import AccessDenied

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "connect_ai_provider.py"
_spec = importlib.util.spec_from_file_location("connect_ai_provider", SCRIPT)
assert _spec is not None and _spec.loader is not None
connect_ai_provider = importlib.util.module_from_spec(_spec)
sys.modules["connect_ai_provider"] = connect_ai_provider
_spec.loader.exec_module(connect_ai_provider)
main = connect_ai_provider.main

NOW = datetime(2026, 10, 12, 9, tzinfo=UTC)


class Secrets:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def get_secret_value(self, *, SecretId: str) -> dict[str, str]:  # noqa: N803 - boto3's name
        self.asked.append(SecretId)
        return {"SecretString": "test-key"}


class Reports:
    def __init__(self, key: Any, failure: Exception | None = None) -> None:
        self.key = key
        self.failure = failure
        self.asked: list[tuple[datetime, datetime]] = []

    def costs(
        self, _account: ProviderAccount, start: datetime, end: datetime
    ) -> Iterable[CostRecord]:
        assert self.key() == "test-key"
        if self.failure:
            raise self.failure
        self.asked.append((start, end))
        return ()

    def usage(self, *_args: Any) -> Iterable[AiUsage]:
        return ()


def args(tenant: UUID, organization: str, secret: str = "meter/test/ai/openai") -> list[str]:
    return [
        "--env", "test", "--tenant", str(tenant), "--provider", "openai",
        "--organization", organization, "--name", "Platform", "--secret", secret,
    ]  # fmt: skip


def rows(engine: Engine, organization: str) -> list[Any]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    "SELECT tenant_id, name, key_secret_name, active FROM ai_provider_account "
                    "WHERE organization_id = :o"
                ),
                {"o": organization},
            ).all()
        )


@pytest.fixture
def database(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Engine:
    monkeypatch.setenv("METER_DATABASE_URL", engine.url.render_as_string(hide_password=False))
    return engine


def test_a_key_that_reads_a_day_of_costs_connects_the_organization(
    database: Engine, tenant_id: UUID
) -> None:
    organization = f"org-{tenant_id}"
    secrets = Secrets()
    made: list[Reports] = []

    def factory(key: Any) -> Reports:
        made.append(Reports(key))
        return made[-1]

    code = main(args(tenant_id, organization), secrets=secrets, factory=factory, clock=lambda: NOW)

    assert code == 0
    assert secrets.asked == ["meter/test/ai/openai"]
    (asked,) = made[0].asked
    assert asked[1] == NOW and (asked[1] - asked[0]).days == 1
    assert [tuple(row) for row in rows(database, organization)] == [
        (tenant_id, "Platform", "meter/test/ai/openai", True)
    ]


def test_a_refused_key_connects_nothing(
    database: Engine, tenant_id: UUID, capsys: pytest.CaptureFixture[str]
) -> None:
    organization = f"org-{tenant_id}"
    refused = AccessDenied(scope_key="openai:x", collector="openai_usage", detail="refused")
    code = main(
        args(tenant_id, organization),
        secrets=Secrets(),
        factory=lambda key: Reports(key, failure=refused),
        clock=lambda: NOW,
    )
    assert code == 3
    assert "AccessDenied" in capsys.readouterr().err
    assert rows(database, organization) == []


@pytest.mark.usefixtures("database")
def test_a_secret_outside_the_ai_path_is_refused_before_anything(tenant_id: UUID) -> None:
    secrets = Secrets()
    code = main(
        args(tenant_id, f"org-{tenant_id}", secret="meter/test/database"),
        secrets=secrets,
        factory=Reports,
    )
    assert code == 2
    assert secrets.asked == []


def test_an_organization_another_tenant_holds_is_not_taken(
    database: Engine, tenant_id: UUID
) -> None:
    organization = f"org-{tenant_id}"
    assert main(args(tenant_id, organization), secrets=Secrets(), factory=Reports) == 0
    with database.begin() as connection:
        other = connection.execute(
            text(
                "INSERT INTO tenant (tenant_id, name) VALUES (gen_random_uuid(), :n) "
                "RETURNING tenant_id"
            ),
            {"n": f"other-{tenant_id}"},
        ).scalar_one()
    assert main(args(other, organization), secrets=Secrets(), factory=Reports) == 2
    assert [row.tenant_id for row in rows(database, organization)] == [tenant_id]


def test_it_needs_a_database(monkeypatch: pytest.MonkeyPatch, tenant_id: UUID) -> None:
    monkeypatch.delenv("METER_DATABASE_URL", raising=False)
    assert main(args(tenant_id, "org-x"), secrets=Secrets(), factory=Reports) == 2


def test_an_anthropic_organization_connects_the_same_way(database: Engine, tenant_id: UUID) -> None:
    organization = f"org-anthropic-{tenant_id}"
    argv = args(tenant_id, organization, "meter/test/ai/anthropic")
    argv[argv.index("openai")] = "anthropic"
    assert main(argv, secrets=Secrets(), factory=Reports, clock=lambda: NOW) == 0
    assert [tuple(row)[2] for row in rows(database, organization)] == ["meter/test/ai/anthropic"]
