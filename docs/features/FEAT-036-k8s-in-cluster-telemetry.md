# FEAT-036: In cluster telemetry

| Field | Value |
| --- | --- |
| Sub project | P6 |
| Status | Planned |
| Specification | Not written. This document expands when P6 is specified |
| Tasks | Not planned |
| Refresh cadence | 15 minutes, pushed |

## What it does

Requested versus used CPU and memory per namespace, node bin packing efficiency, idle and unallocated node cost, Spot ratio, orphaned persistent volumes, unused LoadBalancer services.

## Why it exists

Over requesting is the single largest source of Kubernetes waste and typically runs 40 to 60 percent. It is invisible in billing data.

## What is already known

OpenCost or an ADOT collector pushes to the warehouse. Meter does not poll into a cluster. In cluster agents are a different deployment and security story from read only IAM roles, which is why P6 is late.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P6 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P6.
