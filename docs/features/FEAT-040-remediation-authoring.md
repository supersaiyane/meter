# FEAT-040: Remediation authoring

| Field | Value |
| --- | --- |
| Sub project | P7 |
| Status | Planned |
| Specification | Not written. This document expands when P7 is specified |
| Tasks | Not planned |
| Refresh cadence | On demand |

## What it does

Generates the Terraform or CloudFormation diff, or the Grafana panel patch, and opens a merge request for human approval.

## Why it exists

Meter is read only in v1. Remediation as a reviewable code change is how it acts without holding write credentials.

## What is already known

Never merged automatically. The same constraint as the security autofix, and for the same reason.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P7 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P7.
