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


#: The places, ordered west to east so a caller that iterates produces a stable order.
#:
#: Checked against the AWS region list on 2026-09-27 rather than written from memory, which found
#: two things memory had missed: Mexico is a live region and had no entry, and the European
#: Sovereign Cloud carries a four letter prefix that no one letter pair would ever match.
GEOGRAPHIES: tuple[Geography, ...] = (
    Geography("us", "United States"),
    Geography("ca", "Canada"),
    Geography("mx", "Mexico"),
    Geography("sa", "South America"),
    Geography("eu", "Europe"),
    Geography("af", "Africa"),
    Geography("il", "Israel"),
    Geography("me", "Middle East"),
    Geography("cn", "China"),
    Geography("ap", "Asia Pacific"),
)

_BY_KEY = {geography.key: geography for geography in GEOGRAPHIES}

#: Which prefix means which place, and it is a separate table from the places for one reason.
#:
#: The first version keyed the places by their prefix, which assumed one prefix per place, and
#: `eusc-de-east-1` is the counterexample: the AWS European Sovereign Cloud is a partition rather
#: than a location, and it is in Europe. Two prefixes therefore have to reach one place, which a
#: table keyed by prefix cannot express without inventing a second Europe that the drawing would
#: then have to position twice.
#:
#: Still prefixes and never regions, which is the argument the whole module rests on: no entry
#: here names a region, and a region this table has never heard of resolves as long as its prefix
#: has. `eu-south-3` works on the day it opens.
#:
#: `us-gov-west-1` resolves to the United States through `us`, which is correct: where a region is
#: and which partition it is in are different questions, and this one is geography.
PREFIXES: dict[str, Geography] = {
    prefix: _BY_KEY[key]
    for prefix, key in (
        ("us", "us"),
        ("ca", "ca"),
        ("mx", "mx"),
        ("sa", "sa"),
        ("eu", "eu"),
        # The sovereign cloud, which is a partition and not a place. Germany is in Europe.
        ("eusc", "eu"),
        ("af", "af"),
        ("il", "il"),
        ("me", "me"),
        ("cn", "cn"),
        ("ap", "ap"),
    )
}


#: The compass words a provider puts in a region name, longest first so `northeast` is matched
#: before `north` would strip it to the wrong answer.
#:
#: This is the second thing a region name says, and it is the whole of ISS-213's reduction. The
#: prefix gives a continent and can never give a city, and that was recorded as a hard limit. It
#: is not quite: `eu-west-1` and `eu-central-1` are both Europe and the name also says one is
#: western and one is central, so a drawing can put them in different parts of the continent
#: without any table of regions and without going stale when the next one opens.
#:
#: It still cannot say Dublin. Western Europe is not a city, and the caption keeps saying so.
DIRECTIONS: tuple[str, ...] = (
    "northeast",
    "northwest",
    "southeast",
    "southwest",
    "central",
    "north",
    "south",
    "east",
    "west",
)


def direction_of(region_id: str | None) -> str | None:
    """Where in its geography a region is, from its own name, or None where the name does not say.

    Read from any component rather than a fixed position, because the position varies: `us-east-1`
    has it second and `us-gov-west-1` has it third, and a rule counting hyphens would place every
    GovCloud region in the wrong half of the United States.

    Returns a word and never a coordinate. Which compass point a region is in is a fact about its
    name; where that lands in a picture is a fact about the picture, and the drawing owns that for
    the same reason it owns the continent anchors.
    """
    if region_id is None:
        return None
    parts = region_id.strip().lower().split("-")
    for part in parts[1:]:
        if part in DIRECTIONS:
            return part
    return None


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
    return PREFIXES.get(prefix)


def is_global(region_id: str | None) -> bool:
    """True where the resource belongs to no region.

    IAM, Route 53, CloudFront and an organization itself have no region, and that is a fact about
    the service rather than a hole in the inventory. A map has to say so rather than counting them
    as unplaceable, because unplaceable is a prompt to go and fix something and this is not.
    """
    return region_id is None or region_id.strip() == ""
