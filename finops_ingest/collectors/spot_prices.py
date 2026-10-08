"""Spot prices: the latest per pool, and each day's low and high for 90 days. TASK-P9-013.

FEAT-071, P9 spec sections 14 and 14.7, and OPEN-18 as the owner answered it on 2026-10-07.
Readings come through the relay outside the VPC, ADR-0035.

**A window since the last read.** Each Region is asked for the window from the last time its
prices were collected to now, or the last 8 hours on a first read. EC2 answers with the price each
pool had when the window opened and every change inside it, so every pool arrives each run.

**The latest is replaced, never rolled back.** `spot_price` holds one row a pool, replaced by a
reading at least as new, so a late page cannot put an older price back. A pool whose price has not
moved has its `collected_at` refreshed, which is how freshness reads on a screen.

**Each day's low and high.** A reading counts towards the day it was in effect on: the day it was
set, or the day the window opened for a price set before it, and the price still in effect when
the window closes counts towards that day too. Days merge across runs, the low only falling and
the high only rising; `readings` counts observations, so a price seen in two windows counts twice.
A window longer than a day, after an outage, records the days at its two ends only.

**Ninety days, then removed.** Each run removes daily rows older than `RETAIN_DAYS`, counted in
`items_removed`. The latest price per pool is kept however old, with its own `as_of`.

**One Region fails alone**, constraint 5, recorded in `sync_error` by its typed cause; a Region not
opted into is NotOptedIn and never a price of nought. Only a run that read nothing at all fails.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.catalog import SpotPrice
from finops_core.errors import CollectionError
from finops_core.ports.catalog import SpotPrices
from finops_ingest.collectors.price_catalog import BATCH, refuse
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "spot_prices"
EC2: Final = "AmazonEC2"
#: How long a day's low and high are kept, OPEN-18.
RETAIN_DAYS: Final = 90
#: The window a Region's first read covers: one cadence of the schedule row, 8 hours.
FIRST_WINDOW: Final = timedelta(hours=8)

#: Every Region the price catalog holds an EC2 version for.
REGIONS = text(
    "SELECT DISTINCT region FROM price_list_version WHERE tenant_id = :t AND service_code = :s"
)
LAST_READ = text("SELECT max(collected_at) FROM spot_price WHERE tenant_id = :t AND region = :r")

WRITE_LATEST = text(
    "INSERT INTO spot_price (spot_pk, tenant_id, ingest_run_id, region, availability_zone, "
    "instance_type, product_description, price, as_of, collected_at) "
    "VALUES (:pk, :t, :run, :r, :zone, :type, :product, :price, :as_of, :collected) "
    "ON CONFLICT (tenant_id, region, availability_zone, instance_type, product_description) "
    "DO UPDATE SET price = EXCLUDED.price, as_of = EXCLUDED.as_of, "
    "collected_at = EXCLUDED.collected_at, ingest_run_id = EXCLUDED.ingest_run_id "
    "WHERE spot_price.as_of <= EXCLUDED.as_of"
)

WRITE_DAY = text(
    "INSERT INTO spot_price_daily (spot_day_pk, tenant_id, ingest_run_id, region, "
    "availability_zone, instance_type, product_description, day, low, high, readings, as_of, "
    "collected_at) "
    "VALUES (:pk, :t, :run, :r, :zone, :type, :product, :day, :low, :high, :readings, :as_of, "
    ":collected) "
    "ON CONFLICT (tenant_id, region, availability_zone, instance_type, product_description, day) "
    "DO UPDATE SET low = LEAST(spot_price_daily.low, EXCLUDED.low), "
    "high = GREATEST(spot_price_daily.high, EXCLUDED.high), "
    "readings = spot_price_daily.readings + EXCLUDED.readings, "
    "as_of = GREATEST(spot_price_daily.as_of, EXCLUDED.as_of), "
    "collected_at = GREATEST(spot_price_daily.collected_at, EXCLUDED.collected_at), "
    "ingest_run_id = EXCLUDED.ingest_run_id"
)

EXPIRE_DAYS = text("DELETE FROM spot_price_daily WHERE tenant_id = :t AND day < :cutoff")

Pool = tuple[str, str, str]


def _system_clock() -> datetime:
    return datetime.now(UTC)


def daily(
    readings: Sequence[SpotPrice], since: datetime, until: datetime
) -> dict[tuple[Pool, date], list[SpotPrice]]:
    """The readings each pool's day is made of, by the rule in this module's docstring."""
    days: dict[tuple[Pool, date], list[SpotPrice]] = defaultdict(list)
    latest = newest(readings)
    for reading in readings:
        days[(reading.pool, max(reading.as_of, since).date())].append(reading)
    closing = until.date()
    for pool, reading in latest.items():
        if max(reading.as_of, since).date() != closing:
            days[(pool, closing)].append(reading)
    return days


def newest(readings: Sequence[SpotPrice]) -> dict[Pool, SpotPrice]:
    """Each pool's newest reading, the one in effect when the window closed."""
    latest: dict[Pool, SpotPrice] = {}
    for reading in readings:
        held = latest.get(reading.pool)
        if held is None or reading.as_of >= held.as_of:
            latest[reading.pool] = reading
    return latest


class SpotPricesCollector:
    """Each Region's spot window, folded into the latest price and the daily low and high."""

    def __init__(self, source: SpotPrices, clock: Callable[[], datetime] = _system_clock) -> None:
        self._source = source
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        now = self._clock()
        tenant = context.unit.tenant_id
        connection = context.connection
        regions = sorted(r.region for r in connection.execute(REGIONS, {"t": tenant, "s": EC2}))
        written = 0
        read = False
        failures: list[CollectionError] = []
        for region in regions:
            last = connection.execute(LAST_READ, {"t": tenant, "r": region}).scalar_one()
            since = last or now - FIRST_WINDOW
            try:
                readings = tuple(self._source.prices(region, since))
            except CollectionError as failure:
                failures.append(refuse(context, COLLECTOR, failure, now))
                continue
            read = True
            written += self._store(context, region, readings, since, now)
        cutoff = now.date() - timedelta(days=RETAIN_DAYS)
        removed = connection.execute(EXPIRE_DAYS, {"t": tenant, "cutoff": cutoff}).rowcount
        if failures and not read:
            raise failures[0]
        return CollectorOutcome(items_written=written, items_removed=int(removed))

    @staticmethod
    def _store(
        context: CollectorContext,
        region: str,
        readings: Sequence[SpotPrice],
        since: datetime,
        now: datetime,
    ) -> int:
        common = {"t": context.unit.tenant_id, "run": context.run_id, "r": region}
        # Only each pool's newest reading can win the upsert, so only it is written.
        latest = [
            {
                **common,
                "pk": uuid4(),
                "zone": r.availability_zone,
                "type": r.instance_type,
                "product": r.product_description,
                "price": r.price,
                "as_of": r.as_of,
                "collected": r.collected_at,
            }
            for r in newest(readings).values()
        ]
        days = [
            {
                **common,
                "pk": uuid4(),
                "zone": pool[0],
                "type": pool[1],
                "product": pool[2],
                "day": day,
                "low": min(r.price for r in seen),
                "high": max(r.price for r in seen),
                "readings": len(seen),
                "as_of": max(r.as_of for r in seen),
                "collected": max(r.collected_at for r in seen),
            }
            for (pool, day), seen in sorted(daily(readings, since, now).items())
        ]
        _write(context, WRITE_LATEST, latest)
        _write(context, WRITE_DAY, days)
        return len(latest) + len(days)


def _write(context: CollectorContext, statement: Any, rows: list[dict[str, Any]]) -> None:
    for start in range(0, len(rows), BATCH):
        context.connection.execute(statement, rows[start : start + BATCH])
