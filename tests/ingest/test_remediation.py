"""The workspace refresh floor, and the record of what it replaced. FEAT-014.

This is Meter's smallest write and its first. The tests here are mostly about
refusals, because a write that happens when it should not is the failure this
feature is gated against, and a refusal is the normal case: the write level
defaults to `none` everywhere.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.query import SurfaceInstance, SurfaceKind, WriteLevel
from finops_core.errors import AccessDenied, NotOptedIn
from finops_ingest.remediation import (
    KIND,
    FloorOutcome,
    RewriteOutcome,
    apply_panel_rewrite,
    apply_refresh_floor,
    undo_change,
)
from finops_providers.fake.surface import FakeQuerySurface

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 14, 9, 0, tzinfo=UTC)

INSTANCE = SurfaceInstance(
    surface_id="ws-4e5f6a7b",
    name="meter-prod-eu-west-2",
    kind=SurfaceKind.MANAGED_GRAFANA,
    location="https://grafana.internal.example",
)


class Refusing:
    """A surface that will not accept the write, with a typed cause."""

    def __init__(self, failure: type[AccessDenied] | type[NotOptedIn]) -> None:
        self._failure = failure

    def read_refresh_floor(self, _instance: SurfaceInstance) -> int | None:
        # No floor at all, which is why a caller would be setting one. Both
        # callers pass positionally, so the leading underscore costs nothing.
        return None

    def set_refresh_floor(self, instance: SurfaceInstance, seconds: int) -> int | None:
        raise self._failure(
            scope_key=instance.surface_id,
            collector="query_audit",
            detail=f"planned refusal of a {seconds}s floor",
        )


def changes(engine: Engine, tenant: UUID) -> list[dict[str, object]]:
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                "SELECT kind, before, after, applied_by FROM remediation_change "
                "WHERE tenant_id = :t"
            ),
            {"t": tenant},
        ).mappings()
        return [dict(row) for row in rows]


def apply(engine: Engine, tenant: UUID, level: WriteLevel, control: object = None) -> FloorOutcome:
    instance_pk = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenant (tenant_id, name) VALUES (:t, :name)"),
            {"t": tenant, "name": f"floor test {tenant}"},
        )
        connection.execute(
            text(
                "INSERT INTO grafana_instance (instance_id, tenant_id, kind, name, endpoint, "
                "reachable, as_of, collected_at) VALUES "
                "(:id, :t, 'SELF_HOSTED', :name, :endpoint, true, :at, :at)"
            ),
            {
                "id": instance_pk,
                "t": tenant,
                "name": INSTANCE.name,
                "endpoint": f"{INSTANCE.location}/{tenant}",
                "at": NOW,
            },
        )
        return apply_refresh_floor(
            connection=connection,
            tenant_id=tenant,
            instance=INSTANCE,
            control=control or FakeQuerySurface(),
            seconds=60,
            write_level=level,
            applied_by="a-test",
            instance_pk=instance_pk,
            now=NOW,
        )


def test_the_default_level_writes_nothing(engine: Engine) -> None:
    """`none` is the default everywhere, so this is the normal path.

    Enabling a write is a decision somebody signs rather than one they inherit,
    and a refusal is reported rather than raised so a caller can say why.
    """
    outcome = apply(engine, uuid4(), WriteLevel.NONE)
    assert outcome.applied is False
    assert "write level is none" in outcome.detail


def test_a_permitted_write_records_what_it_replaced(engine: Engine) -> None:
    tenant = uuid4()
    outcome = apply(engine, tenant, WriteLevel.WORKSPACE_FLOOR)
    assert outcome.applied is True
    # The fake workspace has no floor at all, which is the estate this feature
    # exists to find, and `before` records that rather than omitting it.
    assert outcome.previous_seconds is None

    (change,) = changes(engine, tenant)
    assert change["kind"] == KIND
    assert change["before"] == {"refresh_floor_seconds": None}
    assert change["after"] == {"refresh_floor_seconds": 60}
    assert change["applied_by"] == "a-test"


def test_a_higher_level_also_permits_it(engine: Engine) -> None:
    # `full` is a strictly larger blast radius, so it includes this one. A level
    # compared by name rather than by rank would refuse here.
    assert apply(engine, uuid4(), WriteLevel.FULL).applied is True


def test_a_refused_write_records_nothing(engine: Engine) -> None:
    """A change row is a claim that the estate changed.

    Writing it optimistically and failing afterwards leaves an undo that would
    restore a value nobody ever replaced.
    """
    tenant = uuid4()
    outcome = apply(engine, tenant, WriteLevel.WORKSPACE_FLOOR, control=Refusing(AccessDenied))
    assert outcome.applied is False
    assert "AccessDenied" in outcome.detail
    assert changes(engine, tenant) == []


def test_a_surface_with_no_such_setting_says_so_rather_than_succeeding(engine: Engine) -> None:
    tenant = uuid4()
    outcome = apply(engine, tenant, WriteLevel.FULL, control=Refusing(NotOptedIn))
    assert outcome.applied is False
    assert "NotOptedIn" in outcome.detail
    assert changes(engine, tenant) == []


# --- panel rewrite, FEAT-017 --------------------------------------------------

FINGERPRINT = "fp-panel-0001"
SLOWER = {"refresh_seconds": 300}


def rewrite(
    engine: Engine,
    tenant: UUID,
    level: WriteLevel,
    surface: FakeQuerySurface | None = None,
) -> tuple[RewriteOutcome, UUID, FakeQuerySurface]:
    control = surface or FakeQuerySurface()
    query_pk = uuid4()
    instance_pk = uuid4()
    with engine.begin() as connection:
        _seed_instance(connection, tenant, instance_pk, query_pk)
        outcome = apply_panel_rewrite(
            connection=connection,
            tenant_id=tenant,
            instance=INSTANCE,
            control=control,
            fingerprint=FINGERPRINT,
            changes=SLOWER,
            write_level=level,
            applied_by="a-test",
            query_pk=query_pk,
            instance_pk=instance_pk,
            now=NOW,
        )
    return outcome, query_pk, control


def _seed_instance(connection: Any, tenant: UUID, instance_pk: UUID, query_pk: UUID) -> None:
    connection.execute(
        text("INSERT INTO tenant (tenant_id, name) VALUES (:t, :name)"),
        {"t": tenant, "name": f"rewrite test {tenant}"},
    )
    connection.execute(
        text(
            "INSERT INTO grafana_instance (instance_id, tenant_id, kind, name, endpoint, "
            "reachable, as_of, collected_at) VALUES "
            "(:id, :t, 'SELF_HOSTED', :name, :endpoint, true, :at, :at)"
        ),
        {
            "id": instance_pk,
            "t": tenant,
            "name": INSTANCE.name,
            "endpoint": f"{INSTANCE.location}/{tenant}",
            "at": NOW,
        },
    )
    connection.execute(
        text(
            "INSERT INTO query_definition (query_id, tenant_id, instance_id, origin, engine, "
            "query_text, fingerprint, target, refresh_seconds, range_seconds, "
            "as_of, collected_at) VALUES "
            "(:q, :t, :i, 'PANEL', 'LOGS_INSIGHTS', 'fields @timestamp', :fp, "
            "'{}'::jsonb, 10, 3600, :at, :at)"
        ),
        # The surface's own fingerprint, not the database identity. Undoing to
        # the wrong one addresses an element the surface has never heard of.
        {"q": query_pk, "t": tenant, "i": instance_pk, "fp": FINGERPRINT, "at": NOW},
    )


def test_a_rewrite_needs_the_highest_write_level(engine: Engine) -> None:
    """`workspace_floor` permits one setting, not somebody's dashboard.

    The levels are ordered so that each step up is a strictly larger blast
    radius, and this is the step that changes something a person authored.
    """
    outcome, _, control = rewrite(engine, uuid4(), WriteLevel.WORKSPACE_FLOOR)
    assert outcome.applied is False
    assert "needs full" in outcome.detail
    # And it did not touch the element on the way to refusing.
    assert control.read_element(INSTANCE, FINGERPRINT)["refresh_seconds"] == 10


def test_a_permitted_rewrite_changes_only_the_named_fields(engine: Engine) -> None:
    # Sending a whole element would overwrite everything a person edited between
    # the read and the write.
    tenant = uuid4()
    outcome, _, control = rewrite(engine, tenant, WriteLevel.FULL)
    assert outcome.applied is True
    stored = control.read_element(INSTANCE, FINGERPRINT)
    assert stored["refresh_seconds"] == 300
    assert stored["query"] == "fields @timestamp, @message | filter @message like /ERROR/"


def test_a_write_that_did_not_take_is_reverted(engine: Engine) -> None:
    """The case FEAT-017 exists for.

    A surface that accepted a write is not a surface that applied it, and a
    partial write to somebody's dashboard is worse than the problem it was
    fixing. Nothing is recorded, because a change row is a claim that the estate
    changed and stayed changed.
    """
    tenant = uuid4()
    surface = FakeQuerySurface(drop_writes=[INSTANCE.surface_id])
    outcome, _, _ = rewrite(engine, tenant, WriteLevel.FULL, surface=surface)
    assert outcome.applied is False
    assert outcome.reverted is True
    assert "did not match" in outcome.detail
    assert changes(engine, tenant) == []


def test_an_undo_restores_exactly_what_was_there(engine: Engine) -> None:
    tenant = uuid4()
    outcome, _, control = rewrite(engine, tenant, WriteLevel.FULL)
    assert outcome.change_id is not None
    original = "fields @timestamp, @message | filter @message like /ERROR/"

    with engine.begin() as connection:
        undone = undo_change(
            connection=connection,
            tenant_id=tenant,
            instance=INSTANCE,
            control=control,
            change_id=outcome.change_id,
            reverted_by="a-person",
            now=NOW,
        )
    assert undone.applied is True
    stored = control.read_element(INSTANCE, FINGERPRINT)
    # Exactly, from the stored form rather than from a reconstruction of the
    # fields Meter happens to understand.
    assert stored["refresh_seconds"] == 10
    assert stored["query"] == original


def test_undoing_twice_is_refused(engine: Engine) -> None:
    # The second undo would restore a state the first one already replaced.
    tenant = uuid4()
    outcome, _, control = rewrite(engine, tenant, WriteLevel.FULL)
    assert outcome.change_id is not None
    for expected in (True, False):
        with engine.begin() as connection:
            undone = undo_change(
                connection=connection,
                tenant_id=tenant,
                instance=INSTANCE,
                control=control,
                change_id=outcome.change_id,
                reverted_by="a-person",
                now=NOW,
            )
        assert undone.applied is expected
    assert "already reverted" in undone.detail
