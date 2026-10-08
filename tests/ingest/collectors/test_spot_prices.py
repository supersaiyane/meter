"""Spot prices folded into the latest and a 90 day daily range, against a migrated database.

TASK-P9-013, FEAT-071, OPEN-18. The fake answers a window as EC2 does: each pool's price when it
opened, a day earlier, and one change an hour into it. At `AT` the first window opens at 22:00 the
day before, so a pool's two readings fall on 2026-10-07 and its price at the close on 2026-10-08.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.catalog import SpotPrice
from finops_core.errors import AccessDenied
from finops_fakes.catalog import FakePriceCatalog, FakeSpotPrices
from finops_fakes.estate_shape import REGIONS
from finops_fakes.prices import INSTANCE_USD
from finops_ingest.collectors.price_catalog import PriceCatalogCollector
from finops_ingest.collectors.spot_prices import RETAIN_DAYS, SpotPricesCollector
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext, CollectorOutcome

AT = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
POOLS = len(INSTANCE_USD) * 2

pytestmark = pytest.mark.integration


def context(connection: Any, tenant: UUID, collector: str) -> CollectorContext:
    unit = WorkUnit(
        tenant_id=tenant,
        collector=collector,
        window_start=AT,
        window_end=AT,
        account=None,
        region=None,
    )
    return CollectorContext(unit=unit, connection=connection, run_id=uuid4())


def run(engine: Engine, tenant: UUID, source: Any, at: datetime = AT) -> CollectorOutcome:
    with engine.begin() as connection:
        collector = SpotPricesCollector(source, clock=lambda: at)
        return collector(context(connection, tenant, "spot_prices"))


def priced(engine: Engine, tenant: UUID) -> None:
    with engine.begin() as connection:
        PriceCatalogCollector(FakePriceCatalog(), clock=lambda: AT)(
            context(connection, tenant, "price_catalog")
        )


def rows(engine: Engine, tenant: UUID, table: str, **where: Any) -> list[dict[str, Any]]:
    clauses = "".join(f" AND {column} = :{column}" for column in where)
    with engine.connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                text(f"SELECT * FROM {table} WHERE tenant_id = :t{clauses}"),
                {"t": tenant, **where},
            ).mappings()
        ]


def pool_of(row: dict[str, Any]) -> tuple[str, str, str]:
    return (row["availability_zone"], row["instance_type"], row["product_description"])


def m5_large(engine: Engine, tenant: UUID, table: str) -> list[dict[str, Any]]:
    """The rows of one pool, m5.large in the first Region's first zone."""
    region = sorted(REGIONS)[0]
    pool = (f"{region}a", "m5.large", "Linux/UNIX")
    return [r for r in rows(engine, tenant, table, region=region) if pool_of(r) == pool]


class Older:
    """The fake, every reading a week older than the window it was asked for."""

    def __init__(self) -> None:
        self._inner = FakeSpotPrices()

    def prices(self, region: str, since: datetime) -> Iterable[SpotPrice]:
        return self._inner.prices(region, since - timedelta(days=7))


def test_with_no_prices_held_there_is_no_region_to_read(engine: Engine, tenant_id: UUID) -> None:
    outcome = run(engine, tenant_id, FakeSpotPrices())
    assert outcome.items_written == 0
    assert rows(engine, tenant_id, "spot_price") == []


def test_a_first_read_stores_the_latest_and_each_days_range(
    engine: Engine, tenant_id: UUID
) -> None:
    priced(engine, tenant_id)
    outcome = run(engine, tenant_id, FakeSpotPrices())
    # Each pool once in spot_price, and on two days in spot_price_daily.
    assert outcome.items_written == POOLS * 3 * len(REGIONS)
    (latest,) = m5_large(engine, tenant_id, "spot_price")
    days = {r["day"]: r for r in m5_large(engine, tenant_id, "spot_price_daily")}
    assert set(days) == {date(2026, 10, 7), date(2026, 10, 8)}
    first, closing = days[date(2026, 10, 7)], days[date(2026, 10, 8)]
    assert first["readings"] == 2
    assert first["low"] < first["high"]
    assert closing["readings"] == 1
    assert closing["low"] == closing["high"] == latest["price"]
    assert latest["as_of"] == datetime(2026, 10, 7, 23, 0, tzinfo=UTC)


def test_the_next_window_opens_where_the_last_read_ended_and_merges_its_day(
    engine: Engine, tenant_id: UUID
) -> None:
    priced(engine, tenant_id)
    run(engine, tenant_id, FakeSpotPrices())
    run(engine, tenant_id, FakeSpotPrices(), at=AT + timedelta(hours=8))
    days = {r["day"]: r for r in m5_large(engine, tenant_id, "spot_price_daily")}
    assert days[date(2026, 10, 8)]["readings"] == 3
    (latest,) = m5_large(engine, tenant_id, "spot_price")
    assert latest["as_of"] == datetime(2026, 10, 8, 1, 0, tzinfo=UTC)


def test_the_latest_price_is_never_rolled_back_by_an_older_reading(
    engine: Engine, tenant_id: UUID
) -> None:
    priced(engine, tenant_id)
    run(engine, tenant_id, FakeSpotPrices())
    before = {pool_of(r): r["as_of"] for r in rows(engine, tenant_id, "spot_price")}
    run(engine, tenant_id, Older(), at=AT + timedelta(hours=8))
    after = {pool_of(r): r["as_of"] for r in rows(engine, tenant_id, "spot_price")}
    assert after == before


def test_a_day_older_than_ninety_is_removed_and_the_ninetieth_kept(
    engine: Engine, tenant_id: UUID
) -> None:
    priced(engine, tenant_id)
    region = sorted(REGIONS)[0]
    with engine.begin() as connection:
        for age in (RETAIN_DAYS, RETAIN_DAYS + 1):
            day = AT.date() - timedelta(days=age)
            noon = datetime(day.year, day.month, day.day, 12, tzinfo=UTC)
            connection.execute(
                text(
                    "INSERT INTO spot_price_daily (spot_day_pk, tenant_id, ingest_run_id, region, "
                    "availability_zone, instance_type, product_description, day, low, high, "
                    "readings, as_of, collected_at) VALUES (:pk, :t, :run, :r, :z, 'm5.large', "
                    "'Linux/UNIX', :day, 0.03, 0.04, 1, :at, :at)"
                ),
                {
                    "pk": uuid4(),
                    "t": tenant_id,
                    "run": uuid4(),
                    "r": region,
                    "z": f"{region}a",
                    "day": day,
                    "at": noon,
                },
            )
    outcome = run(engine, tenant_id, FakeSpotPrices())
    assert outcome.items_removed == 1
    kept = {r["day"] for r in rows(engine, tenant_id, "spot_price_daily", region=region)}
    assert AT.date() - timedelta(days=RETAIN_DAYS) in kept
    assert AT.date() - timedelta(days=RETAIN_DAYS + 1) not in kept


def test_a_region_not_opted_into_is_recorded_and_the_rest_stored(
    engine: Engine, tenant_id: UUID
) -> None:
    priced(engine, tenant_id)
    refused = sorted(REGIONS)[1]
    run(engine, tenant_id, FakeSpotPrices(not_opted_in=[refused]))
    assert {r["region"] for r in rows(engine, tenant_id, "spot_price")} == set(REGIONS) - {refused}
    with engine.connect() as connection:
        found = connection.execute(
            text(
                "SELECT error_type FROM sync_error WHERE tenant_id = :t "
                "AND collector = 'spot_prices' AND scope_key = :s"
            ),
            {"t": tenant_id, "s": f"spot:{refused}"},
        ).scalar_one()
    assert found == "NotOptedIn"


def test_a_run_that_reads_nothing_at_all_fails(engine: Engine, tenant_id: UUID) -> None:
    priced(engine, tenant_id)
    with pytest.raises(AccessDenied):
        run(engine, tenant_id, FakeSpotPrices(failure=AccessDenied))


def test_a_price_is_held_as_the_decimal_it_was_read_as(engine: Engine, tenant_id: UUID) -> None:
    priced(engine, tenant_id)
    run(engine, tenant_id, FakeSpotPrices())
    stored = rows(engine, tenant_id, "spot_price")
    assert stored
    assert all(isinstance(r["price"], Decimal) and r["price"] > 0 for r in stored)
