"""What CloudWatch is storing and watching on our behalf.

Separate from `MetricSource`, which reads values. This reads the **inventory**: how
many log groups there are, what retention they have, and which alarms have been
sitting in insufficient data long enough to be meaningless.

The distinction matters because the money is in different places. A metric read
tells you an instance is idle. This tells you that the service doing the watching
is itself a line item, which is the observation FEAT-027 exists for and the one
most teams never make.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LogGroup:
    """One log group, and the two facts that decide whether it is wasteful."""

    name: str
    account_id: str
    region_id: str
    stored_bytes: int
    #: None means never expires, which is the finding rather than a gap.
    retention_days: int | None
    created_at: datetime


@dataclass(frozen=True)
class Alarm:
    """One alarm, and how long it has been unable to say anything."""

    name: str
    account_id: str
    region_id: str
    state: str
    #: When it last changed state. An alarm in INSUFFICIENT_DATA since it was
    #: created is watching a metric that no longer exists.
    state_changed_at: datetime


@runtime_checkable
class CloudWatchEstate(Protocol):
    """The inventory of what CloudWatch holds, not the values in it."""

    def log_groups(self) -> Iterable[LogGroup]:
        """Every log group, with its retention and its size.

        Raises:
            AccessDenied: The role cannot describe log groups here.
            Throttled, Unreachable: As elsewhere.
        """
        ...

    def alarms(self) -> Iterable[Alarm]:
        """Every alarm and its current state.

        Raises:
            AccessDenied, Throttled, Unreachable: As above.
        """
        ...

    def storage_price_per_gb_month(self) -> Decimal:
        """What a gigabyte month of log storage costs here.

        On the port rather than in the collector, because it is regional and a
        collector hardcoding it would be inventing a price. An adapter that cannot
        determine it raises rather than guessing, since a saving computed from an
        invented price is worse than no saving at all.

        Raises:
            NoData: The price could not be determined for this region.
        """
        ...
