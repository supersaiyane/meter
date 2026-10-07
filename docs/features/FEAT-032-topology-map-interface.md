# FEAT-032: Topology map interface

| Field | Value |
| --- | --- |
| Sub project | P4 |
| Status | Delivered |
| Specification | [P4 spec](../specs/2026-09-20-p4-inventory-and-topology-design.md), section 9 |
| Tasks | TASK-P4-009 |
| Refresh cadence | Live |

## What it does

The interactive resource map, filtered and searchable.

## Why it exists

A graph nobody can navigate is a picture.

## What is already known

Cytoscape.js, filtered server side to at most 2,000 nodes, because a browser will not survive more.

## How it works

Cytoscape.js, filtered server side to at most 2,000 nodes because a browser will
not survive more. The cap is enforced by the route rather than by the client.

Since TASK-P8-013, 2026-10-06, the map's two accessible tables, its resources and its relationships, are `DataTable`s: sortable by any column, each row still named by a row header.

## Failure behaviour

Two things this map must do that a topology map usually does not.

**Say what it could not see.** A region with `PARTIAL` coverage is named above the
graph, not in a footnote. Drawing an unreadable region as sparse is the failure
mode, because a sparse graph looks like a simple estate.

**Say when it truncated.** A subgraph that hit the cap says so and says how many
nodes were omitted. A map silently showing the first two thousand is a map that is
wrong about the shape of the estate.

## Security considerations

Scoped by the same guard as the tables it draws. A reader sees the nodes they are
entitled to and the coverage of what they asked for.

## Interface

Two changes on 2026-09-27, both found by opening the screen.

The coverage notice is a count and its typed causes with the slices one click behind a disclosure,
the same shape the resource list uses. Nine lines of slice identifiers above a graph is the
honesty machinery being the first thing a reader sees instead of the picture they came for.
Collapsed and never dropped: nothing is fetched to open it and the slices stay in the document.

The root picker was a bulleted list of every node in the estate, which on a real one is a page of
bullets before the graph, and bullets on a set of controls say "read this" where the shape needed
is "choose one of these". It is a grid of chips now, capped in height and scrolled, so the picture
and the picker are on the screen together.

`/inventory/topology`. Keyboard reachable, as the organization map already proves
is possible at three hundred accounts.

## Not doing

**Drawing an unbounded graph.** An unbounded traversal of a real estate returns the
estate, and the browser is not where that should be discovered.
