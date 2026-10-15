"""Meter's fixes as GitHub pull requests: opened, read, followed and merged. TASK-P15-002.

FEAT-040 and FEAT-091 to FEAT-094, OPEN-13. `GitHubCodeHost` implements the four code host ports
over GitHub's REST API through `finops_providers.github.app`, each request in its own session, with
a token minted for the one repository and the permissions the request needs.

**Opening is idempotent and never overwrites.** The draft names a branch for its fix. An open pull
request from that branch is returned rather than a second opened. Otherwise one commit holding the
draft's files is made on the base branch's head, carrying `Meter-Reference: <id>` in its message,
and the branch is pointed at it. A branch that already exists is moved only when its last commit is
Meter's for the same fix, which is what a closed pull request or a run that stopped part way leaves;
any other branch is refused, Misconfigured, because Meter never overwrites work it did not write.

**Merging is GitHub's own merge, at the head the rule saw.** ADR-0038: the one caller is
`finops_ingest.fix_merge`, after `finops_core.domain.fixes.may_merge`, and the contract test allows
the method's name here because this is where it is implemented. GitHub applies the repository's
branch protection to the merge, and a head that moved since it was read merges nothing. A merge
GitHub refuses is an answer, recorded, never retried past the protection.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from typing import Any, Final
from urllib.parse import quote

from finops_core.domain.fixes import PullRequestState, Readiness
from finops_core.ports.merges import MergeAnswer
from finops_core.ports.pull_requests import (
    OpenedPullRequest,
    PullRequestDraft,
    RepositoryFile,
    RepositoryTarget,
)
from finops_providers.github.app import (
    METADATA,
    READ,
    WRITE,
    GitHubApp,
    Repository,
    Session,
    field,
)

COLLECTOR: Final = "fix_pull_requests"

#: The line in a commit's message that says which fix Meter made it for.
REFERENCE_TRAILER: Final = "Meter-Reference"

#: GitHub's `mergeable_state`, as the merge rule reads it. Anything else, and a pull request whose
#: mergeability GitHub has not yet worked out, is UNKNOWN; the next run reads it again.
READINESS: Final[Mapping[str, Readiness]] = {
    # Mergeable, every required check passed and every required review given.
    "clean": Readiness.READY,
    # As clean, on a host that runs pre-receive hooks.
    "has_hooks": Readiness.READY,
    # A required check still running or not passed, or a required review not given.
    "blocked": Readiness.WAITING,
    # Mergeable with a check failing. Meter does not merge past a red check, required or not.
    "unstable": Readiness.BLOCKED,
    # A conflict with the base branch.
    "dirty": Readiness.BLOCKED,
    # Behind a base branch the repository requires it to be up to date with.
    "behind": Readiness.BLOCKED,
    "draft": Readiness.BLOCKED,
}

#: The merge methods Meter uses, in the order it prefers them, with the repository setting that
#: allows each. One commit on the base branch reads most plainly as the one fix it is.
MERGE_METHODS: Final[tuple[tuple[str, str], ...]] = (
    ("squash", "allow_squash_merge"),
    ("merge", "allow_merge_commit"),
    ("rebase", "allow_rebase_merge"),
)

#: The most repositories first contact lists, one page.
LISTED: Final = 100  # allow-hardcoded: GitHub's documented largest page


def trailer(reference: str) -> str:
    """The commit message line that marks a commit as Meter's for one fix."""
    return f"{REFERENCE_TRAILER}: {reference}"


class GitHubCodeHost:
    """PullRequestSink, RepositoryReader, PullRequestTracker and PullRequestMerger over GitHub."""

    def __init__(self, app: GitHubApp) -> None:
        self._app = app

    # -- PullRequestSink ---------------------------------------------------

    def open_pull_request(
        self, draft: PullRequestDraft, target: RepositoryTarget
    ) -> OpenedPullRequest:
        """Open the draft against the target's base branch, or return the one already open."""
        with self._app.session(target.repository, WRITE) as (session, repo):
            opened = _open_from(session, repo, draft.branch)
            if opened is not None:
                return opened
            commit = _commit(session, repo, draft, target.base_branch)
            _point_branch(session, repo, draft, commit)
            answer = session.call(
                "POST",
                f"{repo.path}/pulls",
                json={
                    "title": draft.title,
                    "body": draft.body,
                    "head": draft.branch,
                    "base": target.base_branch,
                },
                answers=frozenset({422}),
            )
            if answer.status_code == 422:
                # Opened by another run between the look and the ask; anything else is drift.
                opened = _open_from(session, repo, draft.branch)
                if opened is not None:
                    return opened
                raise session.drift(
                    f"GitHub would not open the pull request: {session.said(answer)}"
                )
            return _opened(session, session.body(answer, "the new pull request"))

    # -- RepositoryReader --------------------------------------------------

    def read_folder(self, target: RepositoryTarget, suffix: str) -> tuple[RepositoryFile, ...]:
        """Every file directly in the folder whose name ends with `suffix`, at the base branch."""
        with self._app.session(target.repository, READ) as (session, repo):
            where = f"{repo.path}/contents"
            if target.folder:
                where = f"{where}/{quote(target.folder)}"
            ref = {"ref": target.base_branch}
            listing = session.json(
                "GET",
                where,
                params=ref,
                absent=f"no folder {target.folder or 'at the root'} on {target.base_branch} in "
                f"{target.repository}",
            )
            if not isinstance(listing, list):
                raise session.misconfigured(f"{target.folder} is a file, not a folder")
            found = []
            for entry in listing:
                name = str(field(session, entry, "name"))
                if field(session, entry, "type") != "file" or not name.endswith(suffix):
                    continue
                path = str(field(session, entry, "path"))
                one = session.json("GET", f"{repo.path}/contents/{quote(path)}", params=ref)
                found.append(RepositoryFile(path=path, content=_decoded(session, one, path)))
            return tuple(sorted(found, key=lambda one: one.path))

    # -- PullRequestTracker ------------------------------------------------

    def pull_request_state(self, repository: str, number: int) -> PullRequestState:
        """Open or merged, by whom, and whether GitHub would accept a merge now."""
        with self._app.session(repository, READ) as (session, repo):
            body = session.json(
                "GET",
                f"{repo.path}/pulls/{number}",
                absent=f"no pull request #{number} in {repository}",
            )
            merged_by = body.get("merged_by") if isinstance(body, dict) else None
            return PullRequestState(
                number=int(field(session, body, "number")),
                url=str(field(session, body, "html_url")),
                open=field(session, body, "state") == "open",
                merged=bool(field(session, body, "merged")),
                readiness=_readiness(body),
                head_sha=str(field(session, body, "head", "sha")),
                merged_by=str(merged_by["login"]) if isinstance(merged_by, dict) else None,
            )

    # -- PullRequestMerger, ADR-0038 ----------------------------------------

    def merge_pull_request(self, repository: str, number: int, head_sha: str) -> MergeAnswer:
        """GitHub's own merge of the pull request, only if its head is still `head_sha`."""
        with self._app.session(repository, WRITE) as (session, repo):
            settings = session.json("GET", repo.path, absent=f"no repository {repository}")
            method = next((name for name, allowed in MERGE_METHODS if settings.get(allowed)), None)
            if method is None:
                return MergeAnswer(False, "The repository allows no merge method.")
            answer = session.call(
                "PUT",
                f"{repo.path}/pulls/{number}/merge",
                json={"sha": head_sha, "merge_method": method},
                absent=f"no pull request #{number} in {repository}",
                answers=frozenset({405, 409, 422}),
            )
            if answer.status_code == 409:
                return MergeAnswer(False, "Its head moved after Meter read it, so nothing merged.")
            if answer.status_code in (405, 422):
                return MergeAnswer(False, f"GitHub refused the merge: {session.said(answer)}")
            body = session.body(answer, "the merge")
            return MergeAnswer(True, f"Merged by {method}.", sha=str(field(session, body, "sha")))

    # -- first contact ------------------------------------------------------

    def installation_repositories(self, repository: str) -> tuple[str, ...]:
        """The repositories the app is installed on, found through one. Reads metadata only."""
        with self._app.session(repository, METADATA, narrowed=False) as (session, _repo):
            body = session.json("GET", "/installation/repositories", params={"per_page": LISTED})
            listed = field(session, body, "repositories")
            return tuple(sorted(str(field(session, one, "full_name")) for one in listed))


# -- opening, one step at a time ------------------------------------------------


def _open_from(session: Session, repo: Repository, branch: str) -> OpenedPullRequest | None:
    """The open pull request from `branch`, if there is one."""
    listed = session.json(
        "GET",
        f"{repo.path}/pulls",
        params={"head": f"{repo.owner}:{branch}", "state": "open"},
    )
    if not isinstance(listed, list):
        raise session.drift("GitHub listed pull requests as something that is not a list")
    return _opened(session, listed[0]) if listed else None


def _opened(session: Session, body: Any) -> OpenedPullRequest:
    return OpenedPullRequest(
        number=int(field(session, body, "number")), url=str(field(session, body, "html_url"))
    )


def _commit(session: Session, repo: Repository, draft: PullRequestDraft, base: str) -> str:
    """One commit on the base branch's head holding the draft's files. Returns its sha."""
    head = session.json(
        "GET",
        f"{repo.path}/git/ref/heads/{quote(base)}",
        absent=f"no branch {base} in {repo.owner}/{repo.name}",
    )
    parent = str(field(session, head, "object", "sha"))
    tree = field(session, session.json("GET", f"{repo.path}/git/commits/{parent}"), "tree", "sha")
    files = [
        {"path": change.path, "mode": "100644", "type": "blob", "content": change.content}
        for change in draft.changes
    ]
    made = session.json("POST", f"{repo.path}/git/trees", json={"base_tree": tree, "tree": files})
    commit = session.json(
        "POST",
        f"{repo.path}/git/commits",
        json={
            "message": f"{draft.title}\n\n{trailer(draft.reference)}\n",
            "tree": field(session, made, "sha"),
            "parents": [parent],
        },
    )
    return str(field(session, commit, "sha"))


def _point_branch(session: Session, repo: Repository, draft: PullRequestDraft, commit: str) -> None:
    """Make the draft's branch at `commit`, or move Meter's own branch for this fix there."""
    made = session.call(
        "POST",
        f"{repo.path}/git/refs",
        json={"ref": f"refs/heads/{draft.branch}", "sha": commit},
        answers=frozenset({422}),
    )
    if made.status_code != 422:
        return
    branch = quote(draft.branch)
    tip = field(
        session, session.json("GET", f"{repo.path}/git/ref/heads/{branch}"), "object", "sha"
    )
    last = session.json("GET", f"{repo.path}/git/commits/{tip}")
    if trailer(draft.reference) not in str(field(session, last, "message")).splitlines():
        raise session.misconfigured(
            f"the branch {draft.branch} exists and its last commit is not Meter's for this fix. "
            "Meter never overwrites a branch it did not write: delete or rename it, and ask again"
        )
    session.json(
        "PATCH", f"{repo.path}/git/refs/heads/{branch}", json={"sha": commit, "force": True}
    )


def _decoded(session: Session, body: Any, path: str) -> str:
    """A file's text from the contents API's base64, which holds files up to a megabyte."""
    if field(session, body, "encoding") != "base64":
        raise session.drift(
            f"{path} came back without its content; the contents API returns a file's text up to "
            "a megabyte"
        )
    try:
        return base64.b64decode(str(field(session, body, "content"))).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as error:
        raise session.drift(f"{path} is not text Meter can read") from error


def _readiness(body: Any) -> Readiness:
    if not isinstance(body, dict) or body.get("mergeable") is None:
        return Readiness.UNKNOWN
    return READINESS.get(str(body.get("mergeable_state")), Readiness.UNKNOWN)
