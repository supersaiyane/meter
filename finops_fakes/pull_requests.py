"""A code host that records what it was asked to open, and opens each thing once.

TASK-P7-009, and P15, TASK-P15-001. Stands in for GitHub on the local stack and in tests.
Idempotent by reference, as the port asks, because a second pull request for the same
recommendation is how a team learns to close them unread. It reads a folder from the files it
was given, reports the states it was given, and its merger records each merge it was asked for.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from finops_core.domain.fixes import PullRequestState, Readiness
from finops_core.errors import Misconfigured
from finops_core.ports.merges import MergeAnswer
from finops_core.ports.pull_requests import (
    OpenedPullRequest,
    PullRequestDraft,
    RepositoryFile,
    RepositoryTarget,
)

COLLECTOR = "fix_pull_requests"


class RecordingPullRequests:
    """Every code host port: opens, reads a folder, reports state and merges. TASK-P15-007.

    One object for all four, as the GitHub adapter is, so the local stack's collector can follow
    a pull request it opened and merge it. A merge succeeds at the head it reported and refuses
    any other, as GitHub does, or refuses every time with `refuse_merges` set.
    """

    def __init__(self, files: Mapping[str, str] | None = None) -> None:
        #: Set to a sentence to refuse every merge with it, as a repository's protection would.
        self.refuse_merges: str | None = None
        self.merges: list[tuple[str, int, str]] = []
        self._opened: dict[str, OpenedPullRequest] = {}
        self._drafts: list[PullRequestDraft] = []
        self._targets: list[RepositoryTarget] = []
        self._files = dict(files or {})
        self._states: dict[tuple[str, int], PullRequestState] = {}

    @property
    def drafts(self) -> tuple[PullRequestDraft, ...]:
        """Every pull request opened, once each, in the order they were opened."""
        return tuple(self._drafts)

    @property
    def targets(self) -> tuple[RepositoryTarget, ...]:
        """Where each was opened, in the same order."""
        return tuple(self._targets)

    def open_pull_request(
        self, draft: PullRequestDraft, target: RepositoryTarget
    ) -> OpenedPullRequest:
        if draft.reference not in self._opened:
            number = len(self._opened) + 1
            opened = OpenedPullRequest(
                number=number, url=f"https://code.example/{target.repository}/pull/{number}"
            )
            self._opened[draft.reference] = opened
            self._drafts.append(draft)
            self._targets.append(target)
            self.set_state(
                target.repository,
                PullRequestState(
                    number=number,
                    url=opened.url,
                    open=True,
                    merged=False,
                    readiness=Readiness.WAITING,
                    head_sha=f"head-{number}",
                ),
            )
        return self._opened[draft.reference]

    def read_folder(self, target: RepositoryTarget, suffix: str) -> tuple[RepositoryFile, ...]:
        prefix = f"{target.folder}/" if target.folder else ""
        return tuple(
            RepositoryFile(path=path, content=content)
            for path, content in sorted(self._files.items())
            if path.startswith(prefix) and "/" not in path[len(prefix) :] and path.endswith(suffix)
        )

    def set_state(self, repository: str, state: PullRequestState) -> None:
        """What the host reports for one pull request from now on."""
        self._states[(repository, state.number)] = state

    def pull_request_state(self, repository: str, number: int) -> PullRequestState:
        found = self._states.get((repository, number))
        if found is None:
            raise Misconfigured(
                scope_key=f"{repository}#{number}",
                collector=COLLECTOR,
                detail="the fake host holds no such pull request",
            )
        return found

    def merge_pull_request(self, repository: str, number: int, head_sha: str) -> MergeAnswer:
        """Merge at the head reported, as GitHub's own merge does, and report it merged."""
        state = self.pull_request_state(repository, number)
        self.merges.append((repository, number, head_sha))
        if self.refuse_merges is not None:
            return MergeAnswer(merged=False, reason=self.refuse_merges)
        if state.head_sha != head_sha:
            return MergeAnswer(merged=False, reason="The head moved, so nothing was merged.")
        self.set_state(
            repository, replace(state, open=False, merged=True, merged_by="meter-app[bot]")
        )
        return MergeAnswer(merged=True, reason="Merged.", sha=f"merge-{number}")


class LocalCodeHost(RecordingPullRequests):
    """The local stack's GitHub, TASK-P15-009: any pull request it was not told of is open.

    The demo seed writes fixes whose pull requests this process never opened, and the worker
    follows them every ten minutes. A strict fake would call each unknown and fail the fix within
    a run, so the demo would show only failures. This one reports such a pull request open and
    waiting on its checks, which is what an untouched pull request on GitHub would report. Tests
    use `RecordingPullRequests`, which is strict.
    """

    def pull_request_state(self, repository: str, number: int) -> PullRequestState:
        if (repository, number) not in self._states:
            self.set_state(
                repository,
                PullRequestState(
                    number=number,
                    url=f"https://code.example/{repository}/pull/{number}",
                    open=True,
                    merged=False,
                    readiness=Readiness.WAITING,
                    head_sha=f"head-{number}",
                ),
            )
        return super().pull_request_state(repository, number)


class RecordingMerger:
    """A `PullRequestMerger` recording each merge it was asked for, accepting or refusing all."""

    def __init__(self, *, accept: bool = True) -> None:
        self._accept = accept
        self.merges: list[tuple[str, int, str]] = []

    def merge_pull_request(self, repository: str, number: int, head_sha: str) -> MergeAnswer:
        self.merges.append((repository, number, head_sha))
        if not self._accept:
            return MergeAnswer(merged=False, reason="The fake host refused the merge.")
        return MergeAnswer(merged=True, reason="Merged.", sha=f"merge-{number}")
