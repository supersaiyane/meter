# FEAT-039: Anomaly narration

| Field | Value |
| --- | --- |
| Sub project | P7 |
| Status | Planned |
| Specification | Not written. This document expands when P7 is specified |
| Tasks | Not planned |
| Refresh cadence | Follows FEAT-023 |

## What it does

Explains why a cost anomaly happened by correlating the cost delta with Config change events, CloudTrail and deploy timestamps, and drafts the ticket.

## Why it exists

Correlating heterogeneous evidence and writing a readable explanation is what a language model is actually good at.

## What is already known

Deterministic detection finds what changed. The model only explains. It never computes a figure, see ADR-0007.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P7 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P7.
