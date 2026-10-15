"""The GitHub adapter: open, read, follow and merge, against recorded shapes. TASK-P15-002.

FEAT-040 and FEAT-091 to FEAT-094. Opening is idempotent and never overwrites a branch Meter did
not write; a folder is read at its base branch; GitHub's mergeable state becomes the merge rule's
readiness; a merge is GitHub's own, at the head Meter read, and a refusal is an answer.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx
import pytest

from finops_core import errors
from finops_core.domain.fixes import Readiness
from finops_core.ports.merges import PullRequestMerger
from finops_core.ports.pull_requests import (
    FileChange,
    OpenedPullRequest,
    PullRequestDraft,
    PullRequestSink,
    PullRequestTracker,
    RepositoryFile,
    RepositoryReader,
    RepositoryTarget,
)
from tests.providers.github.fake import BASE_SHA, BASE_TREE, REPO, REPOSITORY, FakeGitHub, pull

BRANCH = "meter/remediation-rec-41"
TARGET = RepositoryTarget(REPOSITORY, "main", "storage")
DRAFT = PullRequestDraft(
    title="Remove unattached volume vol-0abc",
    body="Meter found this volume unattached for 30 days.",
    branch=BRANCH,
    changes=(FileChange("storage/meter_remediation_rec-41.tf", "removed {\n  from = x\n}\n"),),
    reference="rec-41",
)
TREE_SHA = "d" * 40
COMMIT_SHA = "e" * 40
THEIRS = "f" * 40


def opening(github: FakeGitHub, *, branch_exists: bool = False) -> None:
    """The answers a first opening reads, from GitHub's examples for each endpoint."""
    github.on("GET", f"{REPO}/pulls", 200, [])
    github.on(
        "GET",
        f"{REPO}/git/ref/heads/main",
        200,
        {"ref": "refs/heads/main", "object": {"sha": BASE_SHA, "type": "commit"}},
    )
    github.on(
        "GET",
        f"{REPO}/git/commits/{BASE_SHA}",
        200,
        {"sha": BASE_SHA, "tree": {"sha": BASE_TREE}, "message": "Add the storage stack"},
    )
    github.on("POST", f"{REPO}/git/trees", 201, {"sha": TREE_SHA, "truncated": False})
    github.on("POST", f"{REPO}/git/commits", 201, {"sha": COMMIT_SHA, "tree": {"sha": TREE_SHA}})
    if branch_exists:
        github.on("POST", f"{REPO}/git/refs", 422, {"message": "Reference already exists"})
    else:
        github.on("POST", f"{REPO}/git/refs", 201, {"ref": f"refs/heads/{BRANCH}"})
    github.on("POST", f"{REPO}/pulls", 201, pull(7))


def existing_branch(github: FakeGitHub, message: str) -> None:
    github.on("GET", f"{REPO}/git/ref/heads/{BRANCH}", 200, {"object": {"sha": THEIRS}})
    github.on("GET", f"{REPO}/git/commits/{THEIRS}", 200, {"sha": THEIRS, "message": message})
    github.on("PATCH", f"{REPO}/git/refs/heads/{BRANCH}", 200, {"object": {"sha": COMMIT_SHA}})


def test_the_adapter_is_every_code_host_port() -> None:
    host = FakeGitHub().host()
    for port in (PullRequestSink, RepositoryReader, PullRequestTracker, PullRequestMerger):
        assert isinstance(host, port)


def test_a_fix_is_opened_as_one_commit_on_the_base_branch_with_its_reference() -> None:
    github = FakeGitHub()
    opening(github)
    opened = github.host().open_pull_request(DRAFT, TARGET)
    assert opened == OpenedPullRequest(7, f"https://github.com/{REPOSITORY}/pull/7")
    looked = github.asked("GET", f"{REPO}/pulls")[0]
    assert dict(looked.url.params) == {"head": f"acme:{BRANCH}", "state": "open"}
    assert github.sent("POST", f"{REPO}/git/trees") == {
        "base_tree": BASE_TREE,
        "tree": [
            {
                "path": "storage/meter_remediation_rec-41.tf",
                "mode": "100644",
                "type": "blob",
                "content": DRAFT.changes[0].content,
            }
        ],
    }
    commit = github.sent("POST", f"{REPO}/git/commits")
    assert commit["parents"] == [BASE_SHA]
    assert commit["tree"] == TREE_SHA
    assert "Meter-Reference: rec-41" in commit["message"].splitlines()
    assert github.sent("POST", f"{REPO}/git/refs") == {
        "ref": f"refs/heads/{BRANCH}",
        "sha": COMMIT_SHA,
    }
    assert github.sent("POST", f"{REPO}/pulls") == {
        "title": DRAFT.title,
        "body": DRAFT.body,
        "head": BRANCH,
        "base": "main",
    }


def test_asked_twice_for_one_fix_it_returns_the_first_pull_request() -> None:
    github = FakeGitHub()
    opening(github)
    github.on("GET", f"{REPO}/pulls", 200, [pull(7)])
    assert github.host().open_pull_request(DRAFT, TARGET).number == 7
    asked = [(one.method, one.url.path) for one in github.requests if one.url.path.startswith(REPO)]
    assert asked == [("GET", f"{REPO}/installation"), ("GET", f"{REPO}/pulls")]


def test_meters_own_branch_for_the_fix_is_moved_to_the_new_commit() -> None:
    github = FakeGitHub()
    opening(github, branch_exists=True)
    existing_branch(github, "Remove unattached volume vol-0abc\n\nMeter-Reference: rec-41\n")
    assert github.host().open_pull_request(DRAFT, TARGET).number == 7
    assert github.sent("PATCH", f"{REPO}/git/refs/heads/{BRANCH}") == {
        "sha": COMMIT_SHA,
        "force": True,
    }


@pytest.mark.parametrize(
    "message",
    ["A person's own work on this branch", "Remove it\n\nMeter-Reference: rec-410\n"],
)
def test_a_branch_meter_did_not_write_for_this_fix_is_never_overwritten(message: str) -> None:
    github = FakeGitHub()
    opening(github, branch_exists=True)
    existing_branch(github, message)
    with pytest.raises(errors.Misconfigured, match="never overwrites a branch"):
        github.host().open_pull_request(DRAFT, TARGET)
    assert github.asked("PATCH", f"{REPO}/git/refs/heads/{BRANCH}") == []
    assert github.asked("POST", f"{REPO}/pulls") == []


def test_a_pull_request_opened_by_another_run_meanwhile_is_returned() -> None:
    github = FakeGitHub()
    opening(github)
    listed: list[list[dict[str, Any]]] = [[], [pull(9)]]
    github.answer("GET", f"{REPO}/pulls", lambda _r: httpx.Response(200, json=listed.pop(0)))
    github.on("POST", f"{REPO}/pulls", 422, {"message": "A pull request already exists"})
    assert github.host().open_pull_request(DRAFT, TARGET).number == 9


def test_a_pull_request_github_will_not_open_for_another_reason_is_drift() -> None:
    github = FakeGitHub()
    opening(github)
    github.on("POST", f"{REPO}/pulls", 422, {"message": "No commits between main and branch"})
    with pytest.raises(errors.SchemaDrift, match="No commits between"):
        github.host().open_pull_request(DRAFT, TARGET)


def test_a_pull_request_list_in_another_shape_is_drift() -> None:
    github = FakeGitHub()
    opening(github)
    github.on("GET", f"{REPO}/pulls", 200, {"items": []})
    with pytest.raises(errors.SchemaDrift, match="not a list"):
        github.host().open_pull_request(DRAFT, TARGET)


def test_a_base_branch_that_does_not_exist_is_misconfigured() -> None:
    github = FakeGitHub()
    opening(github)
    github.on("GET", f"{REPO}/git/ref/heads/main", 404, {"message": "Not Found"})
    with pytest.raises(errors.Misconfigured, match="no branch main in acme/infra"):
        github.host().open_pull_request(DRAFT, TARGET)


# -- reading a folder ------------------------------------------------------------


def encoded(text: str) -> str:
    """Base64 as the contents API sends it, wrapped at 60 characters."""
    flat = base64.b64encode(text.encode()).decode()
    return "\n".join(flat[i : i + 60] for i in range(0, len(flat), 60)) + "\n"


def contents(github: FakeGitHub, folder: str, files: dict[str, str], others: list[Any]) -> None:
    where = f"{REPO}/contents/{folder}" if folder else f"{REPO}/contents"
    prefix = f"{folder}/" if folder else ""
    listing = [
        {"type": "file", "name": name, "path": f"{prefix}{name}", "size": len(text)}
        for name, text in files.items()
    ]
    github.on("GET", where, 200, listing + others)
    for name, text in files.items():
        github.on(
            "GET",
            f"{REPO}/contents/{prefix}{name}",
            200,
            {"type": "file", "encoding": "base64", "content": encoded(text)},
        )


def test_a_folder_is_read_at_its_base_branch_its_own_terraform_only() -> None:
    github = FakeGitHub()
    volume = 'resource "aws_ebs_volume" "data" {\n  type = "gp2"\n  size = ' + "1" * 80 + "\n}\n"
    contents(
        github,
        "storage",
        {"volumes.tf": volume, "main.tf": "terraform {}\n", "README.md": "# Storage\n"},
        [{"type": "dir", "name": "modules.tf", "path": "storage/modules.tf"}],
    )
    found = github.host().read_folder(TARGET, ".tf")
    assert found == (
        RepositoryFile("storage/main.tf", "terraform {}\n"),
        RepositoryFile("storage/volumes.tf", volume),
    )
    reads = [one for one in github.requests if "/contents" in one.url.path]
    assert all(dict(one.url.params) == {"ref": "main"} for one in reads)


def test_the_root_folder_is_read_from_the_top_of_the_repository() -> None:
    github = FakeGitHub()
    contents(github, "", {"main.tf": "terraform {}\n"}, [])
    root = RepositoryTarget(REPOSITORY, "main", "")
    assert github.host().read_folder(root, ".tf") == (RepositoryFile("main.tf", "terraform {}\n"),)


def test_a_folder_that_is_not_there_or_is_a_file_is_misconfigured() -> None:
    github = FakeGitHub()
    with pytest.raises(errors.Misconfigured, match="no folder storage on main"):
        github.host().read_folder(TARGET, ".tf")
    github.on("GET", f"{REPO}/contents/storage", 200, {"type": "file", "name": "storage"})
    with pytest.raises(errors.Misconfigured, match="is a file, not a folder"):
        github.host().read_folder(TARGET, ".tf")


def test_a_file_the_contents_api_will_not_return_is_drift() -> None:
    github = FakeGitHub()
    contents(github, "storage", {"main.tf": "x"}, [])
    github.on("GET", f"{REPO}/contents/storage/main.tf", 200, {"encoding": "none", "content": ""})
    with pytest.raises(errors.SchemaDrift, match="up to a megabyte"):
        github.host().read_folder(TARGET, ".tf")


def test_a_file_that_is_not_text_is_drift() -> None:
    github = FakeGitHub()
    contents(github, "storage", {"main.tf": "x"}, [])
    binary = base64.b64encode(b"\xff\xfe\x00").decode()
    github.on(
        "GET", f"{REPO}/contents/storage/main.tf", 200, {"encoding": "base64", "content": binary}
    )
    with pytest.raises(errors.SchemaDrift, match="not text"):
        github.host().read_folder(TARGET, ".tf")


# -- following a pull request ----------------------------------------------------


@pytest.mark.parametrize(
    ("mergeable", "state", "readiness"),
    [
        (True, "clean", Readiness.READY),
        (True, "has_hooks", Readiness.READY),
        (False, "blocked", Readiness.WAITING),
        (True, "unstable", Readiness.BLOCKED),
        (False, "dirty", Readiness.BLOCKED),
        (False, "behind", Readiness.BLOCKED),
        (False, "draft", Readiness.BLOCKED),
        (None, "unknown", Readiness.UNKNOWN),
        (None, "clean", Readiness.UNKNOWN),
        (True, "a state GitHub adds later", Readiness.UNKNOWN),
    ],
)
def test_githubs_mergeable_state_is_the_rules_readiness(
    mergeable: bool | None, state: str, readiness: Readiness
) -> None:
    github = FakeGitHub()
    github.on("GET", f"{REPO}/pulls/7", 200, pull(7, mergeable=mergeable, mergeable_state=state))
    found = github.host().pull_request_state(REPOSITORY, 7)
    assert found.readiness is readiness
    assert (found.open, found.merged, found.head_sha, found.merged_by) == (
        True,
        False,
        "c" * 40,
        None,
    )


def test_a_merged_pull_request_says_who_merged_it() -> None:
    github = FakeGitHub()
    github.on(
        "GET",
        f"{REPO}/pulls/7",
        200,
        pull(7, state="closed", merged=True, merged_by={"login": "octocat"}, mergeable=None),
    )
    found = github.host().pull_request_state(REPOSITORY, 7)
    assert (found.open, found.merged, found.merged_by) == (False, True, "octocat")


def test_a_pull_request_that_does_not_exist_is_misconfigured() -> None:
    with pytest.raises(errors.Misconfigured, match="no pull request #7 in acme/infra"):
        FakeGitHub().host().pull_request_state(REPOSITORY, 7)


def test_a_pull_request_in_another_shape_is_drift() -> None:
    github = FakeGitHub()
    github.on("GET", f"{REPO}/pulls/7", 200, {"number": 7, "html_url": "x", "state": "open"})
    with pytest.raises(errors.SchemaDrift, match="no merged"):
        github.host().pull_request_state(REPOSITORY, 7)


# -- merging, ADR-0038 -----------------------------------------------------------

ALL_METHODS = {"allow_squash_merge": True, "allow_merge_commit": True, "allow_rebase_merge": True}


def merging(github: FakeGitHub, settings: dict[str, bool], status: int, answer: Any) -> None:
    github.on("GET", REPO, 200, {"full_name": REPOSITORY, **settings})
    github.on("PUT", f"{REPO}/pulls/7/merge", status, answer)


def test_a_merge_is_githubs_own_at_the_head_meter_read() -> None:
    github = FakeGitHub()
    merging(github, ALL_METHODS, 200, {"sha": "9" * 40, "merged": True, "message": "merged"})
    answer = github.host().merge_pull_request(REPOSITORY, 7, "c" * 40)
    assert (answer.merged, answer.sha) == (True, "9" * 40)
    assert github.sent("PUT", f"{REPO}/pulls/7/merge") == {
        "sha": "c" * 40,
        "merge_method": "squash",
    }


def test_the_merge_method_is_one_the_repository_allows() -> None:
    github = FakeGitHub()
    merging(
        github,
        {"allow_squash_merge": False, "allow_merge_commit": True},
        200,
        {"sha": "9" * 40, "merged": True},
    )
    github.host().merge_pull_request(REPOSITORY, 7, "c" * 40)
    assert github.sent("PUT", f"{REPO}/pulls/7/merge")["merge_method"] == "merge"


def test_a_repository_that_allows_no_merge_method_is_asked_nothing() -> None:
    github = FakeGitHub()
    merging(github, {}, 200, {})
    answer = github.host().merge_pull_request(REPOSITORY, 7, "c" * 40)
    assert (answer.merged, answer.reason) == (False, "The repository allows no merge method.")
    assert github.asked("PUT", f"{REPO}/pulls/7/merge") == []


@pytest.mark.parametrize(
    ("status", "message", "says"),
    [
        (405, 'Required status check "plan" is expected.', "GitHub refused the merge"),
        (422, "Pull Request is not mergeable", "GitHub refused the merge"),
        (409, "Head branch was modified. Review and try the merge again.", "head moved"),
    ],
)
def test_a_merge_github_refuses_is_an_answer_not_an_error(
    status: int, message: str, says: str
) -> None:
    github = FakeGitHub()
    merging(github, ALL_METHODS, status, {"message": message})
    answer = github.host().merge_pull_request(REPOSITORY, 7, "c" * 40)
    assert answer.merged is False
    assert says in answer.reason


def test_a_merge_the_app_may_not_make_raises_access_denied() -> None:
    github = FakeGitHub()
    merging(github, ALL_METHODS, 403, {"message": "Resource not accessible by integration"})
    with pytest.raises(errors.AccessDenied):
        github.host().merge_pull_request(REPOSITORY, 7, "c" * 40)


# -- first contact ---------------------------------------------------------------


def test_first_contact_lists_the_installations_repositories() -> None:
    github = FakeGitHub()
    github.on(
        "GET",
        "/installation/repositories",
        200,
        {
            "total_count": 2,
            "repositories": [{"full_name": "acme/network"}, {"full_name": REPOSITORY}],
        },
    )
    assert github.host().installation_repositories(REPOSITORY) == ("acme/infra", "acme/network")
