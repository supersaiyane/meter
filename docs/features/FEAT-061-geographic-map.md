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

Since TASK-P8-013, 2026-10-06, the continent's table is a `DataTable` under the resource list's rule: sortable only when it holds every resource there, otherwise in the server's order with its count in the caption.

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

`/inventory/topology/geography`, the Geography tab of Topology under the Inventory group.

**Land as dots on a rounded world, redrawn on 2026-10-06 by TASK-P8-017 to the owner's direction
of 2026-10-05.** 4,569 dots, measured, on an Equal Earth grid cropped to 83N and 56S, sit on the
projection's own rounded edge. Equal Earth is equal area, so a continent's dots are in proportion
to its size, and its curved sides are what make the world read as round.

The map shipped first as a graticule with no land, then with continents written from memory, then
with generated coastlines. The first looked like an empty panel, the second drew shapes nobody
recognised, and the third drew two stray horizontal lines across the whole map, Russia's and
Fiji's rings joined straight across where their longitudes jump from 180 to minus 180.

**Generated at build time, with nothing new at runtime.** `make world` runs
`finops-web/scripts/build_world.mjs`, which lays a regular grid over the projection, takes each
point back to a longitude and a latitude, and keeps it where the Natural Earth 110m land holds
it, each ring unwrapped across the antimeridian before a point is tested against it. Only dots
are emitted, so no line can cross the map. `world-atlas` and `topojson-client` are dev
dependencies, admitted through `make dep-check`, and neither reaches a browser. What ships is
`worldDots.ts`, 8 kilobytes of run lengths, measured, drawn as one SVG path of round capped
strokes. `equalEarth.ts` projects each bubble with the same four constants, and its test projects
the generator's own check points, so a bubble cannot drift off its continent unseen.

**Why land may be written down when a region coordinate table may not.** A table naming
`eu-west-1` and `eu-west-2` is a fact about somebody else's estate and goes stale the day they
open another region, which is what `check_hardcoded.py` exists to prevent. Land is a fact about
the world: nothing a provider does changes where Africa is. That is the property the region table
lacked, and it is the whole distinction.

**One glowing bubble per geography, sized by this month's Effective Cost.** The cost is Cost
Explorer's own view by region, month to date, and the route's answer says which geography each
region is in, `region_geographies`, placed by the same prefix rule as the resources, so the
application carries no copy of the rule. A bubble is sized by area, so four times the cost is four
times the ink; a measured nought is the smallest bubble; and a cost that is loading or could not
be read sizes nothing, which the caption says. The geography's resource count sits beside it. A
geography with cost and no resources is drawn too, because the map must not drop one.

**Lines for links across regions.** The geography route's `links` are pairs of regions joined by
topology edges whose two ends this reader can read, counted as pairs of resources, so a peering
recorded from both of its ends counts once. A line joins two geographies. A link inside one
geography, or to a region no table places, is real, and is listed in the table under the map
rather than drawn. The far end is read through the scope guard as well as the edge, so a reader
narrowed away from an account learns nothing about where it runs.

**Hover or focus shows the numbers, and every number is in a table.** Each bubble is a button a
keyboard reaches, with its numbers in its accessible name and in a card on hover or focus:
Effective Cost, resources, accounts, regions and links. A table of every geography and a table of
every link hold them all, with totals where the figures add: cost and resources, and links. Not
accounts, because one account in two geographies is one account.

**Glass tiles below the map, one per geography.** Each is the figure tile the Overview uses: this
month's Effective Cost against the same days last month, and thirty days of its shape. The shape
is the geography's own Cost Explorer view, filtered to its regions, because the view by region
names five series and folds the rest. The resource count and the control that lists the
resources sit in the tile's footer, which a failed cost read does not replace.

**Cost leftovers are sentences too.** Cost carrying no region is global services, support and
fees, which no continent owns. Cost in a region whose prefix no table knows is named by region.
And regions past Cost Explorer's row limit are counted with what they cost, so the continents
never silently add up to less than the month.

**A continent is still the finest grain.** A region name says which geography and never which
city. The markers placed per region by compass word, ISS-213's reduction of 2026-09-27, are
retired with this redraw, because the owner's direction draws one bubble per geography; the
regions inside each are named in its card, its tile and the table. `direction` stays on the route
for any reader that wants it.

The account figure is a distinct count across the geography, not the sum of its regions' counts.
That was ISS-214, and the fix is neither of the two the issue proposed: the grouped read returns
the account identifiers rather than a count of them, and the route unions them per geography and
counts once. No second read, and no second implementation of the prefix rule, which was the
objection to both.

Nothing is loaded until a continent is chosen. A screen that loads the first one has decided which
continent matters, and on an estate across nine of them that is wrong eight times out of nine.

The inline list is a first page with its denominator and no pager. Paging and filtering already
exist on the resource list, and a second implementation of the offset arithmetic is a second place
for it to be wrong, so the screen links there instead.

## Not doing

Placing a resource on a city, and latency between regions. The first needs a coordinate per
region, which is the design this feature rejected for a reason. Latency is a
different feature and a different measurement, and inferring it from geography would be a modelled
number presented beside measured ones.

## Redrawn in P8

On 2026-10-05 the owner asked for the map to be more beautiful and chose the direction: land as
fine dots on a rounded projection, each geography a glowing bubble sized by this month's
Effective Cost with its resource count beside it, lines for cross region links, and glass tiles
with a small trend below. Delivered on 2026-10-06 by TASK-P8-017 in the
[P8 plan](../plans/P8-implementation-plan.md), as the Interface section above describes. A
continent stays the finest grain.
