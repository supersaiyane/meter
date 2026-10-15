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
    #: The tables ISS-226, ISS-249, ISS-255 and ISS-256 found erasure did not reach, decided by the
    #: owner on 2026-10-12: the person's questions and exports tombstoned and kept, their private
    #: views removed and shared ones kept unowned, their schedules paused, and their name taken off
    #: every recipient list.
    exchanges_tombstoned: int = 0
    redactions_tombstoned: int = 0
    exports_tombstoned: int = 0
    private_views_removed: int = 0
    shared_views_unowned: int = 0
    schedules_paused: int = 0
    recipient_lists_changed: int = 0
    #: TASK-P14-005. The commitment policy they last changed: the decision kept, the name gone.
    policies_reattributed: int = 0
    #: TASK-P14-008. The steps they took on a purchase plan: each step kept, the name gone.
    plan_steps_reattributed: int = 0
    #: TASK-P15-003. The code host they connected and the repositories they mapped: each kept,
    #: the name gone.
    code_host_reattributed: int = 0
    mappings_reattributed: int = 0
    #: Always zero. Present so the report says out loud what was left alone,
    #: rather than leaving the reader to infer it from an absence.
    audit_events_removed: int = 0

    def lines(self) -> tuple[str, ...]:
        return (
            f"principal {self.principal_id}",
            f"  principal rows anonymised      {self.principals_anonymised}",
            f"  entitlement cache rows removed {self.scope_rows_removed}",
            f"  schedule rows reattributed     {self.schedule_rows_reattributed}",
            f"  assistant questions tombstoned {self.exchanges_tombstoned}",
            f"  redaction records tombstoned   {self.redactions_tombstoned}",
            f"  export records tombstoned      {self.exports_tombstoned}",
            f"  private views removed          {self.private_views_removed}",
            f"  shared views left unowned      {self.shared_views_unowned}",
            f"  report schedules paused        {self.schedules_paused}",
            f"  recipient lists changed        {self.recipient_lists_changed}",
            f"  commitment policies reattributed {self.policies_reattributed}",
            f"  purchase plan steps reattributed {self.plan_steps_reattributed}",
            f"  code host connections reattributed {self.code_host_reattributed}",
            f"  repository mappings reattributed {self.mappings_reattributed}",
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
    # Checked first, because the audit event names the principal by a foreign key: an erasure
    # of a person the tenant does not have would otherwise fail on its own audit record instead
    # of saying so, and the caller's "no principal" answer could never be reached.
    exists = connection.execute(
        text("SELECT 1 FROM principal WHERE tenant_id = :tenant AND principal_id = :principal"),
        {"tenant": tenant_id, "principal": principal_id},
    ).first()
    if exists is None:
        return ErasureReport(
            principal_id=principal_id,
            principals_anonymised=0,
            scope_rows_removed=0,
            schedule_rows_reattributed=0,
            audit_events_written=0,
        )
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

    # The commitment policy a person last set, as with a cadence: the decision is the tenant's and
    # stays, and only the attribution goes. TASK-P14-005.
    policy_rows = connection.execute(
        text(
            "UPDATE commitment_policy SET updated_by = :tombstone "
            "WHERE tenant_id = :tenant AND updated_by = :who"
        ),
        {"tombstone": TOMBSTONE, "tenant": tenant_id, "who": str(principal_id)},
    ).rowcount

    # The steps a person took on a purchase plan, approving, recording a purchase or withdrawing:
    # a plan's history is the payer's record of a commitment and stays, and only the name goes.
    # TASK-P14-008.
    step_rows = connection.execute(
        text(
            "UPDATE purchase_plan_event SET principal = :tombstone "
            "WHERE tenant_id = :tenant AND principal = :who"
        ),
        {"tombstone": TOMBSTONE, "tenant": tenant_id, "who": str(principal_id)},
    ).rowcount

    # The code host a person connected and the repositories they mapped: where the organization's
    # fixes go is its decision and stays, and only the attribution goes. TASK-P15-003.
    code_host_rows = connection.execute(
        text(
            "UPDATE code_host_connection SET connected_by = :tombstone "
            "WHERE tenant_id = :tenant AND connected_by = :who"
        ),
        {"tombstone": TOMBSTONE, "tenant": tenant_id, "who": str(principal_id)},
    ).rowcount
    mapping_rows = connection.execute(
        text(
            "UPDATE repository_mapping SET set_by = :tombstone "
            "WHERE tenant_id = :tenant AND set_by = :who"
        ),
        {"tombstone": TOMBSTONE, "tenant": tenant_id, "who": str(principal_id)},
    ).rowcount

    reached = _reach_personal_tables(connection, tenant_id, str(principal_id))

    _audit(connection, tenant_id, principal_id, "erasure.completed", request_id, requested_by, at)

    return ErasureReport(
        principal_id=principal_id,
        principals_anonymised=anonymised or 0,
        scope_rows_removed=scope_rows or 0,
        schedule_rows_reattributed=schedule_rows or 0,
        policies_reattributed=policy_rows or 0,
        plan_steps_reattributed=step_rows or 0,
        code_host_reattributed=code_host_rows or 0,
        mappings_reattributed=mapping_rows or 0,
        audit_events_written=2,
        **reached,
    )


#: What a refused question's reason becomes: the constraint wants twelve characters or more.
ERASED_TEXT = "anonymised on erasure"


def _reach_personal_tables(connection: Any, tenant_id: UUID, who: str) -> dict[str, int]:
    """The person's questions, exports, views and schedules, as the owner decided on 2026-10-12.

    A question and an export are kept and tombstoned, so the month's token spend and the export
    counts stay true; the text and the person's identifier go. A private view goes with the
    person; a shared one stays for the people it was shared with, owned by nobody nameable. A
    schedule they own is paused for an administrator to reassign, and their name comes off
    every list it was on; a schedule left with no recipient goes to its owner and is paused,
    because the table requires one recipient and nobody chose that schedule's new reader.
    """
    erased = f"{TOMBSTONE}:{sha256(who.encode()).hexdigest()}"
    values = {"tenant": tenant_id, "who": who, "erased": erased, "text": ERASED_TEXT}

    def run(sql: str) -> int:
        return int(connection.execute(text(sql), values).rowcount or 0)

    return {
        "redactions_tombstoned": run(
            "UPDATE redaction_event SET principal_id = :erased "
            "WHERE tenant_id = :tenant AND principal_id = :who"
        ),
        "exchanges_tombstoned": run(
            "UPDATE assistant_exchange SET principal_id = :erased, question = :text, "
            "answer = CASE WHEN answer IS NULL THEN NULL ELSE :text END, "
            "refusal_reason = CASE WHEN refusal_reason IS NULL THEN NULL ELSE :text END "
            "WHERE tenant_id = :tenant AND principal_id = :who"
        ),
        "exports_tombstoned": run(
            "UPDATE report_run SET principal_id = :erased "
            "WHERE tenant_id = :tenant AND principal_id = :who"
        ),
        "private_views_removed": run(
            "DELETE FROM saved_view "
            "WHERE tenant_id = :tenant AND owner_id = :who AND visibility = 'PRIVATE'"
        ),
        "shared_views_unowned": run(
            "UPDATE saved_view SET owner_id = :erased "
            "WHERE tenant_id = :tenant AND owner_id = :who AND visibility = 'SHARED'"
        ),
        "schedules_paused": run(
            "UPDATE report_schedule SET owner_id = :erased, enabled = false "
            "WHERE tenant_id = :tenant AND owner_id = :who"
        ),
        "recipient_lists_changed": run(
            "UPDATE report_schedule SET "
            "recipients = CASE WHEN recipients = ARRAY[:who]::text[] THEN ARRAY[owner_id] "
            "ELSE array_remove(recipients, :who) END, "
            "enabled = CASE WHEN recipients = ARRAY[:who]::text[] THEN false ELSE enabled END "
            "WHERE tenant_id = :tenant AND :who = ANY(recipients)"
        ),
    }


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
