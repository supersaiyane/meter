# FEAT-018: Cost model calibration

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Specified |
| Specification | Not written. This document expands when P2 is specified |
| Tasks | Not planned |
| Refresh cadence | Monthly |

## What it does

Back tests the modelled query cost against the actual CUR usage types for scanned bytes and metrics requested, and publishes the accuracy percentage inside the product.

## Why it exists

ISS-022 and ISS-032. This is what turns modelled from a disclaimer into a number an engineering director will act on.

## What is already known

Compares the modelled monthly figure against `*-DataScanned-Bytes` and `CW:MetricsRequested` in the billing data for the same period.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P2 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P2.
