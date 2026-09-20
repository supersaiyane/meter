# FEAT-044: Blast radius scoring from the dependency graph, gating auto apply

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Specified |
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

Walks the resource dependency graph outward from a target, bounded, and scores how
much a proposed change could affect. Inputs are FEAT-031's node and edge tables. A
resource with no inbound edges and no dependents scores low. A shared VPC endpoint,
a security group referenced by forty instances, or a load balancer target group
scores high.

## Failure behaviour

**It refuses to score against a graph that is not known to be complete.** If
`graph_coverage` for the resource's account or region is `PARTIAL` or `UNREAD`, it
returns no score and a reason.

That is the whole safety property. A region Meter could not read contributes no
edges, so a resource with forty dependents there scores as having none, and a low
score reads as "this change is safe". A missing score reads as "we do not know",
which is the truth. The first is a claim the product would be making on its own
initiative about somebody's production estate.

The score is also a **lower bound**, never an upper one, and the screen says so:
application level dependencies, a service calling another over the internet, are
invisible to an infrastructure graph.

## Security considerations

It does not by itself create a write path. Meter is read only in v1, and this exists
so that a future auto apply has a gate to consult rather than being built first and
made safe afterwards.

## Interface

A score on the recommendation detail screen, or a refusal with its reason.

## Not doing

**Gating anything automatically**, because there is nothing automatic to gate.
