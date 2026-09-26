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

`/inventory/topology`. Keyboard reachable, as the organization map already proves
is possible at three hundred accounts.

## Not doing

**Drawing an unbounded graph.** An unbounded traversal of a real estate returns the
estate, and the browser is not where that should be discovered.
