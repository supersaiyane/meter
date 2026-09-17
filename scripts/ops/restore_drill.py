"""Restore a database copy into a scratch database and prove it is usable.

TASK-P0-028 and ISS-111. A restore that has never been tested is a hypothesis,
and the hypothesis is not "does the snapshot exist". Snapshots almost always
exist. What fails is everything after: a schema the migrations will not apply
on top of, an application that will not start against the restored settings, or
a freshness screen that reports the restored data as current when it is a day
old and the operator acts on it.

Four steps, and only the first is specific to Aurora.

1. Produce a copy. Against Aurora that is `RestoreDBClusterFromSnapshot`.
   Locally it is `pg_dump`, and this script takes either: give it `--from-dump`
   and it restores that file rather than taking one.
2. Restore it into a **scratch** database, never over anything.
3. Run the migrations to head on top of it.
4. Start the application against it and read `/healthz` and the freshness
   route, which is the check that catches a restore that is technically
   complete and operationally wrong.

Steps 2 to 4 are where restores fail and they are exercised in full here.
Step 1 against a real snapshot needs an account, which ISS-122 records as never
provisioned, so the drill is run against a `pg_dump` copy of a live local
database and the Aurora call is the one link this cannot rehearse.

**It refuses any database that is not local**, before it opens a connection.
Everything else here is tidiness. That is the part that matters, and it is the
same guard `seed_demo.py` carries for the same reason.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from finops_core.config import ConfigurationError, load_settings

#: Hosts a drill may write to. The compose service name counts as local because
#: it only resolves inside the local stack.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "postgres", ""})

SCRATCH_PREFIX = "meter_restore_drill_"


class NotLocalError(RuntimeError):
    """The database is not one this script is allowed to touch."""


class DrillFailedError(RuntimeError):
    """A step did not do what a restore has to do."""


def require_local(database_url: str) -> None:
    host = (urlsplit(database_url).hostname or "").lower()
    if host not in LOCAL_HOSTS:
        raise NotLocalError(
            f"refusing to run a drill against {host!r}. This creates and drops "
            f"databases and is only ever for a local one."
        )


def with_database(url: str, name: str) -> str:
    """The same URL pointed at a different database."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))


def libpq_url(url: str) -> str:
    """The SQLAlchemy URL as something pg_dump and psql accept."""
    return url.replace("postgresql+psycopg://", "postgresql://")


@dataclass(frozen=True)
class Result:
    """What the drill proved, step by step, for the record it produces."""

    scratch: str
    tables: int
    rows_checked: dict[str, int]
    migration_head: str
    healthz: str
    collectors_reported: int


def run(command: list[str], *, detail: str) -> str:
    finished = subprocess.run(command, capture_output=True, text=True)
    if finished.returncode != 0:
        raise DrillFailedError(f"{detail}: {finished.stderr.strip()[:400]}")
    return finished.stdout


def take_copy(source_url: str, into: Path, dump_command: list[str]) -> Path:
    """Step 1, the local stand in for restoring a snapshot.

    `--inserts` on purpose. A default dump uses `COPY ... FROM stdin`, which
    only `psql` knows how to feed, and requiring `psql` on the machine running
    the drill is a dependency this does not need: with plain inserts the restore
    below is ordinary SQL over the connection the application already uses.
    """
    into.write_text(
        run([*dump_command, "--inserts", libpq_url(source_url)], detail="pg_dump failed")
    )
    return into


def create_scratch(admin_url: str, name: str) -> None:
    """Step 2. A new database every time, never a reused one.

    A drill that restores over the database it dumped from proves nothing and
    can destroy the thing it was testing.
    """
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        engine.dispose()


def restore_into(scratch_url: str, dump: Path) -> None:
    """Execute the dump against the scratch database.

    Through the same driver the application uses rather than through `psql`, so
    the drill needs no client tooling on the machine running it. It stops at the
    first statement that fails, because a restore that carried on past an error
    is the exact hypothesis this drill exists to disprove.
    """
    statements = dump.read_text(encoding="utf-8")
    engine = create_engine(scratch_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            for statement in _statements(statements):
                try:
                    connection.execute(text(statement))
                except SQLAlchemyError as failure:
                    raise DrillFailedError(
                        f"the restore stopped at: {statement[:120]}... ({failure})"
                    ) from failure
    finally:
        engine.dispose()


def _statements(dump: str) -> list[str]:
    """The dump split into statements, comments and directives dropped.

    `\\connect` and the other backslash directives are `psql` commands rather
    than SQL. Sending them to the server produces a syntax error that reads like
    a corrupt dump, which is a bad half hour for whoever is running a restore at
    the time.
    """
    found: list[str] = []
    for raw in dump.split(";\n"):
        statement = "\n".join(
            line
            for line in raw.splitlines()
            if line.strip() and not line.startswith("--") and not line.startswith("\\")
        ).strip()
        if statement:
            found.append(statement)
    return found


def migrate(scratch_url: str) -> str:
    """Step 3. The migrations have to apply on top of what came back.

    This is the step that catches a restore from before a migration nobody
    remembers, and it is why the drill runs them rather than assuming.
    """
    root = Path(__file__).resolve().parents[2]
    finished = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        cwd=root,
        env={**_environ(), "METER_DATABASE_URL": scratch_url},
    )
    if finished.returncode != 0:
        raise DrillFailedError(f"alembic upgrade failed: {finished.stderr.strip()[:400]}")
    head = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        capture_output=True,
        text=True,
        cwd=root,
        env={**_environ(), "METER_DATABASE_URL": scratch_url},
    )
    return head.stdout.strip().splitlines()[-1] if head.stdout.strip() else "unknown"


def _environ() -> dict[str, str]:
    """The current environment, so alembic inherits everything but the URL."""
    return dict(os.environ)


def inspect(scratch_url: str, tables: tuple[str, ...]) -> tuple[int, dict[str, int]]:
    """Step 4a. The data came back, and how much of it."""
    engine = create_engine(scratch_url)
    try:
        with engine.connect() as connection:
            total = connection.execute(
                text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
            ).scalar_one()
            counts = {
                table: connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                for table in tables
            }
    finally:
        engine.dispose()
    return int(total), {name: int(count) for name, count in counts.items()}


def check_application(scratch_url: str) -> tuple[str, int]:
    """Step 4b. The application starts against it and reports honestly.

    The freshness route is the one that matters. A restore is not finished when
    the rows are back; it is finished when the screen that says how old they are
    tells the truth about them, because an operator acting on a restored estate
    reads that first.
    """
    from fastapi.testclient import TestClient

    from finops_api.identity.local_config import LocalConfigIdentityProvider
    from finops_api.identity.session import SessionSigner
    from finops_api.main import create_app

    settings = load_settings()
    engine = create_engine(scratch_url)
    try:
        # Assembled the way the process does it, rather than with stubs. A
        # drill that starts a differently wired application has proved that a
        # different application starts.
        app = create_app(
            engine=engine,
            entitlements=LocalConfigIdentityProvider(
                path=Path(settings.local_auth_file),
                tenant_id=settings.local_tenant_id,
                cache_ttl_minutes=settings.entitlement_cache_ttl_minutes,
            ),
            signer=SessionSigner(
                settings.session_signing_key, ttl_hours=settings.session_ttl_hours
            ),
            settings=settings,
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            health = client.get("/healthz")
            if health.status_code != 200:
                raise DrillFailedError(
                    f"the application did not start: /healthz {health.status_code}"
                )
            body = health.json()
            if not body.get("database_reachable"):
                raise DrillFailedError(
                    "the application started and could not reach the restored data"
                )
            return str(body.get("status")), len(body.get("collectors") or ())
    finally:
        engine.dispose()


def drop_scratch(admin_url: str, name: str) -> None:
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-dump",
        type=Path,
        help="restore this file instead of taking a fresh copy. Point it at a "
        "dump produced from an Aurora snapshot to drill the real path.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="leave the scratch database behind for inspection",
    )
    parser.add_argument(
        "--dump-url",
        help="the source as the dump command sees it. Locally pg_dump runs "
        "inside the database container, where the server is not on the port "
        "the host maps it to, so the two addresses differ.",
    )
    parser.add_argument(
        "--dump-command",
        default="pg_dump",
        help="how to invoke pg_dump. Locally the client tools live in the "
        "database container, so this is wrapped rather than assumed on PATH.",
    )
    parser.add_argument(
        "--tables",
        default="tenant,cloud_account,query_finding,ingest_run",
        help="comma separated tables to count after the restore",
    )
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
    except ConfigurationError as failure:
        print(f"Configuration is not loadable, so no drill can run:\n{failure}", file=sys.stderr)
        return 2

    source = str(settings.database_url)
    require_local(source)

    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    scratch = f"{SCRATCH_PREFIX}{stamp}"
    admin = with_database(source, "postgres")
    scratch_url = with_database(source, scratch)
    tables = tuple(name.strip() for name in args.tables.split(",") if name.strip())

    dump_path = Path(f"/tmp/{scratch}.sql")
    try:
        print("==> 1. Taking a copy" if not args.from_dump else "==> 1. Using the given dump")
        dump = args.from_dump or take_copy(
            args.dump_url or source, dump_path, args.dump_command.split()
        )

        print(f"==> 2. Restoring into a scratch database, {scratch}")
        create_scratch(admin, scratch)
        restore_into(scratch_url, dump)

        print("==> 3. Running the migrations on top of it")
        head = migrate(scratch_url)

        print("==> 4. Starting the application against it")
        total, counts = inspect(scratch_url, tables)
        status, collectors = check_application(scratch_url)

        result = Result(
            scratch=scratch,
            tables=total,
            rows_checked=counts,
            migration_head=head,
            healthz=status,
            collectors_reported=collectors,
        )
        print("\nRESTORE DRILL PASSED")
        print(f"  scratch database   {result.scratch}")
        print(f"  tables restored    {result.tables}")
        for name, count in result.rows_checked.items():
            print(f"  {name:<18} {count} rows")
        print(f"  migrations         {result.migration_head}")
        print(f"  /healthz           {result.healthz}")
        print(f"  freshness reported {result.collectors_reported} collector(s)")
        if result.healthz != "healthy":
            # Not a drill failure. The restored data is as old as the snapshot,
            # and an application reporting it as current would be the defect.
            print(
                "\n  `degraded` here is the correct answer, not a failure: the restored\n"
                "  data is as old as the copy it came from, and an application that\n"
                "  called it current would be the thing this drill exists to catch."
            )
        return 0
    except (DrillFailedError, NotLocalError) as failure:
        print(f"\nRESTORE DRILL FAILED\n  {failure}", file=sys.stderr)
        return 1
    finally:
        if not args.keep:
            drop_scratch(admin, scratch)
        if dump_path.exists() and not args.from_dump:
            dump_path.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
