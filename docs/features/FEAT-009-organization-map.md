# FEAT-009: Organization map

| Field | Value |
| --- | --- |
| Sub project | P0 |
| Status | Specified |
| Specification | `docs/specs/2026-08-23-p0-foundation-design.md` section 9 screen 3 |
| Tasks | TASK-P0-026, 027 |
| Decisions | ADR-0005 |
| Issues addressed | ISS-016 |
| Refresh cadence | Follows FEAT-001, hourly |

## What it does

The parent to child map of the whole organization, as a tree and as a graph.

## Why it exists

The requirement asked to see the parent to child map. Both views answer different questions: the tree answers where is this account, the graph answers what does the organization look like.

## How it works

One dataset, two renderings. The tree is the default because at 300 accounts it is faster to read and is keyboard navigable. The graph uses Cytoscape.js, filtered server side to at most 2,000 nodes. Branches outside the user's scope are drawn and marked unreachable rather than hidden, because a tree with unexplained gaps reads as broken data.

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

Does not show resources inside an account. That is FEAT-031 and FEAT-032.
