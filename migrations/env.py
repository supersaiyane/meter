"""Alembic environment.

The database URL comes from the settings object rather than from `alembic.ini`,
so a connection string is read from exactly one place and no credential sits in
a committed file. A caller that needs a different database, such as the
integration tests against a throwaway container, sets `sqlalchemy.url` on the
config object and this honours it.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from finops_api.db.models import metadata

config = context.config
target_metadata = metadata


def database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url", None)
    if configured:
        return configured
    # Imported lazily so that a caller supplying its own URL, which is every
    # test, never has to satisfy the whole settings object to run a migration.
    from finops_core.config import load_settings

    return load_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {}) or {}
    section["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
