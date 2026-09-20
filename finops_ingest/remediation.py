"""Applying the workspace refresh floor, and recording what it replaced.

FEAT-014, TASK-P2-017. This is the whole of Meter's smallest write: one setting
on one workspace, no dashboard touched. It is separate from the collector
because a collector reads, and mixing a write into a read path means the next
person to add a collector inherits a write capability nobody asked them to
think about.

Three rules, and the third is the one that matters.

**The level is checked here, not by the caller.** A guard the caller performs is
a guard the next caller forgets.

**The previous value is captured from the write itself**, not read back
afterwards. A caller that reads it back has already lost the race with anyone
else changing the same workspace, and would then record a `before` that was
never true.

**Nothing is recorded unless the write succeeded.** A `remediation_change` row
is a claim that the estate changed. Writing it optimistically and failing after
leaves an undo that would restore a value nobody ever replaced.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from finops_core.domain.query import SurfaceInstance, WriteLevel
from finops_core.errors import CollectionError

KIND = "WORKSPACE_FLOOR"
PANEL_KIND = "PANEL_REWRITE"


@dataclass(frozen=True)
class FloorOutcome:
    """What happened, in enough detail to explain a refusal.

    `applied` false is a normal answer. The common case is a deployment whose
    write level is `none`, which is the default and is a decision rather than a
    fault.
    """

    surface_id: str
    applied: bool
    previous_seconds: int | None = None
    requested_seconds: int | None = None
    detail: str = ""
    change_id: UUID | None = None


def apply_refresh_floor(
    *,
    connection: Any,
    tenant_id: UUID,
    instance: SurfaceInstance,
    control: Any,
    seconds: int,
    write_level: WriteLevel,
    applied_by: str,
    instance_pk: UUID,
    now: datetime | None = None,
) -> FloorOutcome:
    """Raise one workspace's floor, if this deployment is permitted to.

    `control` is anything satisfying the `RefreshFloor` port. It is passed in
    rather than constructed here so this function has no opinion about which
    surface it is talking to, which is what keeps the write path testable
    without a workspace.

    `instance_pk` is required, and the database requires it too: a change that
    names no instance is a change nobody can undo, and `remediation_change`
    makes that a constraint rather than a convention.
    """
    if not write_level.permits(WriteLevel.WORKSPACE_FLOOR):
        return FloorOutcome(
            surface_id=instance.surface_id,
            applied=False,
            requested_seconds=seconds,
            detail=(
                f"write level is {write_level.value}, and this needs "
                f"{WriteLevel.WORKSPACE_FLOOR.value} or above"
            ),
        )

    try:
        previous = control.set_refresh_floor(instance, seconds)
    except CollectionError as failure:
        # Typed, and reported rather than raised. A refusal by one workspace is
        # not a reason to abandon the others.
        return FloorOutcome(
            surface_id=instance.surface_id,
            applied=False,
            requested_seconds=seconds,
            detail=f"{type(failure).__name__}: {failure}",
        )

    change_id = uuid4()
    connection.execute(
        text(
            "INSERT INTO remediation_change (change_id, tenant_id, instance_id, kind, "
            "before, after, applied_by, applied_at) VALUES "
            "(:id, :tenant, :instance, :kind, :before, :after, :who, :at)"
        ),
        {
            "id": change_id,
            "tenant": tenant_id,
            "instance": instance_pk,
            "kind": KIND,
            # `before` is NOT NULL in the table, and a null previous floor is
            # still a fact about the workspace: it had none. The JSON says which
            # rather than the column being absent.
            "before": json.dumps({"refresh_floor_seconds": previous}),
            "after": json.dumps({"refresh_floor_seconds": seconds}),
            "who": applied_by,
            "at": now or datetime.now(UTC),
        },
    )
    connection.execute(
        text(
            "UPDATE grafana_instance SET refresh_floor_seconds = :floor "
            "WHERE tenant_id = :tenant AND instance_id = :instance"
        ),
        {"floor": seconds, "tenant": tenant_id, "instance": instance_pk},
    )
    return FloorOutcome(
        surface_id=instance.surface_id,
        applied=True,
        previous_seconds=previous,
        requested_seconds=seconds,
        change_id=change_id,
    )


@dataclass(frozen=True)
class RewriteOutcome:
    """What a panel rewrite did, including the case where it undid itself."""

    fingerprint: str
    applied: bool
    reverted: bool = False
    detail: str = ""
    change_id: UUID | None = None


def apply_panel_rewrite(
    *,
    connection: Any,
    tenant_id: UUID,
    instance: SurfaceInstance,
    control: Any,
    fingerprint: str,
    changes: Mapping[str, Any],
    write_level: WriteLevel,
    applied_by: str,
    query_pk: UUID,
    instance_pk: UUID,
    now: datetime | None = None,
) -> RewriteOutcome:
    """Replace part of one element, verify it took, and undo it if it did not.

    The largest write Meter makes, and the order of operations is the feature.

    Read first, and keep what was read. `before` is the stored form exactly as
    the surface held it, not a reconstruction from the fields Meter understands,
    which is what makes the undo exact rather than approximate.

    Write, then read back and compare. A surface that accepted a write is not a
    surface that applied it, and FEAT-017 requires the caller to check rather
    than be told. A mismatch reverts immediately: a partial write to somebody's
    dashboard is worse than the problem it was fixing.

    `changes` names only the fields to replace. Sending a whole element would
    overwrite everything a person edited between the read and the write.
    """
    if not write_level.permits(WriteLevel.FULL):
        return RewriteOutcome(
            fingerprint=fingerprint,
            applied=False,
            detail=(
                f"write level is {write_level.value}, and a panel rewrite needs "
                f"{WriteLevel.FULL.value}"
            ),
        )

    try:
        before = dict(control.read_element(instance, fingerprint))
    except CollectionError as failure:
        return RewriteOutcome(
            fingerprint=fingerprint,
            applied=False,
            detail=f"could not read the element first: {type(failure).__name__}: {failure}",
        )

    after = {**before, **changes}
    try:
        control.write_element(instance, fingerprint, after)
    except CollectionError as failure:
        return RewriteOutcome(
            fingerprint=fingerprint,
            applied=False,
            detail=f"{type(failure).__name__}: {failure}",
        )

    try:
        confirmed = dict(control.read_element(instance, fingerprint))
    except CollectionError as failure:
        # Cannot confirm, so it is not left in place. An unverified write is the
        # one state this feature must never leave behind.
        return _revert(control, instance, fingerprint, before, failure=failure)

    if confirmed != after:
        return _revert(control, instance, fingerprint, before)

    change_id = uuid4()
    connection.execute(
        text(
            "INSERT INTO remediation_change (change_id, tenant_id, query_id, instance_id, kind, "
            "before, after, applied_by, applied_at) VALUES "
            "(:id, :tenant, :query, :instance, :kind, :before, :after, :who, :at)"
        ),
        {
            "id": change_id,
            "tenant": tenant_id,
            "query": query_pk,
            "instance": instance_pk,
            "kind": PANEL_KIND,
            "before": json.dumps(before, sort_keys=True),
            "after": json.dumps(after, sort_keys=True),
            "who": applied_by,
            "at": now or datetime.now(UTC),
        },
    )
    return RewriteOutcome(fingerprint=fingerprint, applied=True, change_id=change_id)


def _revert(
    control: Any,
    instance: SurfaceInstance,
    fingerprint: str,
    before: Mapping[str, Any],
    failure: CollectionError | None = None,
) -> RewriteOutcome:
    """Put it back, and say whether that worked.

    Nothing is recorded either way. A change row is a claim that the estate
    changed and stayed changed, and a rewrite that undid itself did not.
    """
    reason = (
        f"could not confirm the write: {type(failure).__name__}"
        if failure is not None
        else "the element did not match what was written"
    )
    try:
        control.write_element(instance, fingerprint, before)
    except CollectionError as broken:
        return RewriteOutcome(
            fingerprint=fingerprint,
            applied=False,
            reverted=False,
            detail=(
                f"{reason}, and the revert also failed: {type(broken).__name__}. "
                f"The element is left as written and needs a person."
            ),
        )
    return RewriteOutcome(
        fingerprint=fingerprint,
        applied=False,
        reverted=True,
        detail=f"{reason}, so it was reverted",
    )


def undo_change(
    *,
    connection: Any,
    tenant_id: UUID,
    instance: SurfaceInstance,
    control: Any,
    change_id: UUID,
    reverted_by: str,
    now: datetime | None = None,
) -> RewriteOutcome:
    """Restore exactly what was there, from the row that recorded it.

    From the stored `before` rather than from a reconstruction, which is the
    whole reason `before` is the surface's own form. A change already reverted
    is refused rather than applied twice: the second undo would restore a state
    that was itself replaced by the first.
    """
    # Joined to the definition for the surface's own fingerprint. The change row
    # holds the database identity, and writing to that would address an element
    # the surface has never heard of. That is exactly what the first version did.
    row = connection.execute(
        text(
            "SELECT d.fingerprint AS fingerprint, c.before AS before, "
            "c.reverted_at AS reverted_at FROM remediation_change c "
            "JOIN query_definition d ON d.query_id = c.query_id "
            "WHERE c.change_id = :id AND c.tenant_id = :tenant"
        ),
        {"id": change_id, "tenant": tenant_id},
    ).one_or_none()
    if row is None:
        return RewriteOutcome(fingerprint="", applied=False, detail="no such change")
    if row.reverted_at is not None:
        return RewriteOutcome(
            fingerprint="",
            applied=False,
            detail="already reverted, and undoing it twice would restore a replaced state",
        )

    fingerprint = str(row.fingerprint)
    try:
        control.write_element(instance, fingerprint, row.before)
    except CollectionError as failure:
        return RewriteOutcome(
            fingerprint=fingerprint,
            applied=False,
            detail=f"{type(failure).__name__}: {failure}",
        )

    connection.execute(
        text(
            "UPDATE remediation_change SET reverted_at = :at, reverted_by = :who "
            "WHERE change_id = :id AND tenant_id = :tenant"
        ),
        {"at": now or datetime.now(UTC), "who": reverted_by, "id": change_id, "tenant": tenant_id},
    )
    return RewriteOutcome(fingerprint=fingerprint, applied=True, reverted=True, change_id=change_id)
