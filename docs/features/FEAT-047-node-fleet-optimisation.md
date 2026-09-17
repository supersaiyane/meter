# FEAT-047: Cluster node fleet optimisation as an integer linear program

| Field | Value |
| --- | --- |
| Sub project | P6 |
| Status | Planned |
| Specification | Not written. This document expands when P6 is specified |
| Tasks | Not planned |
| Refresh cadence | 24 hours |
| Source | Adopted from a competitive review on 2026-08-23 |

## What it does

Selects the cheapest mix of instance types that satisfies a cluster's actual CPU and memory demand, solved as a cost minimising integer linear program.

## Why it exists

The P6 plan stopped at reporting bin packing efficiency, which tells a team their cluster is 61 percent efficient and leaves them to work out what to buy instead. This solves for the answer.

## What is already known

Inputs are the aggregate demand from FEAT-036 and the instance catalogue with on demand and Spot pricing. Constraints include instance family availability per region, Spot interruption tolerance per workload class, and any node group the team has pinned.

The output is a recommendation like every other: it carries its evidence window, its confidence, its measured or modelled flag, and a dollar impact that sets its severity under ADR-0016. It is not applied automatically.

## Status of this document

Planned. The remaining sections are written when P6 is specified. Recording
only what is decided is deliberate: a document that invents detail ahead of the
decision is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P6, and
[docs/11-COMPETITIVE-REVIEW.md](../11-COMPETITIVE-REVIEW.md).
