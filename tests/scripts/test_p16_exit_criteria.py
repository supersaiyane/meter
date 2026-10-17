"""P16's exit criteria, read over the seeded demo. TASK-P16-009, spec section 13.

The local stack is seeded by `scripts/demo/seed_demo.py` with `finops_fakes.plans`: a plan in every
status in the fake estate's repository, comments written by the `plan_comments` collector against
a fake GitHub, and a comparison in every verdict. Each criterion is read here as a person meets it,
through the routes a screen reads, or by running the collectors the worker runs.

Criterion 1 prices one plan holding every type spec section 5.3 names against one catalog: the
compute and EBS shelf of `tests/query/test_plan_pricing.py` and AWS's own eu-west-1 rows of
`tests/query/test_plan_services.py`, every service read through the real price list adapter.
Criterion 2 stores the plan `tests/query/test_plan_reading.py` plants a value in, and finds it in
no table. Criterion 4's collector is proven against the database by
`tests/ingest/collectors/test_estimate_comparison.py`; here, its verdicts as the demo shows them.
Criterion 5's screen is held by `EstimatesScreen.test.tsx` and `e2e/estimates.spec.ts`.

Criterion 6, a plan arriving from a repository's pipeline, waits on OPEN-44, held by the owner, and
is TASK-P16-010's. Until it is answered the demo records its plans with `record_plan`, the call the
route will make.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_core.domain.fixes import PullRequestState, Readiness
from finops_core.domain.tenant import Scope
from finops_fakes import fixtures
from finops_fakes.pull_requests import RecordingPullRequests
from finops_ingest.collectors.estimate_comparison import UNSEEN
from finops_ingest.collectors.plan_comments import PlanCommentsCollector
from finops_ingest.collectors.plan_estimates import PlanEstimatesCollector
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.plan_records import PlanTarget, record_plan
from finops_ingest.registry import CollectorContext
from finops_query.estimate_comment import marker
from finops_query.plan_pricing import price_plan
from finops_query.plan_quotes import Catalogue, Quote
from finops_query.plan_reading import PlannedChange, ReducedPlan, reduce_plan
from tests.api.test_query_routes import auth, client_for
from tests.api.test_waste_routes import get, only
from tests.query.test_plan_pricing import SHELF
from tests.query.test_plan_reading import SECRET, planted
from tests.query.test_plan_services import GP3_DISK, ROWS, VALKEY, database, search
from tests.scripts.test_seed_demo import DEMO_TENANT, _now, seed_demo

pytestmark = pytest.mark.integration

OWNER = "owner@example.local"
REPOSITORY = seed_demo.DEMO_REPOSITORY
PLANS = "/api/v1/estimates"
ACCURACY = "/api/v1/estimates/accuracy"
SIX = {
    "aws_instance",
    "aws_ebs_volume",
    "aws_db_instance",
    "aws_elasticache_replication_group",
    "aws_redshift_cluster",
    "aws_opensearch_domain",
}


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


def run(engine: Engine, collector: Any, name: str) -> None:
    """One run of a collector over the demo tenant, as the worker makes it."""
    now = _now()
    start = now - timedelta(minutes=10)
    work = WorkUnit(tenant_id=DEMO_TENANT, collector=name, window_start=start, window_end=now)
    with engine.begin() as connection:
        collector(CollectorContext(unit=work, connection=connection, run_id=uuid4()))


def record(engine: Engine, number: int, head: str, folder: str, found: Any) -> None:
    target = PlanTarget(REPOSITORY, number, head, folder)
    with engine.begin() as connection:
        record_plan(connection, DEMO_TENANT, target, found, route="test", now=_now())


def estimates(engine: Engine, number: int) -> dict[str, Any]:
    """Each plan of a pull request by its head: its status and its comment."""
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT p.head_sha, p.folder, p.status, e.comment_status, e.comment_id, "
                "e.comment_reason, e.comment_failure_cause FROM terraform_plan p LEFT JOIN "
                "plan_estimate e ON e.plan_id = p.plan_id WHERE p.tenant_id = :t "
                "AND p.pull_request = :n"
            ),
            {"t": DEMO_TENANT, "n": number},
        ).all()
    return {row.head_sha: row for row in rows}


class OneCatalogue:
    """Compute and EBS from the test shelf, the managed services from AWS's real rows."""

    def instance_hour(self, region: str, instance_type: str) -> Quote | str:
        return SHELF.instance_hour(region, instance_type)

    def volume_month(self, region: str, volume_type: str, term: str) -> Quote | str:
        return SHELF.volume_month(region, volume_type, term)

    def service_price(
        self, service: str, region: str, attributes: Mapping[str, str], term: str
    ) -> Quote | str:
        return ROWS.service_price(service, region, attributes, term)


def created(
    address: str,
    after: Mapping[str, Any] | None = None,
    *,
    region: str = "eu-west-1",
    unknown: tuple[str, ...] = (),
) -> PlannedChange:
    kind = address.split(".")[0]
    return PlannedChange(address, kind, ("create",), region, {}, after or {}, unknown=unknown)


def test_criterion_1_every_type_is_priced_from_the_catalog_and_what_cannot_be_says_why() -> None:
    catalogue: Catalogue = OneCatalogue()
    plan = ReducedPlan(
        "1.2",
        "1.9.8",
        None,
        (
            created("aws_instance.web", {"instance_type": "m6i.large"}),
            created("aws_ebs_volume.data", {"type": "gp3", "size": 100}),
            created("aws_db_instance.main", database()),
            created("aws_elasticache_replication_group.cache", {**VALKEY, "num_cache_clusters": 2}),
            created(
                "aws_redshift_cluster.warehouse",
                {"node_type": "ra3.xlplus", "cluster_type": "multi-node", "number_of_nodes": 2},
            ),
            created("aws_opensearch_domain.search", search({}, GP3_DISK)),
            created("aws_nat_gateway.out"),
            created("aws_instance.elsewhere", {"instance_type": "m6i.large"}, region="xx-none-1"),
            created("aws_instance.later", unknown=("instance_type",)),
        ),
    )
    estimate = price_plan(plan, catalogue)

    priced = [line for line in estimate.lines if line.priced]
    assert {line.resource_type for line in priced} == SIX
    for line in priced:
        assert line.after is not None and line.after.components, line.address
        for part in line.after.components:
            assert part.monthly == part.quantity * part.quote.unit_price, part.what
            if part.quote.unit.lower() == "hrs":
                assert part.quantity % 730 == 0, part.what

    refused = {line.address: line for line in estimate.unpriced}
    assert set(refused) == {"aws_nat_gateway.out", "aws_instance.elsewhere", "aws_instance.later"}
    for line in refused.values():
        assert line.reason and (line.before, line.after) == (None, None), line.address
    assert "xx-none-1" in str(refused["aws_instance.elsewhere"].reason)
    assert "instance_type" in str(refused["aws_instance.later"].reason)


@pytest.mark.usefixtures("demo")
def test_criterion_2_a_value_planted_in_every_dropped_field_is_stored_in_no_table(
    engine: Engine,
) -> None:
    found = reduce_plan(planted())
    assert isinstance(found, ReducedPlan)
    record(engine, 40, "1234567abcdef", "network", found)
    run(engine, PlanEstimatesCollector(clock=_now), "plan_estimates")

    with engine.connect() as connection:
        tables = list(
            connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )
        holding = [
            table
            for table in sorted(tables)
            if connection.execute(
                text(
                    f'SELECT count(*) FROM "{table}" AS r '
                    "WHERE CAST(row_to_json(r) AS text) LIKE :needle"
                ),
                {"needle": f"%{SECRET}%"},
            ).scalar_one()
        ]
        kept = connection.execute(
            text(
                "SELECT count(*) FROM planned_change c JOIN terraform_plan p ON "
                "p.plan_id = c.plan_id WHERE p.tenant_id = :t AND p.pull_request = 40"
            ),
            {"t": DEMO_TENANT},
        ).scalar_one()
    assert holding == []
    assert kept == 3, "the database, the instance and the policy are kept, without the value"


@pytest.mark.usefixtures("demo")
def test_criterion_3_one_comment_per_folder_edited_for_the_head_and_left_for_an_older_commit(
    engine: Engine,
) -> None:
    seeded = estimates(engine, 31)
    assert seeded["b2c3d4e5f6a7"].comment_status == "WRITTEN"
    assert seeded["a1b2c3d4e5f6"].comment_status == "SUPERSEDED"
    assert seeded["a1b2c3d4e5f6"].comment_reason
    failed = estimates(engine, 33)["d4e5f6a7b8c9"]
    assert (failed.comment_status, failed.comment_failure_cause) == ("FAILED", "Misconfigured")

    head = "9f8e7d6c5b4a"
    host = RecordingPullRequests()
    host.set_state(
        REPOSITORY,
        PullRequestState(
            number=31,
            url=f"https://code.example/{REPOSITORY}/pull/31",
            open=True,
            merged=False,
            readiness=Readiness.WAITING,
            head_sha=head,
        ),
    )
    earlier = host.write_comment(REPOSITORY, 31, marker("platform"), marker("platform") + "\nold")
    change = created("aws_instance.web", {"instance_type": "m5.large"}, region=fixtures.REGION)
    for folder in ("platform", "network"):
        record(engine, 31, head, folder, ReducedPlan("1.2", "1.9.5", None, (change,)))
    run(engine, PlanEstimatesCollector(clock=_now), "plan_estimates")
    commenter = PlanCommentsCollector(lambda _context, _connected: host, clock=_now)
    run(engine, commenter, "plan_comments")

    bodies = host.comments_on(REPOSITORY, 31)
    assert len(bodies) == 2, "one comment per folder"
    with engine.connect() as connection:
        platform = connection.execute(
            text(
                "SELECT e.comment_id FROM plan_estimate e JOIN terraform_plan p ON "
                "p.plan_id = e.plan_id WHERE p.tenant_id = :t AND p.pull_request = 31 "
                "AND p.head_sha = :h AND p.folder = 'platform'"
            ),
            {"t": DEMO_TENANT, "h": head},
        ).scalar_one()
    assert platform == earlier.comment_id, "the folder's comment is edited, not written again"
    for body in bodies:
        assert "list prices" in body and "effective" not in body.lower()

    older = ReducedPlan("1.2", "1.9.5", None, (change,))
    record(engine, 31, "5a6b7c8d9e0f", "platform", older)
    run(engine, PlanEstimatesCollector(clock=_now), "plan_estimates")
    run(engine, commenter, "plan_comments")
    assert host.comments_on(REPOSITORY, 31) == bodies, "an older commit leaves the comment alone"
    assert estimates(engine, 31)["5a6b7c8d9e0f"].comment_status == "SUPERSEDED"


def test_criterion_4_created_resources_are_compared_at_list_and_accuracy_is_by_type(
    demo: Callable[[], Any],
) -> None:
    client, token = demo()
    accuracy = get(client, token, ACCURACY)["data"]
    by_type = [(one["resource_type"], one["compared"], one["within"]) for one in accuracy["types"]]
    assert by_type == [("aws_ebs_volume", 1, 0), ("aws_instance", 2, 1), ("all", 3, 1)]
    assert (accuracy["pending"], accuracy["not_compared"]) == (1, 1)

    plans = get(client, token, PLANS)["data"]["plans"]
    merged = next(one for one in plans if one["pull_request"] == 32)
    detail = get(client, token, f"{PLANS}/{merged['plan_id']}")["data"]
    lines = {one["address"]: one["comparison"] for one in detail["lines"]}
    assert {address: line["verdict"] for address, line in lines.items()} == {
        "aws_instance.api": "WITHIN",
        "aws_instance.batch": "ABOVE",
        "aws_ebs_volume.logs": "BELOW",
        "aws_instance.gone": "NOT_COMPARED",
    }
    within = lines["aws_instance.api"]
    assert Decimal(within["effective_monthly"]) < Decimal(within["list_monthly"])
    gone = lines["aws_instance.gone"]
    assert (gone["reason"], gone["list_monthly"]) == (UNSEEN, None)


def test_criterion_5_the_organization_reads_every_estimate_and_a_narrowed_person_is_refused(
    engine: Engine, settings: Settings, demo: Callable[[], Any]
) -> None:
    client, token = demo()
    listed = get(client, token, PLANS)["data"]["plans"]
    assert {one["status"] for one in listed} == {"RECEIVED", "PRICED", "REFUSED"}
    assert {one["comment_status"] for one in listed} >= {"WRITTEN", "SUPERSEDED", "FAILED"}
    head = next(one for one in listed if one["head_sha"] == "b2c3d4e5f6a7")
    first, *_ = get(client, token, f"{PLANS}/{head['plan_id']}")["data"]["lines"]
    assert (first["address"], first["monthly_after"]) == ("aws_nat_gateway.out", None)

    scope = only(DEMO_TENANT, seed_demo.DEMO_ACCOUNT)
    narrowed, narrowed_token = client_for(engine, scope, settings)
    for path in (PLANS, ACCURACY, f"{PLANS}/{head['plan_id']}"):
        assert narrowed.get(path, headers=auth(narrowed_token)).status_code == 404, path
