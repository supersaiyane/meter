"""The estimate's comment on GitHub, written once and edited after. TASK-P16-006, FEAT-096.

Against GitHub's REST shapes, API version 2022-11-28, trimmed from its published examples for the
issue comments endpoints. Meter's comment is the one an app wrote that opens with the marker; a
person quoting the marker is never edited. The comments are read a page at a time.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from finops_core import errors
from finops_core.ports.pull_requests import PostedComment, PullRequestCommenter
from finops_fakes.pull_requests import RecordingPullRequests
from tests.providers.github.fake import REPO, REPOSITORY, FakeGitHub

MARKER = "<!-- meter:estimate folder=storage -->"
BODY = f"{MARKER}\n### Meter: what this change costs a month, `storage`\n"
COMMENTS = f"{REPO}/issues/7/comments"


def comment(comment_id: int, body: str, kind: str = "Bot") -> dict[str, Any]:
    """An issue comment as GET .../issues/{number}/comments lists it, trimmed."""
    return {
        "id": comment_id,
        "body": body,
        "html_url": f"https://github.com/{REPOSITORY}/pull/7#issuecomment-{comment_id}",
        "user": {"login": "meter-app[bot]" if kind == "Bot" else "octocat", "type": kind},
    }


def test_the_adapter_and_the_fake_are_both_commenters() -> None:
    assert isinstance(FakeGitHub().host(), PullRequestCommenter)
    assert isinstance(RecordingPullRequests(), PullRequestCommenter)


def test_with_no_comment_of_its_own_meter_writes_one() -> None:
    github = FakeGitHub()
    github.on("GET", COMMENTS, 200, [comment(1, "Looks good", "User")])
    github.on("POST", COMMENTS, 201, comment(99, BODY))
    found = github.host().write_comment(REPOSITORY, 7, MARKER, BODY)
    assert found == PostedComment(
        comment_id="99", url=f"https://github.com/{REPOSITORY}/pull/7#issuecomment-99"
    )
    assert github.sent("POST", COMMENTS) == {"body": BODY}
    (asked,) = github.asked("GET", COMMENTS)
    assert asked.url.params["per_page"] == "100"


def test_its_own_comment_is_edited_in_place_and_a_quoting_person_is_left_alone() -> None:
    github = FakeGitHub()
    quoted = comment(5, f"{MARKER} why is this so expensive?", "User")
    later = comment(6, f"> {MARKER}\nquoted")
    github.on("GET", COMMENTS, 200, [quoted, later, comment(8, f"{MARKER}\nold figures")])
    github.on("PATCH", f"{REPO}/issues/comments/8", 200, comment(8, BODY))
    found = github.host().write_comment(REPOSITORY, 7, MARKER, BODY)
    assert found.comment_id == "8"
    assert github.sent("PATCH", f"{REPO}/issues/comments/8") == {"body": BODY}
    assert github.asked("POST", COMMENTS) == []


def test_the_comments_are_read_a_page_at_a_time_until_its_own_is_found() -> None:
    github = FakeGitHub()

    def paged(request: httpx.Request) -> httpx.Response:
        if request.url.params["page"] == "1":
            return httpx.Response(200, json=[comment(n, "chatter", "User") for n in range(100)])
        return httpx.Response(200, json=[comment(300, f"{MARKER}\nold")])

    github.answer("GET", COMMENTS, paged)
    github.on("PATCH", f"{REPO}/issues/comments/300", 200, comment(300, BODY))
    assert github.host().write_comment(REPOSITORY, 7, MARKER, BODY).comment_id == "300"
    assert [one.url.params["page"] for one in github.asked("GET", COMMENTS)] == ["1", "2"]


def test_a_pull_request_with_more_comments_than_meter_reads_is_refused() -> None:
    github = FakeGitHub()
    github.on("GET", COMMENTS, 200, [comment(n, "chatter", "User") for n in range(100)])
    with pytest.raises(errors.Misconfigured, match="more than 3000 comments"):
        github.host().write_comment(REPOSITORY, 7, MARKER, BODY)


def test_a_missing_pull_request_is_misconfigured_and_another_shape_is_drift() -> None:
    with pytest.raises(errors.Misconfigured, match="no pull request #7 in acme/infra"):
        FakeGitHub().host().write_comment(REPOSITORY, 7, MARKER, BODY)
    github = FakeGitHub()
    github.on("GET", COMMENTS, 200, {"comments": []})
    with pytest.raises(errors.SchemaDrift, match="not a list"):
        github.host().write_comment(REPOSITORY, 7, MARKER, BODY)


def test_the_token_is_asked_for_pull_requests_write_alone() -> None:
    github = FakeGitHub()
    github.on("GET", COMMENTS, 200, [])
    github.on("POST", COMMENTS, 201, comment(1, BODY))
    github.host().write_comment(REPOSITORY, 7, MARKER, BODY)
    asked = github.sent("POST", "/app/installations/4242/access_tokens")
    assert asked["permissions"] == {"pull_requests": "write"}
