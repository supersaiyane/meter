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

**Sizing rules, adopted from the competitive review on 2026-08-23.**

| Resource | Rule |
| --- | --- |
| CPU request | 99th percentile of the max rate |
| Memory request | Observed peak plus 15 percent, **or plus 25 percent if the workload has been OOMKilled** |
| Minimum evidence | 50 data points over a 2 week window |

The OOMKill condition is the part worth having. A workload that has been killed
for exceeding memory has already demonstrated that its observed peak was not
its real peak, so sizing it at peak plus the usual margin repeats the failure.
Widening the margin only for workloads with that history is more precise than
widening it for everything.

**Also in scope**, both cheap additions to a collector already being built:

- **Abandoned workload detection.** A deployment with no traffic and no
  meaningful CPU over a 7 day window.
- **Persistent volume growth forecasting.** Storage trend with a safety margin,
  so a volume is resized before it fills rather than after.

OpenCost or an ADOT collector pushes to the warehouse. Meter does not poll into a cluster. In cluster agents are a different deployment and security story from read only IAM roles, which is why P6 is late.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P6 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P6.
