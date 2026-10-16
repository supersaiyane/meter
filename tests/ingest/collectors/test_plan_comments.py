"""Each estimate's one comment, and each pull request followed. TASK-P16-006, FEAT-096.

Against the strict fake code host. The head's estimate is written as the pull request's comment and
a newer commit's edits it; an older commit's, or one whose pull request merged first, is superseded
and says why; a refusal for good fails the comment with its cause, and a throttled host leaves it
waiting. Each pull request's state is kept, with when it was first seen merged.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core import errors
from finops_core.domain.fixes import PullRequestState, Readiness
from finops_fakes.pull_requests import RecordingPullRequests
from finops_ingest.collectors.plan_comments import COLLECTOR, PlanCommentsCollector
from finops_ingest.collectors.plan_estimates import PlanEstimatesCollector
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.plan_records import PlanTarget, record_plan
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.estimate_comment import marker
from finops_query.plan_reading import PlannedChange, ReducedPlan

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
REPOSITORY = "acme/infra"
FIRST = "abc1234def" + "0" * 30
SECOND = "fedcba9876" + "1" * 30
CHANGE = PlannedChange(
    address="aws_nat_gateway.out",
    resource_type="aws_nat_gateway",
    actions=("create",),
    region="eu-west-1",
    before={},
    after={},
)


def connected(engine: Engine, tenant: UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO code_host_connection (tenant_id, host, app_id, key_secret_name, "
                "connected_by) VALUES (:t, 'github', '1001', 'meter/test/codehost/app', 'owner')"
            ),
            {"t": tenant},
        )


def priced(engine: Engine, tenant: UUID, head: str) -> UUID:
    """A plan for `head`, recorded and priced, waiting for its comment."""
    target = PlanTarget(REPOSITORY, 7, head[:12], "storage")
    found = ReducedPlan("1.2", None, None, (CHANGE,))
    with engine.begin() as connection:
        plan_id = record_plan(connection, tenant, target, found, route="test", now=NOW)
    work = WorkUnit(tenant_id=tenant, collector="plan_estimates", window_start=NOW, window_end=NOW)
    with engine.begin() as connection:
        PlanEstimatesCollector(clock=lambda: NOW)(
            CollectorContext(unit=work, connection=connection, run_id=uuid4())
        )
    return plan_id


def state(head: str, *, open_: bool = True, merged: bool = False) -> PullRequestState:
    return PullRequestState(
        number=7,
        url=f"https://code.example/{REPOSITORY}/pull/7",
        open=open_,
        merged=merged,
        readiness=Readiness.WAITING,
        head_sha=head,
    )


def run(engine: Engine, tenant: UUID, host: Any, at: datetime = NOW) -> CollectorOutcome:
    work = WorkUnit(tenant_id=tenant, collector=COLLECTOR, window_start=at, window_end=at)
    collector = PlanCommentsCollector(lambda _context, _connected: host, clock=lambda: at)
    with engine.begin() as connection:
        return collector(CollectorContext(unit=work, connection=connection, run_id=uuid4()))


def comment_of(engine: Engine, plan_id: UUID) -> Any:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT * FROM plan_estimate WHERE plan_id = :p"), {"p": plan_id}
        ).one()


def pull_request(engine: Engine, tenant: UUID) -> Any:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT * FROM plan_pull_request WHERE tenant_id = :t"), {"t": tenant}
        ).one()


class Refusing(RecordingPullRequests):
    """A host that reports the pull request and refuses its comment with one typed cause."""

    def __init__(self, failure: Exception) -> None:
        super().__init__()
        self.failure = failure

    def write_comment(self, _repository: str, _number: int, _marker: str, _body: str) -> Any:
        raise self.failure


def test_the_heads_estimate_is_written_and_a_newer_commits_edits_the_same_comment(
    engine: Engine, tenant_id: UUID
) -> None:
    connected(engine, tenant_id)
    first = priced(engine, tenant_id, FIRST)
    host = RecordingPullRequests()
    host.set_state(REPOSITORY, state(FIRST))
    assert run(engine, tenant_id, host).items_written == 1
    written = comment_of(engine, first)
    assert (written.comment_status, written.comment_id) == ("WRITTEN", "1")
    assert written.comment_url.endswith("#issuecomment-1")
    (body,) = host.comments_on(REPOSITORY, 7)
    assert body.startswith(marker("storage"))
    assert "aws_nat_gateway is billed by use" in body
    followed = pull_request(engine, tenant_id)
    assert (followed.state, followed.head_sha, followed.merged_seen_at) == ("OPEN", FIRST, None)
    second = priced(engine, tenant_id, SECOND)
    host.set_state(REPOSITORY, state(SECOND))
    run(engine, tenant_id, host)
    assert comment_of(engine, second).comment_id == "1"
    (edited,) = host.comments_on(REPOSITORY, 7)
    assert f"`{SECOND[:12]}`" in edited


def test_an_older_commits_estimate_is_superseded_and_says_why(
    engine: Engine, tenant_id: UUID
) -> None:
    connected(engine, tenant_id)
    old = priced(engine, tenant_id, FIRST)
    host = RecordingPullRequests()
    host.set_state(REPOSITORY, state(SECOND))
    run(engine, tenant_id, host)
    found = comment_of(engine, old)
    assert found.comment_status == "SUPERSEDED"
    assert found.comment_reason == f"the pull request's head moved to {SECOND[:12]} first"
    assert host.comments_on(REPOSITORY, 7) == ()


def test_a_merge_is_kept_with_when_it_was_first_seen(engine: Engine, tenant_id: UUID) -> None:
    connected(engine, tenant_id)
    plan_id = priced(engine, tenant_id, FIRST)
    host = RecordingPullRequests()
    host.set_state(REPOSITORY, state(FIRST, open_=False, merged=True))
    run(engine, tenant_id, host)
    assert comment_of(engine, plan_id).comment_reason == "the pull request merged first"
    seen = pull_request(engine, tenant_id)
    assert (seen.state, seen.merged_seen_at) == ("MERGED", NOW)


def test_an_open_pull_request_is_followed_until_it_merges(engine: Engine, tenant_id: UUID) -> None:
    connected(engine, tenant_id)
    priced(engine, tenant_id, FIRST)
    host = RecordingPullRequests()
    host.set_state(REPOSITORY, state(FIRST))
    run(engine, tenant_id, host)
    host.set_state(REPOSITORY, state(FIRST, open_=False, merged=True))
    later = NOW + timedelta(hours=2)
    run(engine, tenant_id, host, at=later)
    run(engine, tenant_id, host, at=later + timedelta(hours=1))
    seen = pull_request(engine, tenant_id)
    assert (seen.state, seen.merged_seen_at) == ("MERGED", later)


def test_a_refusal_for_good_fails_the_comment_with_its_cause(
    engine: Engine, tenant_id: UUID
) -> None:
    connected(engine, tenant_id)
    plan_id = priced(engine, tenant_id, FIRST)
    refused = errors.AccessDenied(scope_key="github", collector=COLLECTOR, detail="no write")
    host = Refusing(refused)
    host.set_state(REPOSITORY, state(FIRST))
    run(engine, tenant_id, host)
    found = comment_of(engine, plan_id)
    assert (found.comment_status, found.comment_failure_cause) == ("FAILED", "AccessDenied")
    assert "no write" in found.comment_reason


def test_a_pull_request_that_is_not_there_fails_its_estimates(
    engine: Engine, tenant_id: UUID
) -> None:
    connected(engine, tenant_id)
    plan_id = priced(engine, tenant_id, FIRST)
    run(engine, tenant_id, RecordingPullRequests())
    found = comment_of(engine, plan_id)
    assert (found.comment_status, found.comment_failure_cause) == ("FAILED", "Misconfigured")


def test_a_throttled_host_leaves_the_comment_waiting(engine: Engine, tenant_id: UUID) -> None:
    connected(engine, tenant_id)
    plan_id = priced(engine, tenant_id, FIRST)
    host = Refusing(errors.Throttled(scope_key="github", collector=COLLECTOR, detail="limit"))
    host.set_state(REPOSITORY, state(FIRST))
    assert run(engine, tenant_id, host).items_written == 0
    assert comment_of(engine, plan_id).comment_status is None


def test_with_no_code_host_connected_the_waiting_comments_are_refused_by_name(
    engine: Engine, tenant_id: UUID
) -> None:
    priced(engine, tenant_id, FIRST)
    with pytest.raises(errors.Misconfigured, match="1 estimate\\(s\\) wait for a comment"):
        run(engine, tenant_id, RecordingPullRequests())


def test_with_nothing_waiting_or_open_nothing_is_asked(engine: Engine, tenant_id: UUID) -> None:
    assert run(engine, tenant_id, RecordingPullRequests()).items_written == 0
