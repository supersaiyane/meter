"""A code host that records what it was asked to open, and opens each thing once.

TASK-P7-009. Stands in for the adapter OPEN-13 has not chosen. Idempotent by reference, as
the port asks, because a second pull request for the same recommendation is how a team
learns to close them unread.
"""

from __future__ import annotations

from finops_core.ports.pull_requests import PullRequestDraft


class RecordingPullRequests:
    """A `PullRequestSink` holding what it opened, in order."""

    def __init__(self) -> None:
        self._opened: dict[str, str] = {}
        self._drafts: list[PullRequestDraft] = []

    @property
    def drafts(self) -> tuple[PullRequestDraft, ...]:
        """Every pull request opened, once each, in the order they were opened."""
        return tuple(self._drafts)

    def open_pull_request(self, draft: PullRequestDraft) -> str:
        if draft.reference not in self._opened:
            self._opened[draft.reference] = f"pull-request-{len(self._opened) + 1}"
            self._drafts.append(draft)
        return self._opened[draft.reference]
