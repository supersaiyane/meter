"""Writing Meter's own cost, by module, once a day.

Constraint 7 in CLAUDE.md. A tool that reports other people's spending without
reporting its own is asking for a trust it has not earned, so this runs like any
other collector and lands on the front page.

Two rules, and both are about not flattering the result.

Untagged cost goes to the literal `unallocated` bucket. Dropping it would make
the self metering report under count quietly, which is worse than having no
report, because a number on a page is believed and an absent one is not.

The cost of metering is attributed to the module that caused it. Cost Explorer
charges per request and the charge arrives untagged, because an account level
API charge has no resource to carry a tag. Leaving it in `unallocated` would
mean the one cost this tool definitely creates is the one cost it never owns.

Daily, not hourly. Each run is a paid request, so the cadence is itself a cost
decision, and it is recorded as one in `collector_schedule` per ADR-0012.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from finops_core.domain.platform import UNALLOCATED
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "platform_cost"

#: Charges that arrive untagged but belong to a known module. An account level
#: API charge cannot carry a resource tag, so without this the cost of measuring
#: sits in unallocated forever, which is the one bucket self metering exists to
#: shrink.
SERVICE_TO_MODULE = {
    "AWS Cost Explorer": "ingest",
}

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


def attribute(module: str, service: str) -> str:
    """Name the module a charge belongs to. Never returns an empty string."""
    if module:
        return module
    return SERVICE_TO_MODULE.get(service, UNALLOCATED)


class PlatformCostCollector:
    """One grouped request a day, written by module and service."""

    def __init__(self, source: Any, clock: Clock = _system_clock) -> None:
        self._source = source
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        unit = context.unit
        charges = self._source.daily_by_module(unit.window_start.date(), unit.window_end.date())
        rolled = self._roll_up(charges)
        at = self._clock()
        for (day, module, service), amount in sorted(rolled.items()):
            context.connection.execute(
                text(
                    "INSERT INTO platform_cost (tenant_id, day, module, service, "
                    "amortized_cost, as_of, collected_at) VALUES "
                    "(:tenant, :day, :module, :service, :amount, :as_of, :collected) "
                    "ON CONFLICT (tenant_id, day, module, service) DO UPDATE SET "
                    "amortized_cost = EXCLUDED.amortized_cost, as_of = EXCLUDED.as_of, "
                    "collected_at = EXCLUDED.collected_at"
                ),
                {
                    "tenant": unit.tenant_id,
                    "day": day,
                    "module": module,
                    "service": service,
                    "amount": amount,
                    "as_of": at,
                    "collected": at,
                },
            )
        return CollectorOutcome(items_written=len(rolled))

    def _roll_up(self, charges: Iterable[Any]) -> dict[tuple[Any, str, str], Decimal]:
        """Sum by day, module and service.

        Re attribution can merge two rows into one, so the amounts are added
        rather than overwritten. Overwriting would silently discard whichever
        charge arrived first.
        """
        rolled: dict[tuple[Any, str, str], Decimal] = {}
        for charge in charges:
            key = (charge.day, attribute(charge.module, charge.service), charge.service)
            rolled[key] = rolled.get(key, Decimal(0)) + charge.amortized_cost
        return rolled


def total(charges: Sequence[Any]) -> Decimal:
    """What the platform cost over the set, for a caller that wants one figure."""
    return sum((charge.amortized_cost for charge in charges), Decimal(0))
