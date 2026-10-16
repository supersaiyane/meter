"""Each estimate's one comment on its pull request, and each pull request followed. FEAT-096.

TASK-P16-006, P16 spec sections 5.5 and 7, OPEN-45. Every ten minutes, in the worker, the one
process that reaches the internet, ADR-0036. For each pull request with an estimate waiting, and
each one still open, the code host is asked its state, which is kept in `plan_pull_request` with
when Meter first saw it merged, for the comparison with the bill, TASK-P16-007.

**The comment is the head's.** An estimate whose commit is the pull request's head is written as the
pull request's one comment for its folder, found again by its marker and edited in place. One whose
commit is no longer the head, or whose pull request merged or closed first, is `SUPERSEDED` and says
why, so an older commit's plan never overwrites a newer one's figures.

**A failure is typed and kept apart.** A refusal the host will give again, access, a pull request
that is not there, an answer in another shape, fails that estimate's comment with its cause. A
throttled or silent host stops the run with what it did, and the next run asks again: raising would
roll back every comment already recorded. Writing an estimate never waits on this collector,
TASK-P16-005, so a host that is down holds back only the comment.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text

from finops_core.domain.fixes import PullRequestState
from finops_core.errors import Misconfigured
from finops_core.ports.pull_requests import PullRequestCommenter, PullRequestTracker
from finops_ingest.collectors.fix_pull_requests import CONNECTED, FOR_GOOD, FOR_NOW, Connected
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.estimate_comment import CommentedEstimate, CommentLine, marker, render

COLLECTOR = "plan_comments"


class CommentHost(PullRequestTracker, PullRequestCommenter, Protocol):
    """What the collector asks of a code host: a pull request's state, and its comment."""


#: The code host for a tenant's connection, built for this run.
CommentHostFor = Callable[[CollectorContext, Connected], CommentHost]
Clock = Callable[[], datetime]

WAITING = text(
    "SELECT e.plan_id, e.monthly_before, e.monthly_after, e.monthly_change, e.priced_at, "
    "p.repository, p.pull_request, p.head_sha, p.folder FROM plan_estimate e "
    "JOIN terraform_plan p ON p.plan_id = e.plan_id "
    "WHERE e.tenant_id = :t AND e.comment_status IS NULL ORDER BY p.received_at, e.plan_id"
)
FOLLOWED = text(
    "SELECT repository, pull_request FROM plan_pull_request WHERE tenant_id = :t "
    "AND state = 'OPEN' ORDER BY repository, pull_request"
)
LINES = text(
    "SELECT address, actions, monthly_before, monthly_after, reason, notes, components "
    "FROM plan_estimate_line WHERE plan_id = :plan ORDER BY address"
)
SEEN = text(
    "INSERT INTO plan_pull_request (tenant_id, repository, pull_request, state, head_sha, "
    "merged_seen_at, as_of, collected_at) VALUES (:t, :repo, :number, :state, :head, :merged, "
    ":now, :now) ON CONFLICT (tenant_id, repository, pull_request) DO UPDATE SET "
    "state = EXCLUDED.state, head_sha = EXCLUDED.head_sha, "
    "merged_seen_at = coalesce(plan_pull_request.merged_seen_at, EXCLUDED.merged_seen_at), "
    "as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
)
WRITTEN = text(
    "UPDATE plan_estimate SET comment_status = 'WRITTEN', comment_id = :id, comment_url = :url, "
    "commented_at = :now WHERE plan_id = :plan"
)
UNWRITTEN = text(
    "UPDATE plan_estimate SET comment_status = :status, comment_reason = :reason, "
    "comment_failure_cause = :cause WHERE plan_id = :plan"
)


class PlanCommentsCollector:
    """Writes the head's estimate as its pull request's comment, and follows each pull request."""

    def __init__(self, code_host_for: CommentHostFor, *, clock: Clock | None = None) -> None:
        self._code_host_for = code_host_for
        self._clock = clock or (lambda: datetime.now(UTC))

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        connection, tenant = context.connection, context.unit.tenant_id
        waiting = connection.execute(WAITING, {"t": tenant}).all()
        followed = connection.execute(FOLLOWED, {"t": tenant}).all()
        pulls = list(
            dict.fromkeys(
                [(row.repository, row.pull_request) for row in waiting]
                + [(row.repository, row.pull_request) for row in followed]
            )
        )
        if not pulls:
            return CollectorOutcome()
        connected = connection.execute(CONNECTED, {"tenant": tenant}).first()
        if connected is None:
            raise Misconfigured(
                scope_key=context.unit.scope_key,
                collector=COLLECTOR,
                detail=f"{len(waiting)} estimate(s) wait for a comment and no code host is "
                "connected; connect the GitHub App, PUT /v1/remediation/connection, "
                "docs/runbooks/code-host.md",
            )
        host = self._code_host_for(
            context, Connected(str(connected.app_id), str(connected.key_secret_name))
        )
        moved = 0
        for pull in pulls:
            plans = [row for row in waiting if (row.repository, row.pull_request) == pull]
            done = self._pull_request(connection, tenant, host, pull, plans)
            if done is None:
                break
            moved += done
        return CollectorOutcome(items_written=moved)

    def _pull_request(
        self,
        connection: Any,
        tenant: UUID,
        host: CommentHost,
        pull: tuple[str, int],
        plans: list[Any],
    ) -> int | None:
        """One pull request's state kept and its waiting estimates moved; None to stop the run."""
        repository, number = pull
        try:
            state = host.pull_request_state(repository, number)
        except FOR_NOW:
            return None
        except FOR_GOOD as failure:
            for plan in plans:
                _unwritten(connection, plan, "FAILED", str(failure), type(failure).__name__)
            return len(plans)
        now = self._clock()
        connection.execute(
            SEEN,
            {
                "t": tenant,
                "repo": repository,
                "number": number,
                "state": _state(state),
                "head": state.head_sha,
                "merged": now if state.merged else None,
                "now": now,
            },
        )
        moved = 0
        for plan in plans:
            with connection.begin_nested():
                done = self._comment(connection, host, plan, state)
            if not done:
                return None
            moved += 1
        return moved

    def _comment(
        self, connection: Any, host: CommentHost, plan: Any, state: PullRequestState
    ) -> bool:
        """One estimate written as the comment, superseded, or failed; False to stop the run."""
        if not state.open:
            how = "merged" if state.merged else "closed"
            _unwritten(connection, plan, "SUPERSEDED", f"the pull request {how} first", None)
            return True
        if not _same(plan.head_sha, state.head_sha):
            reason = f"the pull request's head moved to {state.head_sha[:12]} first"
            _unwritten(connection, plan, "SUPERSEDED", reason, None)
            return True
        body = render(_commented(connection, plan))
        try:
            posted = host.write_comment(
                plan.repository, plan.pull_request, marker(plan.folder), body
            )
        except FOR_NOW:
            return False
        except FOR_GOOD as failure:
            _unwritten(connection, plan, "FAILED", str(failure), type(failure).__name__)
            return True
        connection.execute(
            WRITTEN,
            {
                "id": posted.comment_id,
                "url": posted.url,
                "now": self._clock(),
                "plan": plan.plan_id,
            },
        )
        return True


def _state(state: PullRequestState) -> str:
    if state.merged:
        return "MERGED"
    return "OPEN" if state.open else "CLOSED"


def _same(planned: str, head: str) -> bool:
    """Whether a plan's commit is the head, either written short."""
    return head.startswith(planned) or planned.startswith(head)


def _unwritten(connection: Any, plan: Any, status: str, reason: str, cause: str | None) -> None:
    connection.execute(
        UNWRITTEN, {"status": status, "reason": reason, "cause": cause, "plan": plan.plan_id}
    )


def _commented(connection: Any, plan: Any) -> CommentedEstimate:
    rows = connection.execute(LINES, {"plan": plan.plan_id}).all()
    versions = {
        str(part["version"]) for row in rows for part in row.components if part.get("version")
    }
    return CommentedEstimate(
        folder=plan.folder,
        head_sha=plan.head_sha,
        monthly_before=plan.monthly_before,
        monthly_after=plan.monthly_after,
        monthly_change=plan.monthly_change,
        lines=tuple(
            CommentLine(
                address=row.address,
                actions=tuple(row.actions),
                monthly_before=row.monthly_before,
                monthly_after=row.monthly_after,
                reason=row.reason,
                notes=tuple(row.notes),
            )
            for row in rows
        ),
        versions=tuple(sorted(versions)),
        priced_at=plan.priced_at,
    )
