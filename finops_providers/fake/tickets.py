"""A ticket sink that remembers, in memory.

Idempotent on the recommendation reference, which is the property the port asks
for and the one a real adapter will get wrong first: called twice for the same
recommendation it returns the same ticket. A duplicate ticket is how a team learns
to ignore an integration.
"""

from __future__ import annotations

from finops_core.errors import Unreachable
from finops_providers.fake import fixtures


class FakeTicketSink:
    """`TicketSink` in memory. Every failure is asked for."""

    def __init__(self, *, unreachable: bool = False) -> None:
        self._unreachable = unreachable
        self._by_reference: dict[str, str] = {}
        self._closed: set[str] = set()
        #: What would have been sent, so a test can assert the ticket says
        #: something useful rather than only that one was opened.
        self.opened: list[tuple[str, str, str]] = []

    def _fail_if_planned(self) -> None:
        if self._unreachable:
            raise Unreachable(
                scope_key=fixtures.ORGANIZATION_SCOPE,
                collector="tickets",
                detail="planned by the fake ticket sink",
            )

    def open_ticket(self, *, title: str, body: str, reference: str) -> str:
        self._fail_if_planned()
        # Idempotent. The second call for one recommendation returns the first
        # ticket rather than opening another.
        if reference not in self._by_reference:
            self._by_reference[reference] = f"FAKE-{len(self._by_reference) + 1:04d}"
            self.opened.append((title, body, reference))
        return self._by_reference[reference]

    def is_open(self, ticket_id: str) -> bool:
        self._fail_if_planned()
        return ticket_id not in self._closed

    def close(self, ticket_id: str) -> None:
        """Not part of the port. A test's way of making a ticket go away."""
        self._closed.add(ticket_id)
