# FEAT-044: Blast radius scoring from the dependency graph, gating auto apply

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Delivered |
| Specification | [P3 spec](../specs/2026-09-20-p3-utilization-and-rightsizing-design.md), section 12 |
| Tasks | TASK-P3-020, blocked on P4 |
| Refresh cadence | On demand, per recommendation |
| Source | Adopted from a competitive review on 2026-08-23 |

## What it does

Scores how much a proposed change could affect, by walking the resource dependency graph outward from the target, and uses that score to decide whether the change can be applied automatically or must wait for a human.

## Why it exists

The topology graph in FEAT-031 was going to be built and then used only for drawing pictures. Scoring blast radius from it is the single best idea found in the competitive review, and the data is already there.

## What is already known

Inputs are the node and edge tables from FEAT-031. A resource with no inbound edges and no dependents scores low. A shared VPC endpoint, a security group referenced by forty instances, or a load balancer target group scores high.

It does not by itself create a write path. Meter is read only in v1, so the score gates whether a generated pull request is marked safe to merge, not whether Meter applies a change. When a write path is considered in v2, this score is a precondition for it rather than a nice addition.

## How it works

`finops_query/blast_radius.py` is pure and holds the whole judgement. It takes a `Subgraph`
from FEAT-031's tables, calls `require_whole()` first, and returns a band with the parts that
produced it.

**A band, not a number, and three values rather than a scale.** `CROSS_ACCOUNT` is not simply
wider than `WIDE`. A change that stays inside one account is somebody's own problem; a change
reaching another account is somebody else's problem and they have not been asked. That
distinction survives whatever the counts say, so it is a separate band and not a higher
threshold.

**The parts are published beside the band.** Resources reached, other accounts touched, and
dependencies that leave the graph, each with a sentence. The band is what a reader scans and the
parts are what they argue with, which is the same argument ADR-0016 makes about severity and
`score.py` makes about posture.

**The threshold is configuration.** `METER_BLAST_RADIUS_WIDE_AT`, because a number in code
deciding what counts as wide is a number nobody can argue with. That is ADR-0012's argument
about cadence applied to a judgement rather than to an interval.

**A refusal is only about the slices the answer rests on.** A subgraph carries the coverage of
the slices it touched, so a walk that never enters an unread region is whole and is scored.
Refusing on any incomplete slice anywhere in the estate would make every score unavailable
forever on an estate with one unread region, which is not what the specification asks for. The
first draft of the route test assumed otherwise and a case now pins it.

## Failure behaviour

**It refuses to score against a graph that is not known to be complete.** If
`graph_coverage` for the resource's account or region is `PARTIAL` or `UNREAD`, it
returns no score and a reason.

That is the whole safety property. A region Meter could not read contributes no
edges, so a resource with forty dependents there scores as having none, and a low
score reads as "this change is safe". A missing score reads as "we do not know",
which is the truth. The first is a claim the product would be making on its own
initiative about somebody's production estate.

A walk the node cap cut short refuses too. That bound is ours rather than the estate's, so the
refusal names our own limit and not anything the customer did.

**The refusal is a 200 with a reason, never a status code.** The graph having a hole in it is a
fact about the estate rather than a fault in the request, so both halves travel on one payload
and exactly one is populated. A 409 would make the screen render a failure and send a reader
looking for a broken service instead of for a permission.

The score is also a **lower bound**, never an upper one, and `is_lower_bound` is a field rather
than a docstring so no consumer can render a radius without it: application level dependencies,
a service reading another's queue, a report somebody runs every Monday off this table, are
invisible to an infrastructure graph.

**The reach is a floor a second time whenever the walk reached its depth bound.** Resources
beyond that bound were never looked at, which is different from having been looked at and found
absent. `require_whole` cannot catch this, because a walk that completed within its depth is
bounded rather than truncated, so the value carries `depth_bound_reached` and the screen says so.

## Security considerations

It does not by itself create a write path. Meter is read only in v1, and this exists
so that a future auto apply has a gate to consult rather than being built first and
made safe afterwards.

## Interface

`GET /api/v1/inventory/nodes/{node_id}/blast-radius`, rendered as a panel on the entity page,
FEAT-053. Either the band with its parts and the floor sentence, or the refusal with the slices
named.

Its own route rather than a field on the entity payload. That page walks one hop and this walks
four, so folding it in would make every visit to a resource pay for a traversal most visits do
not need, and a refusal would have to be explained as part of a payload that otherwise
succeeded.

## Not doing

**Gating anything automatically**, because there is nothing automatic to gate.
