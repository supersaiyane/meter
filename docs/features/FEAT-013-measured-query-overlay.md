# FEAT-013: Measured query overlay

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Planned |
| Specification | Not written. This document expands when P2 is specified |
| Tasks | Not planned |
| Refresh cadence | 6 hours |

## What it does

Overlays real execution counts and scanned bytes from CloudTrail and CloudWatch Logs query history onto the modelled figures, so a row is labelled measured rather than estimated where evidence exists.

## Why it exists

A modelled number ranks reliably but cannot be defended. A measured one can.

## What is already known

Prototype already collects CloudTrail `StartQuery` events, `logs:DescribeQueries` history, and `GetMetricData` call counts, and matches them to panel queries by fingerprint.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P2 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P2.
