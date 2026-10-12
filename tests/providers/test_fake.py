"""The fake exists so that failure paths are as easy to test as success paths.

The three behaviours this project cares most about are all failures: an account
that denies access, a provider that throttles, and a service nobody opted into.
A fake that can only succeed would leave all three untested, and they are
exactly the ones that decide whether a screen shows a number or an honest gap.

Determinism is the other half. A fixture that reaches for the wall clock or for
randomness makes every test downstream of it untrustworthy, and the failure
arrives weeks later as a test that fails one run in fifty.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

from finops_core import errors, ports
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.org import OrgNodeType
from finops_fakes import fixtures
from finops_fakes.provider import FakeProvider

ROOT = Path(__file__).resolve().parent.parent.parent
FAKE_PACKAGE = ROOT / "finops_fakes"

# The eight provider ports, from the group rather than from `__all__`. The
# package also exports `QuerySurface`, which describes a tool holding saved
# queries rather than a cloud, and a cloud fake has no business implementing it.
PORT_TYPES = list(ports.PROVIDER_PORTS)


def provider(**kwargs: object) -> FakeProvider:
    return FakeProvider(**kwargs)  # type: ignore[arg-type]


# --- the contract ------------------------------------------------------------


def test_implements_all_eight_ports() -> None:
    subject = provider()
    for port in PORT_TYPES:
        assert isinstance(subject, port), port.__name__


# --- the fixture organization ------------------------------------------------


def test_the_fixture_has_a_root_two_units_and_five_accounts() -> None:
    subject = provider()
    nodes = list(subject.describe_organization())
    by_type = {t: [n for n in nodes if n.node_type is t] for t in OrgNodeType}
    assert len(by_type[OrgNodeType.ROOT]) == 1
    assert len(by_type[OrgNodeType.OU]) == 2
    assert len(by_type[OrgNodeType.ACCOUNT]) == 5
    assert len(list(subject.list_accounts())) == 5


def test_every_fixture_node_hangs_off_the_root() -> None:
    nodes = {n.node_id: n for n in provider().describe_organization()}
    for node in nodes.values():
        seen = set()
        current = node
        while current.parent_id is not None:
            assert current.node_id not in seen, "the fixture tree contains a cycle"
            seen.add(current.node_id)
            current = nodes[current.parent_id]
        assert current.node_type is OrgNodeType.ROOT


def test_discovery_still_lists_the_account_that_denies_access() -> None:
    """An account we cannot read is still an account, and hiding it hides the gap."""
    keys = {a.key for a in provider().list_accounts()}
    assert fixtures.DENIED_ACCOUNT_KEY in keys


# --- failure paths -----------------------------------------------------------


def test_the_denied_account_raises_access_denied_not_a_generic_error() -> None:
    with pytest.raises(errors.AccessDenied) as caught:
        provider().session_for(fixtures.DENIED_ACCOUNT_KEY, fixtures.REGION)
    assert caught.value.scope_key == f"{fixtures.DENIED_ACCOUNT_KEY}:{fixtures.REGION}"
    assert caught.value.remediation


@pytest.mark.parametrize(
    "cause",
    [
        errors.AccessDenied,
        errors.Throttled,
        errors.NotOptedIn,
        errors.NoData,
        errors.Unreachable,
        errors.SchemaDrift,
    ],
)
def test_any_of_the_six_causes_can_be_planned_for_a_scope(
    cause: type[errors.CollectionError],
) -> None:
    key = fixtures.ACCOUNT_KEYS[0]
    subject = provider(failures={str(key): cause})
    with pytest.raises(cause):
        subject.session_for(key, fixtures.REGION)


def test_a_planned_failure_at_the_organization_scope_stops_discovery() -> None:
    subject = provider(failures={fixtures.ORGANIZATION_SCOPE: errors.NotOptedIn})
    with pytest.raises(errors.NotOptedIn):
        list(subject.describe_organization())


def test_an_unplanned_scope_succeeds() -> None:
    subject = provider(failures={"aws:not-a-fixture-account": errors.Throttled})
    assert subject.session_for(fixtures.ACCOUNT_KEYS[0], fixtures.REGION) is not None


# --- determinism -------------------------------------------------------------


def test_two_runs_produce_the_same_output() -> None:
    first = [tuple(sorted(str(a.key) for a in provider().list_accounts())) for _ in range(3)]
    assert len(set(first)) == 1


def test_timestamps_do_not_move_between_runs() -> None:
    one = next(iter(provider().list_accounts()))
    two = next(iter(provider().list_accounts()))
    assert one.as_of == two.as_of
    assert one.collected_at == two.collected_at


def test_the_fixtures_touch_neither_the_clock_nor_randomness() -> None:
    banned = {"random", "uuid4", "now", "today", "monotonic", "time"}
    offenders: list[str] = []
    for path in sorted(FAKE_PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in banned:
                offenders.append(f"{path.name}: {node.attr}")
            if isinstance(node, ast.Name) and node.id in banned:
                offenders.append(f"{path.name}: {node.id}")
    assert offenders == []


def test_collected_at_is_never_before_as_of() -> None:
    for account in provider().list_accounts():
        assert account.collected_at >= account.as_of


# --- the remaining ports -----------------------------------------------------


def test_cost_rows_come_back_as_focus_records() -> None:
    subject = provider()
    period = subject.latest_available_period()
    assert period is not None
    rows = list(subject.read_period(period, fixtures.PERIOD_END))
    assert rows
    assert all(row.billed_cost is not None for row in rows)


def test_a_period_with_nothing_in_it_raises_no_data_rather_than_returning_empty() -> None:
    """NoData is the one cause a caller may draw as a zero, so it has to be said."""
    subject = provider()
    with pytest.raises(errors.NoData):
        list(subject.read_period(date(2020, 1, 1), date(2020, 2, 1)))


def test_metrics_resources_and_quotas_return_domain_types() -> None:
    subject = provider()
    key = fixtures.ACCOUNT_KEYS[0]
    assert list(
        subject.read_series(
            key,
            fixtures.REGION,
            fixtures.NAMESPACE,
            fixtures.METRIC_NAME,
            {},
            "Sum",
            fixtures.WINDOW_START,
            fixtures.WINDOW_END,
        )
    )
    assert list(subject.list_resources(key, fixtures.REGION))
    assert list(subject.list_quotas(key, fixtures.REGION))


def test_dependencies_exclude_the_resource_asked_about() -> None:
    """One level out, and the walk belongs to the caller so it can be bounded."""
    subject = provider()
    key = fixtures.ACCOUNT_KEYS[0]
    target = fixtures.RESOURCES[0]
    neighbours = list(subject.list_dependencies(key, target.resource_id))
    assert target.resource_id not in {ref.resource_id for ref in neighbours}
    assert neighbours


def test_dependencies_are_refused_for_an_account_that_denies_access() -> None:
    with pytest.raises(errors.AccessDenied):
        list(provider().list_dependencies(fixtures.DENIED_ACCOUNT_KEY, "fake-resource-a"))


def test_an_unknown_token_is_refused_without_saying_why() -> None:
    with pytest.raises(errors.AccessDenied):
        provider().authenticate("not-a-token")


def test_a_known_token_resolves_to_a_principal_and_a_scope() -> None:
    subject = provider()
    principal = subject.authenticate(fixtures.VALID_TOKEN)
    entitlement = subject.resolve(principal)
    assert entitlement.principal == principal
    assert entitlement.scope.permits(fixtures.ACCOUNT_KEYS[0])


def test_an_unknown_principal_resolves_to_an_empty_scope_rather_than_raising() -> None:
    """Failing closed beats an exception that tempts a caller into a fallback."""
    subject = provider()
    stranger = fixtures.STRANGER
    entitlement = subject.resolve(stranger)
    assert entitlement.scope.is_global is False
    assert entitlement.scope.accounts == frozenset()
    assert entitlement.scope.permits(fixtures.ACCOUNT_KEYS[0]) is False


def test_no_fixture_account_id_can_be_mistaken_for_a_real_one() -> None:
    """A twelve digit literal in a fixture is one somebody eventually pages about."""
    for key in fixtures.ACCOUNT_KEYS:
        assert not key.account_id.isdigit()
        assert key.provider is Provider.AWS


def test_a_key_the_fixture_does_not_know_is_refused() -> None:
    unknown = AccountKey(provider=Provider.AWS, account_id="fake-not-enrolled")
    with pytest.raises(errors.AccessDenied):
        provider().session_for(unknown, fixtures.REGION)
