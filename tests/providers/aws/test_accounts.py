"""Discovery, and the two ways it silently lies if it is written carelessly.

An unpaginated call does not fail. It returns the first page, and those hundred
accounts become the denominator behind every organization total and every
`scope_coverage` figure on every screen. Nothing looks wrong.

A dropped account does the same thing for a different reason. A suspended or
departing account is still an account, and omitting it makes the totals wrong by
an amount that is invisible precisely because the account is missing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from finops_core import ports
from finops_core.config import Settings
from finops_core.domain.account import AccountStatus, CloudAccount
from finops_core.domain.org import OrgNode, OrgNodeType
from finops_core.errors import Throttled
from finops_providers.aws.accounts import AwsAccountDiscovery

AT = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
ROOT = "r-root"


def page(key: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {key: items}


class StubPaginator:
    def __init__(self, stub: StubOrganizations, operation: str) -> None:
        self._stub = stub
        self._operation = operation

    def paginate(self, **kwargs: Any) -> Any:
        self._stub.calls.append((self._operation, kwargs.get("ParentId")))
        if self._stub.throttle_for > 0:
            self._stub.throttle_for -= 1
            raise ClientError(
                {"Error": {"Code": "TooManyRequestsException", "Message": "slow down"}},
                self._operation,
            )
        return iter(self._stub.pages_for(self._operation, kwargs.get("ParentId")))


class StubOrganizations:
    """Programmable pages, so pagination and throttling are testable exactly."""

    def __init__(
        self,
        roots: list[dict[str, Any]],
        units: dict[str, list[list[dict[str, Any]]]] | None = None,
        accounts: dict[str, list[list[dict[str, Any]]]] | None = None,
        throttle_for: int = 0,
    ) -> None:
        self.roots = roots
        self.units = units or {}
        self.accounts = accounts or {}
        self.throttle_for = throttle_for
        self.calls: list[tuple[str, str | None]] = []

    def get_paginator(self, operation: str) -> StubPaginator:
        return StubPaginator(self, operation)

    def pages_for(self, operation: str, parent: str | None) -> list[dict[str, Any]]:
        if operation == "list_roots":
            return [page("Roots", self.roots)]
        if operation == "list_organizational_units_for_parent":
            return [
                page("OrganizationalUnits", chunk) for chunk in self.units.get(parent or "", [[]])
            ]
        return [page("Accounts", chunk) for chunk in self.accounts.get(parent or "", [[]])]


def discovery(settings: Settings, stub: StubOrganizations, **kwargs: Any) -> AwsAccountDiscovery:
    return AwsAccountDiscovery(
        settings,
        client_factory=lambda: stub,
        clock=lambda: AT,
        sleeper=kwargs.pop("sleeper", lambda _s: None),
        **kwargs,
    )


def account(identifier: str, name: str, status: str = "ACTIVE") -> dict[str, Any]:
    return {"Id": identifier, "Name": name, "Status": status}


# --- the port ----------------------------------------------------------------


def test_it_satisfies_the_account_discovery_port(settings: Settings) -> None:
    subject = discovery(settings, StubOrganizations(roots=[{"Id": ROOT, "Name": "root"}]))
    assert isinstance(subject, ports.AccountDiscovery)


# --- the tree ----------------------------------------------------------------


def four_level_stub() -> StubOrganizations:
    """root, then two units nested, then accounts at the bottom and the middle."""
    return StubOrganizations(
        roots=[{"Id": ROOT, "Name": "root"}],
        units={
            ROOT: [[{"Id": "ou-platform", "Name": "platform"}]],
            "ou-platform": [[{"Id": "ou-data", "Name": "data"}]],
        },
        accounts={
            "ou-platform": [[account("111122223333", "shared")]],
            "ou-data": [[account("444455556666", "warehouse")]],
        },
    )


def test_builds_four_level_tree(settings: Settings) -> None:
    nodes = {n.node_id: n for n in discovery(settings, four_level_stub()).describe_organization()}
    assert nodes[ROOT].node_type is OrgNodeType.ROOT
    assert nodes[ROOT].parent_id is None
    assert nodes["ou-platform"].parent_id == ROOT
    assert nodes["ou-data"].parent_id == "ou-platform"
    assert nodes["444455556666"].parent_id == "ou-data"
    assert nodes["444455556666"].node_type is OrgNodeType.ACCOUNT


def test_every_node_reaches_the_root(settings: Settings) -> None:
    nodes = {n.node_id: n for n in discovery(settings, four_level_stub()).describe_organization()}
    for node in nodes.values():
        current = node
        seen: set[str] = set()
        while current.parent_id is not None:
            assert current.node_id not in seen, "the tree contains a cycle"
            seen.add(current.node_id)
            current = nodes[current.parent_id]
        assert current.node_type is OrgNodeType.ROOT


def test_returns_domain_types_never_a_raw_api_shape(settings: Settings) -> None:
    subject = discovery(settings, four_level_stub())
    assert all(isinstance(n, OrgNode) for n in subject.describe_organization())
    assert all(isinstance(a, CloudAccount) for a in subject.list_accounts())


def test_every_fact_carries_both_timestamps(settings: Settings) -> None:
    for record in discovery(settings, four_level_stub()).list_accounts():
        assert record.as_of == AT
        assert record.collected_at == AT


# --- pagination --------------------------------------------------------------


def test_paginates(settings: Settings) -> None:
    """Three hundred accounts, not the first hundred."""
    pages = [
        [account(f"{i:012d}", f"account-{i}") for i in range(start, start + 100)]
        for start in (0, 100, 200)
    ]
    stub = StubOrganizations(roots=[{"Id": ROOT, "Name": "root"}], accounts={ROOT: pages})
    assert len(list(discovery(settings, stub).list_accounts())) == 300


def test_organizational_units_paginate_too(settings: Settings) -> None:
    stub = StubOrganizations(
        roots=[{"Id": ROOT, "Name": "root"}],
        units={ROOT: [[{"Id": f"ou-{i}", "Name": f"ou-{i}"}] for i in range(5)]},
    )
    units = [
        n
        for n in discovery(settings, stub).describe_organization()
        if n.node_type is OrgNodeType.OU
    ]
    assert len(units) == 5


def test_no_call_is_made_without_a_paginator(settings: Settings) -> None:
    """An unpaginated call returns the first page and looks like a full answer."""
    stub = StubOrganizations(roots=[{"Id": ROOT, "Name": "root"}])
    discovery(settings, stub).list_accounts()
    assert stub.calls
    assert all(operation.startswith("list_") for operation, _ in stub.calls)


# --- statuses ----------------------------------------------------------------


def test_suspended_account_is_marked_not_dropped(settings: Settings) -> None:
    stub = StubOrganizations(
        roots=[{"Id": ROOT, "Name": "root"}],
        accounts={
            ROOT: [[account("111122223333", "live"), account("444455556666", "old", "SUSPENDED")]]
        },
    )
    found = {a.key.account_id: a.status for a in discovery(settings, stub).list_accounts()}
    assert found == {
        "111122223333": AccountStatus.ACTIVE,
        "444455556666": AccountStatus.SUSPENDED,
    }


def test_a_departing_account_is_kept(settings: Settings) -> None:
    stub = StubOrganizations(
        roots=[{"Id": ROOT, "Name": "root"}],
        accounts={ROOT: [[account("111122223333", "leaving", "PENDING_CLOSURE")]]},
    )
    found = list(discovery(settings, stub).list_accounts())
    assert found[0].status is AccountStatus.DEPARTED


def test_an_unrecognised_status_becomes_unknown_rather_than_a_drop(
    settings: Settings,
) -> None:
    """Dropping it shrinks the denominator behind every total. ISS-016."""
    stub = StubOrganizations(
        roots=[{"Id": ROOT, "Name": "root"}],
        accounts={ROOT: [[account("111122223333", "odd", "SOMETHING_NEW")]]},
    )
    found = list(discovery(settings, stub).list_accounts())
    assert len(found) == 1
    assert found[0].status is AccountStatus.UNKNOWN


# --- throttling --------------------------------------------------------------


def test_backs_off_on_throttling_rather_than_failing(settings: Settings) -> None:
    waits: list[float] = []
    stub = StubOrganizations(roots=[{"Id": ROOT, "Name": "root"}], throttle_for=1)
    subject = discovery(settings, stub, sleeper=waits.append)
    assert list(subject.describe_organization())
    assert waits, "a throttled call must wait before retrying, not sprint"


def test_it_gives_up_as_throttled_after_the_configured_retries(
    settings: Settings,
) -> None:
    """Bounded. An unbounded retry across three hundred accounts is the herd."""
    stub = StubOrganizations(
        roots=[{"Id": ROOT, "Name": "root"}],
        throttle_for=settings.aws_max_retries + 5,
    )
    subject = discovery(settings, stub, sleeper=lambda _s: None)
    with pytest.raises(Throttled):
        list(subject.describe_organization())


def test_the_backoff_grows_between_attempts(settings: Settings) -> None:
    waits: list[float] = []
    stub = StubOrganizations(
        roots=[{"Id": ROOT, "Name": "root"}], throttle_for=settings.aws_max_retries
    )
    subject = discovery(settings, stub, sleeper=waits.append)
    list(subject.describe_organization())
    assert waits == sorted(waits)
    if len(waits) > 1:
        assert waits[1] > waits[0]


# --- against moto ------------------------------------------------------------


@mock_aws
def test_the_real_api_shape_resolves_into_domain_types(settings: Settings) -> None:
    client = boto3.client("organizations", region_name="eu-west-1")
    client.create_organization(FeatureSet="ALL")
    root_id = client.list_roots()["Roots"][0]["Id"]
    unit = client.create_organizational_unit(ParentId=root_id, Name="platform")
    unit_id = unit["OrganizationalUnit"]["Id"]
    created = client.create_account(Email="team@example.invalid", AccountName="shared")
    account_id = created["CreateAccountStatus"]["AccountId"]
    client.move_account(AccountId=account_id, SourceParentId=root_id, DestinationParentId=unit_id)

    subject = AwsAccountDiscovery(settings, client_factory=lambda: client, clock=lambda: AT)
    nodes = {n.node_id: n for n in subject.describe_organization()}
    assert nodes[root_id].node_type is OrgNodeType.ROOT
    assert nodes[unit_id].parent_id == root_id
    assert nodes[account_id].parent_id == unit_id
    assert any(a.key.account_id == account_id for a in subject.list_accounts())
