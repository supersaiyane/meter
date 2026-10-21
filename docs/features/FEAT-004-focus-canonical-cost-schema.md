# FEAT-004: FOCUS canonical cost schema

| Field | Value |
| --- | --- |
| Sub project | P0 |
| Status | In build |
| Specification | `docs/specs/2026-08-23-p0-foundation-design.md` section 5.4 |
| Tasks | TASK-P0-006, 010 |
| Decisions | ADR-0002 |
| Issues addressed | ISS-005, ISS-007, ISS-008 |
| Refresh cadence | Schema only. Populated by FEAT-020 |

## What it does

One cost table, in the FinOps Open Cost and Usage Specification shape, that every provider normalises into at ingest.

## Why it exists

Every cloud bills in a different shape. Inventing an internal schema means a migration for every provider added. FOCUS is the industry standard, AWS Data Exports emits it natively, and GCP and Azure both publish FOCUS exports.

## How it works

`cost_focus_daily` carries the FOCUS 1.1 columns unchanged, with Meter columns alongside rather than inside that namespace: `tenant_id`, `as_of`, `ingest_run_id`, `source_fingerprint`. Provider specific fields that FOCUS does not carry live in `cost_provider_extra`, keyed by the same fact. Amortized and net amortized are the primary measures everywhere, because with Reserved Instances and Savings Plans in play unblended per resource cost is fiction. Unblended is retained only for invoice reconciliation and is never the default on a chart. The table is partitioned by billing period, and ingestion is idempotent, because CUR is restated throughout the month.

## Failure behaviour

Governed by the closed error taxonomy in [FEAT-006](FEAT-006-typed-errors-and-freshness.md).
A collection that fails renders as a typed failure with its remediation, never
as the number zero. `NoData` is the only cause that renders as a zero, and only
because the source genuinely returned nothing.

## Security considerations

Read only. Access is filtered by the caller's scope at both the request
dependency and the repository guard, see
[FEAT-007](FEAT-007-authorization-scope-enforcement.md). Every read writes an
audit event recording the scope evaluated.

## Interface

API routes are listed in the specification section 8. MCP tools exposing this
feature are listed in [ADR-0009](../adr/ADR-0009-mcp-alongside-http-api.md).

## Not doing

Does not populate the table. That is FEAT-020 in P1. Does not reconcile to the invoice.
