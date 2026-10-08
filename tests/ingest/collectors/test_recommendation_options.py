"""Compute Optimizer's ranked options, priced from the catalog, over a real database. TASK-P9-006.

The fake's oversized instance runs as m5.xlarge and is offered m6i.large, then Graviton m6g.large,
which the fake catalog does not sell, then m5.large. So with the catalog loaded, two options are
priced and one is kept saying why it is not.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.catalog import Price, PriceListVersion
from finops_core.domain.waste import Recommendation, ScopedFindings, Source
from finops_core.errors import Throttled
from finops_fakes import fixtures
from finops_fakes.catalog import VERSION, FakePriceCatalog, on_demand_hourly
from finops_fakes.recommendations import FakeRecommendationSource, findings
from finops_ingest.collectors.price_catalog import PriceCatalogCollector
from finops_ingest.collectors.recommendations import RecommendationCollector
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)
OVERSIZED = f"arn:aws:ec2:{fixtures.REGION}:fake-platform-a:instance/i-oversized"
BURSTABLE = f"arn:aws:ec2:{fixtures.REGION}:fake-platform-b:instance/i-burstable"


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


def collect(engine: Engine, tenant: UUID, provider: object | None = None) -> None:
    with engine.begin() as connection:
        RecommendationCollector(provider or FakeRecommendationSource(), clock=lambda: NOW)(
            CollectorContext(unit=Unit(tenant_id=tenant), connection=connection, run_id=uuid4())
        )


def priced(engine: Engine, tenant: UUID, source: Any = None) -> None:
    unit = WorkUnit(
        tenant_id=tenant,
        collector="price_catalog",
        window_start=NOW,
        window_end=NOW,
        account=None,
        region=None,
    )
    with engine.begin() as connection:
        PriceCatalogCollector(source or FakePriceCatalog(), clock=lambda: NOW)(
            CollectorContext(unit=unit, connection=connection, run_id=uuid4())
        )


def options_of(engine: Engine, tenant: UUID, reference: str) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                text(
                    "SELECT o.* FROM recommendation_option o "
                    "JOIN recommendation r ON r.recommendation_id = o.recommendation_id "
                    "WHERE o.tenant_id = :t AND r.source_reference = :ref ORDER BY o.rank"
                ),
                {"t": tenant, "ref": reference},
            ).mappings()
        ]


def recommendation(engine: Engine, tenant: UUID, reference: str) -> dict[str, Any]:
    with engine.connect() as connection:
        return dict(
            connection.execute(
                text(
                    "SELECT * FROM recommendation WHERE tenant_id = :t AND source_reference = :ref"
                ),
                {"t": tenant, "ref": reference},
            )
            .mappings()
            .one()
        )


class Republished:
    """The fake catalog, every Region republished a day later under a new version."""

    def __init__(self) -> None:
        self._inner = FakePriceCatalog()

    def versions(self, service_code: str) -> Iterable[PriceListVersion]:
        return tuple(
            replace(v, version="20260821000000", as_of=v.as_of + timedelta(days=1))
            for v in self._inner.versions(service_code)
        )

    def prices(self, version: PriceListVersion) -> Iterator[Price]:
        original = replace(version, version=VERSION, as_of=version.as_of - timedelta(days=1))
        for price in self._inner.prices(original):
            yield replace(price, version=version.version, as_of=version.as_of)


class Scoped:
    """Compute Optimizer read in one account, the other refused; the other services empty."""

    def __init__(self, found: tuple[Recommendation, ...]) -> None:
        self._found = found

    def compute_optimizer(self) -> ScopedFindings:
        return ScopedFindings(
            found=self._found,
            read=frozenset({("fake-platform-a", fixtures.REGION)}),
            refused=(
                Throttled(
                    scope_key=f"fake-platform-b:{fixtures.REGION}", collector="recommendations"
                ),
            ),
        )

    def cost_optimization_hub(self) -> Iterable[Recommendation]:
        return ()

    def trusted_advisor(self) -> Iterable[Recommendation]:
        return ()


def test_without_a_catalog_every_option_is_kept_and_says_why(
    engine: Engine, tenant_id: UUID
) -> None:
    collect(engine, tenant_id)
    found = options_of(engine, tenant_id, OVERSIZED)
    assert [o["instance_type"] for o in found] == ["m6i.large", "m6g.large", "m5.large"]
    assert all(o["sku_price_id"] is None and o["hourly_price"] is None for o in found)
    assert all(f"no EC2 price list for {fixtures.REGION}" in o["unpriced_reason"] for o in found)
    held = recommendation(engine, tenant_id, OVERSIZED)
    assert held["target_instance_type"] is None
    assert held["price_version"] is None


def test_with_the_catalog_each_option_is_priced_or_kept_saying_why(
    engine: Engine, tenant_id: UUID
) -> None:
    priced(engine, tenant_id)
    collect(engine, tenant_id)
    first, graviton, third = options_of(engine, tenant_id, OVERSIZED)
    assert first["hourly_price"] == on_demand_hourly("m6i.large")
    assert first["price_version"] == VERSION
    assert third["hourly_price"] == on_demand_hourly("m5.large")
    assert graviton["sku_price_id"] is None
    assert "no Linux on demand price for m6g.large" in graviton["unpriced_reason"]
    assert graviton["platform_differences"] == ["Architecture"]
    held = recommendation(engine, tenant_id, OVERSIZED)
    assert held["target_instance_type"] == "m6i.large"
    assert held["target_sku_price_id"] == first["sku_price_id"]
    assert held["current_sku_price_id"] is not None
    assert held["price_version"] == VERSION


def test_a_re_read_replaces_the_options_rather_than_adding_to_them(
    engine: Engine, tenant_id: UUID
) -> None:
    priced(engine, tenant_id)
    collect(engine, tenant_id)
    collect(engine, tenant_id)
    assert len(options_of(engine, tenant_id, OVERSIZED)) == 3


def test_a_price_an_option_quotes_outlives_a_new_catalog_version(
    engine: Engine, tenant_id: UUID
) -> None:
    priced(engine, tenant_id)
    collect(engine, tenant_id)
    priced(engine, tenant_id, Republished())
    first, *_ = options_of(engine, tenant_id, OVERSIZED)
    with engine.connect() as connection:
        still = connection.execute(
            text(
                "SELECT count(*) FROM price WHERE tenant_id = :t AND sku_price_id = :sku "
                "AND version = :v"
            ),
            {"t": tenant_id, "sku": first["sku_price_id"], "v": VERSION},
        ).scalar_one()
    assert still == 1


def test_a_refused_scope_keeps_its_findings_and_says_why(engine: Engine, tenant_id: UUID) -> None:
    collect(engine, tenant_id)
    # The oversized instance's account was read and it was gone; the burstable one's was not.
    collect(engine, tenant_id, Scoped(found=()))
    assert recommendation(engine, tenant_id, OVERSIZED)["lifecycle"] == "DISMISSED"
    assert recommendation(engine, tenant_id, BURSTABLE)["lifecycle"] == "OPEN"
    with engine.connect() as connection:
        cause = connection.execute(
            text(
                "SELECT error_type FROM sync_error WHERE tenant_id = :t "
                "AND collector = 'recommendations' AND scope_key = :s"
            ),
            {"t": tenant_id, "s": f"fake-platform-b:{fixtures.REGION}"},
        ).scalar_one()
    assert cause == "Throttled"


def test_a_scoped_read_still_writes_what_it_found(engine: Engine, tenant_id: UUID) -> None:
    oversized = next(f for f in findings(NOW) if f.source is Source.COMPUTE_OPTIMIZER)
    collect(engine, tenant_id, Scoped(found=(oversized,)))
    assert recommendation(engine, tenant_id, oversized.source_reference)["lifecycle"] == "OPEN"
    assert len(options_of(engine, tenant_id, oversized.source_reference)) == 3
