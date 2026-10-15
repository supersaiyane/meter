"""Opening each fix a person asked for. TASK-P15-004, FEAT-092 and FEAT-040, ISS-228.

The collector opens a removal in the folder the tenant mapped the resource's state to and moves
the recommendation to IN_PROGRESS; says why where it cannot, NOT_AUTHORED; fails a fix the host
will refuse again, typed; and leaves a fix the host throttled requested for the next run, without
asking about the rest.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core import errors
from finops_core.domain.fixes import PullRequestState, Readiness
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
    iops: int | None = None,
    mibps: int | None = None,
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
                "owner, rationale, as_of, collected_at, target_iops, target_throughput_mibps) "
                "VALUES (:id, :t, :account, 'METER', :ref, :class, :resource, 'eu-west-1', "
                ":saving, 'HIGH', 'HIGH', 30, :lifecycle, 'team-storage', "
                "'unattached for 30 days', :at, :at, :iops, :mibps)"
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
                "iops": iops,
                "mibps": mibps,
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


def run(engine: Engine, tenant: UUID, host: Any, settings: Any = None) -> CollectorOutcome:
    work = WorkUnit(
        tenant_id=tenant,
        collector=COLLECTOR,
        window_start=NOW - timedelta(minutes=10),
        window_end=NOW,
    )
    collector = FixPullRequestsCollector(lambda _context, _connected: host, clock=lambda: NOW)
    with engine.begin() as connection:
        context = CollectorContext(
            unit=work, connection=connection, run_id=uuid4(), settings=settings
        )
        return collector(context)


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
        ({"waste_class": "RIGHTSIZE_INSTANCE"}, "needs a new value"),
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


# -- gp2 to gp3, an edit, TASK-P15-005 ---------------------------------------------------------


def declared(recommendation: UUID) -> str:
    """The storage folder's Terraform, declaring the recommendation's volume as gp2."""
    return (
        f'resource "aws_ebs_volume" "v{recommendation.hex[:12]}" {{\n'
        '  availability_zone = "eu-west-1a"\n'
        "  size              = 500\n"
        '  type              = "gp2"\n'
        "}\n"
    )


def test_a_gp2_volume_opens_as_an_edit_to_the_block_that_declares_it(
    engine: Engine, tenant_id: UUID
) -> None:
    recommendation, fix = estate(
        engine, tenant_id, waste_class="EBS_GP2_TO_GP3", iops=6000, mibps=250
    )
    host = RecordingPullRequests(
        {"storage/main.tf": declared(recommendation), "network/main.tf": "# another folder\n"}
    )
    run(engine, tenant_id, host)
    row = fixed(engine, fix)
    assert (row.status, row.number) == ("OPEN", 1)
    (draft,) = host.drafts
    assert draft.title.endswith("from gp2 to gp3")
    ((path, content),) = [(one.path, one.content) for one in draft.changes]
    assert path == "storage/main.tf"
    assert '  type              = "gp3"\n  iops              = 6000\n' in content
    assert "  throughput        = 250\n" in content
    assert lifecycle(engine, recommendation) == "IN_PROGRESS"


@pytest.mark.parametrize(
    ("iops", "mibps", "files", "says"),
    [
        (None, None, True, "does not record the IOPS"),
        (3000, 125, False, "No .tf file in the mapped folder declares"),
    ],
)
def test_a_gp2_volume_the_edit_cannot_make_is_not_authored_and_says_why(
    engine: Engine, tenant_id: UUID, iops: int | None, mibps: int | None, files: bool, says: str
) -> None:
    recommendation, fix = estate(
        engine, tenant_id, waste_class="EBS_GP2_TO_GP3", iops=iops, mibps=mibps
    )
    host = RecordingPullRequests({"storage/main.tf": declared(recommendation)} if files else {})
    run(engine, tenant_id, host)
    row = fixed(engine, fix)
    assert row.status == "NOT_AUTHORED"
    assert says in row.reason
    assert host.drafts == ()


# -- each pull request followed until the inventory sees it, TASK-P15-006 ---------------------

LATER = NOW + timedelta(hours=1)
INVENTORY_RUN = text(
    "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, idempotency_key, "
    "status, as_of_window_start, as_of_window_end) "
    "VALUES (:run, :t, 'inventory', 'scope', :key, 'SUCCEEDED', :at, :at)"
)
NODE = text(
    "INSERT INTO topology_node (node_id, tenant_id, ingest_run_id, sub_account_id, provider_id, "
    "node_kind, resource_type, region_id, availability_zone, name, tags, as_of, collected_at) "
    "VALUES (:node, :t, :run, :account, :resource, 'VOLUME', 'AWS::EC2::Volume', "
    "'eu-west-1', NULL, :resource, CAST('{}' AS jsonb), :at, :at)"
)
UNLISTED = text("DELETE FROM topology_node WHERE provider_id = :resource")
OBSERVED = text(
    "INSERT INTO volume_observation (tenant_id, sub_account_id, resource_id, region_id, "
    "volume_type, size_gib, as_of, collected_at) VALUES (:t, :account, :resource, 'eu-west-1', "
    ":type, 500, :at, :at)"
)


def volume_of(recommendation: UUID) -> str:
    return f"arn:aws:ec2:eu-west-1:{ACCOUNT}:volume/vol-{recommendation.hex[:12]}"


def opened(
    engine: Engine, tenant: UUID, **setting: Any
) -> tuple[UUID, UUID, RecordingPullRequests]:
    """A fix asked for and opened, as the first run leaves it."""
    recommendation, fix = estate(engine, tenant, **setting)
    host = RecordingPullRequests({"storage/main.tf": declared(recommendation)})
    run(engine, tenant, host)
    assert fixed(engine, fix).status == "OPEN"
    return recommendation, fix, host


def reported(
    host: RecordingPullRequests, *, still_open: bool, merged: bool, by: str | None = None
) -> None:
    host.set_state(
        "acme/infra",
        PullRequestState(
            number=1,
            url="https://code.example/acme/infra/pull/1",
            open=still_open,
            merged=merged,
            readiness=Readiness.READY if still_open else Readiness.UNKNOWN,
            head_sha="head-1",
            merged_by=by,
        ),
    )


def inventoried(engine: Engine, tenant: UUID, *resources: str) -> None:
    """An inventory read of the account after the merge, listing these resources."""
    run_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            INVENTORY_RUN, {"run": run_id, "t": tenant, "key": str(run_id), "at": LATER}
        )
        for resource in resources:
            connection.execute(
                NODE,
                {
                    "node": uuid4(),
                    "t": tenant,
                    "run": run_id,
                    "account": ACCOUNT,
                    "resource": resource,
                    "at": LATER,
                },
            )


def test_a_merge_is_recorded_with_whom_and_the_recommendation_waits_for_the_inventory(
    engine: Engine, tenant_id: UUID
) -> None:
    recommendation, fix, host = opened(engine, tenant_id)
    reported(host, still_open=False, merged=True, by="octocat")
    assert run(engine, tenant_id, host).items_written == 1
    row = fixed(engine, fix)
    assert (row.status, row.merged_by, row.merged_at) == ("MERGED", "octocat", NOW)
    assert steps(engine, fix)[-1] == ("OPEN", "MERGED", "octocat")
    assert lifecycle(engine, recommendation) == "IN_PROGRESS"


def test_a_pull_request_closed_without_merging_returns_the_recommendation(
    engine: Engine, tenant_id: UUID
) -> None:
    recommendation, fix, host = opened(engine, tenant_id)
    reported(host, still_open=False, merged=False)
    run(engine, tenant_id, host)
    row = fixed(engine, fix)
    assert (row.status, row.closed_at) == ("CLOSED", NOW)
    assert steps(engine, fix)[-1] == ("OPEN", "CLOSED", "github")
    assert lifecycle(engine, recommendation) == "ACCEPTED"
    with engine.connect() as connection:
        said = connection.execute(
            text(
                "SELECT reason FROM recommendation_event WHERE recommendation_id = :id "
                "AND to_lifecycle = 'ACCEPTED'"
            ),
            {"id": recommendation},
        ).scalar_one()
    assert "closed without merging" in said


def test_an_open_pull_request_is_left_as_it_is(engine: Engine, tenant_id: UUID) -> None:
    _recommendation, fix, host = opened(engine, tenant_id)
    assert run(engine, tenant_id, host).items_written == 0
    assert fixed(engine, fix).status == "OPEN"
    assert steps(engine, fix) == [("REQUESTED", "OPEN", "meter")]


def test_a_merged_removal_is_done_once_the_inventory_no_longer_lists_it(
    engine: Engine, tenant_id: UUID
) -> None:
    recommendation, fix, host = opened(engine, tenant_id)
    reported(host, still_open=False, merged=True, by="octocat")
    run(engine, tenant_id, host)
    # Read after the merge and still listed: not done.
    inventoried(engine, tenant_id, volume_of(recommendation))
    run(engine, tenant_id, host)
    assert lifecycle(engine, recommendation) == "IN_PROGRESS"
    with engine.begin() as connection:
        connection.execute(UNLISTED, {"resource": volume_of(recommendation)})
    inventoried(engine, tenant_id, f"arn:aws:ec2:eu-west-1:{ACCOUNT}:volume/vol-other")
    run(engine, tenant_id, host)
    assert lifecycle(engine, recommendation) == "DONE"
    assert steps(engine, fix)[-1] == ("MERGED", "MERGED", "meter")


def test_a_merged_gp3_edit_is_done_once_the_volume_reads_gp3(
    engine: Engine, tenant_id: UUID
) -> None:
    recommendation, _fix, host = opened(
        engine, tenant_id, waste_class="EBS_GP2_TO_GP3", iops=3000, mibps=125
    )
    reported(host, still_open=False, merged=True, by="octocat")
    run(engine, tenant_id, host)
    observed = {"t": tenant_id, "account": ACCOUNT, "resource": volume_of(recommendation)}
    with engine.begin() as connection:
        connection.execute(OBSERVED, {**observed, "type": "gp2", "at": LATER})
    run(engine, tenant_id, host)
    assert lifecycle(engine, recommendation) == "IN_PROGRESS"
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE volume_observation SET volume_type = 'gp3' WHERE resource_id = :resource"),
            observed,
        )
    run(engine, tenant_id, host)
    assert lifecycle(engine, recommendation) == "DONE"


def test_a_pull_request_the_host_no_longer_knows_fails_with_its_cause(
    engine: Engine, tenant_id: UUID
) -> None:
    _recommendation, fix, _host = opened(engine, tenant_id)
    run(engine, tenant_id, RecordingPullRequests())
    row = fixed(engine, fix)
    assert (row.status, row.failure_cause) == ("FAILED", "Misconfigured")
    assert steps(engine, fix)[-1] == ("OPEN", "FAILED", "meter")


# -- Meter's merge under the policy, TASK-P15-007, ADR-0038 -----------------------------------

MERGING = SimpleNamespace(feature_pull_request_merge=True)
NOT_MERGING = SimpleNamespace(feature_pull_request_merge=False)


def named(engine: Engine, tenant: UUID, *classes: str) -> None:
    with engine.begin() as connection:
        for waste_class in classes:
            connection.execute(
                text(
                    "INSERT INTO merge_policy (tenant_id, waste_class, reason, set_by) "
                    "VALUES (:t, :class, 'reversible, so merged when the checks pass', 'owner')"
                ),
                {"t": tenant, "class": waste_class},
            )


def ready(host: RecordingPullRequests, readiness: Readiness = Readiness.READY) -> None:
    host.set_state(
        "acme/infra",
        PullRequestState(
            number=1,
            url="https://code.example/acme/infra/pull/1",
            open=True,
            merged=False,
            readiness=readiness,
            head_sha="head-1",
        ),
    )


GP3_FIX = {"waste_class": "EBS_GP2_TO_GP3", "iops": 3000, "mibps": 125}


def test_meter_merges_a_ready_gp3_fix_the_policy_names_and_says_why(
    engine: Engine, tenant_id: UUID
) -> None:
    recommendation, fix, host = opened(engine, tenant_id, **GP3_FIX)
    named(engine, tenant_id, "EBS_GP2_TO_GP3")
    ready(host)
    run(engine, tenant_id, host, MERGING)
    row = fixed(engine, fix)
    assert (row.status, row.merged_by) == ("MERGED", "meter")
    assert host.merges == [("acme/infra", 1, "head-1")]
    assert steps(engine, fix)[-1] == ("OPEN", "MERGED", "meter")
    with engine.connect() as connection:
        note = connection.execute(
            text(
                "SELECT note FROM fix_pull_request_event WHERE fix_id = :fix "
                "AND to_status = 'MERGED'"
            ),
            {"fix": fix},
        ).scalar_one()
    assert "merge policy names EBS_GP2_TO_GP3" in note
    # Merged is not done: the volume must read gp3 first.
    assert lifecycle(engine, recommendation) == "IN_PROGRESS"


@pytest.mark.parametrize(
    ("fix_class", "policy", "settings", "readiness"),
    [
        (GP3_FIX, (), MERGING, Readiness.READY),
        (GP3_FIX, ("EBS_GP2_TO_GP3",), NOT_MERGING, Readiness.READY),
        (GP3_FIX, ("EBS_GP2_TO_GP3",), None, Readiness.READY),
        (GP3_FIX, ("EBS_GP2_TO_GP3",), MERGING, Readiness.WAITING),
        (GP3_FIX, ("EBS_GP2_TO_GP3",), MERGING, Readiness.BLOCKED),
        ({}, ("EBS_GP2_TO_GP3",), MERGING, Readiness.READY),
    ],
)
def test_nothing_is_merged_unless_every_condition_holds(
    engine: Engine,
    tenant_id: UUID,
    fix_class: dict[str, Any],
    policy: tuple[str, ...],
    settings: Any,
    readiness: Readiness,
) -> None:
    _recommendation, fix, host = opened(engine, tenant_id, **fix_class)
    named(engine, tenant_id, *policy)
    ready(host, readiness)
    run(engine, tenant_id, host, settings)
    assert host.merges == []
    assert fixed(engine, fix).status == "OPEN"


def test_a_merge_the_host_refuses_is_recorded_once_and_left_for_a_person(
    engine: Engine, tenant_id: UUID
) -> None:
    _recommendation, fix, host = opened(engine, tenant_id, **GP3_FIX)
    named(engine, tenant_id, "EBS_GP2_TO_GP3")
    ready(host)
    host.refuse_merges = "Required status check plan is expected."
    run(engine, tenant_id, host, MERGING)
    run(engine, tenant_id, host, MERGING)
    assert fixed(engine, fix).status == "OPEN"
    assert len(host.merges) == 2
    assert steps(engine, fix)[1:] == [("OPEN", "OPEN", "meter")]
