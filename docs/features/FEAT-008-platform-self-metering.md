# FEAT-008: Platform self metering

| Field | Value |
| --- | --- |
| Sub project | P0 |
| Status | In build |
| Specification | `docs/specs/2026-08-23-p0-foundation-design.md` section 5.5 |
| Tasks | TASK-P0-015, 023, 025, 028 |
| Decisions | ADR-0012 |
| Issues addressed | ISS-018 |
| Refresh cadence | `platform_cost`, daily |

## What it does

Shows Meter's own AWS cost, broken down by module, on its own front page.

## Why it exists

A FinOps tool that cannot show its own bill has no standing to comment on anyone else's. There is also a concrete risk: the ingestion layer makes metered API calls, and `GetMetricData`, Cost Explorer and Athena scanning are all billed. Without this the platform can quietly become the cost problem it exists to solve.

## How it works

Every Terraform resource carries a `finops:module` tag. A daily collector makes one Cost Explorer request grouped by that tag and writes `platform_cost`. Daily rather than hourly because Cost Explorer charges per request, and one grouped request rather than one per module for the same reason. Untagged cost lands in an explicit unallocated bucket rather than being dropped, because a self metering report that quietly under counts is worse than none, since it is believed.

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

Does not attribute cost below module level in P0.
