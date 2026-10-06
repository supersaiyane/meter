# FEAT-047: Cluster node fleet optimisation as an integer linear program

| Field | Value |
| --- | --- |
| Sub project | P6 |
| Status | Specified |
| Specification | [P6 spec](../specs/2026-09-20-p6-containers-design.md), section 3 |
| Tasks | Second cut, not planned |
| Refresh cadence | 24 hours |
| Source | Adopted from a competitive review on 2026-08-23 |

## What it does

Selects the cheapest mix of instance types that satisfies a cluster's actual CPU and memory demand, solved as a cost minimising integer linear program.

## Why it exists

The P6 plan stopped at reporting bin packing efficiency, which tells a team their cluster is 61 percent efficient and leaves them to work out what to buy instead. This solves for the answer.

## What is already known

Inputs are the aggregate demand from FEAT-036 and the instance catalogue with on demand and Spot pricing. Constraints include instance family availability per region, Spot interruption tolerance per workload class, and any node group the team has pinned.

The output is a recommendation like every other: it carries its evidence window, its confidence, its measured or modelled flag, and a dollar impact that sets its severity under ADR-0016. It is not applied automatically.

## How it works

Not yet designed in detail, and deliberately so. It consumes FEAT-036's aggregate
demand, and an optimiser fed by figures nobody has seen yet produces confident
answers that are wrong.

What is decided: it is a cost minimising integer linear program over the instance
catalogue, constrained by family availability per region, Spot interruption
tolerance per workload class, and any node group a team has pinned. Its output is a
recommendation like every other, carrying its evidence window, its confidence, its
measured or modelled flag and a dollar impact that sets its severity.

Since TASK-P8-013, 2026-10-06, the cluster table is a `DataTable`, sortable by any column, with the nodes totalled: a cluster with no nodes adds none, and a fleet nobody could read stops the total rather than counting as empty.

## Failure behaviour

Undecided. The known risk is that a fleet recommendation computed from partial
demand is confidently wrong, in the same way a blast radius score from a partial
graph is, and it will need the same kind of refusal.

## Security considerations

Read only, and it recommends rather than applies. Constraint 6.

## Interface

Undecided.

## Not doing

**Anything, yet.** This is the P6 second cut, deferred for the reason P6 spec
section 3 gives. A solver is also a new dependency and goes through `make
dep-check` like any other, and it is the first thing in this product whose output a
reader cannot check by hand, so it will need its inputs and constraints visible
beside the answer.
