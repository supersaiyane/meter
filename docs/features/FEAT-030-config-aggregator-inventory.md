# FEAT-030: Config aggregator inventory

| Field | Value |
| --- | --- |
| Sub project | P4 |
| Status | Planned |
| Specification | Not written. This document expands when P4 is specified |
| Tasks | Not planned |
| Refresh cadence | 6 hours, plus change driven |

## What it does

Every resource, by region and availability zone, from an organization wide AWS Config aggregator.

## Why it exists

The requirement asked for a list of all resources by zone and region. Writing hundreds of describe loops is a year of work and a rate limit farm, see ISS-013.

## What is already known

Known cost risk: recording all resource types organization wide is a five figure monthly line item, ISS-012. Mitigation is periodic recording for stable types and continuous only for critical ones, stated to stakeholders up front.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P4 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P4.
