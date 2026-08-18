# FEAT-005: Ingestion framework

| Field | Value |
| --- | --- |
| Sub project | P0 |
| Status | Specified |
| Specification | `docs/specs/2026-08-23-p0-foundation-design.md` section 7 |
| Tasks | TASK-P0-020, 021 |
| Decisions | ADR-0012 |
| Issues addressed | ISS-008 |
| Refresh cadence | Per collector, see ADR-0012 |

## What it does

Fans work out across accounts and regions, runs it concurrently, records every outcome, and never lets one account's failure fail a run.

## Why it exists

At 300 accounts, something always fails. A framework that treats failure as exceptional produces either a run that dies on the first AccessDenied or, worse, one that swallows it and reports zero.

## How it works

EventBridge Scheduler triggers a dispatcher that enumerates every tenant, account, region and collector unit and publishes one SQS message each with a deduplication key. Fargate workers scale on queue depth. Each worker claims a run in `ingest_run` by an idempotency key of collector, scope key and as of window, so running three times writes one result set. Watermarks advance only on success, so a failure never silently skips a window. Failures are recorded per scope with a typed cause and the run continues. A crashed run is reclaimable after a timeout rather than blocking that scope forever.

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

Does not decide cadence. Cadence is data in `collector_schedule`, see ADR-0012.
