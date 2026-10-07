"""Where a scheduled report's file is kept, and who it is sent to. FEAT-069, TASK-P8-011.

Two ports. A store, which the hub's data bucket implements, because a file a schedule rendered
has to outlive the run that made it and be fetched later through a route that checks scope
again. And a sender, with a fake and no adapter, because OPEN-11 has not said whether reports go
by email or by Slack: a run with no sender is stored and listed as rendered and not sent, the
shape the digests already use.

Both raise the typed causes of `finops_core.errors` and nothing else, so a run records why a
file was not stored or not sent in the same seven words every other failure uses.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ReportStore(Protocol):
    """Somewhere a rendered file is kept under a key, and read back by that key."""

    def put(self, key: str, body: bytes, content_type: str) -> None:
        """Keep `body` under `key`. Every key a run writes is new, so nothing is replaced.

        Raises Unreachable when the store cannot be reached and AccessDenied when it refuses.
        """
        ...

    def get(self, key: str) -> bytes:
        """The file kept under `key`.

        Raises NoData when nothing is kept there, never an empty file, and Unreachable or
        AccessDenied as `put` does.
        """
        ...


@runtime_checkable
class ReportSender(Protocol):
    """Somewhere a person will receive a file. OPEN-11 decides where."""

    def send(self, *, recipient: str, subject: str, file_name: str, body: bytes) -> None:
        """Deliver one file to one person.

        Raises Unreachable when the channel cannot be reached and Misconfigured when the
        person has no address on it, so a run says which.
        """
        ...
