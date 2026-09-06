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
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from finops_core.config import Settings, load_settings


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

#: A database to run against instead of starting one, for a runner that has a
#: PostgreSQL service beside it and no Docker socket to start another.
#:
#: Deliberately not `METER_DATABASE_URL`. That one is in every `.env` and in the
#: shell of anybody who has run `make seed`, and a suite that migrated and wrote
#: rows into whatever they had loaded would be a data loss bug wearing a
#: fixture's clothes. This has to be set on purpose, for this.
TEST_DATABASE_URL = "METER_TEST_DATABASE_URL"

#: Hosts accepted as a throwaway database. The same list as
#: `scripts/ops/seed_demo.py`, copied rather than imported because `scripts/` is
#: deliberately not a package, and kept honest by a test that compares the two.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "postgres", ""})


def alembic_config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


@contextmanager
def migrated(url: str) -> Iterator[Engine]:
    """A database at head, however it was obtained."""
    command.upgrade(alembic_config(url), "head")
    built = create_engine(url)
    try:
        yield built
    finally:
        built.dispose()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    provided = os.environ.get(TEST_DATABASE_URL)
    if provided:
        host = (urlsplit(provided).hostname or "").lower()
        if host not in LOCAL_HOSTS:
            # Exit rather than skip. A suite that quietly ran fewer tests
            # because a variable was wrong is the failure this whole session
            # has been about, and a suite that ran them against a real
            # database is worse than either.
            pytest.exit(
                f"{TEST_DATABASE_URL} points at {host!r}, which is not a local host.\n"
                "This fixture migrates the database and writes to it.\n"
                f"Accepted hosts: {', '.join(sorted(h for h in LOCAL_HOSTS if h))}.",
                returncode=2,
            )
        with migrated(provided) as built:
            yield built
        return

    try:
        from testcontainers.community.postgres import PostgresContainer
    except ImportError:  # pragma: no cover - older testcontainers layout
        from testcontainers.postgres import PostgresContainer

    with (
        PostgresContainer("postgres:16-alpine", driver="psycopg") as container,
        migrated(container.get_connection_url()) as built,
    ):
        yield built


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


# --- settings, built from the documented environment -------------------------
#
# Promoted here once a third layer needed it. Every test that constructs
# anything real needs a Settings, and .env.example is the one description of
# what a complete environment looks like, so building from it means a test can
# never drift from the documented set.

ENV_EXAMPLE = ROOT / ".env.example"
_VARIABLE = re.compile(r"^(METER_[A-Z0-9_]+)=(.*)$", re.MULTILINE)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for key, value in _VARIABLE.findall(ENV_EXAMPLE.read_text(encoding="utf-8")):
        monkeypatch.setenv(key, value)
    return load_settings()
