# FEAT-024: Savings Plan and Reserved Instance coverage

| Field | Value |
| --- | --- |
| Sub project | P1 |
| Status | Planned |
| Specification | Not written. This document expands when P1 is specified |
| Tasks | Not planned |
| Refresh cadence | 24 hours |

## What it does

Reports utilization and coverage for Savings Plans and Reserved Instances, and surfaces AWS purchase recommendations.

## Why it exists

Commitment waste is usually the largest single addressable line item, and it is invisible in unblended cost.

## What is already known

Reads the AWS utilization and coverage APIs directly rather than deriving them, because AWS owns the definition.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P1 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P1.
