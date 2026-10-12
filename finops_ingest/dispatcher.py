"""Fanning work out, one message per unit, with a key that makes a redispatch free.

The dispatcher enumerates units and publishes them. It does no collection and
holds no credentials, which is what keeps a fan out over three hundred accounts
cheap and what stops a bug here from being able to read anything.

The dedup key is the same key the run ledger claims on. That matters: a unit
published twice in one dispatch is refused by the publisher, and a unit sent
again by a later dispatch, or delivered twice by the queue, is a no operation at
the database, so neither end has to trust the other to have got it right. The
hub's queue is a standard SQS queue and deduplicates nothing itself.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from finops_core.domain.account import AccountKey
from finops_ingest.ledger import idempotency_key
from finops_ingest.registry import CollectorRegistry, CollectorScope

ORGANIZATION_SCOPE = "organization"


@dataclass(frozen=True)
class WorkUnit:
    """One thing one worker will do, once."""

    tenant_id: UUID
    collector: str
    window_start: datetime
    window_end: datetime
    account: AccountKey | None = None
    region: str | None = None

    @property
    def scope_key(self) -> str:
        """The identifier this unit is recorded and reported under.

        The shape is the one `docs/07-DATA-MODEL.md` documents,
        provider:account:region, so a failure in a run, a sync error and a log
        line can be joined without anyone parsing anything.
        """
        if self.account is None:
            return ORGANIZATION_SCOPE
        return f"{self.account}:{self.region}" if self.region else str(self.account)

    @property
    def dedup_key(self) -> str:
        """Identical to the key the ledger claims on, deliberately."""
        return idempotency_key(self.collector, self.scope_key, self.window_start, self.window_end)

    @property
    def publish_key(self) -> tuple[UUID, str]:
        """What a publisher refuses a second of: the tenant, and the ledger's key.

        The ledger's key holds no tenant because the ledger is one tenant's, unique on
        (tenant_id, idempotency_key). A publisher sees every tenant in one dispatch, and keyed on
        `dedup_key` alone it refused a second tenant's organization wide unit as a duplicate of
        the first's, ISS-275.
        """
        return self.tenant_id, self.dedup_key


class Publisher(Protocol):
    """Somewhere to put a unit of work.

    Returns False when the unit was recognised as a duplicate and not published.
    """

    def publish(self, unit: WorkUnit) -> bool: ...


class InMemoryPublisher:
    """A publisher for the local stack and for tests.

    It remembers the dedup keys it has seen, as `finops_ingest.sqs.SqsPublisher`
    does for one dispatch, so behaviour here and in deployment differ in
    durability rather than in semantics. Neither is the queue deduplicating: the
    hub's is a standard queue, and the ledger's claim is what makes a unit sent
    twice free.
    """

    def __init__(self) -> None:
        self.published: list[WorkUnit] = []
        self._seen: set[tuple[UUID, str]] = set()

    def publish(self, unit: WorkUnit) -> bool:
        if unit.publish_key in self._seen:
            return False
        self._seen.add(unit.publish_key)
        self.published.append(unit)
        return True


@dataclass(frozen=True)
class DispatchResult:
    published: int
    deduplicated: int

    @property
    def total(self) -> int:
        return self.published + self.deduplicated


class Dispatcher:
    """Turns a tenant, its accounts and its collectors into units of work."""

    def __init__(self, registry: CollectorRegistry, publisher: Publisher) -> None:
        self._registry = registry
        self._publisher = publisher

    def enumerate_units(
        self,
        tenant_id: UUID,
        collectors: Sequence[str],
        accounts: Sequence[AccountKey],
        regions: Sequence[str],
        window_start: datetime,
        window_end: datetime,
    ) -> Iterator[WorkUnit]:
        """One unit per (tenant, account, region, collector), or one per tenant."""
        for name in collectors:
            collector = self._registry.get(name)
            if collector.scope is CollectorScope.ORGANIZATION:
                yield WorkUnit(
                    tenant_id=tenant_id,
                    collector=name,
                    window_start=window_start,
                    window_end=window_end,
                )
                continue
            for account in accounts:
                for region in regions:
                    yield WorkUnit(
                        tenant_id=tenant_id,
                        collector=name,
                        window_start=window_start,
                        window_end=window_end,
                        account=account,
                        region=region,
                    )

    def dispatch(self, units: Iterable[WorkUnit]) -> DispatchResult:
        published = 0
        deduplicated = 0
        for unit in units:
            if self._publisher.publish(unit):
                published += 1
            else:
                deduplicated += 1
        return DispatchResult(published=published, deduplicated=deduplicated)


if __name__ == "__main__":  # pragma: no cover - run as a process, and tested as one
    from finops_ingest.processes import dispatcher_main

    raise SystemExit(dispatcher_main())
