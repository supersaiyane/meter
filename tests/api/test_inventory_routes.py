"""The three P4 routes, called rather than imported.

TASK-P2-021 wrote six routes that imported cleanly, passed their tests and returned 500 on
every real call. Every case here goes through the client.

Two things carry this file. Whether the coverage travels in the envelope, so a screen cannot
draw the map without the list of slices it is missing; and whether the banner counts slices
rather than accounts or rows, which is asserted against another route because a number that
looks plausible on its own is how that defect survived three times.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from finops_api.routes.inventory import NO_SUCH_NODE
from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.tenant import Scope
from finops_core.domain.topology import EdgeKind, NodeKind, node_id_for
from tests.api.test_query_routes import auth, client_for

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 26, 6, 0, tzinfo=UTC)
FETCHED = datetime(2026, 9, 26, 6, 5, tzinfo=UTC)
MINE = "111122223333"
THEIRS = "444455556666"
REGION = "eu-west-1"
REFUSED_REGION = "eu-north-1"

TOPOLOGY = "/api/v1/inventory/topology"
COVERAGE = "/api/v1/inventory/coverage"
ROOTS = "/api/v1/inventory/roots"
ACCOUNTS = "/api/v1/accounts"

INSERT_ACCOUNT = text(
    "INSERT INTO cloud_account (account_pk, tenant_id, provider, account_id, name, status, "
    "as_of, collected_at) VALUES (:pk, :t, 'aws', :a, :a, 'ACTIVE', :at, :at) "
    "ON CONFLICT DO NOTHING"
)
INSERT_RUN = text(
    "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, idempotency_key, "
    "status, as_of_window_start, as_of_window_end) "
    "VALUES (:run, :t, 'inventory', 'scope', :key, 'SUCCEEDED', :at, :at)"
)
INSERT_NODE = text(
    "INSERT INTO topology_node (node_id, tenant_id, ingest_run_id, sub_account_id, "
    "provider_id, node_kind, resource_type, region_id, availability_zone, name, as_of, "
    "collected_at) VALUES (:node, :t, :run, :a, :p, :k, 'AWS::EC2::VPC', :r, NULL, :n, "
    ":at, :fetched)"
)
INSERT_EDGE = text(
    "INSERT INTO topology_edge (edge_id, tenant_id, ingest_run_id, from_node_id, to_node_id, "
    "edge_kind, is_cross_account, source, sub_account_id, region_id, as_of, collected_at) "
    "VALUES (:e, :t, :run, :frm, :to, :kind, :cross, 'CONFIG_RELATIONSHIP', :a, :r, :at, "
    ":fetched)"
)
INSERT_COVERAGE = text(
    "INSERT INTO graph_coverage (coverage_id, tenant_id, ingest_run_id, sub_account_id, "
    "region_id, state, cause, node_count, edge_count, as_of, collected_at) "
    "VALUES (:c, :t, :run, :a, :r, :s, :cause, 1, 1, :at, :fetched)"
)


def arn(account: str, region: str | None, name: str) -> str:
    return f"arn:aws:ec2:{region or 'global'}:{account}:vpc/{name}"


def identifier(tenant: UUID, account: str, region: str | None, name: str) -> UUID:
    return node_id_for(tenant_id=tenant, provider_id=arn(account, region, name))


def seed(engine: Engine, tenant: UUID, *, fan_out: int = 3) -> None:
    """A VPC with `fan_out` subnets, one cross account edge, and one refused region.

    The refused region holds nothing, which is the point: a reader has to be able to tell it
    from a region that genuinely has nothing, and the coverage row is the only thing that
    can.
    """
    with engine.begin() as connection:
        run = uuid4()
        for account in (MINE, THEIRS):
            connection.execute(
                INSERT_ACCOUNT, {"pk": uuid4(), "t": tenant, "a": account, "at": NOW}
            )
        connection.execute(INSERT_RUN, {"run": run, "t": tenant, "key": str(run), "at": NOW})

        def add_node(account: str, name: str, kind: NodeKind) -> None:
            connection.execute(
                INSERT_NODE,
                {
                    "node": identifier(tenant, account, REGION, name),
                    "t": tenant,
                    "run": run,
                    "a": account,
                    "p": arn(account, REGION, name),
                    "k": kind.value,
                    "r": REGION,
                    "n": name,
                    "at": NOW,
                    "fetched": FETCHED,
                },
            )

        def add_edge(origin: tuple[str, str], target: tuple[str, str], *, cross: bool) -> None:
            connection.execute(
                INSERT_EDGE,
                {
                    "e": uuid4(),
                    "t": tenant,
                    "run": run,
                    "frm": identifier(tenant, origin[0], REGION, origin[1]),
                    "to": identifier(tenant, target[0], REGION, target[1]),
                    "kind": EdgeKind.PEERS_WITH.value if cross else EdgeKind.CONTAINS.value,
                    "cross": cross,
                    "a": origin[0],
                    "r": REGION,
                    "at": NOW,
                    "fetched": FETCHED,
                },
            )

        add_node(MINE, "vpc", NodeKind.VPC)
        for index in range(fan_out):
            add_node(MINE, f"subnet-{index:03d}", NodeKind.SUBNET)
            add_edge((MINE, "vpc"), (MINE, f"subnet-{index:03d}"), cross=False)
        add_node(THEIRS, "far", NodeKind.VPC)
        add_edge((MINE, "vpc"), (THEIRS, "far"), cross=True)

        for account, region, state, cause in (
            (MINE, REGION, "COMPLETE", None),
            (MINE, REFUSED_REGION, "PARTIAL", "AccessDenied"),
            (MINE, None, "COMPLETE", None),
            (THEIRS, REGION, "COMPLETE", None),
        ):
            connection.execute(
                INSERT_COVERAGE,
                {
                    "c": uuid4(),
                    "t": tenant,
                    "run": run,
                    "a": account,
                    "r": region,
                    "s": state,
                    "cause": cause,
                    "at": NOW,
                    "fetched": FETCHED,
                },
            )


def everything(tenant: UUID) -> Scope:
    return Scope(tenant_id=tenant, is_global=True, accounts=frozenset())


def only(tenant: UUID, account: str) -> Scope:
    return Scope(
        tenant_id=tenant,
        is_global=False,
        accounts=frozenset({AccountKey(provider=Provider.AWS, account_id=account)}),
    )


def get(client: TestClient, token: str, path: str, **params: Any) -> dict[str, Any]:
    # httpx replaces a URL's query string when `params` is passed, including when it is empty,
    # so a filter written into the path here is discarded in silence and the route answers as
    # though nothing was asked. Refused rather than merged: a caller who wrote one into the
    # path meant it to apply, and the route being correct makes that failure very hard to see.
    assert "?" not in path, f"pass query parameters as keywords, not in the path: {path}"
    response = client.get(path, headers=auth(token), params=params)
    assert response.status_code == 200, f"{path} returned {response.status_code}: {response.text}"
    result = response.json()
    assert isinstance(result, dict)
    return result


def root_path(tenant: UUID) -> str:
    return f"{TOPOLOGY}/{identifier(tenant, MINE, REGION, 'vpc')}"


# --- the subgraph route -----------------------------------------------------


def test_the_subgraph_route_answers_and_carries_its_coverage(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The criterion. A screen cannot draw the map without the list of slices it is missing,
    because the list is in the same payload."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    body = get(client, token, root_path(tenant_id))
    data = body["data"]
    assert len(data["nodes"]) == 5
    assert data["coverage"], "a subgraph with no coverage is the one thing P4 forbids"
    assert {entry["account_id"] for entry in data["coverage"]} == {MINE, THEIRS}


def test_an_edge_leaving_the_graph_is_marked(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A boundary rather than a line to nowhere. Under a narrow scope the far VPC is not
    drawn, and the edge to it has to say so or the map draws an arrow into empty space."""
    seed(engine, tenant_id)
    client, token = client_for(engine, only(tenant_id, MINE), settings)
    body = get(client, token, root_path(tenant_id))
    crossing = [edge for edge in body["data"]["edges"] if edge["is_cross_account"]]
    assert len(crossing) == 1
    assert crossing[0]["leaves_the_graph"] is True
    assert crossing[0]["source"] == "CONFIG_RELATIONSHIP"


def test_a_root_nothing_has_collected_is_a_404(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """An empty graph would say the resource is connected to nothing, which is a different
    and unearned claim."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    response = client.get(f"{TOPOLOGY}/{uuid4()}", headers=auth(token))
    assert response.status_code == 404
    assert NO_SUCH_NODE in response.json()["detail"]


def test_the_route_enforces_the_cap_and_reports_the_truncation(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """TASK-P4-009's criterion, asserted at the route rather than only in the query layer. A
    map that quietly drew four of twelve nodes is indistinguishable from an estate with
    four."""
    seed(engine, tenant_id, fan_out=11)
    client, token = client_for(engine, everything(tenant_id), settings)
    body = get(client, token, root_path(tenant_id), nodes=4)
    data = body["data"]
    assert len(data["nodes"]) == 4
    assert data["omitted_nodes"] == 9
    assert data["max_nodes"] == 4


def test_a_cap_above_the_ceiling_is_refused_by_the_route(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A bound any caller can widen without limit is not a bound."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    response = client.get(root_path(tenant_id), headers=auth(token), params={"nodes": 999_999})
    assert response.status_code == 422


def test_the_depth_bound_is_a_parameter_the_caller_can_lower(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    body = get(client, token, root_path(tenant_id), depth=0)
    assert len(body["data"]["nodes"]) == 1
    assert body["data"]["max_depth"] == 0
    assert body["data"]["edges"] == []


def test_the_inward_walk_is_a_parameter_too(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    subnet = identifier(tenant_id, MINE, REGION, "subnet-000")
    outward = get(client, token, f"{TOPOLOGY}/{subnet}")
    inward = get(client, token, f"{TOPOLOGY}/{subnet}", inward=True)
    assert len(outward["data"]["nodes"]) == 1
    assert len(inward["data"]["nodes"]) == 2


# --- the banner counts slices, asserted against another route ---------------


def test_the_banner_counts_slices_and_says_so(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    body = get(client, token, root_path(tenant_id))
    coverage = body["meta"]["scope_coverage"]
    assert coverage["unit"] == "slices"
    # Two slices crossed, both complete, so this map is whole even though the estate has a
    # refused region elsewhere.
    assert (coverage["visible"], coverage["total"]) == (2, 2)


def test_the_slice_unit_is_not_the_account_unit_another_route_uses(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The assertion the criterion asks for. A plausible looking number in this slot has been
    the defect three times, and comparing it with a route that counts a different unit is
    what stops it being plausible."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    estate = get(client, token, COVERAGE)["meta"]["scope_coverage"]
    accounts = get(client, token, ACCOUNTS)["meta"]["scope_coverage"]
    assert estate["unit"] == "slices"
    assert accounts["unit"] == "accounts"
    # Four slices across two accounts, so the two denominators cannot be the same number.
    assert estate["total"] == 4
    assert accounts["total"] == 2


def test_the_estate_banner_is_partial_while_a_slice_is_refused(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    body = get(client, token, COVERAGE)
    (incomplete,) = body["data"]["incomplete"]
    assert (incomplete["region_id"], incomplete["state"]) == (REFUSED_REGION, "PARTIAL")
    assert incomplete["cause"] == "AccessDenied"
    assert body["meta"]["scope_coverage"]["is_partial"] is True
    assert body["meta"]["degraded"] is True


# --- the scope, at the route -------------------------------------------------


def test_a_narrow_scope_sees_less_of_the_graph_than_a_global_one(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    wide, wide_token = client_for(engine, everything(tenant_id), settings)
    narrow, narrow_token = client_for(engine, only(tenant_id, MINE), settings)
    whole = get(wide, wide_token, root_path(tenant_id))["data"]
    part = get(narrow, narrow_token, root_path(tenant_id))["data"]
    assert len(part["nodes"]) < len(whole["nodes"])
    assert {node["account_id"] for node in part["nodes"]} == {MINE}


def test_a_narrow_scope_sees_only_its_own_coverage(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, only(tenant_id, THEIRS), settings)
    body = get(client, token, COVERAGE)
    assert body["data"]["incomplete"] == []
    assert body["meta"]["scope_coverage"]["total"] == 1


def test_a_narrow_scope_cannot_reach_another_accounts_root(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, only(tenant_id, THEIRS), settings)
    response = client.get(root_path(tenant_id), headers=auth(token))
    assert response.status_code == 404


# --- the roots list ---------------------------------------------------------


def test_the_roots_route_offers_somewhere_to_start(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    body = get(client, token, ROOTS)
    assert len(body["data"]["roots"]) == 5
    assert body["meta"]["scope_coverage"]["unit"] == "accounts"


def test_the_roots_route_can_narrow_to_one_kind(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    body = get(client, token, ROOTS, node_kind=NodeKind.VPC.value)
    assert {one["node_kind"] for one in body["data"]["roots"]} == {"VPC"}


def test_every_root_carries_its_provider_identifier_and_type(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A reader has to be able to find the thing in their own console, and ten of the
    generated estate's twenty four types draw as OTHER, so the kind alone is not enough."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    for one in get(client, token, ROOTS)["data"]["roots"]:
        assert one["provider_id"].startswith("arn:aws:")
        assert one["resource_type"] == "AWS::EC2::VPC"


# --- FEAT-053, the entity detail page ---------------------------------------

NODES = "/api/v1/inventory/nodes"


def entity_path(tenant: UUID, name: str = "vpc") -> str:
    return f"{NODES}/{identifier(tenant, MINE, REGION, name)}"


def test_the_entity_route_says_what_a_resource_is(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    node = get(client, token, entity_path(tenant_id))["data"]["node"]
    assert node["node_kind"] == "VPC"
    assert node["resource_type"] == "AWS::EC2::VPC"
    assert node["account_id"] == MINE
    assert node["region_id"] == REGION
    # The ARN, because a reader has to be able to find the thing in their own console.
    assert node["provider_id"].startswith("arn:aws:")


def test_the_entity_route_lists_one_hop_of_neighbours(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """One hop, through the same bounded traversal the map uses, so the two cannot disagree
    about what a resource is attached to."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    data = get(client, token, entity_path(tenant_id))["data"]
    names = {one["name"] for one in data["neighbours"]}
    assert names == {"subnet-000", "subnet-001", "subnet-002", "far"}
    # The resource itself is not among its own neighbours.
    assert data["node"]["node_id"] not in {one["node_id"] for one in data["neighbours"]}
    assert len(data["edges"]) == 4


def test_the_entity_route_carries_the_coverage_of_its_own_slice(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A page drawn from a PARTIAL slice may be missing the neighbour that matters, so the
    slice's state travels with it rather than being assumed."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    body = get(client, token, entity_path(tenant_id))
    coverage = body["data"]["coverage"]
    assert coverage is not None
    assert (coverage["account_id"], coverage["region_id"]) == (MINE, REGION)
    assert coverage["state"] == "COMPLETE"
    # One of one slices, because the page is about one resource.
    assert body["meta"]["scope_coverage"] == {
        "visible": 1,
        "total": 1,
        "is_partial": False,
        "unit": "slices",
    }


def test_a_resource_in_an_unreadable_slice_reports_the_page_as_degraded(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The case the coverage field exists for. The trust strip has to say degraded rather than
    leaving a reader to treat a short neighbour list as the whole truth."""
    seed(engine, tenant_id)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE graph_coverage SET state = 'PARTIAL', cause = 'AccessDenied' "
                "WHERE tenant_id = :t AND sub_account_id = :a AND region_id = :r"
            ),
            {"t": tenant_id, "a": MINE, "r": REGION},
        )
    client, token = client_for(engine, everything(tenant_id), settings)
    body = get(client, token, entity_path(tenant_id))
    assert body["data"]["coverage"]["state"] == "PARTIAL"
    assert body["data"]["coverage"]["cause"] == "AccessDenied"
    assert body["meta"]["scope_coverage"]["is_partial"] is True
    assert body["meta"]["degraded"] is True


def test_a_node_this_scope_cannot_see_is_a_404(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The same answer as one that does not exist. Distinguishing them would tell a narrowed
    reader that a resource exists in an account they were not granted."""
    seed(engine, tenant_id)
    client, token = client_for(engine, only(tenant_id, THEIRS), settings)
    refused = client.get(entity_path(tenant_id), headers=auth(token))
    assert refused.status_code == 404
    missing = client.get(f"{NODES}/{uuid4()}", headers=auth(token))
    assert missing.status_code == 404
    assert refused.json()["detail"] == missing.json()["detail"]


def test_a_resource_the_bill_does_not_mention_has_a_null_cost_rather_than_zero(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Null is not zero. A resource with no line item is one the bill does not mention, which
    happens for one created after the period closed and for one whose charges land under a
    parent. A zero would tell a reader it is free."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    data = get(client, token, entity_path(tenant_id))["data"]
    assert data["monthly_cost"] is None
    # And no period either, because this estate has no cost rows at all.
    assert data["cost_period"] is None


def test_the_entity_route_says_how_many_findings_could_not_be_matched(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The honest half. A recommendation joins to a node on the provider's identifier, and the
    first party sources report identifiers that do not always match what Config recorded, so
    an empty finding list would otherwise read as a clean resource."""
    seed(engine, tenant_id)
    run = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, "
                "idempotency_key, status, as_of_window_start, as_of_window_end) "
                "VALUES (:run, :t, 'recommendations', 'scope', :key, 'SUCCEEDED', :at, :at)"
            ),
            {"run": run, "t": tenant_id, "key": str(run), "at": NOW},
        )
        # One finding that joins, and one whose resource this tenant holds no node for.
        for resource, reference in (
            (arn(MINE, REGION, "vpc"), "joins"),
            ("i-not-a-node", "does-not-join"),
        ):
            connection.execute(
                text(
                    "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, "
                    "source, source_reference, waste_class, resource_id, region_id, "
                    "estimated_monthly_saving, confidence, severity, observation_days, "
                    "lifecycle, rationale, as_of, collected_at) "
                    "VALUES (:id, :t, :a, 'METER', :ref, 'EBS_GP2_TO_GP3', :resource, :r, "
                    "'12.5000', 'HIGH', 'LOW', 30, 'OPEN', 'seeded for the entity page', "
                    ":at, :at)"
                ),
                {
                    "id": uuid4(),
                    "t": tenant_id,
                    "a": MINE,
                    "ref": reference,
                    "resource": resource,
                    "r": REGION,
                    "at": NOW,
                },
            )

    client, token = client_for(engine, everything(tenant_id), settings)
    data = get(client, token, entity_path(tenant_id))["data"]
    assert len(data["findings"]) == 1
    assert data["findings"][0]["waste_class"] == "EBS_GP2_TO_GP3"
    # FEAT-052's risk rides along, so the entity page and the home panel say the same thing.
    assert data["findings"][0]["is_no_regret"] is True
    assert data["unmatched_findings"] == 1


def test_a_resource_with_no_findings_and_none_unmatched_says_both(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Zero and zero is the only combination that means clean, and the page has to be able to
    say it rather than leaving a blank list to imply it."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    data = get(client, token, entity_path(tenant_id))["data"]
    assert data["findings"] == []
    assert data["unmatched_findings"] == 0


# --- FEAT-056, the resource list ---------------------------------------------

RESOURCES = "/api/v1/inventory/resources"


def test_the_resource_list_pages_and_states_the_denominator(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Five resources across two accounts: a VPC with three subnets, and the far end of the
    cross account edge. A page of two says so rather than implying it is everything, because a
    list that does not publish its denominator reads as complete."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    body = get(client, token, RESOURCES, limit=2)
    assert len(body["data"]["resources"]) == 2
    assert body["data"]["total"] == 5
    assert (body["data"]["limit"], body["data"]["offset"]) == (2, 0)


def test_the_pages_partition_the_estate_rather_than_overlapping(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The failure a non deterministic order produces: a page boundary that repeats one row
    and skips another, which nothing notices because both pages look full. The order ends at
    the identifier for exactly this reason."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    seen: list[str] = []
    for offset in (0, 2, 4):
        page = get(client, token, RESOURCES, limit=2, offset=offset)["data"]["resources"]
        seen.extend(one["node_id"] for one in page)
    assert len(seen) == 5
    assert len(set(seen)) == 5


def test_every_filter_narrows_the_list_and_the_total_with_it(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The total has to follow the filter. A denominator that stayed at the estate size while
    the page narrowed would tell a reader their filter was hiding rows it never matched."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    subnets = get(client, token, RESOURCES, node_kind="SUBNET")["data"]
    assert subnets["total"] == 3
    assert {one["node_kind"] for one in subnets["resources"]} == {"SUBNET"}

    mine = get(client, token, RESOURCES, account_id=MINE)["data"]
    assert mine["total"] == 4
    assert {one["account_id"] for one in mine["resources"]} == {MINE}

    by_type = get(client, token, RESOURCES, resource_type="AWS::EC2::VPC")["data"]
    assert by_type["total"] == 5


def test_a_narrowed_reader_sees_a_total_of_what_they_may_see(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The case that makes the count worth asserting. A total over everything beside a page of
    the readable rows is the arithmetic that tells a narrowed reader how much they are not
    allowed to look at, and it is counted through the same guard as the page for that reason."""
    seed(engine, tenant_id)
    client, token = client_for(engine, only(tenant_id, THEIRS), settings)
    body = get(client, token, RESOURCES)["data"]
    assert body["total"] == 1
    assert {one["account_id"] for one in body["resources"]} == {THEIRS}


def test_the_filter_vocabularies_come_from_the_data(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Read rather than listed. Offering all fourteen node kinds when the estate holds two
    teaches a reader that twelve of the filters return nothing, and `resource_type` has no
    enumeration at all, so the data is the only place that list exists."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    filters = get(client, token, RESOURCES)["data"]["filters"]
    assert set(filters["node_kind"]) == {"VPC", "SUBNET"}
    assert set(filters["account_id"]) == {MINE, THEIRS}
    assert filters["resource_type"] == ["AWS::EC2::VPC"]
    # Never an empty string. A null region is the global slice and the screen names it, and a
    # blank option in a select reads as a defect.
    assert "" not in filters["region_id"]


def test_a_narrowed_reader_is_not_offered_a_filter_for_somebody_elses_account(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The vocabularies go through the scope guard too. A select listing every account in the
    estate would disclose the estate to a reader granted one account of it."""
    seed(engine, tenant_id)
    client, token = client_for(engine, only(tenant_id, THEIRS), settings)
    filters = get(client, token, RESOURCES)["data"]["filters"]
    assert filters["account_id"] == [THEIRS]


def test_the_list_counts_slices_rather_than_rows_in_its_coverage(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A full page of rows is not complete coverage of an estate half of which was never read.
    The seeded estate has one refused region, so the list is drawn from fewer slices than
    exist and the strip says so."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    body = get(client, token, RESOURCES)
    coverage = body["meta"]["scope_coverage"]
    assert coverage["unit"] == "slices"
    assert coverage["visible"] < coverage["total"]
    assert coverage["is_partial"] is True
    assert body["meta"]["degraded"] is True


def test_a_filter_matching_nothing_is_an_empty_list_rather_than_an_error(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """An empty result is an answer about the estate. A 404 here would say the filter was
    wrong when what it said was that nothing matches."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    body = get(client, token, RESOURCES, node_kind="LAMBDA_FUNCTION")["data"]
    assert body["resources"] == []
    assert body["total"] == 0
    # And the vocabularies still describe the estate, so the reader can widen the filter
    # rather than being left on a dead end with no options.
    assert body["filters"]["node_kind"]


@pytest.mark.parametrize("query", ["limit=0", "limit=501", "offset=-1"])
def test_a_bound_outside_the_allowed_range_is_refused(
    engine: Engine, tenant_id: UUID, settings: Settings, query: str
) -> None:
    """Refused rather than clamped. An unbounded read of a real estate returns the estate, and
    silently correcting the request would leave the caller believing the bound they asked for
    was honoured."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    assert client.get(f"{RESOURCES}?{query}", headers=auth(token)).status_code == 422
