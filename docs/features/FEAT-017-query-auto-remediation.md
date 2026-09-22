# FEAT-017: Query auto remediation

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Specified |
| Specification | Not written. This document expands when P2 is specified |
| Tasks | Not planned |
| Refresh cadence | On demand |

## What it does

Rewrites an offending panel through the Grafana API, with a change record, an owner notification, and an undo.

## Why it exists

Finding the problem is most of the work but none of the saving.

## What is already known

Applies only to violations of an explicit policy, never to a judgement call. Every change is reversible and recorded.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P2 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P2.
