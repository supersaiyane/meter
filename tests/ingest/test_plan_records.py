"""A plan recorded as Meter keeps it. TASK-P16-005, FEAT-095, spec sections 5.1 and 5.2.

What the reduction kept, and nothing more; a plan that could not be read, refused with the reason;
a plan received twice for one commit and folder, one plan; the folder's state from the mapping.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, text

from finops_ingest.plan_records import PlanTarget, record_plan
from finops_query.plan_reading import PlannedChange, ReducedPlan, Unreadable

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
TARGET = PlanTarget("acme/infra", 7, "abc1234def", "storage")
VOLUME = PlannedChange(
    address="aws_ebs_volume.data",
    resource_type="aws_ebs_volume",
    actions=("create",),
    region="eu-west-1",
    before={},
    after={"type": "gp3", "size": 100},
    unknown=("iops",),
)


def plan(*changes: PlannedChange, stamped: datetime | None = None) -> ReducedPlan:
    return ReducedPlan("1.2", "1.9.8", stamped, changes)


def recorded(engine: Engine, tenant: UUID, found: Any, target: PlanTarget = TARGET) -> UUID:
    with engine.begin() as connection:
        return record_plan(connection, tenant, target, found, route="test", now=NOW)


def row(engine: Engine, table: str, plan_id: UUID) -> Any:
    with engine.connect() as connection:
        return connection.execute(
            text(f"SELECT * FROM {table} WHERE plan_id = :p"), {"p": plan_id}
        ).all()


def mapped(engine: Engine, tenant: UUID, *states: str) -> None:
    with engine.begin() as connection:
        for state in states:
            connection.execute(
                text(
                    "INSERT INTO repository_mapping (tenant_id, state_reference, repository, "
                    "base_branch, folder, set_by) VALUES (:t, :s, 'acme/infra', 'main', "
                    "'storage', 'owner')"
                ),
                {"t": tenant, "s": state},
            )


def test_a_plan_keeps_what_the_reduction_kept_and_its_folders_state(
    engine: Engine, tenant_id: UUID
) -> None:
    mapped(engine, tenant_id, "s3://state/storage.tfstate")
    plan_id = recorded(engine, tenant_id, plan(VOLUME, stamped=NOW - timedelta(minutes=3)))
    (kept,) = row(engine, "terraform_plan", plan_id)
    assert (kept.status, kept.route, kept.format_version) == ("RECEIVED", "test", "1.2")
    assert kept.state_reference == "s3://state/storage.tfstate"
    assert (kept.as_of, kept.received_at) == (NOW - timedelta(minutes=3), NOW)
    (change,) = row(engine, "planned_change", plan_id)
    assert (change.address, change.actions, change.region) == (
        "aws_ebs_volume.data",
        ["create"],
        "eu-west-1",
    )
    assert change.after == {"type": "gp3", "size": 100}
    assert (change.unknown, change.withheld) == (["iops"], [])


def test_a_plan_received_twice_for_one_commit_and_folder_is_one_plan(
    engine: Engine, tenant_id: UUID
) -> None:
    first = recorded(engine, tenant_id, plan(VOLUME))
    again = recorded(engine, tenant_id, plan(VOLUME))
    assert again == first
    assert len(row(engine, "planned_change", first)) == 1
    newer = PlanTarget("acme/infra", 7, "0f0f0f0f", "storage")
    assert recorded(engine, tenant_id, plan(VOLUME), newer) != first


def test_a_plan_that_could_not_be_read_is_refused_with_the_reason(
    engine: Engine, tenant_id: UUID
) -> None:
    plan_id = recorded(engine, tenant_id, Unreadable("its format_version is 2.0; Meter reads 1.x"))
    (kept,) = row(engine, "terraform_plan", plan_id)
    assert (kept.status, kept.reason, kept.format_version) == (
        "REFUSED",
        "its format_version is 2.0; Meter reads 1.x",
        None,
    )
    assert row(engine, "planned_change", plan_id) == []


def test_a_folder_mapped_to_two_states_names_neither_and_a_clock_ahead_is_not_believed(
    engine: Engine, tenant_id: UUID
) -> None:
    mapped(engine, tenant_id, "s3://state/a.tfstate", "s3://state/b.tfstate")
    plan_id = recorded(engine, tenant_id, plan(VOLUME, stamped=NOW + timedelta(hours=1)))
    (kept,) = row(engine, "terraform_plan", plan_id)
    assert kept.state_reference is None
    assert kept.as_of == NOW
