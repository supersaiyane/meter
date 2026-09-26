"""The graph's entities, and the one thing about them that is not a dataclass.

The tests worth having here are the three that encode a decision rather than a
field list: that an edge's direction is part of its identity, that a coverage row
cannot say "incomplete" without saying why, and that the coverage cause set has
not drifted from the error taxonomy it was derived from.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from finops_core.domain import (
    AccountKey,
    CoverageCause,
    CoverageState,
    Edge,
    EdgeKind,
    GraphCoverage,
    Node,
    NodeKind,
    Provider,
    node_id_for,
)
from finops_core.errors import CollectionError

NOW = datetime(2026, 9, 26, 6, 0, tzinfo=UTC)
FETCHED = datetime(2026, 9, 26, 6, 5, tzinfo=UTC)
KEY = AccountKey(provider=Provider.AWS, account_id="111111111111")
TENANT = UUID("11111111-1111-1111-1111-111111111111")


def a_node(name: str = "n1", **overrides: object) -> Node:
    values: dict[str, object] = {
        "node_id": node_id_for(tenant_id=TENANT, provider_id=name),
        "account_key": KEY,
        "provider_id": f"arn:aws:ec2:eu-west-1:111111111111:vpc/{name}",
        "node_kind": NodeKind.VPC,
        "resource_type": "AWS::EC2::VPC",
        "region_id": "eu-west-1",
        "availability_zone": None,
        "name": "production",
        "tags": {"finops:module": "network"},
        "as_of": NOW,
        "collected_at": FETCHED,
    }
    values.update(overrides)
    return Node(**values)  # type: ignore[arg-type]


def an_edge(frm: str = "n1", to: str = "n2", **overrides: object) -> Edge:
    values: dict[str, object] = {
        "from_node_id": node_id_for(tenant_id=TENANT, provider_id=frm),
        "to_node_id": node_id_for(tenant_id=TENANT, provider_id=to),
        "edge_kind": EdgeKind.CONTAINS,
        "is_cross_account": False,
        "source": "CONFIG_RELATIONSHIP",
        "as_of": NOW,
        "collected_at": FETCHED,
    }
    values.update(overrides)
    return Edge(**values)  # type: ignore[arg-type]


def coverage(**overrides: object) -> GraphCoverage:
    values: dict[str, object] = {
        "account_key": KEY,
        "region_id": "eu-west-1",
        "state": CoverageState.COMPLETE,
        "cause": None,
        "node_count": 12,
        "edge_count": 19,
        "as_of": NOW,
        "collected_at": FETCHED,
    }
    values.update(overrides)
    return GraphCoverage(**values)  # type: ignore[arg-type]


# --- an edge's direction is part of what it is -------------------------------


def test_reversing_an_edge_is_a_different_edge() -> None:
    """Both directions can exist, and a store that merged them would answer
    "what is inside this VPC" with the VPC's parent."""
    outward = an_edge("vpc", "subnet")
    inward = an_edge("subnet", "vpc")
    assert outward != inward
    assert (outward.from_node_id, outward.to_node_id) != (inward.from_node_id, inward.to_node_id)


def test_an_edge_kind_is_part_of_the_identity_too() -> None:
    assert an_edge("a", "b", edge_kind=EdgeKind.CONTAINS) != an_edge(
        "a", "b", edge_kind=EdgeKind.ROUTES_TO
    )


def test_a_self_edge_is_refused_except_for_permits() -> None:
    with pytest.raises(ValueError, match="never terminates"):
        an_edge("sg", "sg", edge_kind=EdgeKind.CONTAINS)
    reflexive = an_edge("sg", "sg", edge_kind=EdgeKind.PERMITS, source="DescribeSecurityGroups")
    assert reflexive.from_node_id == reflexive.to_node_id


def test_an_edge_without_a_source_is_refused() -> None:
    with pytest.raises(ValueError, match="must name the API call"):
        an_edge(source="")


# --- a regional resource is not a resource in an unknown zone ----------------


def test_a_regional_node_has_a_null_zone_and_a_zonal_node_does_not() -> None:
    assert a_node(node_kind=NodeKind.VPC).availability_zone is None
    zonal = a_node("i1", node_kind=NodeKind.INSTANCE, availability_zone="eu-west-1a")
    assert zonal.availability_zone == "eu-west-1a"


def test_node_tags_cannot_be_mutated_through_the_mapping_handed_in() -> None:
    tags = {"env": "prod"}
    node = a_node(tags=tags)
    tags["env"] = "dev"
    assert node.tags["env"] == "prod"


# --- coverage says why, or it does not say anything --------------------------


def test_a_partial_slice_without_a_cause_is_refused() -> None:
    with pytest.raises(ValueError, match="typed cause"):
        coverage(state=CoverageState.PARTIAL, cause=None)


def test_a_complete_slice_with_a_cause_is_refused() -> None:
    with pytest.raises(ValueError, match="nothing to explain"):
        coverage(state=CoverageState.COMPLETE, cause=CoverageCause.ACCESS_DENIED)


def test_an_unread_slice_carries_not_yet_attempted_and_nothing_else() -> None:
    unread = coverage(
        state=CoverageState.UNREAD,
        cause=CoverageCause.NOT_YET_ATTEMPTED,
        node_count=0,
        edge_count=0,
    )
    assert not unread.is_whole
    with pytest.raises(ValueError, match="did not happen"):
        coverage(state=CoverageState.UNREAD, cause=CoverageCause.THROTTLED)


def test_a_complete_slice_with_nothing_in_it_is_whole() -> None:
    """An account that genuinely has nothing in a region is not a failure."""
    empty = coverage(node_count=0, edge_count=0)
    assert empty.is_whole


def test_negative_counts_are_refused() -> None:
    with pytest.raises(ValueError, match="never negative"):
        coverage(node_count=-1)


# --- the cause set has not drifted from the taxonomy ------------------------


def test_every_taxonomy_cause_is_a_coverage_cause() -> None:
    """ADR-0023. A seventh cause in `finops_core.errors` fails here until this
    enum and the `graph_coverage` check constraint have both seen it."""
    values = {member.value for member in CoverageCause}
    for error_type in CollectionError.__subclasses__():
        assert error_type.__name__ in values, error_type.__name__


def test_the_only_coverage_cause_outside_the_taxonomy_is_not_yet_attempted() -> None:
    taxonomy = {error_type.__name__ for error_type in CollectionError.__subclasses__()}
    extra = {member.value for member in CoverageCause} - taxonomy
    assert extra == {"NotYetAttempted"}
