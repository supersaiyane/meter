"""EC2's spot price readings, read through the relay outside the VPC. FEAT-071, TASK-P9-013.

P9 spec sections 14 and 14.7, ADR-0035 and OPEN-17. Read only, constraint 6. **Unproved against a
real account**: the shapes are the botocore 1.43.108 model's, proof waits on ISS-002 and ISS-264.

**One call a Region.** `DescribeSpotPriceHistory` pages with botocore's own paginator, so the relay
answers a Region's whole window in one invocation: about 2,700 a month across 30 Regions at three
runs a day (modelled), the figure spec section 14.5 gave the owner. EC2 answers a window with the
price each pool had when it opened as well as every change inside it, so a pool whose price has
not moved still arrives once, with the reading's own time.

**Every product description and every zone**, as the plan asks. The window's ends travel as ISO
8601 strings, because the relay's request is JSON and botocore reads either form.

**Refused, never stored.** A price of nought, an unreadable price or time, or a zone outside the
Region is SchemaDrift for the Region; a Region not opted into is NotOptedIn, never a price of
nought, constraint 5.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.domain.catalog import SpotPrice
from finops_core.errors import NoData, SchemaDrift
from finops_providers.aws.client import translate

COLLECTOR: Final = "spot_prices"
PAGE: Final = 1000


def _system_clock() -> datetime:
    return datetime.now(UTC)


class AwsSpotPrices:
    """Every spot pool's readings over a window, one Region at a time."""

    def __init__(
        self,
        *,
        client_for: Callable[[str], Any],
        clock: Callable[[], datetime] = _system_clock,
    ) -> None:
        # An EC2 `RelayClient` for a Region, the relay's own role, ADR-0035.
        self._client_for = client_for
        self._clock = clock

    def prices(self, region: str, since: datetime) -> Iterable[SpotPrice]:
        scope = f"spot:{region}"
        at = self._clock()
        found: list[SpotPrice] = []
        try:
            pages = (
                self._client_for(region)
                .get_paginator("describe_spot_price_history")
                .paginate(StartTime=since.isoformat(), EndTime=at.isoformat(), MaxResults=PAGE)
            )
            for page in pages:
                for raw in page.get("SpotPriceHistory") or ():
                    found.append(_reading(raw, region, at, scope))
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=scope, collector=COLLECTOR) from failure
        if not found:
            raise NoData(scope_key=scope, collector=COLLECTOR, detail="no spot pool in the Region")
        return tuple(found)


def _reading(raw: Any, region: str, at: datetime, scope: str) -> SpotPrice:
    """One `SpotPriceHistory` entry, or SchemaDrift saying what could not be read."""
    name = str(raw.get("InstanceType") or "")
    try:
        when = raw["Timestamp"]
        if not isinstance(when, datetime):
            raise TypeError("a reading's time is not a time")
        when = when if when.tzinfo else when.replace(tzinfo=UTC)
        return SpotPrice(
            region=region,
            availability_zone=str(raw["AvailabilityZone"]),
            instance_type=name,
            product_description=str(raw["ProductDescription"]),
            price=Decimal(str(raw["SpotPrice"])),
            as_of=when,
            # A clock behind EC2's would otherwise read a price before it was set.
            collected_at=max(at, when),
        )
    except (KeyError, TypeError, ValueError, InvalidOperation) as failure:
        raise SchemaDrift(
            scope_key=scope,
            collector=COLLECTOR,
            detail=f"a spot reading this cannot read, {name or 'with no type'}",
        ) from failure
