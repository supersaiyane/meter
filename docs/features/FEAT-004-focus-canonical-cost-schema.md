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

`cost_focus_daily` carries FOCUS 1.4's mandatory Cost and Usage columns and its two invoice columns unchanged, with Meter columns alongside rather than inside that namespace: `tenant_id`, `as_of`, `ingest_run_id`, `source_fingerprint`. Provider specific fields that FOCUS does not carry live in `cost_provider_extra`, keyed by the same fact. Amortized and net amortized are the primary measures everywhere, because with Reserved Instances and Savings Plans in play unblended per resource cost is fiction. Unblended is retained only for invoice reconciliation and is never the default on a chart. The table is partitioned by billing period, and ingestion is idempotent, because CUR is restated throughout the month.

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

Does not populate the table. That is FEAT-020 in P1. Does not reconcile to the invoice, which is FEAT-076 in P10.

## Status of this document

In build since P0 at FOCUS 1.1. TASK-P10-002 gave the row every column FOCUS 1.4 makes
mandatory and the two invoice columns on 2026-10-07, migration 0030, read from AWS's FOCUS export
where it carries them and null where it does not; `tests/api/test_focus_columns.py` holds all 21.
P10 moved the row to FOCUS 1.4's mandatory columns and
its invoice columns, ADR-0034: measured on 2026-10-07, the row lacked 6 of the 21 mandatory
columns, P10 spec section 4, and since TASK-P10-006 on 2026-10-08 constraint 2 and
`FOCUS_VERSION` name FOCUS 1.4. A row written before migration 0030 arrives with its provider
pair backfilled, and the release before P10 still writes after it,
`tests/db/test_focus_1_4_migration.py`. The conditional and recommended columns no source of
Meter's fills yet wait for FOCUS conformance, P10 spec section 4.
