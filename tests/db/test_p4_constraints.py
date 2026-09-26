"""The P4 invariants, watched refusing.

Constraint 11: if application code is the only thing preventing a bad row, the bad
row will eventually exist. A check constraint nobody has watched refuse anything is
in the same position as the code it was meant to back up, because a constraint with
a typo in it accepts everything and looks exactly like one that works.

The cases worth having here are the ones that encode section 6 of the P4
specification rather than a column's type. A `graph_coverage` row that says PARTIAL
and cannot say why is the failure this sub project exists to prevent, arriving
through the one door the domain's `__post_init__` does not cover: a write that did
not come through the domain at all.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from finops_api.db import models
from finops_core.domain.topology import CoverageCause, CoverageState, NodeKind, node_id_for

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 26, 6, 0, tzinfo=UTC)
FETCHED = datetime(2026, 9, 26, 6, 5, tzinfo=UTC)
ACCOUNT = "111122223333"
REGION = "eu-west-1"

INSERT_RUN = text(
    "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, idempotency_key, "
    "status, as_of_window_start, as_of_window_end) "
    "VALUES (:run, :t, 'inventory', :scope, :key, 'SUCCEEDED', :at, :at)"
)

INSERT_NODE = text(
    "INSERT INTO topology_node (node_id, tenant_id, ingest_run_id, sub_account_id, "
    "provider_id, node_kind, resource_type, region_id, availability_zone, name, as_of, "
    "collected_at) VALUES (:node, :t, :run, :account, :provider, :kind, :type, :region, "
    ":zone, :name, :as_of, :collected)"
)

INSERT_EDGE = text(
    "INSERT INTO topology_edge (edge_id, tenant_id, ingest_run_id, from_node_id, "
    "to_node_id, edge_kind, is_cross_account, source, sub_account_id, region_id, as_of, "
    "collected_at) VALUES (:edge, :t, :run, :frm, :to, :kind, :cross, :source, :account, "
    ":region, :as_of, :collected)"
)

INSERT_COVERAGE = text(
    "INSERT INTO graph_coverage (coverage_id, tenant_id, ingest_run_id, sub_account_id, "
    "region_id, state, cause, node_count, edge_count, as_of, collected_at) "
    "VALUES (:coverage, :t, :run, :account, :region, :state, :cause, :nodes, :edges, "
    ":as_of, :collected)"
)


def a_run(connection: Connection, tenant: UUID) -> UUID:
    run = uuid4()
    connection.execute(
        INSERT_RUN,
        {"run": run, "t": tenant, "scope": f"acct:{ACCOUNT}", "key": str(run), "at": NOW},
    )
    return run


def a_node(connection: Connection, tenant: UUID, run: UUID, **overrides: object) -> UUID:
    """One valid node, with any field overridden.

    Written as a valid row plus overrides rather than as one literal per case, so a
    case that fails proves the override was the reason and not a typo elsewhere.
    """
    provider = str(overrides.pop("provider", f"arn:aws:ec2:{REGION}:{ACCOUNT}:vpc/{uuid4().hex}"))
    values: dict[str, object] = {
        "node": node_id_for(tenant_id=tenant, provider_id=provider),
        "t": tenant,
        "run": run,
        "account": ACCOUNT,
        "provider": provider,
        "kind": NodeKind.VPC.value,
        "type": "AWS::EC2::VPC",
        "region": REGION,
        "zone": None,
        "name": "production",
        "as_of": NOW,
        "collected": FETCHED,
    }
    values.update(overrides)
    connection.execute(INSERT_NODE, values)
    return UUID(str(values["node"]))


def an_edge(connection: Connection, tenant: UUID, run: UUID, **overrides: object) -> None:
    frm = overrides.pop("frm", None) or a_node(connection, tenant, run)
    to = overrides.pop("to", None) or a_node(connection, tenant, run)
    values: dict[str, object] = {
        "edge": uuid4(),
        "t": tenant,
        "run": run,
        "frm": frm,
        "to": to,
        "kind": "CONTAINS",
        "cross": False,
        "source": "CONFIG_RELATIONSHIP",
        "account": ACCOUNT,
        "region": REGION,
        "as_of": NOW,
        "collected": FETCHED,
    }
    values.update(overrides)
    connection.execute(INSERT_EDGE, values)


def coverage(connection: Connection, tenant: UUID, run: UUID, **overrides: object) -> None:
    values: dict[str, object] = {
        "coverage": uuid4(),
        "t": tenant,
        "run": run,
        "account": ACCOUNT,
        "region": REGION,
        "state": CoverageState.COMPLETE.value,
        "cause": None,
        "nodes": 3,
        "edges": 2,
        "as_of": NOW,
        "collected": FETCHED,
    }
    values.update(overrides)
    connection.execute(INSERT_COVERAGE, values)


# --- the migration and the domain agree about the value sets ------------------


def test_the_coverage_causes_in_the_schema_match_the_domain_enum() -> None:
    """ADR-0023 names three places a seventh cause has to reach. This is the pair
    of them a test can hold together without a database."""
    assert set(models.COVERAGE_CAUSES) == {member.value for member in CoverageCause}


def test_the_coverage_states_in_the_schema_match_the_domain_enum() -> None:
    assert set(models.COVERAGE_STATES) == {member.value for member in CoverageState}


def test_the_node_kinds_in_the_schema_match_the_domain_enum() -> None:
    assert set(models.NODE_KINDS) == {member.value for member in NodeKind}


# --- coverage says why, or the row does not exist ----------------------------


def test_a_partial_slice_without_a_cause_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """The one that matters. A PARTIAL row with a null cause renders a banner
    saying data is missing that cannot say which data or why."""
    with (
        pytest.raises(IntegrityError, match="cause_iff_not_complete"),
        engine.begin() as connection,
    ):
        run = a_run(connection, tenant_id)
        coverage(connection, tenant_id, run, state="PARTIAL", cause=None)


def test_a_complete_slice_with_a_cause_is_refused(engine: Engine, tenant_id: UUID) -> None:
    with (
        pytest.raises(IntegrityError, match="cause_iff_not_complete"),
        engine.begin() as connection,
    ):
        run = a_run(connection, tenant_id)
        coverage(connection, tenant_id, run, state="COMPLETE", cause="AccessDenied")


def test_an_unread_slice_carrying_a_failure_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """Nothing failed, so naming a failure describes something that did not happen."""
    with (
        pytest.raises(IntegrityError, match="unread_is_not_yet_attempted"),
        engine.begin() as connection,
    ):
        run = a_run(connection, tenant_id)
        coverage(connection, tenant_id, run, state="UNREAD", cause="Throttled", nodes=0, edges=0)


def test_an_unread_slice_with_something_in_it_is_refused(engine: Engine, tenant_id: UUID) -> None:
    with pytest.raises(IntegrityError, match="unread_is_empty"), engine.begin() as connection:
        run = a_run(connection, tenant_id)
        coverage(
            connection,
            tenant_id,
            run,
            state="UNREAD",
            cause="NotYetAttempted",
            nodes=4,
            edges=0,
        )


def test_an_unknown_cause_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """A cause outside the seven is a collector inventing one, which is how a
    typed failure becomes a free text note nobody can route."""
    with pytest.raises(IntegrityError, match="cause_known"), engine.begin() as connection:
        run = a_run(connection, tenant_id)
        coverage(connection, tenant_id, run, state="PARTIAL", cause="SomethingWentWrong")


def test_a_second_row_for_one_slice_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """Two rows would let a consumer read either one and get a different answer
    about whether the graph can be trusted, with nothing saying which is current."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        coverage(connection, tenant_id, run, state="COMPLETE", cause=None)
    with (
        pytest.raises(IntegrityError, match="uq_graph_coverage__slice"),
        engine.begin() as connection,
    ):
        run = a_run(connection, tenant_id)
        coverage(connection, tenant_id, run, state="PARTIAL", cause="AccessDenied")


def test_a_valid_unread_and_a_valid_partial_are_both_accepted(
    engine: Engine, tenant_id: UUID
) -> None:
    """The refusals above are worth nothing unless the rows they refuse are the
    only ones refused."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        coverage(
            connection,
            tenant_id,
            run,
            region="eu-north-1",
            state="UNREAD",
            cause="NotYetAttempted",
            nodes=0,
            edges=0,
        )
        coverage(
            connection,
            tenant_id,
            run,
            region="ap-south-1",
            state="PARTIAL",
            cause="AccessDenied",
            nodes=2,
            edges=1,
        )
        found = connection.execute(
            text(
                "SELECT region_id, state, cause FROM graph_coverage WHERE tenant_id = :t "
                "ORDER BY region_id"
            ),
            {"t": tenant_id},
        ).all()
    assert [(row.region_id, row.state, row.cause) for row in found] == [
        ("ap-south-1", "PARTIAL", "AccessDenied"),
        ("eu-north-1", "UNREAD", "NotYetAttempted"),
    ]


# --- an edge's direction, and the one edge that may point at itself -----------


def test_both_directions_of_one_pair_are_accepted(engine: Engine, tenant_id: UUID) -> None:
    """A store that merged the two directions would answer "what is inside this
    VPC" with the VPC's parent, so the unique index must not be what decides it."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        first = a_node(connection, tenant_id, run)
        second = a_node(connection, tenant_id, run)
        an_edge(connection, tenant_id, run, frm=first, to=second)
        an_edge(connection, tenant_id, run, frm=second, to=first)
        count = connection.execute(
            text("SELECT count(*) FROM topology_edge WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar_one()
    assert count == 2


def test_the_same_directed_edge_twice_is_refused(engine: Engine, tenant_id: UUID) -> None:
    with (
        pytest.raises(IntegrityError, match="uq_topology_edge__directed"),
        engine.begin() as connection,
    ):
        run = a_run(connection, tenant_id)
        first = a_node(connection, tenant_id, run)
        second = a_node(connection, tenant_id, run)
        an_edge(connection, tenant_id, run, frm=first, to=second)
        an_edge(connection, tenant_id, run, frm=first, to=second)


def test_a_self_edge_is_refused_unless_it_permits(engine: Engine, tenant_id: UUID) -> None:
    with (
        pytest.raises(IntegrityError, match="self_edge_only_permits"),
        engine.begin() as connection,
    ):
        run = a_run(connection, tenant_id)
        node = a_node(connection, tenant_id, run)
        an_edge(connection, tenant_id, run, frm=node, to=node, kind="CONTAINS")
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        group = a_node(connection, tenant_id, run, kind="SECURITY_GROUP", type="AWS::EC2::Group")
        an_edge(
            connection,
            tenant_id,
            run,
            frm=group,
            to=group,
            kind="PERMITS",
            source="DescribeSecurityGroups",
        )


def test_an_edge_without_a_source_is_refused(engine: Engine, tenant_id: UUID) -> None:
    with pytest.raises(IntegrityError, match="has_source"), engine.begin() as connection:
        run = a_run(connection, tenant_id)
        an_edge(connection, tenant_id, run, source="")


def test_an_edge_may_point_at_a_node_that_was_never_read(engine: Engine, tenant_id: UUID) -> None:
    """Section 6, at the schema. The far end of a cross account TRUSTS edge is
    routinely a principal in an account Meter does not collect from, and a foreign
    key on `to_node_id` would turn an edge Meter cannot fully see into an absent
    edge, silently, at the database."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        role = a_node(connection, tenant_id, run)
        an_edge(
            connection,
            tenant_id,
            run,
            frm=role,
            to=uuid4(),
            kind="TRUSTS",
            cross=True,
            source="GetRolePolicy",
        )
        found = connection.execute(
            text("SELECT is_cross_account FROM topology_edge WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).scalar_one()
    assert found is True


def test_an_edge_from_a_node_that_does_not_exist_is_refused(
    engine: Engine, tenant_id: UUID
) -> None:
    """The other direction does carry a key, because every edge is written outward
    from a resource the run actually read, and that invariant is true."""
    with pytest.raises(IntegrityError, match="from_node_id"), engine.begin() as connection:
        run = a_run(connection, tenant_id)
        an_edge(connection, tenant_id, run, frm=uuid4(), to=a_node(connection, tenant_id, run))


#: Removing a row, as two statements the cases below reuse. Deliberately not a
#: cascade: a cascade would remove edges nothing counted, so a run's
#: `items_removed` would undercount every departed resource by the size of its
#: neighbourhood, and `tests/db/test_models.py` holds `principal_scope` to being
#: the only table in this schema that cascades at all.
DROP_NODE = text("DELETE FROM topology_node WHERE node_id = :node")
DROP_EDGES_FROM = text("DELETE FROM topology_edge WHERE from_node_id = :node")


def test_removing_a_node_before_its_edges_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """The ordering is forced by the key, so forgetting it is loud rather than
    silent. A collector that removes a departed resource and leaves its edges
    behind fails here instead of leaving a graph with edges out of nowhere."""
    with pytest.raises(IntegrityError, match="topology_edge"), engine.begin() as connection:
        run = a_run(connection, tenant_id)
        vpc = a_node(connection, tenant_id, run)
        subnet = a_node(connection, tenant_id, run)
        an_edge(connection, tenant_id, run, frm=vpc, to=subnet)
        connection.execute(DROP_NODE, {"node": vpc})


def test_removing_the_edges_first_lets_the_node_go(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        vpc = a_node(connection, tenant_id, run)
        subnet = a_node(connection, tenant_id, run)
        an_edge(connection, tenant_id, run, frm=vpc, to=subnet)
        connection.execute(DROP_EDGES_FROM, {"node": vpc})
        connection.execute(DROP_NODE, {"node": vpc})
        left = connection.execute(
            text("SELECT count(*) FROM topology_node WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar_one()
    assert left == 1


# --- a node's place, and what a null zone means ------------------------------


def test_one_provider_identifier_per_tenant(engine: Engine, tenant_id: UUID) -> None:
    """A second row for the same resource would appear twice on the map with half
    its edges each time, which is worse than a duplicate because both look whole."""
    with (
        pytest.raises(IntegrityError, match="uq_topology_node__provider_id"),
        engine.begin() as connection,
    ):
        run = a_run(connection, tenant_id)
        arn = f"arn:aws:ec2:{REGION}:{ACCOUNT}:vpc/vpc-fixed"
        a_node(connection, tenant_id, run, provider=arn)
        connection.execute(
            INSERT_NODE,
            {
                "node": uuid4(),
                "t": tenant_id,
                "run": run,
                "account": ACCOUNT,
                "provider": arn,
                "kind": "VPC",
                "type": "AWS::EC2::VPC",
                "region": REGION,
                "zone": None,
                "name": "a second row for one resource",
                "as_of": NOW,
                "collected": FETCHED,
            },
        )


def test_a_zone_outside_its_own_region_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """The likeliest way to write one is a collector that read the zone from one
    call and the region from another."""
    with pytest.raises(IntegrityError, match="zone_within_region"), engine.begin() as connection:
        run = a_run(connection, tenant_id)
        a_node(connection, tenant_id, run, kind="INSTANCE", zone="us-east-1a")


def test_a_regional_resource_keeps_its_null_zone(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        a_node(connection, tenant_id, run, zone=None)
        found = connection.execute(
            text("SELECT availability_zone FROM topology_node WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).scalar_one()
    assert found is None


def test_an_unknown_node_kind_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """A resource type the adapter does not recognise is OTHER plus a SchemaDrift,
    not a new value invented at the write."""
    with pytest.raises(IntegrityError, match="kind_known"), engine.begin() as connection:
        run = a_run(connection, tenant_id)
        a_node(connection, tenant_id, run, kind="QUANTUM_GATEWAY")


def test_a_fact_collected_before_it_was_true_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """Constraint 10, at the schema. `collected_at` before `as_of` is the two
    timestamps having been filled in the wrong order."""
    with pytest.raises(IntegrityError, match="collected_after_as_of"), engine.begin() as connection:
        run = a_run(connection, tenant_id)
        a_node(connection, tenant_id, run, as_of=FETCHED, collected=NOW)


# --- the global slice, which has no region ----------------------------------


def test_a_global_resource_has_a_null_region(engine: Engine, tenant_id: UUID) -> None:
    """An IAM role belongs to an account and to no region, and a TRUSTS edge between
    two roles is one of the four edge kinds FEAT-031 exists to supply. ISS-196 made
    the same change to `QuotaUsage`, and the workaround both times would have been a
    magic region string that shows on a screen as a region nobody has."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        a_node(
            connection,
            tenant_id,
            run,
            provider=f"arn:aws:iam::{ACCOUNT}:role/platform-ci",
            kind="OTHER",
            type="AWS::IAM::Role",
            region=None,
            zone=None,
        )
        found = connection.execute(
            text("SELECT region_id FROM topology_node WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar_one()
    assert found is None


def test_a_global_resource_cannot_have_a_zone(engine: Engine, tenant_id: UUID) -> None:
    with pytest.raises(IntegrityError, match="zone_within_region"), engine.begin() as connection:
        run = a_run(connection, tenant_id)
        a_node(connection, tenant_id, run, kind="INSTANCE", region=None, zone="eu-west-1a")


def test_one_global_coverage_row_per_account(engine: Engine, tenant_id: UUID) -> None:
    """The unique index coalesces the region, because a unique index treats nulls as
    distinct and two rows for one account's global slice would both be accepted with
    nothing saying which was current."""
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        coverage(connection, tenant_id, run, region=None, state="COMPLETE", cause=None)
    with (
        pytest.raises(IntegrityError, match="uq_graph_coverage__slice"),
        engine.begin() as (connection),
    ):
        run = a_run(connection, tenant_id)
        coverage(connection, tenant_id, run, region=None, state="PARTIAL", cause="AccessDenied")


def test_a_global_slice_and_a_regional_slice_coexist(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        run = a_run(connection, tenant_id)
        coverage(connection, tenant_id, run, region=None)
        coverage(connection, tenant_id, run, region=REGION)
        count = connection.execute(
            text("SELECT count(*) FROM graph_coverage WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar_one()
    assert count == 2
