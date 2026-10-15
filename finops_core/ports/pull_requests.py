"""Where an authored infrastructure change goes for a human to approve, and what it reads.

TASK-P7-009 and FEAT-040, and P15, TASK-P15-001. Constraint 6: v1 makes no write into a member
account, and remediation is delivered as a generated infrastructure as code pull request instead.
These ports are that delivery. OPEN-13 chose the host on 2026-10-15, a GitHub App.

**Open, read, and nothing more, here.** `PullRequestSink` opens a pull request for somebody to
review, into the repository a target names, FEAT-091. `RepositoryReader` reads the files of the
folder a fix will change, FEAT-093. `PullRequestTracker` reads a pull request's state, FEAT-092.
Merging is a port of its own, `finops_core.ports.merges`, so this module names no merge, and an
adapter of these three has nothing to implement that could. `tests/contract/test_no_llm_writes.py`
asserts that by name, and allows the one merge only where ADR-0038 says.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from finops_core.domain.fixes import PullRequestState


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


@dataclass(frozen=True)
class RepositoryTarget:
    """Where a fix goes: a repository, the branch it is based on, and the folder it changes.

    FEAT-091, OPEN-42: from the mapping the owner sets per Terraform state file.
    """

    #: `owner/name`.
    repository: str
    base_branch: str
    #: Relative to the repository root, with no leading or trailing slash; empty for the root.
    folder: str


@dataclass(frozen=True)
class OpenedPullRequest:
    """A pull request the host opened: its number in the repository, and its link."""

    number: int
    url: str


@dataclass(frozen=True)
class RepositoryFile:
    """One file read from a folder, at a path relative to the repository root."""

    path: str
    content: str


@runtime_checkable
class PullRequestSink(Protocol):
    """A code host where a person reviews a change before anything happens."""

    def open_pull_request(
        self, draft: PullRequestDraft, target: RepositoryTarget
    ) -> OpenedPullRequest:
        """Open one for review in the target's repository, against its base branch.

        Idempotent by the draft's reference: asked twice for the same recommendation, it returns
        the first pull request rather than opening a second.

        Raises:
            AccessDenied: The credential may not open pull requests in the repository.
            Misconfigured: The repository or its base branch does not exist.
            Throttled: The host's rate limit is spent.
            Unreachable: The host did not answer.
        """
        ...


@runtime_checkable
class RepositoryReader(Protocol):
    """The files of a folder, read at its base branch. FEAT-093."""

    def read_folder(self, target: RepositoryTarget, suffix: str) -> tuple[RepositoryFile, ...]:
        """Every file directly in the target's folder whose name ends with `suffix`.

        Raises:
            AccessDenied: The credential may not read the repository.
            Misconfigured: The repository, the branch or the folder does not exist.
            Throttled: The host's rate limit is spent.
            Unreachable: The host did not answer.
        """
        ...


@runtime_checkable
class PullRequestTracker(Protocol):
    """A pull request's state, as its host reports it. FEAT-092."""

    def pull_request_state(self, repository: str, number: int) -> PullRequestState:
        """Whether it is open or merged, by whom, and whether a merge would be accepted now.

        Raises:
            AccessDenied: The credential may not read the repository.
            Misconfigured: The pull request does not exist.
            Throttled: The host's rate limit is spent.
            Unreachable: The host did not answer.
        """
        ...
