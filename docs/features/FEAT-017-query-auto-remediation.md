# FEAT-017: Query auto remediation

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Specified |
| Specification | [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) |
| Tasks | Not planned |
| Refresh cadence | On demand |

## What it does

Rewrites an offending panel through the Grafana API, with a change record, an owner notification, and an undo.

## Why it exists

Finding the problem is most of the work but none of the saving.

## How it works

Rewrites an offending panel through the Grafana API, recording the previous state, notifying the owner, and keeping an undo.

## What is already known

Applies only to violations of an explicit policy, never to a judgement call. Every change is reversible and recorded.

## Failure behaviour

A rewrite that cannot be applied is reported with the Grafana error. A rewrite that succeeds but whose verification read back does not match is reverted automatically.

## Security considerations

**The highest risk feature in P2.** It is the first time Meter writes to anything. Gated behind `query_write_level` at `full`, defaulting to `none`, so enabling it is a decision someone signs rather than a default they inherit. `remediation_change.before` is `NOT NULL`: a change Meter cannot undo is a change Meter does not make.

## Interface

`POST /api/v1/query/remediate/{id}` and `POST /api/v1/query/remediate/{id}/undo`. Every change appears on the enforcement screen. See [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) section 5.

## Not doing

Applies only to explicit policy violations, never to a judgement call. Does not touch anything outside the offending panel.
