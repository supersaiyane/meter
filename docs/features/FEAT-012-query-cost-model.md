# FEAT-012: Query cost model

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Specified |
| Specification | Not written. This document expands when P2 is specified |
| Tasks | Not planned |
| Refresh cadence | 6 hours |

## What it does

Models the monthly cost of every dashboard panel and alert rule query from its refresh interval, its time window, and the ingestion rate of the log groups it reads.

## Why it exists

Ranking queries by cost is what turns a list of dashboards into an action.

## What is already known

Prototype models Logs Insights as gigabytes scanned, and metric engines as metrics requested per call. Panels run only while a dashboard is open, so runs per day uses an assumed viewing hours figure. Alert queries run continuously. Every figure is labelled modelled until FEAT-018 calibrates it.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P2 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P2.
