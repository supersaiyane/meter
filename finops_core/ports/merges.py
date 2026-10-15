"""The one write into a repository Meter may make: merging a fix it opened. ADR-0038, FEAT-094.

TASK-P15-001. Its own module, so the ports that open and read name no merge, and so the contract
test can allow the method's name here, in the one function that calls it, `finops_ingest.fix_merge`,
and in the adapter that implements it, and nowhere else. Nothing here decides whether to merge:
`finops_core.domain.fixes.may_merge` decides, and the one function asks it first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class MergeAnswer:
    """What the host did with a merge: merged, with the commit, or refused, with why."""

    merged: bool
    reason: str
    sha: str | None = None


@runtime_checkable
class PullRequestMerger(Protocol):
    """A code host's own merge, through the repository's protections."""

    def merge_pull_request(self, repository: str, number: int, head_sha: str) -> MergeAnswer:
        """Merge the pull request if its head is still `head_sha` and the host accepts it.

        A merge the host refuses, a protection unmet or a head that moved, is an answer, not an
        error: it is recorded and never retried past the protection.

        Raises:
            AccessDenied: The credential may not merge in the repository.
            Throttled: The host's rate limit is spent.
            Unreachable: The host did not answer.
        """
        ...
