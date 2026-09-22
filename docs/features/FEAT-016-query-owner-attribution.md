# FEAT-016: Query owner attribution

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Specified |
| Specification | Not written. This document expands when P2 is specified |
| Tasks | Not planned |
| Refresh cadence | 6 hours |

## What it does

Attaches a human owner to every expensive query: Grafana folder to team mapping, the last editor from the Grafana API, and the CloudTrail principal that ran it.

## Why it exists

ISS-021. An unowned finding is never fixed. This is the difference between a report and a resolution.

## What is already known

The prototype already extracts the CloudTrail principal. Folder and editor attribution is new.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P2 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P2.
