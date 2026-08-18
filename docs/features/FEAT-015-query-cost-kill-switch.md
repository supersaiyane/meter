# FEAT-015: Query cost kill switch

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Planned |
| Specification | Not written. This document expands when P2 is specified |
| Tasks | Not planned |
| Refresh cadence | Event driven, seconds to minutes |

## What it does

Detects a runaway query pattern in near real time and stops it: counts CloudTrail `StartQuery` per principal per hour, alerts on breach, and applies a deny policy through AWS Budgets Actions at threshold.

## Why it exists

A six hour audit of the original failure would still have let roughly 25,000 USD burn between sweeps. Prevention cannot run on a survey cadence.

## What is already known

EventBridge rule on CloudTrail. This is deliberately a separate feature from the audit, at a separate cadence. See ADR-0012.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P2 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P2.
