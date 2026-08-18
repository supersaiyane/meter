# FEAT-027: CloudWatch cost module

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Planned |
| Specification | Not written. This document expands when P3 is specified |
| Tasks | Not planned |
| Refresh cadence | 24 hours |

## What it does

Finds the cheap wins in CloudWatch itself: log groups with no retention policy, high ingest groups with no queries in 90 days, duplicate delivery to both CloudWatch Logs and S3, custom metrics never queried, alarms stuck in insufficient data for 90 days.

## Why it exists

These findings are trivially detectable and typically pay for the whole platform in the first month.

## What is already known

Remediation levers are retention policies, the CloudWatch Logs Infrequent Access class, and export of cold logs to S3.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P3 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P3.
