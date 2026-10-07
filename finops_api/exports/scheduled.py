"""The report runner: each due schedule rendered once for each of its recipients. FEAT-069.

TASK-P8-011, P8 spec section 5.7 and ADR-0033. The schedules render inside the API because
rendering is the API's work: the scope dependency, the guard and the export responder all live
here, and nothing below the API may import them. Each recipient's file is made by calling the
schedule's route in process, as that recipient, with a session minted for that one call. The
same dependency resolves their scope, the same guard confines the read and the same responder
writes the file and its record, so a schedule cannot carry a row to someone who could not open
it. The session never leaves the process.

Its cadence is the `report_schedules` row in `collector_schedule`, which says it runs here and
not in the ingest worker, ADR-0012. Each look claims the tenant's current slot in the run
ledger, so two API containers looking at once render it once, and the freshness screen shows
the runner as it shows every collector. Each due schedule is taken in a transaction of its own
with SKIP LOCKED, so a slow one holds up no other.

One recipient failing never fails the run, constraint 5. The failure is a run row with its typed
cause, the other recipients render, and the ledger records the look as PARTIAL.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from urllib.parse import urlsplit
from uuid import UUID

import anyio
import httpx
from sqlalchemy import Row, select, update

from finops_api.db import models
from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.reports import mark_failed, mark_kept, record_failed_run
from finops_api.db.repositories.views import SavedViewRepository
from finops_api.exports.responder import RUN_HEADER
from finops_api.toolbox import IN_PROCESS_HOST
from finops_core.domain.identity import Principal
from finops_core.domain.report_schedule import Cadence, next_run_after
from finops_core.domain.tenant import Scope
from finops_core.errors import (
    AccessDenied,
    CollectionError,
    Misconfigured,
    NoData,
    SchemaDrift,
    Throttled,
    Unreachable,
)
from finops_core.ports.reports import ReportSender, ReportStore
from finops_ingest.ledger import RunLedger

logger = logging.getLogger(__name__)

COLLECTOR: Final = "report_schedules"
#: The ledger's scope for a look. One look covers every schedule a tenant has.
SCOPE_KEY: Final = "organization"
#: Every stored file is under this prefix and then its tenant's identifier.
REPORTS_PREFIX: Final = "reports"
#: How often the thread wakes to see whether a tenant's slot has begun. The cadence itself is the
#: row in `collector_schedule`; this only bounds how late a slot can be noticed.
WAKE_SECONDS: Final = 60
#: The audit row's request id for what the runner reads, so an incident can tell it from a person.
RUNNER_REQUEST: Final = "report-runner"
#: How much of a refusal's own words a failed run keeps.
DETAIL_LIMIT: Final = 500

ScheduleRow = Row[Any]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def slot_of(now: datetime, cadence_seconds: int) -> tuple[datetime, datetime]:
    """The cadence's slot that `now` falls in, aligned to the epoch so every container agrees."""
    seconds = int(now.timestamp())
    start = datetime.fromtimestamp(seconds - seconds % cadence_seconds, UTC)
    return start, start + timedelta(seconds=cadence_seconds)


def storage_key(tenant_id: UUID, run_id: UUID, file_format: str) -> str:
    """Where a run's file is kept: under the tenant's prefix, named by the run that made it."""
    return f"{REPORTS_PREFIX}/{tenant_id}/{run_id}.{file_format}"


@dataclass(frozen=True)
class Look:
    """What one look did, across every tenant whose slot had begun."""

    tenants: int = 0
    rendered: int = 0
    failed: int = 0


class ReportRunner:
    """Renders due schedules through the application it was built around."""

    def __init__(
        self,
        app: Any,
        store: ReportStore,
        sender: ReportSender | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._app = app
        self._store = store
        self._sender = sender
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- the thread ---------------------------------------------------------------------------

    def start(self) -> None:
        """Look now and then every `WAKE_SECONDS`, until stopped."""
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="report-runner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=WAKE_SECONDS)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.look()
            except Exception:
                # Logged with its traceback rather than raised, because a raise here ends the
                # thread and every schedule after it with it. The tenant's claim stays RUNNING
                # and the ledger reclaims it after its timeout, so the slot is not lost.
                logger.exception("the report runner's look failed")
            self._stop.wait(WAKE_SECONDS)

    # -- a look -------------------------------------------------------------------------------

    def look(self) -> Look:
        """Render every due schedule of every tenant whose slot has begun and is unclaimed."""
        engine = self._app.state.engine
        now = self._clock()
        with engine.connect() as connection:
            cadences = connection.execute(
                select(
                    models.collector_schedule.c.tenant_id,
                    models.collector_schedule.c.cadence_seconds,
                ).where(
                    models.collector_schedule.c.collector == COLLECTOR,
                    models.collector_schedule.c.runs_in == "api",
                    models.collector_schedule.c.is_enabled,
                )
            ).all()
        totals = Look()
        for tenant_id, cadence_seconds in cadences:
            rendered, failed, ran = self._look_at(tenant_id, int(cadence_seconds), now)
            if ran:
                totals = Look(
                    tenants=totals.tenants + 1,
                    rendered=totals.rendered + rendered,
                    failed=totals.failed + failed,
                )
        return totals

    def _look_at(
        self, tenant_id: UUID, cadence_seconds: int, now: datetime
    ) -> tuple[int, int, bool]:
        engine = self._app.state.engine
        timeout = self._app.state.settings.run_claim_timeout_minutes
        start, end = slot_of(now, cadence_seconds)
        with engine.begin() as connection:
            ledger = RunLedger(connection, tenant_id, timeout, clock=self._clock)
            claim = ledger.claim(COLLECTOR, SCOPE_KEY, start, end)
            if claim is not None:
                ledger.running(claim)
        if claim is None:
            return 0, 0, False
        rendered, failed = self._render_due(tenant_id, now)
        with engine.begin() as connection:
            ledger = RunLedger(connection, tenant_id, timeout, clock=self._clock)
            ledger.complete(
                claim,
                items_written=rendered,
                bytes_read=0,
                status="PARTIAL" if failed else "SUCCEEDED",
            )
        return rendered, failed, True

    def _render_due(self, tenant_id: UUID, now: datetime) -> tuple[int, int]:
        """Each due schedule in its own transaction, the earliest due first."""
        engine = self._app.state.engine
        table = models.report_schedule
        rendered = failed = 0
        while True:
            with engine.begin() as connection:
                schedule = connection.execute(
                    select(table)
                    .where(
                        table.c.tenant_id == tenant_id, table.c.enabled, table.c.next_run_at <= now
                    )
                    .order_by(table.c.next_run_at, table.c.schedule_id)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                ).one_or_none()
                if schedule is None:
                    return rendered, failed
                done, missed, viewable = self._render_schedule(connection, schedule, now)
                # A schedule whose view is gone, or no longer one its owner can open, has said
                # why to each recipient once; paused, it says it no more until its owner acts.
                connection.execute(
                    update(table)
                    .where(table.c.schedule_id == schedule.schedule_id)
                    .values(
                        next_run_at=next_run_after(Cadence(schedule.cadence), now),
                        enabled=viewable,
                    )
                )
            rendered += done
            failed += missed

    def _render_schedule(
        self, connection: Any, schedule: ScheduleRow, now: datetime
    ) -> tuple[int, int, bool]:
        """One file per recipient. A recipient who fails is recorded and the rest carry on.

        The last of the three is whether the view could be opened at all, which decides whether
        the schedule keeps running.
        """
        owner = self._scope_of(schedule.tenant_id, schedule.owner_id)
        view = (
            None
            if schedule.view_id is None
            else SavedViewRepository(connection, AccessContext(request_id=RUNNER_REQUEST)).view(
                owner, schedule.view_id
            )
        )
        rendered = failed = 0
        for recipient in schedule.recipients:
            if view is None:
                refusal = AccessDenied(
                    scope_key=str(schedule.schedule_id),
                    collector=COLLECTOR,
                    detail=(
                        "the view this schedule names was deleted, or is no longer one its owner "
                        "can open, so the schedule is paused"
                    ),
                )
                self._failed(
                    connection,
                    schedule,
                    recipient,
                    self._scope_of(schedule.tenant_id, recipient),
                    refusal,
                    now,
                )
                failed += 1
            elif self._render_for(connection, schedule, recipient, str(view.name), now):
                rendered += 1
            else:
                failed += 1
        return rendered, failed, view is not None

    def _render_for(
        self, connection: Any, schedule: ScheduleRow, recipient: str, view_name: str, now: datetime
    ) -> bool:
        """Make one recipient's file as that recipient, keep it, and send it where a sender is."""
        scope = self._scope_of(schedule.tenant_id, recipient)
        if scope.tenant_id != schedule.tenant_id or (not scope.is_global and not scope.accounts):
            refusal: CollectionError = AccessDenied(
                scope_key=recipient,
                collector=COLLECTOR,
                detail="this person's access reaches no account in this organization",
            )
            self._failed(connection, schedule, recipient, scope, refusal, now)
            return False
        try:
            response = self._get(schedule.export_path, schedule.format, scope)
        except httpx.HTTPError as failure:
            refusal = Unreachable(scope_key=recipient, collector=COLLECTOR, detail=str(failure))
            self._failed(connection, schedule, recipient, scope, refusal, now)
            return False
        if response.status_code != httpx.codes.OK or RUN_HEADER not in response.headers:
            self._failed(
                connection, schedule, recipient, scope, _cause_of(response, recipient), now
            )
            return False
        run_id = UUID(response.headers[RUN_HEADER])
        key = storage_key(schedule.tenant_id, run_id, schedule.format)
        try:
            self._store.put(key, response.content, response.headers["content-type"])
        except CollectionError as failure:
            mark_failed(
                connection,
                run_id=run_id,
                schedule_id=schedule.schedule_id,
                cause=failure.cause,
                detail=str(failure),
                finished_at=self._clock(),
            )
            return False
        if self._sender is not None:
            try:
                self._sender.send(
                    recipient=recipient,
                    subject=view_name,
                    file_name=_file_name(response, key),
                    body=response.content,
                )
            except CollectionError as failure:
                # Kept and not sent: the key stays, so the recipient can still fetch the file.
                mark_failed(
                    connection,
                    run_id=run_id,
                    schedule_id=schedule.schedule_id,
                    cause=failure.cause,
                    detail=str(failure),
                    finished_at=self._clock(),
                    storage_key=key,
                )
                return False
        mark_kept(
            connection,
            run_id=run_id,
            schedule_id=schedule.schedule_id,
            storage_key=key,
            sent=self._sender is not None,
            finished_at=self._clock(),
        )
        return True

    # -- helpers ------------------------------------------------------------------------------

    def _scope_of(self, tenant_id: UUID, principal_id: str) -> Scope:
        """The scope this person holds now, resolved as a request of theirs would resolve it."""
        principal = Principal(
            principal_id=principal_id,
            display_name=principal_id,
            tenant_id=tenant_id,
            groups=frozenset(),
        )
        entitlement = self._app.state.entitlements.resolve(principal)
        scope: Scope = replace(entitlement.scope, principal_id=principal_id)
        return scope

    def _get(self, export_path: str, file_format: str, scope: Scope) -> httpx.Response:
        """The route, as the recipient, in process. A plain thread has no event loop, so it
        starts one for the call, unlike the assistant's transport, which runs in a route."""
        token = self._app.state.signer.issue(
            scope.principal_id or "", scope.principal_id or "", scope
        )
        joiner = "&" if "?" in export_path else "?"
        url = f"{export_path}{joiner}format={file_format}"

        async def fetch() -> httpx.Response:
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(transport=transport, base_url=IN_PROCESS_HOST) as client:
                return await client.get(url, headers={"Authorization": f"Bearer {token}"})

        return anyio.run(fetch)

    def _failed(
        self,
        connection: Any,
        schedule: ScheduleRow,
        recipient: str,
        scope: Scope,
        error: CollectionError,
        now: datetime,
    ) -> None:
        split = urlsplit(schedule.export_path)
        record_failed_run(
            connection,
            tenant_id=schedule.tenant_id,
            principal_id=recipient,
            schedule_id=schedule.schedule_id,
            view_path=split.path,
            view_query=split.query,
            scope_accounts=None if scope.is_global else _accounts(scope),
            file_format=schedule.format,
            cause=error.cause,
            detail=error.detail or str(error),
            made_at=now,
        )


def _accounts(scope: Scope) -> Sequence[str]:
    return [account.account_id for account in scope.accounts]


def _cause_of(response: httpx.Response, recipient: str) -> CollectionError:
    """What a refused render was refused for, in the taxonomy, with the API's own words."""
    detail = _detail(response)
    code = response.status_code
    if code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
        return AccessDenied(scope_key=recipient, collector=COLLECTOR, detail=detail)
    if code == httpx.codes.NOT_FOUND:
        return NoData(scope_key=recipient, collector=COLLECTOR, detail=detail)
    if code == httpx.codes.UNPROCESSABLE_ENTITY:
        return Misconfigured(scope_key=recipient, collector=COLLECTOR, detail=detail)
    if code == httpx.codes.TOO_MANY_REQUESTS:
        return Throttled(scope_key=recipient, collector=COLLECTOR, detail=detail)
    if code in (
        httpx.codes.BAD_GATEWAY,
        httpx.codes.SERVICE_UNAVAILABLE,
        httpx.codes.GATEWAY_TIMEOUT,
    ):
        return Unreachable(scope_key=recipient, collector=COLLECTOR, detail=detail)
    return SchemaDrift(scope_key=recipient, collector=COLLECTOR, detail=f"{code}: {detail}")


def _detail(response: httpx.Response) -> str:
    try:
        said: object = response.json().get("detail")
    except ValueError:
        return response.text[:DETAIL_LIMIT]
    return said if isinstance(said, str) else str(said)[:DETAIL_LIMIT]


def _file_name(response: httpx.Response, key: str) -> str:
    disposition: str = response.headers.get("content-disposition", "")
    marker = 'filename="'
    if marker in disposition:
        return disposition.split(marker, 1)[1].split('"', 1)[0]
    return key.rsplit("/", 1)[-1]
