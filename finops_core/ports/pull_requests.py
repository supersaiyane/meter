"""Where an authored infrastructure change goes for a human to approve.

TASK-P7-009 and FEAT-040. Constraint 6: v1 makes no write into a member account, and
remediation is delivered as a generated infrastructure as code pull request instead. This
port is that delivery. A port with a fake and no adapter, the shape `TicketSink` has and for
the same reason: which code host receives the pull request is OPEN-13, and the authoring,
which is the part carrying the risk, can be built and tested against the interface now.

**Open, and nothing more.** The one method opens a pull request for somebody to review. There
is no method to merge one, approve one or apply what it holds, so an adapter has nothing to
implement that could, and `tests/contract/test_no_llm_writes.py` asserts the absence by name.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class FileChange:
    """One file the pull request adds, at a path relative to the repository root."""

    path: str
    content: str


@dataclass(frozen=True)
class PullRequestDraft:
    """A pull request, written in full before anything is sent anywhere."""

    title: str
    body: str
    branch: str
    changes: tuple[FileChange, ...]
    #: Our recommendation id, so an adapter can be idempotent: asked twice for the same
    #: recommendation it returns the first pull request rather than opening a second.
    reference: str


@runtime_checkable
class PullRequestSink(Protocol):
    """A code host where a person reviews a change before anything happens."""

    def open_pull_request(self, draft: PullRequestDraft) -> str:
        """Open one for review and return the host's reference for it.

        Raises:
            AccessDenied: The credential may not open pull requests in the repository.
            Misconfigured: The repository this deployment names does not exist.
            Unreachable: The host did not answer.
        """
        ...
