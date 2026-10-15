"""Opening each fix a person asked for, as a pull request. FEAT-092 and FEAT-040, TASK-P15-004.

P15 spec sections 5.3, 5.5 and 7. The API records an ask; this collector, in the worker, the one
process that reaches the internet, ADR-0036, acts on it every ten minutes. For each fix requested
it reads the recommendation, what FEAT-057 knows of the Terraform behind its resource, and the
repository the tenant mapped that state to, and asks `finops_query.remediation.propose` to author
the change and open it. It is the first caller `propose` has had, ISS-228. A gp2 volume is an
edit instead, TASK-P15-005: the mapped folder's `.tf` files are read and the block that declares it
is changed, `finops_query.gp3_edit`.

**Every fix is its own step.** Each is moved inside a savepoint, so one that fails leaves every
other as it was. A fix that cannot be authored, or whose state has no repository mapped, is
`NOT_AUTHORED` with the sentence why. One the code host refuses for good, an access or a
configuration it will refuse again, is `FAILED` with its typed cause. One it throttles, or that it
does not answer, stays `REQUESTED` with the wait recorded as a step, and the run stops asking and
ends with what it did: raising would roll back every fix it had already moved, and the next run
asks again.

**Opened is not done.** A recommendation whose pull request opens moves from ACCEPTED to
IN_PROGRESS, logged as this collector's move, spec section 5.6; following it to merged and to DONE
is TASK-P15-006.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Protocol
from uuid import UUID, uuid4

from sqlalchemy import text

from finops_core.domain.waste import Lifecycle, WasteClass
from finops_core.errors import AccessDenied, Misconfigured, SchemaDrift, Throttled, Unreachable
from finops_core.ports.pull_requests import PullRequestSink, RepositoryReader, RepositoryTarget
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.gp3_edit import Gp3Figures, author_gp3, edit_volume
from finops_query.remediation import (
    Management,
    NotAuthored,
    Proposed,
    RecommendationFacts,
    author,
    propose,
)

COLLECTOR = "fix_pull_requests"
#: The principal on Meter's own steps, as the event log names it.
METER: Final = "meter"
#: The causes the code host will give again for the same fix, so the fix fails rather than waits.
FOR_GOOD: Final = (AccessDenied, Misconfigured, SchemaDrift)
#: The causes the next run may not meet, so the fix waits and the run stops asking.
FOR_NOW: Final = (Throttled, Unreachable)

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class Connected:
    """The GitHub App a tenant connected: its id and its key's secret name."""

    app_id: str
    key_secret_name: str


class CodeHost(PullRequestSink, RepositoryReader, Protocol):
    """What the collector asks of a code host: open a pull request, and read a folder."""


#: The code host for a tenant's connection, built for this run.
CodeHostFor = Callable[[CollectorContext, Connected], CodeHost]

CONNECTED = text(
    "SELECT app_id, key_secret_name FROM code_host_connection WHERE tenant_id = :tenant"
)

REQUESTED = text(
    "SELECT f.fix_id, f.recommendation_id, f.sub_account_id, r.lifecycle, r.waste_class, "
    "r.resource_id, r.region_id, r.estimated_monthly_saving, r.confidence, r.rationale, r.as_of, "
    "r.target_iops, r.target_throughput_mibps "
    "FROM fix_pull_request f JOIN recommendation r "
    "ON r.recommendation_id = f.recommendation_id AND r.tenant_id = f.tenant_id "
    "WHERE f.tenant_id = :tenant AND f.status = 'REQUESTED' "
    "ORDER BY f.requested_at, f.fix_id FOR UPDATE OF f SKIP LOCKED"
)

MANAGED = text(
    "SELECT address, state_reference FROM resource_management "
    "WHERE tenant_id = :tenant AND sub_account_id = :account AND provider_id = :resource "
    "ORDER BY collected_at DESC, address LIMIT 1"
)

MAPPED = text(
    "SELECT repository, base_branch, folder FROM repository_mapping "
    "WHERE tenant_id = :tenant AND state_reference = :state"
)

SET_STATUS = text(
    "UPDATE fix_pull_request SET status = :to, repository = :repository, branch = :branch, "
    "number = :number, url = :url, reason = :reason, failure_cause = :cause, as_of = :now, "
    "collected_at = :now WHERE fix_id = :fix"
)

STEP = text(
    "INSERT INTO fix_pull_request_event (event_id, fix_id, tenant_id, sub_account_id, "
    "from_status, to_status, principal, note, at) "
    "VALUES (:event, :fix, :tenant, :account, :from, :to, :principal, :note, :now)"
)

MOVE = text(
    "UPDATE recommendation SET lifecycle = :to, collected_at = :now "
    "WHERE tenant_id = :tenant AND recommendation_id = :id AND lifecycle = :from"
)

#: The same append only log the routes write to; the actor is this collector, not a person.
RECOMMENDATION_EVENT = text(
    "INSERT INTO recommendation_event (event_id, recommendation_id, tenant_id, "
    "from_lifecycle, to_lifecycle, actor, reason, occurred_at, as_of, collected_at) "
    "VALUES (:event, :id, :tenant, :from, :to, :actor, :reason, :now, :now, :now)"
)


@dataclass(frozen=True)
class _Moved:
    """Where one fix ended this run, for the row, its step and the recommendation."""

    status: str
    note: str
    repository: str | None = None
    branch: str | None = None
    number: int | None = None
    url: str | None = None
    reason: str | None = None
    cause: str | None = None


class FixPullRequestsCollector:
    """Opens each requested fix in the repository its state is mapped to, or says why not."""

    def __init__(self, code_host_for: CodeHostFor, *, clock: Clock | None = None) -> None:
        self._code_host_for = code_host_for
        self._clock = clock or (lambda: datetime.now(UTC))

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        connection, tenant = context.connection, context.unit.tenant_id
        requested = connection.execute(REQUESTED, {"tenant": tenant}).all()
        if not requested:
            return CollectorOutcome()
        connected = connection.execute(CONNECTED, {"tenant": tenant}).first()
        if connected is None:
            # Nothing is written, so every ask waits for a connection, and connecting opens them.
            raise Misconfigured(
                scope_key=context.unit.scope_key,
                collector=COLLECTOR,
                detail=f"{len(requested)} fix(es) asked for and no code host is connected; "
                "connect the GitHub App, PUT /v1/remediation/connection, "
                "docs/runbooks/code-host.md",
            )
        host = self._code_host_for(
            context, Connected(str(connected.app_id), str(connected.key_secret_name))
        )
        moved = 0
        for fix in requested:
            with connection.begin_nested():
                outcome = self._open(connection, tenant, fix, host)
                self._record(connection, tenant, fix, outcome)
            moved += 1
            if outcome.status == "REQUESTED":
                # Throttled or not answering: asking again this run only spends the limit.
                break
        return CollectorOutcome(items_written=moved)

    def _open(self, connection: Any, tenant: UUID, fix: Any, host: CodeHost) -> _Moved:
        lifecycle = Lifecycle(fix.lifecycle)
        if lifecycle not in (Lifecycle.ACCEPTED, Lifecycle.IN_PROGRESS):
            return _not_authored(
                f"The recommendation is {lifecycle.value} now, so no pull request was opened."
            )
        facts = RecommendationFacts(
            recommendation_id=str(fix.recommendation_id),
            waste_class=WasteClass(fix.waste_class),
            resource_id=str(fix.resource_id),
            sub_account_id=str(fix.sub_account_id),
            region_id=str(fix.region_id),
            estimated_monthly_saving=fix.estimated_monthly_saving,
            confidence=str(fix.confidence),
            rationale=str(fix.rationale),
            as_of=fix.as_of,
        )
        managed = connection.execute(
            MANAGED,
            {"tenant": tenant, "account": fix.sub_account_id, "resource": fix.resource_id},
        ).first()
        management = (
            None if managed is None else Management(managed.address, managed.state_reference)
        )
        if management is None:
            # `propose` says why a resource Terraform does not manage has no file to change.
            return _not_authored(_refusal(facts))
        target = _target(connection, tenant, management)
        if isinstance(target, NotAuthored):
            return _not_authored(target.reason)
        try:
            if facts.waste_class is WasteClass.EBS_GP2_TO_GP3:
                proposed = _propose_gp3(facts, management, fix, host, target)
            else:
                proposed = propose(facts, management, None, host, target)
        except FOR_GOOD as failure:
            return _Moved("FAILED", failure.detail, reason=failure.detail, cause=failure.cause)
        except FOR_NOW as failure:
            return _Moved("REQUESTED", f"{failure.cause}, asking again next run: {failure.detail}")
        if isinstance(proposed, NotAuthored):
            return _not_authored(proposed.reason)
        opened = proposed.pull_request
        return _Moved(
            "OPEN",
            f"Opened #{opened.number}, {opened.url}",
            repository=target.repository,
            branch=proposed.draft.branch,
            number=opened.number,
            url=opened.url,
        )

    def _record(self, connection: Any, tenant: UUID, fix: Any, moved: _Moved) -> None:
        now = self._clock()
        if moved.status != "REQUESTED":
            connection.execute(
                SET_STATUS,
                {
                    "to": moved.status,
                    "repository": moved.repository,
                    "branch": moved.branch,
                    "number": moved.number,
                    "url": moved.url,
                    "reason": moved.reason,
                    "cause": moved.cause,
                    "now": now,
                    "fix": fix.fix_id,
                },
            )
        connection.execute(
            STEP,
            {
                "event": uuid4(),
                "fix": fix.fix_id,
                "tenant": tenant,
                "account": fix.sub_account_id,
                "from": "REQUESTED",
                "to": moved.status,
                "principal": METER,
                "note": moved.note,
                "now": now,
            },
        )
        if moved.status == "OPEN" and fix.lifecycle == Lifecycle.ACCEPTED.value:
            _in_progress(connection, tenant, fix, moved, now)


def _propose_gp3(
    facts: RecommendationFacts,
    management: Management,
    fix: Any,
    host: CodeHost,
    target: RepositoryTarget,
) -> Proposed | NotAuthored:
    """FEAT-093: the block that declares the volume, edited in the mapped folder, and opened."""
    files = host.read_folder(target, ".tf")
    figures = Gp3Figures(fix.target_iops, fix.target_throughput_mibps)
    edited = edit_volume(files, management.address, figures)
    if isinstance(edited, NotAuthored):
        return edited
    draft = author_gp3(facts, management.address, edited)
    return Proposed(draft=draft, pull_request=host.open_pull_request(draft, target))


def _target(
    connection: Any, tenant: UUID, management: Management
) -> RepositoryTarget | NotAuthored:
    """Where the fix goes: the repository the tenant mapped the resource's state to."""
    mapped = connection.execute(
        MAPPED, {"tenant": tenant, "state": management.state_reference}
    ).first()
    if mapped is None:
        return NotAuthored(
            reason=f"No repository is mapped for the state {management.state_reference}, so the "
            "fix has nowhere to go. Map it in the remediation settings, "
            "PUT /v1/remediation/repositories."
        )
    return RepositoryTarget(str(mapped.repository), str(mapped.base_branch), str(mapped.folder))


def _refusal(facts: RecommendationFacts) -> str:
    """`propose`'s own sentence for a resource no Terraform address manages."""
    refused = author(facts, None, None)
    assert isinstance(refused, NotAuthored)
    return refused.reason


def _in_progress(connection: Any, tenant: UUID, fix: Any, moved: _Moved, now: datetime) -> None:
    changed = connection.execute(
        MOVE,
        {
            "to": Lifecycle.IN_PROGRESS.value,
            "now": now,
            "tenant": tenant,
            "id": fix.recommendation_id,
            "from": Lifecycle.ACCEPTED.value,
        },
    ).rowcount
    if changed:
        connection.execute(
            RECOMMENDATION_EVENT,
            {
                "event": uuid4(),
                "id": fix.recommendation_id,
                "tenant": tenant,
                "from": Lifecycle.ACCEPTED.value,
                "to": Lifecycle.IN_PROGRESS.value,
                "actor": COLLECTOR,
                "reason": f"Pull request #{moved.number} opened, {moved.url}",
                "now": now,
            },
        )


def _not_authored(reason: str) -> _Moved:
    return _Moved("NOT_AUTHORED", reason, reason=reason)
