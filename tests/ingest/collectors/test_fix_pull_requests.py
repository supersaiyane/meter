"""Opening each fix a person asked for. TASK-P15-004, FEAT-092 and FEAT-040, ISS-228.

The collector opens a removal in the folder the tenant mapped the resource's state to and moves
the recommendation to IN_PROGRESS; says why where it cannot, NOT_AUTHORED; fails a fix the host
will refuse again, typed; and leaves a fix the host throttled requested for the next run, without
asking about the rest.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core import errors
from finops_core.ports.pull_requests import RepositoryTarget
from finops_fakes.pull_requests import RecordingPullRequests
from finops_ingest.collectors.fix_pull_requests import COLLECTOR, FixPullRequestsCollector
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext, CollectorOutcome

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)
ACCOUNT = "fake-platform-a"
STATE = "s3://state-bucket/storage/terraform.tfstate"
TARGET = RepositoryTarget("acme/infra", "main", "storage")


def estate(
    engine: Engine,
    tenant: UUID,
    *,
    waste_class: str = "EBS_UNATTACHED",
    lifecycle: str = "ACCEPTED",
    managed: bool = True,
    mapped: bool = True,
    connected: bool = True,
) -> tuple[UUID, UUID]:
    """A recommendation a person asked to be fixed, and what the collector needs to open it."""
    recommendation, fix = uuid4(), uuid4()
    # Each recommendation its own volume, so two in one test are two resources.
    volume = f"arn:aws:ec2:eu-west-1:{ACCOUNT}:volume/vol-{recommendation.hex[:12]}"
    address = f"aws_ebs_volume.v{recommendation.hex[:12]}"
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, source, "
                "source_reference, waste_class, resource_id, region_id, "
                "estimated_monthly_saving, confidence, severity, observation_days, lifecycle, "
                "owner, rationale, as_of, collected_at) VALUES (:id, :t, :account, 'METER', :ref, "
                ":class, :resource, 'eu-west-1', :saving, 'HIGH', 'HIGH', 30, :lifecycle, "
                "'team-storage', 'unattached for 30 days', :at, :at)"
            ),
            {
                "id": recommendation,
                "t": tenant,
                "account": ACCOUNT,
                "ref": f"ref:{recommendation}",
                "class": waste_class,
                "resource": volume,
                "saving": Decimal("41.20"),
                "lifecycle": lifecycle,
                "at": NOW,
            },
        )
        if managed:
            connection.execute(
                text(
                    "INSERT INTO resource_management (management_id, tenant_id, ingest_run_id, "
                    "sub_account_id, provider_id, address, state_reference, as_of, collected_at) "
                    "VALUES (:id, :t, :run, :account, :resource, :address, :state, :at, :at)"
                ),
                {
                    "id": uuid4(),
                    "t": tenant,
                    "run": uuid4(),
                    "account": ACCOUNT,
                    "resource": volume,
                    "address": address,
                    "state": STATE,
                    "at": NOW,
                },
            )
        if mapped:
            connection.execute(
                text(
                    "INSERT INTO repository_mapping (tenant_id, state_reference, repository, "
                    "base_branch, folder, set_by) VALUES (:t, :state, 'acme/infra', 'main', "
                    "'storage', 'owner') ON CONFLICT DO NOTHING"
                ),
                {"t": tenant, "state": STATE},
            )
        if connected:
            connection.execute(
                text(
                    "INSERT INTO code_host_connection (tenant_id, host, app_id, key_secret_name, "
                    "connected_by) VALUES (:t, 'github', '1001', 'meter/test/codehost/app', "
                    "'owner') ON CONFLICT DO NOTHING"
                ),
                {"t": tenant},
            )
        connection.execute(
            text(
                "INSERT INTO fix_pull_request (fix_id, tenant_id, recommendation_id, "
                "sub_account_id, status, note, requested_by, requested_at, as_of, collected_at) "
                "VALUES (:fix, :t, :id, :account, 'REQUESTED', 'please', 'owner', :at, :at, :at)"
            ),
            {"fix": fix, "t": tenant, "id": recommendation, "account": ACCOUNT, "at": NOW},
        )
    return recommendation, fix


def run(engine: Engine, tenant: UUID, host: Any) -> CollectorOutcome:
    work = WorkUnit(
        tenant_id=tenant,
        collector=COLLECTOR,
        window_start=NOW - timedelta(minutes=10),
        window_end=NOW,
    )
    collector = FixPullRequestsCollector(lambda _context, _connected: host, clock=lambda: NOW)
    with engine.begin() as connection:
        return collector(CollectorContext(unit=work, connection=connection, run_id=uuid4()))


def fixed(engine: Engine, fix: UUID) -> Any:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT * FROM fix_pull_request WHERE fix_id = :fix"), {"fix": fix}
        ).one()


def steps(engine: Engine, fix: UUID) -> list[tuple[str, str, str]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT from_status, to_status, principal FROM fix_pull_request_event "
                "WHERE fix_id = :fix ORDER BY at"
            ),
            {"fix": fix},
        )
        return [(str(row[0]), str(row[1]), str(row[2])) for row in rows]


def lifecycle(engine: Engine, recommendation: UUID) -> str:
    with engine.connect() as connection:
        return str(
            connection.execute(
                text("SELECT lifecycle FROM recommendation WHERE recommendation_id = :id"),
                {"id": recommendation},
            ).scalar_one()
        )


class Refusing:
    """A code host that refuses every pull request with one typed cause."""

    def __init__(self, failure: Exception) -> None:
        self.failure = failure
        self.asked = 0

    def open_pull_request(self, _draft: Any, _target: Any) -> Any:
        self.asked += 1
        raise self.failure


def test_a_removal_opens_in_the_mapped_folder_and_the_recommendation_moves_on(
    engine: Engine, tenant_id: UUID
) -> None:
    recommendation, fix = estate(engine, tenant_id)
    host = RecordingPullRequests()
    assert run(engine, tenant_id, host).items_written == 1
    row = fixed(engine, fix)
    assert (row.status, row.repository, row.number) == ("OPEN", "acme/infra", 1)
    assert row.url == "https://code.example/acme/infra/pull/1"
    assert row.branch == f"meter/remediation/{recommendation}"
    assert host.targets == (TARGET,)
    (draft,) = host.drafts
    assert [one.path for one in draft.changes] == [f"storage/meter_remediation_{recommendation}.tf"]
    assert steps(engine, fix) == [("REQUESTED", "OPEN", "meter")]
    assert lifecycle(engine, recommendation) == "IN_PROGRESS"
    with engine.connect() as connection:
        actor = connection.execute(
            text(
                "SELECT actor FROM recommendation_event WHERE recommendation_id = :id "
                "AND to_lifecycle = 'IN_PROGRESS'"
            ),
            {"id": recommendation},
        ).scalar_one()
    assert actor == COLLECTOR
    # Opened, so the next run has nothing to ask the host.
    assert run(engine, tenant_id, host).items_written == 0
    assert len(host.drafts) == 1


@pytest.mark.parametrize(
    ("setting", "says"),
    [
        ({"mapped": False}, f"No repository is mapped for the state {STATE}"),
        ({"managed": False}, "FEAT-057"),
        ({"waste_class": "EBS_GP2_TO_GP3"}, "needs a new value"),
        ({"lifecycle": "DISMISSED"}, "DISMISSED now"),
    ],
)
def test_a_fix_with_nowhere_to_go_is_not_authored_and_says_why(
    engine: Engine, tenant_id: UUID, setting: dict[str, Any], says: str
) -> None:
    recommendation, fix = estate(engine, tenant_id, **setting)
    host = RecordingPullRequests()
    run(engine, tenant_id, host)
    row = fixed(engine, fix)
    assert row.status == "NOT_AUTHORED"
    assert says in row.reason
    assert host.drafts == ()
    assert steps(engine, fix) == [("REQUESTED", "NOT_AUTHORED", "meter")]
    assert lifecycle(engine, recommendation) == setting.get("lifecycle", "ACCEPTED")


def test_with_no_code_host_connected_every_ask_waits(engine: Engine, tenant_id: UUID) -> None:
    _recommendation, fix = estate(engine, tenant_id, connected=False)
    with pytest.raises(errors.Misconfigured, match="no code host is connected"):
        run(engine, tenant_id, RecordingPullRequests())
    assert fixed(engine, fix).status == "REQUESTED"
    assert steps(engine, fix) == []


def test_a_fix_the_host_will_refuse_again_fails_with_its_cause(
    engine: Engine, tenant_id: UUID
) -> None:
    recommendation, fix = estate(engine, tenant_id)
    refused = errors.AccessDenied(
        scope_key="github:acme/infra", collector=COLLECTOR, detail="the app may not do this here"
    )
    run(engine, tenant_id, Refusing(refused))
    row = fixed(engine, fix)
    assert (row.status, row.failure_cause) == ("FAILED", "AccessDenied")
    assert "may not do this" in row.reason
    assert lifecycle(engine, recommendation) == "ACCEPTED"


def test_a_throttled_host_leaves_the_fix_requested_and_asks_nothing_more(
    engine: Engine, tenant_id: UUID
) -> None:
    first = estate(engine, tenant_id)[1]
    second = estate(engine, tenant_id)[1]
    host = Refusing(errors.Throttled(scope_key="github", collector=COLLECTOR, detail="limit"))
    assert run(engine, tenant_id, host).items_written == 1
    assert host.asked == 1
    assert {fixed(engine, one).status for one in (first, second)} == {"REQUESTED"}
    waited = sorted(steps(engine, one) for one in (first, second))
    assert waited == [[], [("REQUESTED", "REQUESTED", "meter")]]
