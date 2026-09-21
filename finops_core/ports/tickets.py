"""Where a recommendation goes when somebody accepts it.

A port with a fake and no adapter, deliberately, because OPEN-05 has been open
since 2026-08-23 and nobody has chosen between Jira and ServiceNow.

That is not a reason to leave the lifecycle unbuilt. The port is what lets every
transition, every event and every screen be built and tested now, with the adapter
as one later task against an interface that already exists. Building the lifecycle
around a guess would be worse: the guess would be wrong half the time, and
unpicking it costs more than the port did.

The interface is deliberately thin. A ticket system can do a hundred things and
this product needs three: open one, find out whether it is still open, and record
the reference against the recommendation that caused it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TicketSink(Protocol):
    """Somewhere a human will actually see the work."""

    def open_ticket(self, *, title: str, body: str, reference: str) -> str:
        """Create one and return its identifier.

        `reference` is our recommendation id, passed so the sink can be idempotent:
        called twice for the same recommendation it returns the same ticket rather
        than opening a second. A duplicate ticket is how a team learns to ignore
        the integration.

        Raises:
            AccessDenied: The credentials cannot create in this project.
            Unreachable: The endpoint did not answer.
        """
        ...

    def is_open(self, ticket_id: str) -> bool:
        """Whether it still needs doing.

        Raises:
            NotFound: The ticket was deleted. Distinct from closed, because a
                deleted ticket means the work was never tracked and a closed one
                means it was.
            AccessDenied, Unreachable: As above.
        """
        ...
