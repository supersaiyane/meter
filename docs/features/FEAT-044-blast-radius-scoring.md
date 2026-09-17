# FEAT-044: Blast radius scoring from the dependency graph, gating auto apply

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Planned |
| Specification | Not written. This document expands when P3 is specified |
| Tasks | Not planned |
| Refresh cadence | On demand, per recommendation |
| Source | Adopted from a competitive review on 2026-08-23 |

## What it does

Scores how much a proposed change could affect, by walking the resource dependency graph outward from the target, and uses that score to decide whether the change can be applied automatically or must wait for a human.

## Why it exists

The topology graph in FEAT-031 was going to be built and then used only for drawing pictures. Scoring blast radius from it is the single best idea found in the competitive review, and the data is already there.

## What is already known

Inputs are the node and edge tables from FEAT-031. A resource with no inbound edges and no dependents scores low. A shared VPC endpoint, a security group referenced by forty instances, or a load balancer target group scores high.

It does not by itself create a write path. Meter is read only in v1, so the score gates whether a generated pull request is marked safe to merge, not whether Meter applies a change. When a write path is considered in v2, this score is a precondition for it rather than a nice addition.

## Status of this document

Planned. The remaining sections are written when P3 is specified. Recording
only what is decided is deliberate: a document that invents detail ahead of the
decision is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P3, and
[docs/11-COMPETITIVE-REVIEW.md](../11-COMPETITIVE-REVIEW.md).
