"""A Terraform plan recorded as Meter keeps it. FEAT-095, TASK-P16-005, spec sections 5.1 and 5.2.

Whatever route OPEN-44 chooses hands the same things to this one writer: the pull request, its
commit and folder, and the plan reduced on arrival by `finops_query.plan_reading`. A plan that could
not be read is kept as `REFUSED` with the reason, so the pull request is told why rather than told
nothing. A plan received twice for one commit and folder is one plan: the second is not written,
and the first is returned. The folder's state comes from the repository mapping the owner sets,
P15, so the comparison with the bill knows where to look once the change is applied.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from finops_query.plan_reading import ReducedPlan, Unreadable


@dataclass(frozen=True)
class PlanTarget:
    """Where a plan was made: the pull request, its commit, and the folder Terraform ran in."""

    repository: str
    pull_request: int
    head_sha: str
    folder: str = ""


STATE_OF = text(
    "SELECT state_reference FROM repository_mapping WHERE tenant_id = :t AND repository = :repo "
    "AND folder = :folder ORDER BY state_reference"
)
WRITE_PLAN = text(
    "INSERT INTO terraform_plan (plan_id, tenant_id, repository, pull_request, head_sha, folder, "
    "state_reference, route, status, reason, format_version, terraform_version, received_at, "
    "as_of, collected_at) VALUES (:id, :t, :repo, :number, :head, :folder, :state, :route, "
    ":status, :reason, :format, :terraform, :now, :as_of, :now) "
    "ON CONFLICT ON CONSTRAINT uq_terraform_plan__commit DO NOTHING RETURNING plan_id"
)
HELD = text(
    "SELECT plan_id FROM terraform_plan WHERE tenant_id = :t AND repository = :repo "
    "AND pull_request = :number AND folder = :folder AND head_sha = :head"
)
WRITE_CHANGE = text(
    "INSERT INTO planned_change (plan_id, tenant_id, address, resource_type, actions, region, "
    "before, after, unknown, withheld) VALUES (:plan, :t, :address, :type, :actions, :region, "
    "CAST(:before AS jsonb), CAST(:after AS jsonb), :unknown, :withheld)"
)


def record_plan(
    connection: Any,
    tenant: UUID,
    target: PlanTarget,
    found: ReducedPlan | Unreadable,
    *,
    route: str,
    now: datetime,
) -> UUID:
    """The plan's identifier: newly recorded, or the one already held for its commit and folder.

    `as_of` is the plan's own timestamp where it carries one, and never later than its arrival,
    so a pipeline whose clock runs ahead cannot make a plan look fresher than Meter has it.
    """
    states = (
        connection.execute(
            STATE_OF, {"t": tenant, "repo": target.repository, "folder": target.folder}
        )
        .scalars()
        .all()
    )
    if isinstance(found, ReducedPlan):
        stamped = found.timestamp or now
        read: dict[str, Any] = {
            "status": "RECEIVED",
            "reason": None,
            "format": found.format_version,
            "terraform": found.terraform_version,
        }
        changes = found.changes
    else:
        stamped = now
        read = {"status": "REFUSED", "reason": found.reason, "format": None, "terraform": None}
        changes = ()
    written = connection.execute(
        WRITE_PLAN,
        {
            "id": uuid4(),
            "t": tenant,
            "repo": target.repository,
            "number": target.pull_request,
            "head": target.head_sha,
            "folder": target.folder,
            # A folder mapped to two states is not one Meter can compare against, so none.
            "state": states[0] if len(states) == 1 else None,
            "route": route,
            **read,
            "now": now,
            "as_of": min(stamped, now),
        },
    ).scalar()
    if written is None:
        held = connection.execute(
            HELD,
            {
                "t": tenant,
                "repo": target.repository,
                "number": target.pull_request,
                "folder": target.folder,
                "head": target.head_sha,
            },
        ).scalar_one()
        return UUID(str(held))
    rows = [
        {
            "plan": written,
            "t": tenant,
            "address": change.address,
            "type": change.resource_type,
            "actions": list(change.actions),
            "region": change.region,
            "before": json.dumps(change.before),
            "after": json.dumps(change.after),
            "unknown": list(change.unknown),
            "withheld": list(change.withheld),
        }
        for change in changes
    ]
    if rows:
        connection.execute(WRITE_CHANGE, rows)
    return UUID(str(written))
