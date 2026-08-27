"""Erase one person on request, in one transaction, printing what it changed.

An erasure request is answered by a person under a legal deadline, usually in a
hurry, usually once. That is the worst possible moment to be composing SQL, so
it is written down here in advance and tested, and it prints what it did so the
answer to "what was removed" is not a reconstruction from memory.

What this does NOT do is the important part. It never touches `audit_event`.
Erasing the record of who read an organization's financial data, at the request
of the person who read it, is not defensible in a financial services
environment, and the lawful basis for those records is not consent. The
principal row survives too, anonymised rather than removed, so the audit trail
still joins to something. See docs/09-DATA-CLASSIFICATION.md.

The request and the completion are themselves audit events. An erasure that
leaves no trace of having happened cannot be evidenced to the person who asked
for it.

Usage:

    python scripts/ops/erase_principal.py --tenant <uuid> --principal <uuid> \
        --requested-by <operator> --request-id <ticket> --commit
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import column, table, text

#: What a name is replaced with. The same value the retention job uses, so a row
#: retired by policy and a row retired on request read identically.
TOMBSTONE = "anonymised"

_PRINCIPAL_SCOPE = table("principal_scope", column("tenant_id"), column("principal_id"))

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ErasureReport:
    """What was changed, for printing and for asserting on in a test."""

    principal_id: UUID
    principals_anonymised: int
    scope_rows_removed: int
    schedule_rows_reattributed: int
    audit_events_written: int
    #: Always zero. Present so the report says out loud what was left alone,
    #: rather than leaving the reader to infer it from an absence.
    audit_events_removed: int = 0

    def lines(self) -> tuple[str, ...]:
        return (
            f"principal {self.principal_id}",
            f"  principal rows anonymised      {self.principals_anonymised}",
            f"  entitlement cache rows removed {self.scope_rows_removed}",
            f"  schedule rows reattributed     {self.schedule_rows_reattributed}",
            f"  audit events written           {self.audit_events_written}",
            f"  audit events removed           {self.audit_events_removed}"
            " (never removed, by design)",
        )


def _audit(
    connection: Any,
    tenant_id: UUID,
    principal_id: UUID,
    action: str,
    request_id: str,
    requested_by: str,
    at: datetime,
) -> None:
    connection.execute(
        text(
            "INSERT INTO audit_event (event_id, tenant_id, principal_id, action, resource, "
            "scope_evaluated, is_global_read, outcome, occurred_at, request_id) "
            "VALUES (:event, :tenant, :principal, :action, :resource, "
            "jsonb_build_object('requested_by', CAST(:who AS text)), false, 'ALLOWED', "
            ":at, :request)"
        ),
        {
            "event": uuid4(),
            "tenant": tenant_id,
            "principal": principal_id,
            "action": action,
            "resource": f"principal:{principal_id}",
            "who": requested_by,
            "at": at,
            "request": request_id,
        },
    )


def erase(
    connection: Any,
    tenant_id: UUID,
    principal_id: UUID,
    requested_by: str,
    request_id: str,
    clock: Clock = _system_clock,
) -> ErasureReport:
    """The five steps, in order, on one connection the caller keeps in a transaction.

    The caller owns the transaction rather than this function, because a partial
    erasure is worse than none: it leaves a person half identified, with no
    record of which half.
    """
    at = clock()
    _audit(connection, tenant_id, principal_id, "erasure.requested", request_id, requested_by, at)

    anonymised = connection.execute(
        text(
            "UPDATE principal SET display_name = :tombstone, email = NULL, "
            "subject = :subject WHERE tenant_id = :tenant AND principal_id = :principal"
        ),
        {
            "tombstone": TOMBSTONE,
            "subject": f"{TOMBSTONE}:{sha256(str(principal_id).encode()).hexdigest()}",
            "tenant": tenant_id,
            "principal": principal_id,
        },
    ).rowcount

    scope_rows = connection.execute(
        _PRINCIPAL_SCOPE.delete().where(
            _PRINCIPAL_SCOPE.c.tenant_id == tenant_id,
            _PRINCIPAL_SCOPE.c.principal_id == principal_id,
        )
    ).rowcount

    # A cadence change is operational history, not personal data, so the change
    # survives and only the attribution goes. Removing the row would silently
    # reset a deliberately slowed collector back to its default.
    schedule_rows = connection.execute(
        text(
            "UPDATE collector_schedule SET updated_by = :tombstone "
            "WHERE tenant_id = :tenant AND updated_by = :who"
        ),
        {"tombstone": TOMBSTONE, "tenant": tenant_id, "who": str(principal_id)},
    ).rowcount

    _audit(connection, tenant_id, principal_id, "erasure.completed", request_id, requested_by, at)

    return ErasureReport(
        principal_id=principal_id,
        principals_anonymised=anonymised or 0,
        scope_rows_removed=scope_rows or 0,
        schedule_rows_reattributed=schedule_rows or 0,
        audit_events_written=2,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Erase one principal on request.")
    parser.add_argument("--tenant", required=True, type=UUID)
    parser.add_argument("--principal", required=True, type=UUID)
    parser.add_argument("--requested-by", required=True)
    parser.add_argument(
        "--request-id", required=True, help="the ticket the request arrived on, for the audit trail"
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="without this the work is rolled back and the report is a dry run",
    )
    args = parser.parse_args(argv)

    url = os.environ.get("METER_DATABASE_URL")
    if not url:
        print("METER_DATABASE_URL is not set", file=sys.stderr)
        return 2

    from sqlalchemy import create_engine

    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        report = erase(connection, args.tenant, args.principal, args.requested_by, args.request_id)
        for line in report.lines():
            print(line)
        if report.principals_anonymised == 0:
            transaction.rollback()
            print(f"no principal {args.principal} in tenant {args.tenant}", file=sys.stderr)
            return 3
        if args.commit:
            transaction.commit()
            print("committed.")
        else:
            transaction.rollback()
            print("dry run, rolled back. Pass --commit to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
