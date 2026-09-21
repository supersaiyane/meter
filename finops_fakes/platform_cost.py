"""Meter's own bill in memory, so architectural constraint 7 has something to show.

Constraint 7 says the platform meters itself and its own cost is on the front
page. A demo estate that cannot show that leaves the one screen the constraint
exists for permanently empty.

The unallocated bucket is here on purpose. It is the charge that carried no
`finops:module` tag, and leaving it out of a fixture would let the roll up look
complete while under counting, which is the failure the platform cost screen was
built to prevent.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal

from finops_providers.aws.platform_cost import ModuleCharge

#: One day of the platform's spend, by module and service. A gentle ramp is
#: applied across the window by `daily_by_module`, because a flat estate cannot
#: demonstrate the one question a sparkline answers.
DAILY: tuple[tuple[str, str, str], ...] = (
    ("ingest", "AmazonECS", "4.10"),
    ("ingest", "AWSLambda", "0.62"),
    ("api", "AmazonECS", "3.80"),
    ("api", "AmazonRDS", "5.40"),
    ("web", "AmazonCloudFront", "0.35"),
    # No module tag. Named rather than dropped.
    ("unallocated", "AmazonS3", "0.61"),
)


class FakePlatformCost:
    """`PlatformCostSource` in memory."""

    def __init__(self, daily: Iterable[tuple[str, str, str]] | None = None) -> None:
        self._daily = tuple(DAILY if daily is None else daily)

    def daily_by_module(self, start: date, end: date) -> tuple[ModuleCharge, ...]:
        """The window, day by day, rising gently across it.

        The ramp is small and deterministic. It exists so the sparkline has a
        shape to draw, and it is stated here rather than hidden in a random
        walk, so a reader who checks the arithmetic on the cost screen can
        reproduce the total.
        """
        days = max((end - start).days, 1)
        return tuple(
            ModuleCharge(
                day=start + timedelta(days=offset),
                module=module,
                service=service,
                amortized_cost=(
                    Decimal(amount) * (Decimal(100) + Decimal(offset)) / Decimal(100)
                ).quantize(Decimal("0.01")),
            )
            for offset in range(days)
            for module, service, amount in self._daily
        )
