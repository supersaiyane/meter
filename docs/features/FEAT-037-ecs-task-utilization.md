# FEAT-037: ECS and Fargate utilization

| Field | Value |
| --- | --- |
| Sub project | P6 |
| Status | Planned |
| Specification | Not written. This document expands when P6 is specified |
| Tasks | Not planned |
| Refresh cadence | 24 hours |

## What it does

Task level reservation versus utilization, with recommendations snapped to valid Fargate vCPU and memory combinations.

## Why it exists

Fargate sizing is discrete. A recommendation that names an impossible size will be correctly ignored.

## What is already known

Container Insights supplies the metrics.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P6 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P6.
