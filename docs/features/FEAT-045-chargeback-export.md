# FEAT-045: Chargeback and showback export, CSV and Excel

| Field | Value |
| --- | --- |
| Sub project | P1 |
| Status | Planned |
| Specification | Not written. This document expands when P1 is specified |
| Tasks | Not planned |
| Refresh cadence | On demand |
| Source | Adopted from a competitive review on 2026-08-23 |

## What it does

Exports allocated cost by team, environment, cost category or tag, as CSV and Excel, with the unallocated bucket included rather than quietly dropped.

## Why it exists

Finance does not work inside our interface. A FinOps tool that cannot hand finance a file is missing its actual consumer, and the gap was invisible until a competitive review made it obvious.

## What is already known

The export carries the same `meta` that every API response carries: `as_of`, `collected_at`, and the scope coverage. A spreadsheet that leaves the product without its freshness and coverage becomes a number in a board pack with no way back to what it meant.

The unallocated bucket is a row in the export, never omitted. An export that silently excludes what could not be attributed reconciles to nothing.

## Status of this document

Planned. The remaining sections are written when P1 is specified. Recording
only what is decided is deliberate: a document that invents detail ahead of the
decision is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P1, and
[docs/11-COMPETITIVE-REVIEW.md](../11-COMPETITIVE-REVIEW.md).
