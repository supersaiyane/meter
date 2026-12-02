# FEAT-010: Ingest and freshness surface

| Field | Value |
| --- | --- |
| Sub project | P0 |
| Status | Delivered |
| Specification | `docs/specs/2026-08-23-p0-foundation-design.md` section 9 screen 4 |
| Tasks | TASK-P0-028 |
| Decisions | ADR-0012 |
| Issues addressed | ISS-015, ISS-030 |
| Refresh cadence | Live |

## What it does

The operational screen: per collector and per scope, what ran, when, what it found, and what failed with which typed cause.

## Why it exists

This is the screen that proves the platform is honest about what it does not know. Without it, a user has no way to distinguish a genuinely low number from a collection that never ran.

## How it works

Reads `ingest_run`, `ingest_watermark` and `sync_error`. Shows the typed error and its remediation text, so a user can act without reading logs. A failed collection is rendered visually distinct from a zero result. Staleness is computed per collector against its configured cadence, so a collector that should run hourly and last ran nine hours ago is flagged even though it has data.

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

Does not fix anything. Remediation is text, and any action is a separate decision.
