"""Performance budgets 1 and 2 from specification section 11b.

What these measure, stated plainly, because a performance number without its
conditions is a number nobody can act on.

Budget 1 runs against the fake provider, so it measures this project's own
machinery: claiming, dispatching, the per unit transaction, the ledger writes
and the watermark updates. It does not measure AWS latency, which is additive
and can only be measured against real accounts. A sweep that is already slow
here would be hopeless with a network in the way, so this is a floor rather
than a verdict.

Budget 2 runs against a real PostgreSQL through the real routes, including the
scope guard and the audit write, so it is closer to the thing itself. What it
lacks is a loaded database and a network hop.
"""

from __future__ import annotations

import statistics
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from finops_api.identity import SessionSigner
from finops_api.main import create_app
from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.identity import Entitlement, Principal
from finops_core.domain.tenant import Scope
from finops_ingest.dispatcher import Dispatcher, InMemoryPublisher
from finops_ingest.registry import Collector, CollectorOutcome, CollectorRegistry, CollectorScope
from finops_ingest.worker import Worker

pytestmark = pytest.mark.integration

ACCOUNT_COUNT = 300
REGIONS = ("eu-west-1",)
NOW = datetime(2026, 8, 27, 6, 0, tzinfo=UTC)

#: Budget 1. The cadence is hourly and the definition of done is a new account
#: visible within one hour, so a sweep taking longer than a quarter of its own
#: cadence leaves no headroom for a retry.
SWEEP_BUDGET_SECONDS = 15 * 60

#: Budget 2. Three times better than the ADR-0003 tripwire, so there is room to
#: degrade before the architecture has to be reconsidered.
API_P95_BUDGET_SECONDS = 0.5

#: Enough samples for a p95 to mean something without the test taking minutes.
API_SAMPLES = 60


def accounts(count: int) -> tuple[AccountKey, ...]:
    return tuple(AccountKey(provider=Provider.AWS, account_id=f"{i:012d}") for i in range(count))


def registry() -> CollectorRegistry:
    """Two collectors that do no provider work, so the clock measures our own."""

    def collect(_context: object) -> CollectorOutcome:
        return CollectorOutcome(items_written=1, bytes_read=64)

    built = CollectorRegistry()
    built.register(Collector("org_tree", CollectorScope.ACCOUNT, collect))
    built.register(Collector("account_health", CollectorScope.ACCOUNT, collect))
    return built


class StubBroker:
    def session_for(self, _account: AccountKey, _region: str) -> object:
        return object()


def test_budget_1_full_sweep_of_three_hundred_accounts(engine: Engine, tenant_id: UUID) -> None:
    """A full org_tree and account_health sweep over 300 accounts, under 15 minutes."""
    publisher = InMemoryPublisher()
    dispatcher = Dispatcher(registry(), publisher)
    units = list(
        dispatcher.enumerate_units(
            tenant_id,
            ("org_tree", "account_health"),
            accounts(ACCOUNT_COUNT),
            REGIONS,
            NOW,
            NOW + timedelta(hours=1),
        )
    )
    assert len(units) == ACCOUNT_COUNT * 2, "the sweep must cover every account and collector"

    worker = Worker(
        registry(),
        connections=engine.begin,
        claim_timeout_minutes=30,
        broker=StubBroker(),
        clock=lambda: NOW,
    )

    started = time.perf_counter()
    result = worker.handle_batch(units)
    elapsed = time.perf_counter() - started

    assert result.count(result.outcomes[0].__class__.DONE) == len(units)
    assert elapsed < SWEEP_BUDGET_SECONDS, (
        f"the sweep took {elapsed:.1f}s against the fake provider, and the budget is "
        f"{SWEEP_BUDGET_SECONDS}s including real provider latency. There is no headroom."
    )
    print(f"\nbudget 1: {len(units)} units in {elapsed:.2f}s, budget {SWEEP_BUDGET_SECONDS}s")


class StubEntitlements:
    def __init__(self, scope: Scope) -> None:
        self._scope = scope

    def resolve(self, principal: Principal) -> Entitlement:
        return Entitlement(principal=principal, scope=self._scope, as_of=NOW, collected_at=NOW)


def test_budget_2_api_p95_on_a_scoped_read(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """p95 on a scoped read, through the guard and the audit write, under 500 ms."""
    with engine.begin() as connection:
        for index in range(50):
            connection.execute(
                text(
                    "INSERT INTO cloud_account (account_pk, tenant_id, provider, account_id, "
                    "name, status, as_of, collected_at) VALUES "
                    "(:pk, :t, 'aws', :a, :a, 'ACTIVE', :at, :at)"
                ),
                {"pk": uuid4(), "t": tenant_id, "a": f"{index:012d}", "at": NOW},
            )

    scope = Scope(tenant_id=tenant_id, is_global=True, accounts=frozenset())
    signer = SessionSigner("a-test-key", ttl_hours=8, clock=lambda: NOW)
    app = create_app(
        engine=engine,
        entitlements=StubEntitlements(scope),
        signer=signer,
        settings=settings,
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {signer.issue('p', 's', scope)}"}

    # One warm request first, so the measurement is of a served endpoint rather
    # than of the first import of everything behind it.
    assert client.get("/api/v1/accounts", headers=headers).status_code == 200

    samples: list[float] = []
    for _ in range(API_SAMPLES):
        started = time.perf_counter()
        response = client.get("/api/v1/accounts", headers=headers)
        samples.append(time.perf_counter() - started)
        assert response.status_code == 200

    ordered = sorted(samples)
    p95 = ordered[int(len(ordered) * 0.95) - 1]
    print(
        f"\nbudget 2: p95 {p95 * 1000:.1f}ms over {API_SAMPLES} requests, "
        f"median {statistics.median(samples) * 1000:.1f}ms, budget "
        f"{API_P95_BUDGET_SECONDS * 1000:.0f}ms"
    )
    assert p95 < API_P95_BUDGET_SECONDS, (
        f"p95 was {p95 * 1000:.1f}ms against a local database with no network hop, "
        f"and the budget is {API_P95_BUDGET_SECONDS * 1000:.0f}ms in production."
    )
