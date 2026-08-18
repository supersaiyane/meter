# FEAT-033: Quota utilization per region

| Field | Value |
| --- | --- |
| Sub project | P5 |
| Status | Planned |
| Specification | Not written. This document expands when P5 is specified |
| Tasks | Not planned |
| Refresh cadence | 6 hours |

## What it does

Used against limit, per service, per region, for example Ireland and London.

## Why it exists

The requirement asked for quota utilization per zone and region.

## What is already known

Honest constraint: there is no single API for used versus limit across all services. Service Quotas gives limits, the `AWS/Usage` CloudWatch namespace gives usage for a subset, Trusted Advisor covers more, and the remainder needs service specific calls. Coverage is roughly 70 percent, and the gaps are stated rather than hidden. Headroom is a reliability signal, not a cost one.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P5 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P5.
