# Basic boiler Plate Doc | Grade B
# Why this file exists: Shared test setup, deliberately minimal. It also refuses to run the
# suite against a real cloud account, which is the idea worth copying.
# Grade B here: copy it, then replace the guard's environment variable names.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.

"""Shared pytest configuration.

Two things are set up here and nothing else. Fixtures that belong to one layer
live next to that layer's tests, because a conftest that grows into a shared
fixture library becomes a file every test depends on and nobody understands.

1. `anyio_backend`, so async tests run on asyncio without each one declaring it.
2. A guard that refuses to run the suite against a real AWS account.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True, scope="session")
def _refuse_real_aws() -> None:
    """Fail the run rather than let a test touch a real account.

    The port contract suite runs against `moto` and the fake provider, and the
    local stack points at LocalStack. If a real credential is present and no
    endpoint override is set, a test that forgets to patch a client would reach
    a live account, and in this product that means reading somebody's billing
    data from a unit test.

    Cheaper to refuse than to find out afterwards from CloudTrail.
    """
    endpoint = os.environ.get("AWS_ENDPOINT_URL", "")
    profile = os.environ.get("AWS_PROFILE", "")
    key = os.environ.get("AWS_ACCESS_KEY_ID", "")

    looks_real = bool(profile) or (key and key not in {"test", "testing", "dummy"})
    if looks_real and not endpoint:
        pytest.exit(
            "Refusing to run: real AWS credentials are present and "
            "AWS_ENDPOINT_URL is not set.\n"
            "Tests must run against moto, the fake provider, or LocalStack.\n"
            "Unset AWS_PROFILE and AWS_ACCESS_KEY_ID, or set AWS_ENDPOINT_URL.",
            returncode=2,
        )


# --- the database container, shared by every test that needs one -------------
#
# This was next to the database tests until the ingest tests needed it too.
# Starting a container per directory is the kind of cost that gets integration
# tests quietly disabled, so it is session scoped and lives here. Tests keep out
# of each other's way by taking a fresh tenant each.

ROOT = Path(__file__).resolve().parent.parent


def alembic_config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    try:
        from testcontainers.community.postgres import PostgresContainer
    except ImportError:  # pragma: no cover - older testcontainers layout
        from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as container:
        url = container.get_connection_url()
        command.upgrade(alembic_config(url), "head")
        built = create_engine(url)
        try:
            yield built
        finally:
            built.dispose()


@pytest.fixture
def tenant_id(engine: Engine) -> UUID:
    """A tenant of its own per test, so no test can see another's rows."""
    new_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenant (tenant_id, name) VALUES (:id, :name)"),
            {"id": new_id, "name": f"tenant-{new_id}"},
        )
    return new_id
