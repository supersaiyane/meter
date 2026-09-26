"""One contract for reading the graph, held by the fake and by AWS Config.

The sentences here are the ones section 6 of the P4 specification turns into a
requirement, and they are worth stating as a contract rather than per adapter
because the failure they prevent is silent in both. A source that returned nodes and
no shortfalls would pass every test about nodes.

Four sentences:

1. A refused slice comes back as a result, not as an exception.
2. A refused slice carries a typed cause, and the cause is one of the seven.
3. A slice that is genuinely empty is COMPLETE, and is therefore not the same thing.
4. Every edge names the API that supplied it, so a missing edge can be told apart
   from an API that was refused.
"""

from __future__ import annotations

from collections.abc import Callable

from finops_core.domain.topology import CoverageCause, CoverageState, SliceRead
from finops_core.ports.inventory import TopologySource
from tests.contract.conftest import TOPOLOGY_SOURCE, ProviderUnderTest

Requires = Callable[[str], None]


def test_the_source_satisfies_the_port(subject: ProviderUnderTest, requires_port: Requires) -> None:
    requires_port(TOPOLOGY_SOURCE)
    assert isinstance(subject.provider, TopologySource)


def test_a_readable_slice_yields_nodes_and_is_whole(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    requires_port(TOPOLOGY_SOURCE)
    read = subject.provider.read_slice(subject.known_account, subject.region)
    assert isinstance(read, SliceRead)
    assert read.nodes, "a readable slice with no nodes is not a slice this contract can judge"
    assert read.state is CoverageState.COMPLETE
    assert read.cause is None
    assert read.is_whole


def test_a_refused_slice_is_returned_rather_than_raised(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """The sentence the whole port shape exists for. An exception would discard every
    account after this one, which is constraint 5 broken at the first refusal."""
    requires_port(TOPOLOGY_SOURCE)
    read = subject.provider.read_slice(subject.denied_account, subject.region)
    assert read.nodes == ()
    assert read.edges == ()
    assert read.state is CoverageState.PARTIAL
    assert not read.is_whole


def test_a_refused_slice_names_a_cause_from_the_closed_set(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    requires_port(TOPOLOGY_SOURCE)
    read = subject.provider.read_slice(subject.denied_account, subject.region)
    assert read.cause is CoverageCause.ACCESS_DENIED
    for shortfall in read.shortfalls:
        assert shortfall.cause in set(CoverageCause)
        assert shortfall.source, (
            "a shortfall that cannot name the API says only that something is missing"
        )


def test_the_slice_the_read_describes_is_the_slice_that_was_asked_for(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """A source answering about a different slice than the one requested would write
    one account's coverage over another's, which no screen could detect."""
    requires_port(TOPOLOGY_SOURCE)
    read = subject.provider.read_slice(subject.known_account, subject.region)
    assert read.account_key == subject.known_account
    assert read.region_id == subject.region


def test_every_node_belongs_to_the_account_that_was_asked_for(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    requires_port(TOPOLOGY_SOURCE)
    read = subject.provider.read_slice(subject.known_account, subject.region)
    for node in read.nodes:
        assert node.account_key == subject.known_account


def test_every_node_carries_both_timestamps_in_order(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """Constraint 10, and the database refuses the other order, so an adapter that
    filled them the wrong way round would fail a whole run at the first write."""
    requires_port(TOPOLOGY_SOURCE)
    read = subject.provider.read_slice(subject.known_account, subject.region)
    for node in read.nodes:
        assert node.collected_at >= node.as_of


def test_every_edge_names_the_api_that_supplied_it(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """Without it, a reader seeing no peering edges in a region cannot tell an estate
    with no peering from a slice where the peering call was refused."""
    requires_port(TOPOLOGY_SOURCE)
    read = subject.provider.read_slice(subject.known_account, subject.region)
    assert read.edges, "a slice with nodes and no edges cannot hold this contract"
    for edge in read.edges:
        assert edge.source
        assert edge.collected_at >= edge.as_of


def test_every_edge_leaves_a_node_this_slice_read(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """`topology_edge.from_node_id` keys onto `topology_node`, so an edge out of a
    node the slice did not read fails the write for the whole unit. The far end is
    deliberately unconstrained: that is where a cross account edge points."""
    requires_port(TOPOLOGY_SOURCE)
    read = subject.provider.read_slice(subject.known_account, subject.region)
    known = {node.node_id for node in read.nodes}
    for edge in read.edges:
        assert edge.from_node_id in known


def test_the_global_slice_holds_nothing_with_a_region(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """A region of None is the account's global slice. A node with a region in it
    would be a resource read twice, once here and once in its own region."""
    requires_port(TOPOLOGY_SOURCE)
    read = subject.provider.read_slice(subject.known_account, None)
    assert read.region_id is None
    for node in read.nodes:
        assert node.region_id is None
        assert node.availability_zone is None


def test_the_enrolled_slices_include_the_ones_that_refuse(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """The denominator. A source reporting only the slices it could read would make
    an unread region indistinguishable from one that does not exist."""
    requires_port(TOPOLOGY_SOURCE)
    slices = subject.provider.enrolled_slices
    assert slices
    assert any(account == subject.denied_account for account, _region in slices)


def test_reading_the_same_slice_twice_gives_the_same_answer(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """Not a performance claim. An identifier that changes between runs is a table
    that doubles every time the worker restarts, which is why `node_id_for` uses
    uuid5 and not the salted builtin hash."""
    requires_port(TOPOLOGY_SOURCE)
    first = subject.provider.read_slice(subject.known_account, subject.region)
    second = subject.provider.read_slice(subject.known_account, subject.region)
    assert {node.node_id for node in first.nodes} == {node.node_id for node in second.nodes}


def test_a_type_the_source_cannot_name_does_not_make_the_slice_partial(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """The fifth sentence, and the one the contract itself taught us. A node present
    as OTHER with its `resource_type` intact is a complete slice with imprecise
    labelling, and calling it PARTIAL would leave an estate with a fleet of container
    clusters showing a data is missing banner on every run forever. ISS-201."""
    requires_port(TOPOLOGY_SOURCE)
    read = subject.provider.read_slice(subject.known_account, subject.region)
    for name in read.unmapped:
        assert name, "an unmapped type must be named, or the gap is invisible"
        assert not any(name in shortfall.detail for shortfall in read.shortfalls)
    if read.unmapped:
        assert read.state is CoverageState.COMPLETE


def test_the_two_providers_name_the_same_four_apis() -> None:
    """Not parameterised over a subject, because the point is the pair.

    A consumer grouping edges by `source` sees two different estates if the fake calls
    a trust read `iam:GetRole` and the adapter calls it `iam:ListRoles`, which is what
    they did until this test existed. Held as an equality rather than as a docstring
    note, because a docstring note is what the first version was.
    """
    from finops_fakes import topology as fake
    from finops_providers.aws import topology as real

    assert (fake.TGW_API, fake.PEERING_API, fake.ENDPOINT_API, fake.TRUST_API) == (
        real.TGW_API,
        real.PEERING_API,
        real.ENDPOINT_API,
        real.TRUST_API,
    )
    assert fake.CONFIG == "CONFIG_RELATIONSHIP"
