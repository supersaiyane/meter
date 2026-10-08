"""Savings Plans rates for EC2, in every Region the price list sells EC2 in. TASK-P9-012.

FEAT-071, P9 spec section 14. Rates come through the relay outside the VPC, ADR-0035, and are
stored as `price` rows under `ComputeSavingsPlans`, Committed, with the plan type as the offering
class, beside the on demand and reserved prices FEAT-071 already holds.

**The Regions are the price list's.** A Region is read when the price catalog holds an EC2
version for it, so no Region is named here and a Region AWS adds is read once its prices are.

**Only what changed is stored.** A sheet's version is a digest of its rates, so a Region whose
rates have not moved arrives as a version already held and nothing is written. Every Region is
still read each run, because nothing short of reading the rates says whether they moved: six
relay calls a Region, about 16,200 a month across 30 Regions at three runs a day (modelled), the
figure OPEN-19 puts to the owner.

**One Region fails alone**, constraint 5, recorded in `sync_error` with the sheet already held
kept. A sheet is read whole before anything is written, so a failure never leaves half of one.
Only a run that read nothing at all fails.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import text

from finops_core.domain.catalog import SAVINGS_PLANS
from finops_core.errors import CollectionError
from finops_core.ports.catalog import SavingsPlansRates
from finops_ingest.collectors.price_catalog import held, prune, refuse, store
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "savings_plan_rates"
EC2: Final = "AmazonEC2"

#: Every Region the price catalog holds an EC2 version for.
REGIONS = text(
    "SELECT DISTINCT region FROM price_list_version WHERE tenant_id = :t AND service_code = :s"
)


def _system_clock() -> datetime:
    return datetime.now(UTC)


class SavingsPlanRatesCollector:
    """Each Region's Savings Plans rates, stored when they move."""

    def __init__(
        self, source: SavingsPlansRates, clock: Callable[[], datetime] = _system_clock
    ) -> None:
        self._source = source
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        now = self._clock()
        tenant = context.unit.tenant_id
        regions = sorted(
            row.region for row in context.connection.execute(REGIONS, {"t": tenant, "s": EC2})
        )
        known = held(context, SAVINGS_PLANS)
        written = removed = 0
        read = False
        failures: list[CollectionError] = []
        for region in regions:
            try:
                sheet = self._source.rates(region)
            except CollectionError as failure:
                failures.append(refuse(context, COLLECTOR, failure, now))
                continue
            read = True
            if (region, sheet.version.version) in known:
                continue
            written += store(context, sheet.version, sheet.prices)
            removed += prune(context, sheet.version)
        if failures and not read:
            raise failures[0]
        return CollectorOutcome(items_written=written, items_removed=removed)
