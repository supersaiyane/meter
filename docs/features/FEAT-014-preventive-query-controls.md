# FEAT-014: Preventive query controls

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Specified |
| Specification | Not written. This document expands when P2 is specified |
| Tasks | Not planned |
| Refresh cadence | On save, and in CI |

## What it does

Stops a cost generating dashboard from being saved at all: a workspace level minimum refresh interval, and a pipeline gate that rejects dashboard JSON combining a sub minute refresh with a window longer than 24 hours on a Logs Insights panel.

## Why it exists

ISS-020. A report of money already burned is a post mortem. The workspace refresh floor is free, needs no code, and removes most of the exposure on its own.

## What is already known

Amazon Managed Grafana supports `min_refresh_interval` natively and Grafana enforces it. The CI gate applies to dashboards managed as code.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P2 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P2.
