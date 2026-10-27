"""What every AccountDiscovery implementation must do, whoever wrote it."""

from __future__ import annotations

import pytest

from finops_core.domain.account import CloudAccount, Provider
from finops_core.domain.org import OrgNode, OrgNodeType

from .conftest import ProviderUnderTest

pytestmark = pytest.mark.contract


def test_lists_accounts_as_domain_entities(subject: ProviderUnderTest) -> None:
    accounts = list(subject.provider.list_accounts())  # type: ignore[call-arg]
    assert accounts
    assert all(isinstance(a, CloudAccount) for a in accounts)


def test_every_account_names_its_provider(subject: ProviderUnderTest) -> None:
    """Nothing downstream may assume AWS, so the provider travels with the account."""
    for account in subject.provider.list_accounts():  # type: ignore[attr-defined]
        assert isinstance(account.provider, Provider)


def test_discovery_includes_the_account_that_denies_access(
    subject: ProviderUnderTest,
) -> None:
    """Omitting an unreadable account hides the gap instead of reporting it."""
    keys = {a.key for a in subject.provider.list_accounts()}  # type: ignore[attr-defined]
    assert subject.denied_account in keys


def test_the_organization_has_exactly_one_root(subject: ProviderUnderTest) -> None:
    nodes = list(subject.provider.describe_organization())  # type: ignore[call-arg]
    roots = [n for n in nodes if n.node_type is OrgNodeType.ROOT]
    assert len(roots) == 1


def test_every_node_reaches_the_root(subject: ProviderUnderTest) -> None:
    """A node that does not is invisible on the map without anything reporting it."""
    nodes: dict[str, OrgNode] = {
        n.node_id: n
        for n in subject.provider.describe_organization()  # type: ignore[attr-defined]
    }
    for node in nodes.values():
        seen: set[str] = set()
        current = node
        while current.parent_id is not None:
            assert current.node_id not in seen, "the tree contains a cycle"
            seen.add(current.node_id)
            current = nodes[current.parent_id]
        assert current.node_type is OrgNodeType.ROOT


def test_every_listed_account_appears_in_the_tree(subject: ProviderUnderTest) -> None:
    accounts = {a.key.account_id for a in subject.provider.list_accounts()}  # type: ignore[attr-defined]
    tree = {
        n.node_id
        for n in subject.provider.describe_organization()  # type: ignore[attr-defined]
        if n.node_type is OrgNodeType.ACCOUNT
    }
    assert accounts <= tree


def test_every_fact_carries_both_timestamps(subject: ProviderUnderTest) -> None:
    """Constraint 10. as_of is when it was true, collected_at is when we read it."""
    for account in subject.provider.list_accounts():  # type: ignore[attr-defined]
        assert account.as_of is not None
        assert account.collected_at is not None
        assert account.collected_at >= account.as_of


def test_timestamps_are_timezone_aware(subject: ProviderUnderTest) -> None:
    """A naive timestamp is a freshness claim nobody can compare across regions."""
    for account in subject.provider.list_accounts():  # type: ignore[attr-defined]
        assert account.as_of.tzinfo is not None
        assert account.collected_at.tzinfo is not None
