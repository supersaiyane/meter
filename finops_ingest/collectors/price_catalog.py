"""AWS's prices, stored by version and loaded only when a version changes. FEAT-071, TASK-P9-004.

P9 spec sections 5.2, 5.3 and 14.4.

**Only what changed.** Each run asks every service for its current version in every Region and
loads a version it does not hold. A run that finds nothing new is one ListPriceLists per service
and writes nothing.

**One service in one Region fails alone, constraint 5.** Each load is a savepoint. A refused
product, a throttled page or a page that drifted rolls that one load back and is recorded in
`sync_error` by its typed cause, and the version already held stays the one read. A service whose
versions cannot be listed is recorded the same way. Only a run that read nothing at all fails, so
a wholly unreadable catalog is a failed run in the ledger rather than a green one with errors
beside it.

**Superseded prices go, except the ones a recommendation quotes.** After a load, the prices of
that service and Region's earlier versions are removed, and then the versions left with none. A
recommendation names its prices by version, 0033, so the prices it quotes and their version stay
until it is written again from a newer one. What is removed is counted in `items_removed`.

**Written in batches, never held whole.** Prices arrive from the source a page at a time and are
written `BATCH` at a time.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any, Final
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.catalog import Price, PriceListVersion
from finops_core.errors import CollectionError
from finops_core.ports.catalog import PriceCatalog
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "price_catalog"
#: P9 spec section 14: EC2, which holds EBS, then RDS, ElastiCache, Redshift and OpenSearch.
SERVICES: Final = ("AmazonEC2", "AmazonRDS", "AmazonElastiCache", "AmazonRedshift", "AmazonES")
#: Rows per insert. Large enough that a Region's thousands of prices are a few statements.
BATCH: Final = 1000

HELD = text(
    "SELECT region, version FROM price_list_version WHERE tenant_id = :t AND service_code = :s"
)

WRITE_VERSION = text(
    "INSERT INTO price_list_version (version_pk, tenant_id, ingest_run_id, service_code, region, "
    "version, row_count, as_of, collected_at) "
    "VALUES (:pk, :t, :run, :s, :r, :v, 0, :as_of, :collected)"
)

WRITE_PRICE = text(
    "INSERT INTO price (price_pk, tenant_id, ingest_run_id, service_code, region, sku, "
    "sku_price_id, sku_meter, pricing_unit, pricing_category, currency, recurring_unit_price, "
    "upfront_fee, lease_years, purchase_option, offering_class, sku_price_details, "
    "effective_date, version, as_of, collected_at) "
    "VALUES (:pk, :t, :run, :s, :r, :sku, :sku_price_id, :meter, :unit, :category, :currency, "
    ":recurring, :upfront, :lease, :option, :class, CAST(:details AS jsonb), :effective, :v, "
    ":as_of, :collected) "
    # The same term twice in one version is the same price; it is kept once.
    "ON CONFLICT (tenant_id, region, sku_price_id, version) DO NOTHING"
)

#: The count is the rows stored, not the rows offered, so a term sent twice counts once.
COUNT_VERSION = text(
    "UPDATE price_list_version v SET row_count = ("
    "SELECT count(*) FROM price p WHERE p.tenant_id = v.tenant_id "
    "AND p.service_code = v.service_code AND p.region = v.region AND p.version = v.version) "
    "WHERE v.tenant_id = :t AND v.service_code = :s AND v.region = :r AND v.version = :v "
    "RETURNING v.row_count"
)

PRUNE_PRICES = text(
    "DELETE FROM price p USING price_list_version old "
    "WHERE old.tenant_id = :t AND old.service_code = :s AND old.region = :r "
    "AND old.as_of < :as_of "
    "AND p.tenant_id = old.tenant_id AND p.service_code = old.service_code "
    "AND p.region = old.region AND p.version = old.version "
    "AND NOT EXISTS (SELECT 1 FROM recommendation rec WHERE rec.tenant_id = p.tenant_id "
    "AND rec.region_id = p.region AND rec.price_version = p.version "
    "AND p.sku_price_id IN (rec.current_sku_price_id, rec.target_sku_price_id)) "
    # A ranked option quotes a price too, TASK-P9-006.
    "AND NOT EXISTS (SELECT 1 FROM recommendation_option opt WHERE opt.tenant_id = p.tenant_id "
    "AND opt.region = p.region AND opt.price_version = p.version "
    "AND opt.sku_price_id = p.sku_price_id)"
)

PRUNE_VERSIONS = text(
    "DELETE FROM price_list_version v "
    "WHERE v.tenant_id = :t AND v.service_code = :s AND v.region = :r AND v.as_of < :as_of "
    "AND NOT EXISTS (SELECT 1 FROM price p WHERE p.tenant_id = v.tenant_id "
    "AND p.service_code = v.service_code AND p.region = v.region AND p.version = v.version)"
)

#: Upserted on the scope, like every other sync error, so a lasting refusal is one row with a
#: rising count rather than one row a run.
REFUSED = text(
    "INSERT INTO sync_error (error_id, tenant_id, collector, scope_key, error_type, "
    "detail, remediation, first_seen_at, last_seen_at, occurrences) "
    "VALUES (:id, :t, :c, :s, :type, :d, :r, :now, :now, 1) "
    "ON CONFLICT (tenant_id, collector, scope_key, error_type) DO UPDATE SET "
    "detail = EXCLUDED.detail, last_seen_at = EXCLUDED.last_seen_at, "
    "occurrences = sync_error.occurrences + 1"
)


def _system_clock() -> datetime:
    return datetime.now(UTC)


Clock = Callable[[], datetime]


class PriceCatalogCollector:
    """Each service's current prices in every Region, loaded when AWS publishes new ones."""

    def __init__(
        self,
        source: PriceCatalog,
        clock: Clock = _system_clock,
        services: Iterable[str] = SERVICES,
    ) -> None:
        self._source = source
        self._clock = clock
        self._services = tuple(services)

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        now = self._clock()
        written = removed = 0
        read = False
        failures: list[CollectionError] = []
        for service in self._services:
            try:
                versions = tuple(self._source.versions(service))
            except CollectionError as failure:
                failures.append(refuse(context, COLLECTOR, failure, now))
                continue
            known = held(context, service)
            for version in versions:
                if (version.region, version.version) in known:
                    read = True
                    continue
                try:
                    with context.connection.begin_nested():
                        written += store(context, version, self._source.prices(version))
                        removed += prune(context, version)
                except CollectionError as failure:
                    failures.append(refuse(context, COLLECTOR, failure, now))
                else:
                    read = True
        if failures and not read:
            raise failures[0]
        return CollectorOutcome(items_written=written, items_removed=removed)


# --- shared with the other collectors that store prices by version, TASK-P9-012 -----------


def held(context: CollectorContext, service: str) -> set[tuple[str, str]]:
    """Every (Region, version) of a service already stored."""
    rows = context.connection.execute(HELD, {"t": context.unit.tenant_id, "s": service})
    return {(row.region, row.version) for row in rows}


def store(context: CollectorContext, version: PriceListVersion, prices: Iterable[Price]) -> int:
    """A version and its prices, written `BATCH` at a time. Returns the rows stored."""
    connection = context.connection
    key = _key(context, version)
    connection.execute(
        WRITE_VERSION,
        {
            **key,
            "pk": uuid4(),
            "run": context.run_id,
            "as_of": version.as_of,
            "collected": version.collected_at,
        },
    )
    batch: list[dict[str, Any]] = []
    for price in prices:
        batch.append(_row(context, price))
        if len(batch) == BATCH:
            connection.execute(WRITE_PRICE, batch)
            batch = []
    if batch:
        connection.execute(WRITE_PRICE, batch)
    return int(connection.execute(COUNT_VERSION, key).scalar_one())


def prune(context: CollectorContext, version: PriceListVersion) -> int:
    """The service and Region's earlier versions and their prices, except those quoted."""
    key = {**_key(context, version), "as_of": version.as_of}
    prices = context.connection.execute(PRUNE_PRICES, key).rowcount
    versions = context.connection.execute(PRUNE_VERSIONS, key).rowcount
    return int(prices) + int(versions)


def refuse(
    context: CollectorContext, collector: str, failure: CollectionError, now: datetime
) -> CollectionError:
    """A typed failure recorded in `sync_error`, and returned for the run to count."""
    context.connection.execute(
        REFUSED,
        {
            "id": uuid4(),
            "t": context.unit.tenant_id,
            "c": collector,
            "s": failure.scope_key,
            "type": failure.cause,
            "d": str(failure),
            "r": failure.remediation,
            "now": now,
        },
    )
    return failure


def _key(context: CollectorContext, version: PriceListVersion) -> dict[str, Any]:
    return {
        "t": context.unit.tenant_id,
        "s": version.service_code,
        "r": version.region,
        "v": version.version,
    }


def _row(context: CollectorContext, price: Price) -> dict[str, Any]:
    return {
        "pk": uuid4(),
        "t": context.unit.tenant_id,
        "run": context.run_id,
        "s": price.service_code,
        "r": price.region,
        "sku": price.sku,
        "sku_price_id": price.sku_price_id,
        "meter": price.sku_meter,
        "unit": price.pricing_unit,
        "category": price.pricing_category.value,
        "currency": price.currency,
        "recurring": price.recurring_unit_price,
        "upfront": price.upfront_fee,
        "lease": price.lease_years,
        "option": price.purchase_option.value if price.purchase_option else None,
        "class": price.offering_class,
        "details": json.dumps(dict(price.details), sort_keys=True),
        "effective": price.effective_date,
        "v": price.version,
        "as_of": price.as_of,
        "collected": price.collected_at,
    }
