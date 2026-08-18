# FEAT-021: Cost rollups, trends and per resource attribution

| Field | Value |
| --- | --- |
| Sub project | P1 |
| Status | Planned |
| Specification | Not written. This document expands when P1 is specified |
| Tasks | Not planned |
| Refresh cadence | Follows FEAT-020 |

## What it does

Pre aggregated rollups by day, account, service, region, resource, charge category and tag, serving every cost chart and trend in the product.

## Why it exists

The original requirement asked for cost graphs and trends per resource.

## What is already known

Rollups live in PostgreSQL, not Athena, because putting interactive dashboards on a per terabyte scanned engine recreates the exact problem this product exists to prevent. See ADR-0003 and ISS-006.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P1 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P1.
