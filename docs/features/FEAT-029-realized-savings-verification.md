# FEAT-029: Realized savings verification

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Planned |
| Specification | Not written. This document expands when P3 is specified |
| Tasks | Not planned |
| Refresh cadence | Monthly, 60 day lag |

## What it does

Measures what actually appeared in the bill 60 days after a recommendation was marked done, verified against CUR.

## Why it exists

ISS-029. This is the north star metric. Identified savings is a vanity number that every FinOps tool inflates.

## What is already known

Compares the affected resource's amortized cost before and after, controlling for usage change, and marks a recommendation regressed if the saving did not persist.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P3 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P3.
