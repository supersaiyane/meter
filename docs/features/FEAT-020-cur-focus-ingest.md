# FEAT-020: CUR 2.0 and FOCUS ingest

| Field | Value |
| --- | --- |
| Sub project | P1 |
| Status | Planned |
| Specification | Not written. This document expands when P1 is specified |
| Tasks | Not planned |
| Refresh cadence | 4 hours, plus a final pass days 3 to 5 of the next month |

## What it does

Ingests Data Exports CUR 2.0 from S3 into the FOCUS table, with resource identifiers and split cost allocation data enabled.

## Why it exists

This is the canonical cost surface everything else in P1 and P3 reads from.

## What is already known

Parquet and partitioned, read through Athena and Glue for extract and load only, never in the serving path. Idempotent upsert because CUR is restated all month. Polling more often than four hours gains nothing, because the source refreshes at most three times a day. See ADR-0012.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P1 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P1.
