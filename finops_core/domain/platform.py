"""What Meter's own running costs, by module, at a day's granularity.

Constraint 7 in CLAUDE.md: the platform meters itself, every platform resource
carries the `finops:module` tag, and the platform's own cost is on the front
page. A tool that reports other people's spending without reporting its own is
asking for a trust it has not earned.

`module` is never null. Untagged cost belongs to the literal `unallocated`
bucket, because a null is easy to filter out by accident and a self metering
report that quietly under counts is worse than no report at all: it is believed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from finops_core.domain.fact import Fact

#: Where cost with no module tag goes. A value, never a null.
UNALLOCATED = "unallocated"


@dataclass(frozen=True, kw_only=True)
class PlatformCost(Fact):
    """One day of one module's spend on one service."""

    day: date
    module: str
    service: str
    amortized_cost: Decimal

    def __post_init__(self) -> None:
        if not self.module:
            raise ValueError(
                "A platform cost with no module is untagged cost that was about to be "
                "dropped. It belongs in the unallocated bucket, which is a value."
            )
