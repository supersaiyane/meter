# FEAT-025: AWS native recommendation ingest

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Planned |
| Specification | Not written. This document expands when P3 is specified |
| Tasks | Not planned |
| Refresh cadence | 24 hours |

## What it does

Ingests Cost Optimization Hub, Compute Optimizer and Trusted Advisor, which already consolidate rightsizing, idle, Graviton and commitment recommendations organization wide.

## Why it exists

ADR-0006. These are free, organization wide, and save months. Meter's value is attribution, evidence, ownership and workflow, not re deriving AWS sizing.

## What is already known

Compute Optimizer needs an organization level opt in, and Trusted Advisor limit checks need Business or Enterprise support. Both are stated prerequisites, see ISS-004 and OPEN-03.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P3 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P3.
