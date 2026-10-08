"""A gp2 volume priced as the gp3 that does the same work. TASK-P9-009, P9 spec section 5.8.

No database, no clock, no provider, as `targets.py` is: it takes a gp2 volume's size, what it was
measured to do, and the Region's EBS prices, and returns the gp3 that matches it with both monthly
costs, or the sentence saying why there is none.

**What gp2 gives.** The EBS user guide's figures, General Purpose SSD volumes, read on 2026-10-08
and stored with that source in `volume_type_spec` by the instance catalog collector:
a baseline of 3 IOPS per GiB, never under 100 nor over 16,000, and throughput of 128 MiB/s at 170
GiB and below and 250 MiB/s above. Under 334 GiB the 250 is a burst rather than a baseline, and
gp2's burst to 3,000 IOPS is within what gp3 includes, so matching both never under provisions.

**What gp3 must give.** The larger of what gp2 gives and the p99 measured on the volume, for IOPS
and for throughput: the move must not take away performance the volume has, nor performance it
uses. A figure that was not measured is taken at what gp2 gives, and the rationale says so.

**What gp3 costs.** Its storage price for the size, plus IOPS above the included 3,000 at the IOPS
price, plus MiB/s above the included 125 at the throughput price. The same guide limits throughput
to 0.25 MiB/s per IOPS, so throughput above 750 MiB/s needs IOPS of its own; IOPS above the
included 3,000 to 500 per GiB; and a volume to 80,000 IOPS and 2,000 MiB/s. Every figure out of
this module is modelled.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Final

GP2_IOPS_PER_GIB: Final = 3
GP2_MIN_IOPS: Final = 100
GP2_MAX_IOPS: Final = 16_000
#: The largest gp2 volume held to the lower throughput.
GP2_SMALL_GIB: Final = 170
GP2_SMALL_MIBPS: Final = 128
GP2_LARGE_MIBPS: Final = 250

GP3_INCLUDED_IOPS: Final = 3_000
GP3_INCLUDED_MIBPS: Final = 125
GP3_MAX_IOPS: Final = 80_000
GP3_MAX_MIBPS: Final = 2_000
GP3_IOPS_PER_GIB: Final = 500
GP3_MIBPS_PER_IOPS: Final = Decimal("0.25")

_CENT: Final = Decimal("0.01")

#: The guide's page, cited beside every stored figure and never fetched.
_GUIDE_SITE: Final = "https://docs.aws.amazon.com"  # allow-hardcoded: cited, never fetched
_GUIDE_PAGE: Final = "/ebs/latest/userguide/general-purpose.html"
#: The page and the day it was read, as `volume_type_spec.source` records it.
SOURCE: Final = (
    f"Amazon EBS User Guide, General Purpose SSD volumes, {_GUIDE_SITE}{_GUIDE_PAGE}, "
    "read 2026-10-08"
)
#: When the figures were true at the source, as far as Meter knows: the day the page was read.
READ_AT: Final = datetime(2026, 10, 8, tzinfo=UTC)


@dataclass(frozen=True)
class VolumeType:
    """One volume type's figures, as `volume_type_spec` stores them."""

    volume_type: str
    #: None where the baseline depends on the size, as gp2's does.
    baseline_iops: int | None
    baseline_mibps: int | None
    maximum_iops: int
    maximum_mibps: int
    #: gp2's rate of baseline per GiB; gp3's most provisioned per GiB.
    iops_per_gib: int


#: gp2 and gp3 as the rule above reads them, so the catalog shows the figures it prices from.
VOLUME_TYPES: Final = (
    VolumeType("gp2", None, None, GP2_MAX_IOPS, GP2_LARGE_MIBPS, GP2_IOPS_PER_GIB),
    VolumeType(
        "gp3",
        GP3_INCLUDED_IOPS,
        GP3_INCLUDED_MIBPS,
        GP3_MAX_IOPS,
        GP3_MAX_MIBPS,
        GP3_IOPS_PER_GIB,
    ),
)


@dataclass(frozen=True)
class VolumePrices:
    """One Region's EBS prices by the month, as the catalog holds them."""

    gp2_gib_month: Decimal
    gp3_gib_month: Decimal
    gp3_iops_month: Decimal
    gp3_mibps_month: Decimal


@dataclass(frozen=True)
class VolumeDemand:
    """What the volume was measured to do at p99, None where nothing measured it."""

    iops_p99: Decimal | None = None
    mibps_p99: Decimal | None = None


@dataclass(frozen=True)
class Gp3:
    """The gp3 that matches a gp2 volume, with both monthly costs and how they were reached."""

    size_gib: int
    iops: int
    mibps: int
    prices: VolumePrices
    gp2_monthly: Decimal
    gp3_monthly: Decimal
    notes: tuple[str, ...]

    @property
    def saving(self) -> Decimal:
        return self.gp2_monthly - self.gp3_monthly


def gp2_iops(size_gib: int) -> int:
    """gp2's baseline IOPS for a size."""
    return min(GP2_MAX_IOPS, max(GP2_MIN_IOPS, GP2_IOPS_PER_GIB * size_gib))


def gp2_mibps(size_gib: int) -> int:
    """The most throughput gp2 gives at a size."""
    return GP2_SMALL_MIBPS if size_gib <= GP2_SMALL_GIB else GP2_LARGE_MIBPS


def gp3_for(size_gib: int, demand: VolumeDemand, prices: VolumePrices) -> Gp3 | str:
    """The gp3 that does a gp2 volume's work for less, or why there is none."""
    if size_gib <= 0:
        return "the volume's size is not known"
    notes: list[str] = []
    iops = gp2_iops(size_gib)
    if demand.iops_p99 is None:
        notes.append(f"IOPS were not measured, so gp3 is given gp2's {iops:,}")
    else:
        iops = max(iops, math.ceil(demand.iops_p99))
    mibps = gp2_mibps(size_gib)
    if demand.mibps_p99 is None:
        notes.append(f"throughput was not measured, so gp3 is given gp2's {mibps} MiB/s")
    else:
        mibps = max(mibps, math.ceil(demand.mibps_p99))
    iops = max(iops, GP3_INCLUDED_IOPS, math.ceil(mibps / GP3_MIBPS_PER_IOPS))
    refused = _beyond_gp3(size_gib, iops, mibps)
    if refused is not None:
        return refused
    gp2_monthly = (size_gib * prices.gp2_gib_month).quantize(_CENT)
    gp3_monthly = (
        size_gib * prices.gp3_gib_month
        + (iops - GP3_INCLUDED_IOPS) * prices.gp3_iops_month
        + max(0, mibps - GP3_INCLUDED_MIBPS) * prices.gp3_mibps_month
    ).quantize(_CENT)
    if gp3_monthly >= gp2_monthly:
        return (
            f"gp3 at {iops:,} IOPS and {mibps} MiB/s costs {gp3_monthly} a month, "
            f"no less than gp2's {gp2_monthly}"
        )
    return Gp3(size_gib, iops, mibps, prices, gp2_monthly, gp3_monthly, tuple(notes))


def _beyond_gp3(size_gib: int, iops: int, mibps: int) -> str | None:
    if mibps > GP3_MAX_MIBPS:
        return f"gp3 gives at most {GP3_MAX_MIBPS:,} MiB/s and {mibps:,} are needed"
    if iops > GP3_MAX_IOPS:
        return f"gp3 gives at most {GP3_MAX_IOPS:,} IOPS and {iops:,} are needed"
    if iops > GP3_INCLUDED_IOPS and iops > GP3_IOPS_PER_GIB * size_gib:
        return (
            f"gp3 gives at most {GP3_IOPS_PER_GIB} IOPS per GiB, "
            f"{GP3_IOPS_PER_GIB * size_gib:,} at {size_gib:,} GiB, and {iops:,} are needed"
        )
    return None


def working(found: Gp3) -> str:
    """The sum behind a gp3 cost, as a rationale states it."""
    prices = found.prices
    parts = [f"{found.size_gib:,} GiB at {_plain(prices.gp3_gib_month)}"]
    if found.iops > GP3_INCLUDED_IOPS:
        extra = found.iops - GP3_INCLUDED_IOPS
        parts.append(
            f"{extra:,} IOPS above the included {GP3_INCLUDED_IOPS:,} "
            f"at {_plain(prices.gp3_iops_month)}"
        )
    if found.mibps > GP3_INCLUDED_MIBPS:
        extra = found.mibps - GP3_INCLUDED_MIBPS
        parts.append(
            f"{extra} MiB/s above the included {GP3_INCLUDED_MIBPS} "
            f"at {_plain(prices.gp3_mibps_month)}"
        )
    return (
        f"Move gp2 to gp3 at {found.iops:,} IOPS and {found.mibps} MiB/s: "
        + ", ".join(parts)
        + f", {found.gp3_monthly} a month against {found.gp2_monthly} on gp2 at "
        + f"{_plain(prices.gp2_gib_month)} per GiB"
    )


def _plain(price: Decimal) -> str:
    """A price as written, without the trailing zeros a NUMERIC column pads it with."""
    return format(price.normalize(), "f")
