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
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from finops_core.domain.query import SurfaceInstance, WriteLevel
from finops_core.errors import CollectionError

KIND = "WORKSPACE_FLOOR"


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
