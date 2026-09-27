"""Where a region is, worked out from its name and from nothing else.

FEAT-061. The rule is pure and lives here because it is a fact about how cloud providers name
regions, not a fact about our own configuration.

**Why the prefix and not a coordinate table.** A table of coordinates per region has to name every
region, `eu-west-1` and `eu-west-2` and `eu-west-3`, which is the exact failure
`scripts/ci/check_hardcoded.py` exists to prevent: a region that is not in the table is a region
the feature silently cannot see, and the next region a provider opens is invisible until somebody
notices. A prefix is not a region identifier. `eu` is a geography, it is stable across every
region a provider has ever opened inside it, and `eu-south-3` resolves through it on the day it
opens with no change here.

**The cost of that, stated rather than hidden.** A prefix is continental. It cannot tell Dublin
from Frankfurt, so this places a resource in Europe and never on a city. That is the honest limit
of naming as a data source, and a screen built on it must say so rather than implying a precision
it does not have. ISS-213.

**A region whose prefix is unknown is never dropped.** It is returned as unplaceable and counted.
A map that quietly omits what it cannot place is a map that reports a smaller estate than exists,
which is the same failure as rendering a collection error as the number zero.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Geography:
    """A continental grouping of regions, named by the prefix its regions share."""

    #: The prefix itself, which is also the stable key a screen positions by.
    key: str
    #: What a person calls it. The only part of this that is presentation.
    name: str


#: The geographies every major provider's region names begin with.
#:
#: These are prefixes and not regions, which is the whole argument of this module: no entry here
#: names a region, and a region this table has never heard of still resolves as long as its
#: geography has. Ordered west to east so a caller that iterates produces a stable order.
#:
#: `us-gov-west-1` resolves to the United States through `us`, which is correct: it is a
#: geography question and not a compliance one, and the partition is a different fact.
GEOGRAPHIES: tuple[Geography, ...] = (
    Geography("us", "United States"),
    Geography("ca", "Canada"),
    Geography("sa", "South America"),
    Geography("eu", "Europe"),
    Geography("af", "Africa"),
    Geography("il", "Israel"),
    Geography("me", "Middle East"),
    Geography("cn", "China"),
    Geography("ap", "Asia Pacific"),
)

_BY_KEY = {geography.key: geography for geography in GEOGRAPHIES}


def geography_of(region_id: str | None) -> Geography | None:
    """The geography a region is in, or None where its name does not say.

    None covers three different things on purpose, and the caller separates them because they
    need different words on a screen: no region at all, which is a global resource and is a real
    state rather than a gap; a name with no prefix to read; and a prefix this table does not know,
    which is the one that means somebody should widen the table.
    """
    if region_id is None:
        return None
    prefix, separator, _rest = region_id.strip().lower().partition("-")
    if not separator or not prefix:
        # A region name with no hyphen tells us nothing. Returning None rather than guessing,
        # because a guess here places real resources on the wrong continent.
        return None
    return _BY_KEY.get(prefix)


def is_global(region_id: str | None) -> bool:
    """True where the resource belongs to no region.

    IAM, Route 53, CloudFront and an organization itself have no region, and that is a fact about
    the service rather than a hole in the inventory. A map has to say so rather than counting them
    as unplaceable, because unplaceable is a prompt to go and fix something and this is not.
    """
    return region_id is None or region_id.strip() == ""
