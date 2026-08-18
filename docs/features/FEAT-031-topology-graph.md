# FEAT-031: Topology graph

| Field | Value |
| --- | --- |
| Sub project | P4 |
| Status | Planned |
| Specification | Not written. This document expands when P4 is specified |
| Tasks | Not planned |
| Refresh cadence | Follows FEAT-030 |

## What it does

The connection map between resources: VPC to subnet to network interface to instance to security group to target group to load balancer, plus cross account edges.

## Why it exists

The requirement asked how resources connect to each other.

## What is already known

Node and edge tables in PostgreSQL traversed with recursive common table expressions, see ADR-0005. Config relationships supply most edges. Transit Gateway attachments, VPC peering, PrivateLink and cross account trust need supplementing.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P4 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P4.
