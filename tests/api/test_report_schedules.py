"""Scheduled reports, rendered for each recipient in their own scope. FEAT-069, TASK-P8-011.

TASK-P8-011's acceptance criteria, each held here:

- `report_schedule` refuses what the P8 spec's section 6 says it must, including that the view is
  one its owner can open, which a trigger holds because a check cannot read another table;
- the runner, whose cadence row says it runs in the API, renders each due schedule once per
  recipient in that recipient's scope, asserted with two recipients whose scopes differ;
- files are kept under the tenant's prefix and fetched through a route that checks scope again;
- a sender port with a fake, and runs listed as rendered and not sent without one;
- one recipient failing never fails the run;
- nothing deletes a file, and the schedules route says how long files are kept.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from finops_api.db import models
from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.reports import record_run
from finops_api.db.repositories.schedules import ScheduleRepository
from finops_api.db.repositories.views import SavedViewRepository
from finops_api.exports.scheduled import COLLECTOR, ReportRunner, slot_of, storage_key
from finops_api.guards import SCOPED_TABLES, ByPrincipal
from finops_api.identity.session import SessionSigner
from finops_api.main import create_app
from finops_api.routes.schedules import DELIVERY, NARROWED, NO_FILE, NOT_EXPORTED, RETENTION
from finops_core.config import Settings
from finops_core.domain.identity import Entitlement, Principal
from finops_core.domain.tenant import Scope
from finops_fakes.reports import MemoryReportStore, RecordingSender
from finops_ingest.registry import install_default_schedule
from tests.api.test_query_routes import (
    IN_SCOPE,
    NOW,
    OUT_OF_SCOPE,
    SIGNING_KEY,
    auth,
    everything,
    narrow,
)
from tests.api.test_saved_views import INSERT_ACCOUNT

pytestmark = pytest.mark.integration

SCHEDULES = "/api/v1/reports/schedules"
RUNS = "/api/v1/reports/runs"
OWNER = "p-owner"
NARROW = "p-narrow"
STRANGER = "p-stranger"
EXPORT = "/api/v1/accounts?status=ACTIVE"
CONTEXT = AccessContext(request_id="test")
EARLIER = NOW - timedelta(hours=1)
#: The runner's clock: fixed, so two looks in one test share a slot, and recent, so the ledger rows
#: it writes are not weeks old to the health check, which reports the worst tenant in the database.
LOOKED_AT = datetime.now(UTC)


@pytest.fixture(autouse=True)
def _cadences_off_afterwards(engine: Engine, tenant_id: UUID) -> Iterator[None]:
    """The health check reads every tenant's cadences in the database and reports the oldest last
    success, so a run a test here leaves behind would answer for the health tests' own tenants.
    Switched off afterwards, this tenant's cadences are ones the health check passes over."""
    yield
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE collector_schedule SET is_enabled = false WHERE tenant_id = :t"),
            {"t": tenant_id},
        )


class People:
    """An identity provider that knows two people, the owner of everything and one narrowed to
    one account. Anybody else resolves to a scope reaching nothing, as the real one does."""

    def __init__(self, tenant: UUID, scopes: Mapping[str, Scope] | None = None) -> None:
        self._tenant = tenant
        self._scopes = dict(scopes or {OWNER: everything(tenant), NARROW: narrow(tenant)})

    def resolve(self, principal: Principal) -> Entitlement:
        nobody = Scope(tenant_id=self._tenant, is_global=False, accounts=frozenset())
        scope = self._scopes.get(principal.principal_id, nobody)
        return Entitlement(principal=principal, scope=scope, as_of=NOW, collected_at=NOW)


def application(
    engine: Engine,
    settings: Settings,
    tenant: UUID,
    *,
    store: Any = None,
    sender: Any = None,
    scopes: Mapping[str, Scope] | None = None,
) -> FastAPI:
    return create_app(
        engine=engine,
        entitlements=People(tenant, scopes),
        signer=SessionSigner(SIGNING_KEY, ttl_hours=8, clock=lambda: NOW),
        settings=settings,
        report_store=store,
        report_sender=sender,
    )


def headers(app: FastAPI, person: str) -> dict[str, str]:
    scope = app.state.entitlements.resolve(
        Principal(principal_id=person, display_name=person, tenant_id=uuid4(), groups=frozenset())
    ).scope
    return auth(app.state.signer.issue(person, f"{person}@example.local", scope))


def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def as_owner(tenant: UUID, person: str = OWNER) -> Scope:
    return replace(everything(tenant), principal_id=person)


def estate(engine: Engine, tenant: UUID) -> None:
    """Two accounts, one each side of the narrowed scope, and the tenant's default cadences."""
    with engine.begin() as connection:
        for account in (IN_SCOPE, OUT_OF_SCOPE):
            connection.execute(
                INSERT_ACCOUNT, {"pk": uuid4(), "t": tenant, "a": account, "at": NOW}
            )
        install_default_schedule(connection, tenant, updated_by="test")


def saved_view(
    engine: Engine, tenant: UUID, person: str = OWNER, visibility: str = "SHARED"
) -> UUID:
    with engine.begin() as connection:
        row = SavedViewRepository(connection, CONTEXT).create(
            as_owner(tenant, person),
            name="Active accounts",
            screen_path="/inventory/accounts",
            query={"status": "ACTIVE"},
            visibility=visibility,
            at=NOW,
        )
    view_id: UUID = row.view_id
    return view_id


def schedule(
    engine: Engine,
    tenant: UUID,
    view_id: UUID,
    recipients: list[str],
    *,
    file_format: str = "csv",
    due: datetime = EARLIER,
) -> UUID:
    with engine.begin() as connection:
        row = ScheduleRepository(connection, CONTEXT).create(
            as_owner(tenant),
            view_id=view_id,
            export_path=EXPORT,
            file_format=file_format,
            cadence="DAILY",
            recipients=recipients,
            next_run_at=due,
            at=NOW - timedelta(days=1),
        )
    schedule_id: UUID = row.schedule_id
    return schedule_id


def runs_of(engine: Engine, schedule_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT principal_id, status, failure_cause, storage_key, row_count, scope_global, "
                "scope_accounts FROM report_run WHERE schedule_id = :s"
            ),
            {"s": schedule_id},
        ).mappings()
        return {str(row["principal_id"]): dict(row) for row in rows}


def enabled_of(engine: Engine, schedule_id: UUID) -> bool:
    with engine.connect() as connection:
        enabled: bool = connection.execute(
            text("SELECT enabled FROM report_schedule WHERE schedule_id = :s"), {"s": schedule_id}
        ).scalar_one()
    return enabled


def runner(app: FastAPI, store: Any, sender: Any = None) -> ReportRunner:
    return ReportRunner(app, store=store, sender=sender, clock=lambda: LOOKED_AT)


# --- the table -------------------------------------------------------------------------------


class TestTheTable:
    """Constraint 11, and the one invariant only a trigger can hold."""

    @staticmethod
    def row(tenant: UUID, view_id: UUID, **change: object) -> dict[str, object]:
        return {
            "schedule_id": uuid4(),
            "tenant_id": tenant,
            "owner_id": OWNER,
            "view_id": view_id,
            "export_path": EXPORT,
            "format": "xlsx",
            "cadence": "WEEKLY",
            "recipients": [OWNER],
            "enabled": True,
            "next_run_at": NOW,
            "created_at": NOW,
            "updated_at": NOW,
            **change,
        }

    def test_a_whole_row_is_accepted_so_each_refusal_below_can_fail(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        view_id = saved_view(engine, tenant_id)
        with engine.begin() as connection:
            connection.execute(
                models.report_schedule.insert().values(**self.row(tenant_id, view_id))
            )

    @pytest.mark.parametrize(
        "change",
        [
            {"format": "pdf"},
            {"cadence": "HOURLY"},
            {"recipients": []},
            {"recipients": [OWNER, ""]},
            {"recipients": [f"p-{index}" for index in range(51)]},
            {"owner_id": " "},
            {"export_path": "https://elsewhere.example/api/v1/accounts"},
            {"export_path": "/api/v1/accounts?format=xlsx"},
            {"updated_at": NOW - timedelta(seconds=1)},
        ],
        ids=[
            "format",
            "cadence",
            "nobody",
            "blank-recipient",
            "too-many",
            "no-owner",
            "elsewhere",
            "format-in-path",
            "updated-first",
        ],
    )
    def test_the_table_refuses(
        self, engine: Engine, tenant_id: UUID, change: dict[str, object]
    ) -> None:
        view_id = saved_view(engine, tenant_id)
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                models.report_schedule.insert().values(**self.row(tenant_id, view_id, **change))
            )

    def test_a_schedule_cannot_name_a_view_its_owner_cannot_open(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        private = saved_view(engine, tenant_id, person=NARROW, visibility="PRIVATE")
        shared = saved_view(engine, tenant_id, person=NARROW, visibility="SHARED")
        with engine.begin() as connection:
            connection.execute(
                models.report_schedule.insert().values(**self.row(tenant_id, shared))
            )
        with pytest.raises(IntegrityError, match="cannot open"), engine.begin() as connection:
            connection.execute(
                models.report_schedule.insert().values(**self.row(tenant_id, private))
            )

    @pytest.mark.parametrize(
        "change",
        [
            {"status": "FAILED"},
            {"status": "RENDERED"},
            {"storage_key": "reports/x/y.csv"},
            {"status": "FAILED", "failure_cause": "Unhappy"},
            {"status": "SENT", "failure_cause": "Throttled", "storage_key": "reports/x/y.csv"},
        ],
        ids=["failed-no-cause", "rendered-no-key", "streamed-kept", "unknown-cause", "sent-failed"],
    )
    def test_a_run_record_refuses(
        self, engine: Engine, tenant_id: UUID, change: dict[str, object]
    ) -> None:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            run_id = record_run(
                connection,
                tenant_id=tenant_id,
                principal_id=OWNER,
                view_path="/api/v1/accounts",
                view_query="",
                scope_accounts=None,
                file_format="csv",
                rows=1,
                size=1,
                truncated=False,
                made_at=NOW,
            )
            connection.execute(
                models.report_run.update()
                .where(models.report_run.c.run_id == run_id)
                .values(**change)
            )

    def test_the_schedule_is_its_owners_alone(self) -> None:
        assert SCOPED_TABLES["report_schedule"] == ByPrincipal("owner_id")


# --- the routes ------------------------------------------------------------------------------


class TestTheRoutes:
    def test_a_schedule_is_made_from_a_view_and_a_route_its_screen_exports(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        estate(engine, tenant_id)
        view_id = saved_view(engine, tenant_id)
        app = application(engine, settings, tenant_id, store=MemoryReportStore())
        api = client(app)
        body = {
            "view_id": str(view_id),
            "export_path": f"{EXPORT}&format=csv",
            "format": "xlsx",
            "cadence": "WEEKLY",
            "recipients": [f" {OWNER} ", NARROW, OWNER],
        }
        made = api.post(SCHEDULES, json=body, headers=headers(app, OWNER))
        assert made.status_code == 201, made.text
        data = made.json()["data"]
        assert data["export_path"] == EXPORT
        assert data["recipients"] == [OWNER, NARROW]
        assert (data["view_name"], data["enabled"]) == ("Active accounts", True)
        assert datetime.fromisoformat(data["next_run_at"]) > datetime.fromisoformat(
            data["created_at"]
        )
        assert made.json()["meta"]["as_of"] is not None

        listed = api.get(SCHEDULES, headers=headers(app, OWNER)).json()
        assert listed["data"]["rendering"] is True
        assert (listed["data"]["retention"], listed["data"]["delivery"]) == (RETENTION, DELIVERY)
        assert [s["schedule_id"] for s in listed["data"]["schedules"]] == [data["schedule_id"]]
        assert listed["meta"]["scope_coverage"]["unit"] == "schedules"

    @pytest.mark.parametrize(
        ("path", "status"),
        [("/api/v1/me", 422), ("https://elsewhere.example/api/v1/accounts", 422)],
        ids=["not-exported", "elsewhere"],
    )
    def test_a_route_no_screen_exports_is_refused(
        self, engine: Engine, settings: Settings, tenant_id: UUID, path: str, status: int
    ) -> None:
        view_id = saved_view(engine, tenant_id)
        app = application(engine, settings, tenant_id)
        body = {
            "view_id": str(view_id),
            "export_path": path,
            "format": "csv",
            "cadence": "DAILY",
            "recipients": [OWNER],
        }
        refused = client(app).post(SCHEDULES, json=body, headers=headers(app, OWNER))
        assert (refused.status_code, refused.json()) == (status, {"detail": NOT_EXPORTED})

    def test_a_view_the_reader_cannot_open_is_not_found(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        private = saved_view(engine, tenant_id, person=NARROW, visibility="PRIVATE")
        app = application(engine, settings, tenant_id)
        body = {
            "view_id": str(private),
            "export_path": EXPORT,
            "format": "csv",
            "cadence": "DAILY",
            "recipients": [OWNER],
        }
        assert (
            client(app).post(SCHEDULES, json=body, headers=headers(app, OWNER)).status_code == 404
        )

    def test_another_persons_schedule_is_neither_listed_nor_changed(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        schedule_id = schedule(engine, tenant_id, saved_view(engine, tenant_id), [OWNER])
        app = application(engine, settings, tenant_id)
        api = client(app)
        theirs = headers(app, NARROW)
        assert api.get(SCHEDULES, headers=theirs).json()["data"]["schedules"] == []
        assert (
            api.patch(
                f"{SCHEDULES}/{schedule_id}", json={"enabled": False}, headers=theirs
            ).status_code
            == 404
        )
        assert api.delete(f"{SCHEDULES}/{schedule_id}", headers=theirs).status_code == 404
        with engine.connect() as connection:
            denied = connection.execute(
                text(
                    "SELECT count(*) FROM audit_event WHERE tenant_id = :t "
                    "AND resource = 'report_schedule' AND outcome = 'DENIED'"
                ),
                {"t": tenant_id},
            ).scalar_one()
        # Answered rather than raised, so both refusals' audit rows outlived their requests.
        assert denied == 2

    def test_the_owner_pauses_resumes_changes_and_deletes(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        schedule_id = schedule(engine, tenant_id, saved_view(engine, tenant_id), [OWNER])
        app = application(engine, settings, tenant_id)
        api = client(app)
        mine = headers(app, OWNER)
        path = f"{SCHEDULES}/{schedule_id}"
        paused = api.patch(path, json={"enabled": False}, headers=mine).json()["data"]
        assert paused["enabled"] is False
        assert paused["next_run_at"].startswith(EARLIER.date().isoformat())
        resumed = api.patch(path, json={"enabled": True}, headers=mine).json()["data"]
        # Resumed, it runs next at its next time from now rather than at the one it passed.
        assert datetime.fromisoformat(resumed["next_run_at"]) > datetime.fromisoformat(
            resumed["updated_at"]
        )
        changed = api.patch(
            path,
            json={"cadence": "MONTH_CLOSE", "recipients": [NARROW], "format": "xlsx"},
            headers=mine,
        ).json()["data"]
        assert (changed["cadence"], changed["recipients"], changed["format"]) == (
            "MONTH_CLOSE",
            [NARROW],
            "xlsx",
        )
        assert api.patch(path, json={}, headers=mine).status_code == 422
        deleted = api.delete(path, headers=mine)
        assert deleted.status_code == 200, deleted.text
        assert api.get(SCHEDULES, headers=mine).json()["data"]["schedules"] == []

    def test_a_deployment_with_no_bucket_says_nothing_renders(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        app = application(engine, settings, tenant_id)
        assert (
            client(app).get(SCHEDULES, headers=headers(app, OWNER)).json()["data"]["rendering"]
            is False
        )


# --- the runner ------------------------------------------------------------------------------


class TestTheRunner:
    def test_each_recipient_gets_a_file_of_their_own_scope(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        """The acceptance criterion: two recipients, two scopes, two different files."""
        estate(engine, tenant_id)
        schedule_id = schedule(engine, tenant_id, saved_view(engine, tenant_id), [OWNER, NARROW])
        store = MemoryReportStore()
        app = application(engine, settings, tenant_id, store=store)

        look = runner(app, store).look()
        assert look.rendered >= 2

        made = runs_of(engine, schedule_id)
        assert {person: run["status"] for person, run in made.items()} == {
            OWNER: "RENDERED",
            NARROW: "RENDERED",
        }
        assert (made[OWNER]["row_count"], made[NARROW]["row_count"]) == (2, 1)
        assert (made[OWNER]["scope_global"], made[NARROW]["scope_accounts"]) == (True, [IN_SCOPE])
        owners = store.kept[made[OWNER]["storage_key"]][0].decode()
        theirs = store.kept[made[NARROW]["storage_key"]][0].decode()
        assert IN_SCOPE in owners and OUT_OF_SCOPE in owners
        assert IN_SCOPE in theirs and OUT_OF_SCOPE not in theirs
        assert all(key.startswith(f"reports/{tenant_id}/") for key in store.kept)

        with engine.connect() as connection:
            next_run = connection.execute(
                text("SELECT next_run_at FROM report_schedule WHERE schedule_id = :s"),
                {"s": schedule_id},
            ).scalar_one()
            ledger = connection.execute(
                text(
                    "SELECT status, items_written FROM ingest_run WHERE tenant_id = :t "
                    "AND collector = :c"
                ),
                {"t": tenant_id, "c": COLLECTOR},
            ).one()
        assert next_run > LOOKED_AT
        assert (ledger.status, ledger.items_written) == ("SUCCEEDED", 2)

    def test_a_second_look_in_the_same_slot_renders_nothing_again(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        estate(engine, tenant_id)
        schedule_id = schedule(engine, tenant_id, saved_view(engine, tenant_id), [OWNER])
        store = MemoryReportStore()
        app = application(engine, settings, tenant_id, store=store)
        runner(app, store).look()
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE report_schedule SET next_run_at = :t WHERE schedule_id = :s"),
                {"t": EARLIER, "s": schedule_id},
            )
        runner(app, store).look()
        assert len(runs_of(engine, schedule_id)) == 1

    def test_one_recipient_failing_does_not_fail_the_run(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        estate(engine, tenant_id)
        schedule_id = schedule(engine, tenant_id, saved_view(engine, tenant_id), [STRANGER, NARROW])
        store = MemoryReportStore()
        app = application(engine, settings, tenant_id, store=store)
        runner(app, store).look()
        made = runs_of(engine, schedule_id)
        assert (made[STRANGER]["status"], made[STRANGER]["failure_cause"]) == (
            "FAILED",
            "AccessDenied",
        )
        assert made[STRANGER]["storage_key"] is None
        assert made[NARROW]["status"] == "RENDERED"
        with engine.connect() as connection:
            status = connection.execute(
                text("SELECT status FROM ingest_run WHERE tenant_id = :t AND collector = :c"),
                {"t": tenant_id, "c": COLLECTOR},
            ).scalar_one()
        assert status == "PARTIAL"

    def test_a_sender_sends_and_a_failed_send_keeps_the_file(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        estate(engine, tenant_id)
        schedule_id = schedule(engine, tenant_id, saved_view(engine, tenant_id), [OWNER, NARROW])
        store = MemoryReportStore()
        sender = RecordingSender(failing_for=[NARROW])
        app = application(engine, settings, tenant_id, store=store, sender=sender)
        runner(app, store, sender).look()
        made = runs_of(engine, schedule_id)
        assert made[OWNER]["status"] == "SENT"
        assert [sent[0] for sent in sender.sent] == [OWNER]
        assert (made[NARROW]["status"], made[NARROW]["failure_cause"]) == (
            "FAILED",
            "Misconfigured",
        )
        assert made[NARROW]["storage_key"] in store.kept

    def test_a_store_that_cannot_be_reached_fails_the_run_with_its_cause(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        estate(engine, tenant_id)
        schedule_id = schedule(engine, tenant_id, saved_view(engine, tenant_id), [OWNER])
        store = MemoryReportStore(unreachable=True)
        app = application(engine, settings, tenant_id, store=store)
        runner(app, store).look()
        made = runs_of(engine, schedule_id)[OWNER]
        assert (made["status"], made["failure_cause"], made["storage_key"]) == (
            "FAILED",
            "Unreachable",
            None,
        )

    def test_a_view_its_owner_can_no_longer_open_renders_nothing(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        estate(engine, tenant_id)
        theirs = saved_view(engine, tenant_id, person=NARROW, visibility="SHARED")
        schedule_id = schedule(engine, tenant_id, theirs, [OWNER])
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE saved_view SET visibility = 'PRIVATE' WHERE view_id = :v"),
                {"v": theirs},
            )
        store = MemoryReportStore()
        app = application(engine, settings, tenant_id, store=store)
        runner(app, store).look()
        made = runs_of(engine, schedule_id)[OWNER]
        assert (made["status"], made["failure_cause"]) == ("FAILED", "AccessDenied")
        assert store.kept == {}
        assert enabled_of(engine, schedule_id) is False

    def test_a_deleted_view_leaves_the_schedule_paused_with_its_reason(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        """Not deleted with the view: nobody's schedule disappears because somebody else deleted
        what it rendered. One run says why to each recipient, then the schedule pauses."""
        estate(engine, tenant_id)
        theirs = saved_view(engine, tenant_id, person=NARROW, visibility="SHARED")
        schedule_id = schedule(engine, tenant_id, theirs, [OWNER, NARROW])
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM saved_view WHERE view_id = :v"), {"v": theirs})
        store = MemoryReportStore()
        app = application(engine, settings, tenant_id, store=store)
        runner(app, store).look()
        made = runs_of(engine, schedule_id)
        assert {person: run["failure_cause"] for person, run in made.items()} == {
            OWNER: "AccessDenied",
            NARROW: "AccessDenied",
        }
        assert enabled_of(engine, schedule_id) is False
        listed = client(app).get(SCHEDULES, headers=headers(app, OWNER)).json()["data"]
        assert [(s["view_id"], s["view_name"], s["enabled"]) for s in listed["schedules"]] == [
            (None, None, False)
        ]

    def test_a_paused_schedule_and_one_not_yet_due_render_nothing(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        estate(engine, tenant_id)
        view_id = saved_view(engine, tenant_id)
        paused = schedule(engine, tenant_id, view_id, [OWNER])
        later = schedule(engine, tenant_id, view_id, [OWNER], due=LOOKED_AT + timedelta(hours=1))
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE report_schedule SET enabled = false WHERE schedule_id = :s"),
                {"s": paused},
            )
        store = MemoryReportStore()
        app = application(engine, settings, tenant_id, store=store)
        runner(app, store).look()
        assert runs_of(engine, paused) == {}
        assert runs_of(engine, later) == {}

    def test_a_slot_is_aligned_so_every_container_agrees(self) -> None:
        start, end = slot_of(datetime.fromisoformat("2026-10-07T09:22:41+00:00"), 900)
        assert (start.isoformat(), end.isoformat()) == (
            "2026-10-07T09:15:00+00:00",
            "2026-10-07T09:30:00+00:00",
        )


# --- the runs and their files ----------------------------------------------------------------


class TestTheFiles:
    def rendered(
        self, engine: Engine, settings: Settings, tenant: UUID, recipients: list[str]
    ) -> tuple[MemoryReportStore, UUID]:
        estate(engine, tenant)
        schedule_id = schedule(engine, tenant, saved_view(engine, tenant), recipients)
        store = MemoryReportStore()
        runner(application(engine, settings, tenant, store=store), store).look()
        return store, schedule_id

    def run_id_of(self, engine: Engine, schedule_id: UUID, person: str) -> UUID:
        with engine.connect() as connection:
            run_id: UUID = connection.execute(
                text("SELECT run_id FROM report_run WHERE schedule_id = :s AND principal_id = :p"),
                {"s": schedule_id, "p": person},
            ).scalar_one()
        return run_id

    def test_a_recipient_lists_their_runs_and_fetches_their_file(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        store, schedule_id = self.rendered(engine, settings, tenant_id, [NARROW])
        app = application(engine, settings, tenant_id, store=store)
        api = client(app)
        listed = api.get(RUNS, headers=headers(app, NARROW)).json()
        assert [(run["status"], run["has_file"]) for run in listed["data"]] == [("RENDERED", True)]
        assert listed["meta"]["scope_coverage"]["unit"] == "report runs"
        run_id = self.run_id_of(engine, schedule_id, NARROW)
        fetched = api.get(f"{RUNS}/{run_id}/file", headers=headers(app, NARROW))
        assert fetched.status_code == 200, fetched.text
        assert fetched.content == store.kept[storage_key(tenant_id, run_id, "csv")][0]
        assert fetched.headers["content-disposition"].startswith(
            'attachment; filename="meter-accounts-'
        )
        assert fetched.headers["cache-control"] == "no-store"

    def test_nobody_else_reads_a_recipients_runs(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        store, schedule_id = self.rendered(engine, settings, tenant_id, [NARROW])
        app = application(engine, settings, tenant_id, store=store)
        api = client(app)
        run_id = self.run_id_of(engine, schedule_id, NARROW)
        assert api.get(RUNS, headers=headers(app, OWNER)).json()["data"] == []
        assert api.get(f"{RUNS}/{run_id}/file", headers=headers(app, OWNER)).status_code == 404

    def test_a_file_is_not_handed_over_once_access_has_narrowed(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        store, schedule_id = self.rendered(engine, settings, tenant_id, [OWNER])
        run_id = self.run_id_of(engine, schedule_id, OWNER)
        narrowed = application(
            engine, settings, tenant_id, store=store, scopes={OWNER: narrow(tenant_id)}
        )
        refused = client(narrowed).get(f"{RUNS}/{run_id}/file", headers=headers(narrowed, OWNER))
        assert (refused.status_code, refused.json()) == (403, {"detail": NARROWED})

    def test_a_streamed_export_kept_no_file(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        with engine.begin() as connection:
            run_id = record_run(
                connection,
                tenant_id=tenant_id,
                principal_id=OWNER,
                view_path="/api/v1/accounts",
                view_query="",
                scope_accounts=None,
                file_format="csv",
                rows=1,
                size=1,
                truncated=False,
                made_at=NOW,
            )
        app = application(engine, settings, tenant_id, store=MemoryReportStore())
        api = client(app)
        listed = api.get(RUNS, headers=headers(app, OWNER)).json()["data"]
        assert [(run["status"], run["has_file"]) for run in listed] == [("STREAMED", False)]
        missing = api.get(f"{RUNS}/{run_id}/file", headers=headers(app, OWNER))
        assert (missing.status_code, missing.json()) == (404, {"detail": NO_FILE})

    def test_a_kept_file_gone_from_the_store_and_a_store_not_configured_say_so(
        self, engine: Engine, settings: Settings, tenant_id: UUID
    ) -> None:
        _, schedule_id = self.rendered(engine, settings, tenant_id, [OWNER])
        run_id = self.run_id_of(engine, schedule_id, OWNER)
        emptied = application(engine, settings, tenant_id, store=MemoryReportStore())
        assert (
            client(emptied)
            .get(f"{RUNS}/{run_id}/file", headers=headers(emptied, OWNER))
            .status_code
            == 404
        )
        unconfigured = application(engine, settings, tenant_id)
        assert (
            client(unconfigured)
            .get(f"{RUNS}/{run_id}/file", headers=headers(unconfigured, OWNER))
            .status_code
            == 503
        )
