# FEAT-061: Where the estate is, read from region names

| Field | Value |
| --- | --- |
| Sub project | P4 |
| Status | Delivered |
| Specification | Asked for directly on 2026-09-27, after the chart work |
| Tasks | None. Requested rather than planned |
| Refresh cadence | Follows FEAT-030, the inventory collector |
| Source | A request, and the blocker it had been sitting behind since 2026-09-27 morning |

## What it does

Groups every resource in the inventory onto a continent, draws it, and lists the resources of any
continent in one click.

## Why it exists

The inventory could answer what is connected to what and how many volumes are in one region. It
could not answer the first question anybody asks about an estate they have inherited, which is
where it is. That question has a compliance edge as well as a curiosity one.

## How it works

`finops_core/domain/geography.py` holds the rule and is pure. A region's geography is the part of
its name before the first hyphen, so `eu-west-1` and `eu-central-1` are both Europe.

**The table was checked against the AWS region list on 2026-09-27 rather than written from
memory**, which found two things memory had missed. Mexico is a live region, `mx-central-1`, and
had no entry. And the AWS European Sovereign Cloud is `eusc-de-east-1`, a four letter prefix that
no pair of letters would ever match.

The sovereign cloud forced a design change. The first version keyed the places by their prefix,
which assumed one prefix per place, and `eusc` is a second prefix reaching a place `eu` already
names. A table keyed by prefix cannot express that without inventing a second Europe, which the
drawing would then position twice. Prefix and place are separate tables now, and a test asserts
every prefix resolves to a place the list holds.

**The prefix, not a coordinate table, and this is the decision the feature turns on.** A table of
coordinates has to name every region. `eu-west-1`, `eu-west-2`, `eu-west-3`, and then the next
region a provider opens is invisible until somebody notices, which is exactly the failure
`scripts/ci/check_hardcoded.py` exists to prevent: a region literal in code means the second region
silently does not work. A prefix is not a region. It is stable across every region inside it, and
`eu-south-3` resolves through it on the day it opens with no change to this code.

That was the blocker. The morning of 2026-09-27 this feature was recorded as blocked because the
regions had no coordinates and region literals are forbidden. The prefix is the resolution rather
than an exception to the rule.

**The fixture estate was renamed to match, and that was a defect rather than a convenience.** It
used `fake-region-a`, `fake-region-b` and `fake-region-c`, none of which carries a geography
prefix, so the estate could not exercise a feature that reads provider region names at all. Two
became `us-fake-1` and `eu-fake-1`. The third is deliberately left alone, so the estate holds a
region no prefix table will ever match and the unplaceable path runs against real data. No real
region contains the word fake, so the names are still unmistakably synthetic.

**One click, one implementation of the rule.** `GET /inventory/resources` takes a `geography`
parameter, and the route resolves it to the regions this reader can see by applying the same
domain rule. A prefix match written again in SQL would be a second implementation, and the map
saying a continent holds three above a list showing two is the fault a reader finds before we do.
A test asserts the two routes agree for every geography.

## Failure behaviour

Three kinds of leftover, never added together, because each needs a different remedy.

Resources with **no region** are global. IAM, DNS, CloudFront and the organization itself, and that
is a fact about the service rather than a hole in the inventory. Nobody is asked to fix it.

Resources in a region whose prefix is **unknown** are unplaceable. They are counted and their
regions are named, and this is the one a reader can act on: the geography table needs one more row.

Regions a collection **could not read** are refused. What is in them is unknown rather than
nothing, so every count on the screen is a floor. Constraint 5.

The geographies plus the first two leftovers add up to the estate this reader can see, and a test
asserts that, because a map that omits any of them reports a smaller estate while looking
complete.

## Security considerations

Read only. The grouped read goes through `scoped_select` like every other read, so a narrowed
reader gets a smaller map, and a test asserts that a reader narrowed to one account does not learn
which regions another account runs in. The geography filter on the resource list is scoped the same
way, and that is asserted separately, because a filter and a grouping are two code paths.

## Interface

`/inventory/geography`, under the Inventory group.

A world map with coarse coastlines, one marker per continent, in an equirectangular projection
cropped to the latitudes where people run things.

It shipped first as a graticule with no coastline, on the argument that a coastline would imply a
precision the prefix does not have. That argument was wrong about where the claim lives. A
coastline says "this is the world"; it is the marker's position that would claim a datacentre, and
the caption already handles that. Without land a reader cannot tell which dot is North America
without reading the label, which makes the picture decorative rather than informative, and it
looked like an empty panel with two dots in it.

The second attempt hand authored the continents at roughly thirty points each, and that was the
wrong approach rather than a poor attempt at the right one: coastlines written out from memory
produce shapes nobody recognises. They are generated now, by `make world`, from the Natural Earth
110m land polygons that every mapping library uses.

**Generated at build time, with nothing new at runtime.** `world-atlas` and `topojson-client` are
dev dependencies, admitted through `make dep-check`, and neither reaches a browser. What ships is
`worldPaths.ts`, a committed string of SVG path data, so the page draws a real coastline with no
mapping library, no projection code and no fetch. Islands under a threshold are dropped and
anything outside the crop is left out of the file, because invisible bytes are still bytes a
reader downloads.

**Why a coastline may be written down when a region coordinate table may not.** A table naming
`eu-west-1` and `eu-west-2` is a fact about somebody else's estate and goes stale the day they
open another region, which is what `check_hardcoded.py` exists to prevent. A coastline is a fact
about the world: nothing a provider does changes where Africa is. That is the property the region
table lacked, and it is the whole distinction.

The regions inside each continent are listed rather than counted, which is the honest way to admit
what the name cannot say.
ISS-213.

A marker is two marks, changed 2026-09-27 against the AWS global infrastructure page as the
reference. A fixed core dot says where, and a halo sized by the count says how much. One disc
sized by the count did both badly: at forty pixels across it says the place is somewhere inside
it, which is a precision claim in the wrong direction from the one the caption is careful about.
Every infrastructure map draws a point of presence this way, and it is right for the same reason:
position and quantity are different questions and one mark cannot answer both.

The halo is sized by **area**, so four times the resources is four times the ink. Sizing by radius
would claim four times again for twice the resources, which is the oldest lie in data drawing and
looks entirely correct.

The drawing carries `aria-hidden` and the legend beneath it is both the content and the control.
Every figure in the picture is written out as text, and the legend entries are real buttons,
because SVG markers are not reachable from a keyboard and a picture must never be the only way to
operate a screen. Same choice as `RankedBars`.

Nothing is loaded until a continent is chosen. A screen that loads the first one has decided which
continent matters, and on an estate across nine of them that is wrong eight times out of nine.

The inline list is a first page with its denominator and no pager. Paging and filtering already
exist on the resource list, and a second implementation of the offset arithmetic is a second place
for it to be wrong, so the screen links there instead.

## Not doing

Placing a resource on a city, drawing coastlines, and latency between regions. The first two need
a coordinate per region, which is the design this feature rejected for a reason. Latency is a
different feature and a different measurement, and inferring it from geography would be a modelled
number presented beside measured ones.
