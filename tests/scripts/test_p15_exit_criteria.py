"""P15's exit criteria, read over the seeded demo. TASK-P15-009, spec section 13.

The local stack is seeded by `scripts/demo/seed_demo.py`: the GitHub App connected, two of the fake
estate's Terraform states mapped and one left with nowhere to go, gp2 to gp3 named in the merge
policy, and a fix in every status. Each criterion is read here as a person meets it, through the
routes a screen reads, and with the `fix_pull_requests` collector run against the strict fake
GitHub, since only the worker reaches the real one and no app is installed yet, ISS-300.

Criterion 5 is held where it is decided: the key's path and the one role that reads it by
`tests/providers/aws/test_secrets.py`, a token minted per request and never in a detail by
`tests/providers/github/test_github_app.py`, and GitHub as a host only the worker's code names by
`tests/contract/test_network_paths.py`. Here, that no P15 table could hold a key or a token, and
that the connection's route answers with the secret's name alone. Criterion 6's screens are held by
`RecommendationFix.test.tsx`, `FixSettingsScreen.test.tsx` and `e2e/fixes.spec.ts`; here, the
seeded fixes through the route and a narrowed person refused where the organization's scope is
needed. That FEAT-029 verifies a DONE recommendation is held by its own suite,
`tests/ingest/collectors/test_realized_savings.py`; here, that the merged fix's recommendation
reaches DONE and not before.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_api.db import models
from finops_core.config import Settings
from finops_core.domain.fixes import PullRequestState, Readiness
from finops_core.domain.tenant import Scope
from finops_fakes.pull_requests import RecordingPullRequests
from finops_fakes.terraform_state import NETWORK, PLATFORM
from finops_ingest.collectors.fix_pull_requests import COLLECTOR, FixPullRequestsCollector
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext
from tests.api.test_query_routes import auth, client_for
from tests.api.test_waste_routes import get, only
from tests.scripts.test_seed_demo import DEMO_TENANT, _now, seed_demo

pytestmark = pytest.mark.integration

OWNER = "owner@example.local"
MERGING = SimpleNamespace(feature_pull_request_merge=True)
INSTANCE = "amazonec2/fake-platform-a/0001"
REPOSITORY = seed_demo.DEMO_REPOSITORY


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """The seed bills months into partitions, so this module gives them back. ISS-268."""


@pytest.fixture
def demo(engine: Engine, settings: Settings) -> Iterator[Callable[[], Any]]:
    seed_demo.seed(engine, settings, _now())
    person = Scope(tenant_id=DEMO_TENANT, is_global=True, accounts=frozenset(), principal_id=OWNER)
    client, token = client_for(engine, person, settings)
    try:
        yield lambda: (client, token)
    finally:
        seed_demo.remove(engine)


def follow(engine: Engine, host: Any, settings: Any = None) -> None:
    """One run of the collector over the demo tenant, as the worker makes it."""
    now = _now()
    work = WorkUnit(
        tenant_id=DEMO_TENANT,
        collector=COLLECTOR,
        window_start=now - timedelta(minutes=10),
        window_end=now,
    )
    with engine.begin() as connection:
        FixPullRequestsCollector(lambda _c, _connected: host, clock=_now)(
            CollectorContext(unit=work, connection=connection, run_id=uuid4(), settings=settings)
        )


def managed(engine: Engine, state: str, waste_class: str, *, figures: bool = False) -> UUID:
    """An accepted recommendation for a resource the given Terraform state manages."""
    recommendation = uuid4()
    resource = f"vol-{recommendation.hex[:12]}" if waste_class == "EBS_GP2_TO_GP3" else INSTANCE
    with engine.begin() as connection:
        account = connection.execute(
            text(
                "SELECT sub_account_id FROM resource_management WHERE tenant_id = :t "
                "AND provider_id = :r"
            ),
            {"t": DEMO_TENANT, "r": INSTANCE},
        ).scalar_one()
        if resource != INSTANCE:
            connection.execute(
                text(
                    "INSERT INTO resource_management (management_id, tenant_id, ingest_run_id, "
                    "sub_account_id, provider_id, address, state_reference, as_of, collected_at) "
                    "VALUES (:id, :t, :run, :account, :r, :address, :state, :now, :now)"
                ),
                {
                    "id": uuid4(),
                    "t": DEMO_TENANT,
                    "run": uuid4(),
                    "account": account,
                    "r": resource,
                    "address": f"aws_ebs_volume.v{recommendation.hex[:12]}",
                    "state": state,
                    "now": _now(),
                },
            )
        connection.execute(
            text(
                "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, source, "
                "source_reference, waste_class, resource_id, region_id, "
                "estimated_monthly_saving, confidence, severity, observation_days, lifecycle, "
                "owner, rationale, as_of, collected_at, target_iops, target_throughput_mibps) "
                "VALUES (:id, :t, :account, 'METER', :ref, :class, :r, 'us-fake-1', 12.40, 'HIGH', "
                "'LOW', 30, 'ACCEPTED', 'platform', 'the proof''s own finding', :now, :now, :iops, "
                ":mibps)"
            ),
            {
                "id": recommendation,
                "t": DEMO_TENANT,
                "account": account,
                "ref": f"proof:{recommendation}",
                "class": waste_class,
                "r": resource,
                "now": _now(),
                "iops": 3000 if figures else None,
                "mibps": 125 if figures else None,
            },
        )
    return recommendation


def ask(client: Any, token: str, recommendation: UUID) -> int:
    path = f"/api/v1/waste/recommendations/{recommendation}/pull-request"
    return int(client.post(path, json={"note": "agreed"}, headers=auth(token)).status_code)


def fix_of(engine: Engine, recommendation: UUID) -> Any:
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT * FROM fix_pull_request WHERE recommendation_id = :id "
                "ORDER BY requested_at DESC LIMIT 1"
            ),
            {"id": recommendation},
        ).one()


def lifecycle(engine: Engine, recommendation: UUID) -> str:
    with engine.connect() as connection:
        return str(
            connection.execute(
                text("SELECT lifecycle FROM recommendation WHERE recommendation_id = :id"),
                {"id": recommendation},
            ).scalar_one()
        )


def declaring(recommendation: UUID, kind: str = '"gp2"') -> str:
    return (
        f'resource "aws_ebs_volume" "v{recommendation.hex[:12]}" {{\n'
        '  availability_zone = "us-fake-1a"\n'
        "  size              = 500\n"
        f"  type              = {kind}\n"
        "}\n"
    )


def ready(host: RecordingPullRequests, number: int, *, merged: bool = False) -> None:
    host.set_state(
        REPOSITORY,
        PullRequestState(
            number=number,
            url=f"https://code.example/{REPOSITORY}/pull/{number}",
            open=not merged,
            merged=merged,
            readiness=Readiness.READY,
            head_sha=f"head-{number}",
            merged_by="platform-lead" if merged else None,
        ),
    )


def test_1_a_removal_opens_one_pull_request_in_the_mapped_repository(
    engine: Engine, demo: Callable[[], Any]
) -> None:
    client, token = demo()
    recommendation = managed(engine, PLATFORM, "IDLE_INSTANCE")
    host = RecordingPullRequests()
    assert ask(client, token, recommendation) == 200
    follow(engine, host)
    assert fix_of(engine, recommendation).status == "OPEN"
    (target,) = host.targets
    assert (target.repository, target.folder) == (REPOSITORY, "platform")
    (draft,) = host.drafts
    assert [one.path for one in draft.changes] == [
        f"platform/meter_remediation_{recommendation}.tf"
    ]
    # Asked again: refused while one is open, and the host is asked for nothing new.
    assert ask(client, token, recommendation) == 409
    follow(engine, host)
    assert len(host.drafts) == 1


def test_2_gp2_to_gp3_edits_the_declaring_file_and_a_variable_type_is_refused(
    engine: Engine, demo: Callable[[], Any]
) -> None:
    client, token = demo()
    literal = managed(engine, NETWORK, "EBS_GP2_TO_GP3", figures=True)
    variable = managed(engine, NETWORK, "EBS_GP2_TO_GP3", figures=True)
    host = RecordingPullRequests(
        {
            "network/volumes.tf": declaring(literal),
            "network/more.tf": declaring(variable, "var.kind"),
        }
    )
    assert ask(client, token, literal) == 200
    assert ask(client, token, variable) == 200
    follow(engine, host)
    assert fix_of(engine, literal).status == "OPEN"
    ((path, content),) = [(one.path, one.content) for one in host.drafts[0].changes]
    assert path == "network/volumes.tf"
    assert '  type              = "gp3"\n' in content
    refused = fix_of(engine, variable)
    assert refused.status == "NOT_AUTHORED"
    assert "set by var.kind" in refused.reason


def test_3_meter_merges_a_ready_gp3_fix_under_the_policy_and_no_deletion(
    engine: Engine, demo: Callable[[], Any]
) -> None:
    client, token = demo()
    gp3 = managed(engine, NETWORK, "EBS_GP2_TO_GP3", figures=True)
    removal = managed(engine, PLATFORM, "IDLE_INSTANCE")
    host = RecordingPullRequests({"network/volumes.tf": declaring(gp3)})
    assert ask(client, token, gp3) == 200
    assert ask(client, token, removal) == 200
    follow(engine, host)
    for recommendation in (gp3, removal):
        ready(host, int(fix_of(engine, recommendation).number))
    # The flag off: nothing merges, whatever the seeded policy names.
    follow(engine, host, SimpleNamespace(feature_pull_request_merge=False))
    assert host.merges == []
    follow(engine, host, MERGING)
    merged = fix_of(engine, gp3)
    assert (merged.status, merged.merged_by) == ("MERGED", "meter")
    # A deletion is never merged, whatever the policy says.
    assert fix_of(engine, removal).status == "OPEN"
    assert [one[1] for one in host.merges] == [merged.number]


def test_3_with_the_policy_empty_nothing_is_merged(engine: Engine, demo: Callable[[], Any]) -> None:
    client, token = demo()
    gp3 = managed(engine, NETWORK, "EBS_GP2_TO_GP3", figures=True)
    host = RecordingPullRequests({"network/volumes.tf": declaring(gp3)})
    emptied = client.put(
        "/api/v1/remediation/merge-policy",
        json={"classes": [], "reason": "nothing merged while we watch"},
        headers=auth(token),
    )
    assert emptied.status_code == 200
    assert ask(client, token, gp3) == 200
    follow(engine, host)
    ready(host, int(fix_of(engine, gp3).number))
    follow(engine, host, MERGING)
    assert host.merges == []
    assert fix_of(engine, gp3).status == "OPEN"


def test_4_a_merged_fix_is_in_progress_until_the_inventory_sees_it_then_done(
    engine: Engine, demo: Callable[[], Any]
) -> None:
    client, token = demo()
    gp3 = managed(engine, NETWORK, "EBS_GP2_TO_GP3", figures=True)
    host = RecordingPullRequests({"network/volumes.tf": declaring(gp3)})
    assert ask(client, token, gp3) == 200
    follow(engine, host)
    ready(host, int(fix_of(engine, gp3).number), merged=True)
    follow(engine, host)
    assert fix_of(engine, gp3).status == "MERGED"
    assert lifecycle(engine, gp3) == "IN_PROGRESS"
    later = _now() + timedelta(hours=1)
    with engine.begin() as connection:
        account = connection.execute(
            text("SELECT sub_account_id FROM recommendation WHERE recommendation_id = :id"),
            {"id": gp3},
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO volume_observation (tenant_id, sub_account_id, resource_id, "
                "region_id, volume_type, size_gib, as_of, collected_at) VALUES (:t, :account, "
                ":r, 'us-fake-1', 'gp3', 500, :at, :at)"
            ),
            {"t": DEMO_TENANT, "account": account, "r": f"vol-{gp3.hex[:12]}", "at": later},
        )
    follow(engine, host)
    assert lifecycle(engine, gp3) == "DONE"


def test_5_no_p15_table_could_hold_a_key_or_a_token(demo: Callable[[], Any]) -> None:
    client, token = demo()
    tables = (
        models.code_host_connection,
        models.repository_mapping,
        models.fix_pull_request,
        models.fix_pull_request_event,
        models.merge_policy,
    )
    named = {column.name for table in tables for column in table.columns}
    assert {name for name in named if "token" in name or "key" in name} == {"key_secret_name"}
    found = get(client, token, "/api/v1/remediation/connection")["data"]
    assert found["key_secret_name"].split("/")[2] == "codehost"


def test_6_the_seeded_fixes_read_in_every_status_and_a_narrowed_person_is_refused(
    engine: Engine, settings: Settings, demo: Callable[[], Any]
) -> None:
    client, token = demo()
    fixes = get(client, token, "/api/v1/remediation/pull-requests")["data"]["fixes"]
    assert {one["status"] for one in fixes} == set(seed_demo.DEMO_FIX_STATUSES)
    assert all(one["steps"] for one in fixes)
    mapped = get(client, token, "/api/v1/remediation/repositories")["data"]
    assert {one["state_reference"] for one in mapped["mappings"]} == {NETWORK, PLATFORM}
    # The third state's backend refuses the fake read, so no resource names it to be unmapped.
    assert mapped["unmapped"] == []
    narrowed = only(DEMO_TENANT, "fake-product-a")
    scope = Scope(
        tenant_id=DEMO_TENANT, is_global=False, accounts=narrowed.accounts, principal_id=OWNER
    )
    client, token = client_for(engine, scope, settings)
    for path in ("connection", "repositories", "merge-policy"):
        assert client.get(f"/api/v1/remediation/{path}", headers=auth(token)).status_code == 404
