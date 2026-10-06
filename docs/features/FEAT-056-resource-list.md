# FEAT-056: The resource list

| Field | Value |
| --- | --- |
| Sub project | P4 |
| Status | Delivered |
| Specification | ISS-204, and the [competitive review](../11-COMPETITIVE-REVIEW.md) 2026-09-26 |
| Tasks | `TASK-P4-012` |
| Refresh cadence | Follows FEAT-030, the inventory collector |
| Source | ISS-204, reinforced by the IBM Turbonomic review on 2026-09-26 |

## What it does

`/inventory/resources`. Every resource this scope can see, filtered by account, region, kind
and resource type, paginated server side, each row linking to the entity page FEAT-053 built.

## Why it exists

The navigation has promised this screen since P4 began and the P4 specification never
scheduled one, so a delivered sub project was named as the thing that would bring a screen
nobody planned. That is ISS-204, and this closes it by building the screen rather than by
editing the marker until the inconsistency disappears.

The map cannot answer "how many gp2 volumes do I have in Frankfurt", which is the question
people arrive with. It answers what is connected to what, for one root, bounded to four hops.

## How it works

Server side pagination and filtering over `topology_node`, through `scoped_select`. An estate
of three hundred accounts is not a list the browser sorts.

Since TASK-P8-013, 2026-10-06, the screen draws every resource in scope by type and by region,
from counts the route returns beside its filter values. They are counted over the scope, as the
values are, so narrowing the list does not collapse the charts, and a null type or region is
counted as no type or global rather than dropped.

Since TASK-P8-013, 2026-10-06, the list is a `DataTable`. Its columns sort only when the page holds the whole list: a page of a longer list arrives in the server's order, and sorting it would order fifty rows and read as ordering every one.

## Failure behaviour

The estate wide coverage banner sits above the list, not beside it, and the count says how
many slices the list is drawn from. Every row came out of a slice, and a slice that refused us
contributes nothing while looking identical to a region that is genuinely empty. A count at
the top of a list is a claim about the estate.

A null region renders as global and a null zone as regional, never as unknown and never as an
empty cell.

## Security considerations

Scope twice, per constraint 3: the request dependency and the repository guard. A narrowed
reader sees their own accounts and no count that includes anybody else's.

## Interface

The coverage notice above the table is a count and its typed causes, with the slices one click
behind a disclosure, changed 2026-09-27. Nine slices is nine lines of identifiers above the fold
on a screen whose purpose is the table under them, so the honesty machinery was the first thing a
reader saw instead of their own data. Collapsed and never dropped: nothing is fetched to open it,
and the slices are still in the document, which is what makes this different from hiding them. The
same treatment the shell's failure wall got, so a reader learns one shape.

`/inventory/resources`, in the Inventory group, and the `arrives` marker in `sections.ts`
becomes null in the same commit that ships it.

`filters.region_counts` and `filters.type_counts` on `GET /api/v1/inventory/resources`, since
2026-10-06: each value and how many resources carry it, largest first. Both default to empty, so
a payload made before the counts still validates.

## Not doing

Editing anything. The list is a way in, and the entity page is where a resource is read.

Saved views or custom columns. ADR-0020 fixes the screens on purpose.
