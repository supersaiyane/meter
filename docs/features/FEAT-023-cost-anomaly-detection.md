# FEAT-023: Cost anomaly detection

| Field | Value |
| --- | --- |
| Sub project | P1 |
| Status | Planned |
| Specification | Not written. This document expands when P1 is specified |
| Tasks | Not planned |
| Refresh cadence | 6 hours |

## What it does

Detects unexpected cost movement and ingests AWS Cost Anomaly Detection findings alongside its own statistical detection.

## Why it exists

Detection has to be deterministic and reproducible. Narration is a separate feature, see FEAT-039 and ADR-0007.

## What is already known

Detection finds what changed. It never explains why, which is a different problem with different failure modes.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P1 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P1.
