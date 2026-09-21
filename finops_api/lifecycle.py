"""Moving a recommendation, and recording who moved it.

The transitions themselves are in the domain, in `ALLOWED`. This is the part that
needs a database: check the current state, refuse an illegal move, write the row
and the event in one transaction.

Two rules the routes depend on.

**A dismissal carries a reason.** Enforced here and in the database, because it is
the one transition where the reason is the entire point: a dismissal nobody can
review is indistinguishable from a recommendation nobody looked at.

**Accepting opens a ticket, and failing to open one does not silently succeed.**
If the sink is unreachable the transition is refused rather than half done, because
a recommendation marked accepted with no ticket behind it is work nobody will do
and everybody will assume is happening.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from finops_core.domain.waste import ALLOWED, Lifecycle


class TransitionRefusedError(RuntimeError):
    """The move is not one this recommendation can make."""


@dataclass(frozen=True)
class Moved:
    recommendation_id: UUID
    was: Lifecycle
    now: Lifecycle
    ticket_reference: str | None


READ = text(
    "SELECT lifecycle, ticket_reference, waste_class, resource_id, rationale, "
    "estimated_monthly_saving FROM recommendation "
    "WHERE tenant_id = :tenant AND recommendation_id = :id FOR UPDATE"
)

MOVE = text(
    "UPDATE recommendation SET lifecycle = :to, owner = COALESCE(:owner, owner), "
    "ticket_reference = COALESCE(:ticket, ticket_reference), collected_at = :now "
    "WHERE tenant_id = :tenant AND recommendation_id = :id"
)

EVENT = text(
    "INSERT INTO recommendation_event (event_id, recommendation_id, tenant_id, "
    "from_lifecycle, to_lifecycle, actor, reason, occurred_at, as_of, collected_at) "
    "VALUES (:event, :id, :tenant, :from, :to, :actor, :reason, :now, :now, :now)"
)


def move(
    connection: Any,
    *,
    tenant_id: UUID,
    recommendation_id: UUID,
    target: Lifecycle,
    actor: str,
    reason: str | None = None,
    owner: str | None = None,
    tickets: Any = None,
    clock: Any = None,
) -> Moved:
    """Move one recommendation, or refuse and change nothing."""
    now = (clock or (lambda: datetime.now(UTC)))()
    row = connection.execute(READ, {"tenant": tenant_id, "id": recommendation_id}).first()
    if row is None:
        # Out of scope and not present are the same answer here on purpose. A
        # caller who could tell them apart could enumerate other accounts'
        # recommendations by id.
        raise TransitionRefusedError("no such recommendation in this scope")

    was = Lifecycle(row[0])
    if target not in ALLOWED[was]:
        raise TransitionRefusedError(
            f"{was.value} does not move to {target.value}. "
            f"From {was.value} the moves are: "
            f"{', '.join(sorted(s.value for s in ALLOWED[was])) or 'none, it is terminal'}"
        )

    if target is Lifecycle.DISMISSED and not (reason and reason.strip()):
        raise TransitionRefusedError(
            "a dismissal needs a reason. A dismissal nobody can review is "
            "indistinguishable from a recommendation nobody looked at"
        )

    ticket = row[1]
    if target is Lifecycle.ACCEPTED and tickets is not None and not ticket:
        # If this raises, nothing has been written and the transaction rolls back.
        # A recommendation marked accepted with no ticket behind it is work nobody
        # will do and everybody will assume is happening.
        ticket = tickets.open_ticket(
            title=f"{row[2]} on {row[3]}",
            body=f"{row[4]}\n\nEstimated monthly saving: {row[5]}",
            reference=str(recommendation_id),
        )

    connection.execute(
        MOVE,
        {
            "to": target.value,
            "owner": owner,
            "ticket": ticket,
            "now": now,
            "tenant": tenant_id,
            "id": recommendation_id,
        },
    )
    connection.execute(
        EVENT,
        {
            "event": uuid4(),
            "id": recommendation_id,
            "tenant": tenant_id,
            "from": was.value,
            "to": target.value,
            "actor": actor,
            "reason": reason,
            "now": now,
        },
    )
    return Moved(recommendation_id=recommendation_id, was=was, now=target, ticket_reference=ticket)
