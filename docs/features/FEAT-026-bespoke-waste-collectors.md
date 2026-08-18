# FEAT-026: Bespoke waste collectors

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Planned |
| Specification | Not written. This document expands when P3 is specified |
| Tasks | Not planned |
| Refresh cadence | 24 hours, 14 to 30 day window |

## What it does

Covers what AWS is blind to: memory utilization, EBS provisioned versus used, gp2 to gp3, unattached volumes, aged snapshots, idle NAT Gateways, idle load balancers, unassociated Elastic IPs, DynamoDB provisioned versus consumed.

## Why it exists

ADR-0006 rung six. Only build where the native services genuinely do not reach.

## What is already known

Binding rules: never recommend on fewer than 14 days, use p95 and p99 never max, batch `GetMetricData` at 500 metrics per call at one hour period, account for burstable credits, and recommend at Auto Scaling group level not per instance.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P3 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P3.
