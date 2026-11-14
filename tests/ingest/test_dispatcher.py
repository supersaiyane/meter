"""Fanning out, and the key that makes a redispatch free.

The dedup key is deliberately the same key the ledger claims on. That is what
makes a redispatch inside a window a no operation at both ends, once at the
queue and once at the database, without either end trusting the other to have
got it right.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from finops_core.domain.account import AccountKey, Provider
from finops_ingest.dispatcher import Dispatcher, InMemoryPublisher, WorkUnit
from finops_ingest.ledger import idempotency_key
from finops_ingest.registry import Collector, CollectorOutcome, CollectorRegistry, CollectorScope

TENANT = uuid4()
START = datetime(2026, 8, 24, 0, 0, tzinfo=UTC)
END = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
ACCOUNTS = (
    AccountKey(provider=Provider.AWS, account_id="111122223333"),
    AccountKey(provider=Provider.AWS, account_id="444455556666"),
)
REGIONS = ("eu-west-1", "eu-west-2")


def nothing(_context: object) -> CollectorOutcome:
    return CollectorOutcome()


def registry() -> CollectorRegistry:
    built = CollectorRegistry()
    built.register(Collector("account_health", CollectorScope.ACCOUNT, nothing))
    built.register(Collector("org_tree", CollectorScope.ORGANIZATION, nothing))
    return built


def dispatcher(publisher: InMemoryPublisher) -> Dispatcher:
    return Dispatcher(registry(), publisher)


def units(names: tuple[str, ...]) -> list[WorkUnit]:
    return list(
        dispatcher(InMemoryPublisher()).enumerate_units(
            TENANT, names, ACCOUNTS, REGIONS, START, END
        )
    )


# --- enumeration -------------------------------------------------------------


def test_one_unit_per_account_region_and_collector() -> None:
    assert len(units(("account_health",))) == len(ACCOUNTS) * len(REGIONS)


def test_an_organization_scoped_collector_gets_exactly_one_unit() -> None:
    """It runs on the hub's credentials, so fanning it per account would be waste."""
    produced = units(("org_tree",))
    assert len(produced) == 1
    assert produced[0].account is None
    assert produced[0].scope_key == "organization"


def test_the_scope_key_uses_the_documented_shape() -> None:
    """provider:account:region, so a run, an error and a log line join up."""
    produced = units(("account_health",))
    assert produced[0].scope_key == "aws:111122223333:eu-west-1"


def test_an_unknown_collector_is_a_dispatch_bug_rather_than_a_skip() -> None:
    with pytest.raises(KeyError):
        units(("no_such_collector",))


# --- deduplication -----------------------------------------------------------


def test_dedup_key_prevents_duplicate_units() -> None:
    """A redispatch inside the same window publishes nothing."""
    publisher = InMemoryPublisher()
    subject = dispatcher(publisher)
    first = subject.dispatch(
        subject.enumerate_units(TENANT, ("account_health",), ACCOUNTS, REGIONS, START, END)
    )
    second = subject.dispatch(
        subject.enumerate_units(TENANT, ("account_health",), ACCOUNTS, REGIONS, START, END)
    )
    assert first.published == 4
    assert first.deduplicated == 0
    assert second.published == 0
    assert second.deduplicated == 4
    assert len(publisher.published) == 4


def test_the_dedup_key_is_the_key_the_ledger_claims_on() -> None:
    """Two mechanisms, one identity. Neither has to trust the other."""
    unit = units(("account_health",))[0]
    assert unit.dedup_key == idempotency_key(
        unit.collector, unit.scope_key, unit.window_start, unit.window_end
    )


def test_a_different_window_is_a_different_unit() -> None:
    publisher = InMemoryPublisher()
    subject = dispatcher(publisher)
    subject.dispatch(subject.enumerate_units(TENANT, ("org_tree",), ACCOUNTS, REGIONS, START, END))
    later = subject.dispatch(
        subject.enumerate_units(
            TENANT, ("org_tree",), ACCOUNTS, REGIONS, END, datetime(2026, 8, 24, 12, tzinfo=UTC)
        )
    )
    assert later.published == 1


def test_two_accounts_never_share_a_key() -> None:
    keys = {unit.dedup_key for unit in units(("account_health",))}
    assert len(keys) == 4
