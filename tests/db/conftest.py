"""One PostgreSQL container, shared by every database test in this directory.

Starting a container per file is the kind of cost that gets integration tests
quietly disabled, so the engine is session scoped and the tests keep out of each
other's way by using a fresh tenant each.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

ROOT = Path(__file__).resolve().parent.parent.parent


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
