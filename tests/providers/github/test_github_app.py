"""Meter's GitHub App: its token, the installation token, and every failure typed. TASK-P15-002.

FEAT-091, OPEN-13, spec sections 5.1 and 9. A token is minted for each request, for the one
repository and what the request needs, and no detail ever carries a token or the key.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import jwt
import pytest

from finops_core import errors
from finops_providers.github.app import METADATA, READ, WRITE, app_token
from tests.providers.github.fake import (
    APP_ID,
    INSTALLATION,
    NOW,
    REPO,
    REPOSITORY,
    TOKEN,
    FakeGitHub,
    private_key,
    private_key_pem,
)

TOKENS = f"/app/installations/{INSTALLATION}/access_tokens"


def ask(github: FakeGitHub, permissions: Any = READ, **options: Any) -> Any:
    """Open a session and make one read in it, as every adapter request does."""
    with github.app().session(REPOSITORY, permissions, **options) as (session, repo):
        return session.json("GET", repo.path)


def body(request: httpx.Request) -> Any:
    return json.loads(request.content)


def test_the_app_token_names_the_app_and_lasts_ten_minutes_from_a_minute_ago() -> None:
    token = app_token(APP_ID, private_key_pem(), NOW)
    claims = jwt.decode(
        token,
        private_key().public_key(),
        algorithms=["RS256"],
        options={"verify_exp": False, "verify_iat": False},
    )
    issued = int(NOW.timestamp()) - 60
    assert claims == {"iat": issued, "exp": issued + 600, "iss": APP_ID}
    assert jwt.get_unverified_header(token)["alg"] == "RS256"


def test_a_token_is_minted_for_each_request_for_one_repository_and_what_it_needs() -> None:
    github = FakeGitHub()
    github.on("GET", REPO, 200, {"full_name": REPOSITORY})
    ask(github, READ)
    ask(github, WRITE)
    minted = [body(one) for one in github.asked("POST", TOKENS)]
    assert [one["permissions"] for one in minted] == [dict(READ), dict(WRITE)]
    assert all(one["repositories"] == ["infra"] for one in minted)
    # The app's own token finds the installation; the installation token makes the read.
    found = github.asked("GET", f"{REPO}/installation")
    assert all(one.headers["authorization"].startswith("Bearer ey") for one in found)
    assert all(
        one.headers["authorization"] == f"Bearer {TOKEN}" for one in github.asked("GET", REPO)
    )


def test_first_contact_asks_for_metadata_across_the_installation() -> None:
    github = FakeGitHub()
    github.on("GET", REPO, 200, {"full_name": REPOSITORY})
    ask(github, METADATA, narrowed=False)
    assert github.sent("POST", TOKENS) == {"permissions": {"metadata": "read"}}


@pytest.mark.parametrize(
    ("status", "answer", "headers", "cause", "says"),
    [
        (401, {"message": "A JSON web token could not be decoded"}, {}, errors.AccessDenied,
         "refused the app's credential"),
        (403, {"message": "API rate limit exceeded"}, {"x-ratelimit-remaining": "0"},
         errors.Throttled, "rate limit is spent"),
        (403, {"message": "You have exceeded a secondary rate limit."}, {}, errors.Throttled,
         "rate limit is spent"),
        (429, {"message": "Too many requests"}, {}, errors.Throttled, "rate limit is spent"),
        (403, {"message": "Resource not accessible by integration"}, {}, errors.AccessDenied,
         "Contents and Pull requests"),
        (404, {"message": "Not Found"}, {}, errors.Misconfigured,
         "not installed on acme/infra"),
        (502, "<html>Bad gateway</html>", {}, errors.Unreachable, "HTTP 502"),
        (418, {"message": "I'm a teapot"}, {}, errors.SchemaDrift, "teapot"),
    ],
)  # fmt: skip
def test_every_answer_github_refuses_with_is_typed(
    status: int, answer: Any, headers: dict[str, str], cause: type[Exception], says: str
) -> None:
    github = FakeGitHub()
    github.on("GET", f"{REPO}/installation", status, answer, headers)
    with pytest.raises(cause, match=says) as raised:
        ask(github)
    assert isinstance(raised.value, errors.CollectionError)
    assert raised.value.scope_key == f"github:{REPOSITORY}"
    assert raised.value.collector == "fix_pull_requests"


def test_nothing_github_says_about_a_refused_credential_is_kept() -> None:
    github = FakeGitHub()
    github.on("GET", f"{REPO}/installation", 401, {"message": f"Bad credentials {TOKEN}"})
    with pytest.raises(errors.AccessDenied) as raised:
        ask(github)
    assert "Bad credentials" not in raised.value.detail


def test_a_token_github_echoes_in_an_error_never_reaches_a_detail() -> None:
    github = FakeGitHub()
    github.on("GET", REPO, 500, {"message": f"upstream failed for token {TOKEN}"})
    with pytest.raises(errors.Unreachable) as raised:
        ask(github)
    assert TOKEN not in raised.value.detail
    assert "[redacted]" in raised.value.detail


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("slow"), httpx.ConnectError("refused")])
def test_a_github_that_does_not_answer_is_unreachable(failure: Exception) -> None:
    github = FakeGitHub()

    def silent(_request: httpx.Request) -> httpx.Response:
        raise failure

    github.answer("GET", f"{REPO}/installation", silent)
    with pytest.raises(errors.Unreachable):
        ask(github)


def test_a_secret_that_is_not_a_private_key_is_misconfigured_and_never_quoted() -> None:
    github = FakeGitHub()
    app = github.app(key=lambda: "not-a-key-but-a-secret-value")
    with pytest.raises(errors.Misconfigured, match="PEM") as raised, app.session(REPOSITORY, READ):
        pass
    assert "secret-value" not in raised.value.detail
    assert github.requests == []


def test_permissions_the_app_was_not_granted_say_where_to_grant_them() -> None:
    github = FakeGitHub()
    github.on(
        "POST",
        TOKENS,
        422,
        {"message": "The permissions requested are not granted to this installation."},
    )
    with pytest.raises(errors.Misconfigured, match="would not grant contents write"):
        ask(github, WRITE)


def test_a_repository_not_written_owner_slash_name_is_refused_before_any_call() -> None:
    github = FakeGitHub()
    with (
        pytest.raises(errors.Misconfigured, match="owner/name"),
        github.app().session("infra", READ),
    ):
        pass
    assert github.requests == []


@pytest.mark.parametrize(
    ("route", "answer", "says"),
    [
        (f"{REPO}/installation", {"account": {"login": "acme"}}, "no id"),
        (REPO, "<html>maintenance</html>", "not JSON"),
    ],
)
def test_an_answer_not_in_the_recorded_shape_is_drift(route: str, answer: Any, says: str) -> None:
    github = FakeGitHub()
    github.on("GET", REPO, 200, {"full_name": REPOSITORY})
    github.on("GET", route, 200, answer)
    with pytest.raises(errors.SchemaDrift, match=says):
        ask(github)
