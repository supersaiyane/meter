# FEAT-011: Grafana workspace scanner

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Specified |
| Specification | Not written. This document expands when P2 is specified |
| Tasks | Not planned |
| Refresh cadence | 6 hours, see ADR-0012 |

## What it does

Walks every Amazon Managed Grafana workspace, dashboard, panel and alert rule across accounts and regions, extracts each query, and classifies its engine.

## Why it exists

The failure that started this project was invisible. Nobody knew which dashboard was running which query at what refresh over what window.

## What is already known

A working prototype exists, `sample_lambda.py`, 2,740 lines. It already does workspace discovery, token minting, dashboard and alert walking, and engine classification across Logs Insights, CloudWatch metric search, Metric Insights SQL and PromQL. Productionizing means decomposing it against the 800 line ceiling, adding tests, and moving history into the warehouse. ISS-023, ISS-026, ISS-027.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P2 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P2.
