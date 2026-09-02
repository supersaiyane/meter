"""Fill a local database with a demo estate, so the product can be developed
against something before any of it can talk to AWS.

The data is produced by running the **real collector** against the **existing
fake surface**, not by writing rows. That matters: a second hand written estate
would drift from what the collector actually writes, and the first time the real
one ran the screens would change shape. Every row here is a row
`QueryAuditCollector` would have written.

Three safeguards, because a seeding script is exactly the kind of tool that ends
up pointed somewhere it should not be.

**It refuses any database that is not local.** Not a warning, a refusal. This is
the only one of the three that matters if the others are forgotten.

**Everything lives under one tenant with a fixed identifier.** Removal is then
exact rather than a search, and scope enforcement means the demo estate cannot
appear inside a real tenant's view even while it exists.

**`--remove` is part of this script rather than a note in a document.** The
request was to seed now and clear it later, and later is when nobody remembers
which tables were touched.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import create_engine, text

from finops_core.config import load_settings
from finops_ingest.collectors.query_audit import (
    QueryAuditCollector,
    default_ingest_rate,
    rates_from,
)
from finops_ingest.registry import CollectorContext
from finops_providers.fake.surface import FakeQuerySurface

#: Fixed, and readable as "seeded" in the first block, so a row found in a
#: database months from now identifies itself without a lookup.
DEMO_TENANT = UUID("5eeded00-0000-4000-8000-000000000001")
DEMO_NAME = "demo estate, seeded, safe to remove"

#: Hosts a seed may write to. The compose service name counts as local because
#: it only resolves inside the local stack.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "postgres", ""})

#: Reverse dependency order. A removal that orphaned a foreign key would leave
#: the database refusing it and the operator guessing why.
DEMO_TABLES = (
    "remediation_change",
    "enforcement_action",
    "folder_team_map",
    "query_finding",
    "query_definition",
    "grafana_instance",
)


class NotLocalError(RuntimeError):
    """The database is not one this script is allowed to write to."""


def require_local(database_url: str) -> None:
    """Refuse anything that is not a local database.

    The whole risk of a seeding tool is that it runs somewhere real. Everything
    else in this file is tidiness; this is the part that matters.
    """
    host = (urlsplit(database_url).hostname or "").lower()
    if host not in LOCAL_HOSTS:
        raise NotLocalError(
            f"refusing to seed {host!r}. This writes a fake estate and is only "
            f"ever for a local database, one of {sorted(LOCAL_HOSTS - {''})}."
        )


@dataclass(frozen=True)
class Unit:
    """What the collector reads off a work unit, and nothing else."""

    tenant_id: UUID
    scope_key: str = "organization"


def seed(engine: Any, settings: Any, now: datetime) -> tuple[int, int]:
    """Create the tenant and run the collector into it. Returns rows, instances."""
    collector = QueryAuditCollector(
        FakeQuerySurface(),
        rates_from(settings),
        default_ingest_rate(settings),
        clock=lambda: now,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO tenant (tenant_id, name) VALUES (:id, :name) "
                "ON CONFLICT (tenant_id) DO NOTHING"
            ),
            {"id": DEMO_TENANT, "name": DEMO_NAME},
        )
        outcome = collector(
            CollectorContext(unit=Unit(tenant_id=DEMO_TENANT), connection=connection)
        )
        instances = connection.execute(
            text("SELECT count(*) FROM grafana_instance WHERE tenant_id = :t"),
            {"t": DEMO_TENANT},
        ).scalar_one()
    return outcome.items_written, int(instances)


def remove(engine: Any) -> dict[str, int]:
    """Clear every demo row, in an order the foreign keys accept."""
    cleared: dict[str, int] = {}
    with engine.begin() as connection:
        for table_name in DEMO_TABLES:
            result = connection.execute(
                text(f"DELETE FROM {table_name} WHERE tenant_id = :t"),
                {"t": DEMO_TENANT},
            )
            cleared[table_name] = result.rowcount or 0
        result = connection.execute(
            text("DELETE FROM tenant WHERE tenant_id = :t"), {"t": DEMO_TENANT}
        )
        cleared["tenant"] = result.rowcount or 0
    return cleared


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed or clear the local demo estate.")
    parser.add_argument(
        "--remove",
        action="store_true",
        help="clear the demo estate instead of creating it",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    try:
        require_local(settings.database_url)
    except NotLocalError as refused:
        print(f"FAIL: {refused}", file=sys.stderr)
        return 2

    engine = create_engine(settings.database_url)
    try:
        if args.remove:
            for table_name, count in remove(engine).items():
                print(f"  cleared {count:>4} from {table_name}")
            print(f"Demo tenant {DEMO_TENANT} is gone.")
            return 0

        written, instances = seed(engine, settings, datetime.now(UTC))
        print(f"Seeded tenant {DEMO_TENANT}, {DEMO_NAME}.")
        print(f"  {instances} instances, {written} rows written by the real collector")
        print("  every figure is modelled, and the screens say so")
        print("Clear it with: make unseed")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
