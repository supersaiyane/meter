"""A publisher refuses a unit twice for one tenant, never across tenants. ISS-275.

The ledger's dedup key holds no tenant, because the ledger is one tenant's. A dispatch publishes
every tenant's units through one publisher, which keyed on that key alone and so refused the
second tenant's organization wide unit as a duplicate of the first's.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from finops_ingest.dispatcher import InMemoryPublisher, WorkUnit

AT = datetime(2026, 10, 12, 6, 0, tzinfo=UTC)


def test_the_same_unit_for_two_tenants_is_published_for_both() -> None:
    first, second = (
        WorkUnit(tenant_id=uuid4(), collector="org_tree", window_start=AT, window_end=AT)
        for _ in range(2)
    )
    assert first.dedup_key == second.dedup_key
    publisher = InMemoryPublisher()
    assert publisher.publish(first)
    assert publisher.publish(second)
    assert not publisher.publish(first), "a second of one tenant's unit is still refused"
    assert publisher.published == [first, second]
