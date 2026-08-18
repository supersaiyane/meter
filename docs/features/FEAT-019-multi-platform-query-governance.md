# FEAT-019: Multi platform query governance

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Planned |
| Specification | Not written. This document expands when P2 is specified |
| Tasks | Not planned |
| Refresh cadence | Per adapter |

## What it does

Applies the same detection, attribution and prevention to QuickSight SPICE refreshes, Athena workgroups, Redshift and OpenSearch Dashboards.

## Why it exists

ISS-025. The failure mode is not Grafana specific. Grafana is the first adapter, not the only one.

## What is already known

Built as a query cost governance engine with pluggable platform adapters.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P2 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P2.
