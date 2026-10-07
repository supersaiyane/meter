"""A report store and a report sender that remember, in memory. FEAT-069, TASK-P8-011.

The store keeps what it was handed under its key and refuses a key it never saw with NoData, the
port's promise: an absent file is never an empty one. The sender records what it would have
sent, so a test can assert who received which file, and fails for the people it is told to, so a
test can hold that one recipient failing does not fail the run.
"""

from __future__ import annotations

from collections.abc import Iterable

from finops_core.errors import Misconfigured, NoData, Unreachable

COLLECTOR = "report_store"


class MemoryReportStore:
    """`ReportStore` in memory. Every failure is asked for."""

    def __init__(self, *, unreachable: bool = False) -> None:
        self._unreachable = unreachable
        self.kept: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, body: bytes, content_type: str) -> None:
        if self._unreachable:
            raise Unreachable(
                scope_key=key, collector=COLLECTOR, detail="the store was asked to fail"
            )
        self.kept[key] = (body, content_type)

    def get(self, key: str) -> bytes:
        if self._unreachable:
            raise Unreachable(
                scope_key=key, collector=COLLECTOR, detail="the store was asked to fail"
            )
        if key not in self.kept:
            raise NoData(
                scope_key=key, collector=COLLECTOR, detail="nothing is kept under this key"
            )
        return self.kept[key][0]


class RecordingSender:
    """`ReportSender` that records each file instead of delivering it."""

    def __init__(self, *, failing_for: Iterable[str] = ()) -> None:
        self._failing_for = frozenset(failing_for)
        #: Recipient, subject, file name and size, in the order they were sent.
        self.sent: list[tuple[str, str, str, int]] = []

    def send(self, *, recipient: str, subject: str, file_name: str, body: bytes) -> None:
        if recipient in self._failing_for:
            raise Misconfigured(
                scope_key=recipient,
                collector="report_sender",
                detail="the fake was told this person has no address",
            )
        self.sent.append((recipient, subject, file_name, len(body)))
