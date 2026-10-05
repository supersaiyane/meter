# FEAT-008: Platform self metering

| Field | Value |
| --- | --- |
| Sub project | P0 |
| Status | Delivered |
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

**Amended 2026-10-05, ISS-230.** The assistant's model calls are not resources, so no Terraform tag reaches them. The hub stack routes each model through an application inference profile tagged `finops:module = assistant`, and the task role may reach the model only through it, so its spend arrives as a module of its own. Unverified against a real bill, ISS-002.

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

The screen states the total and draws the breakdown, added 2026-09-27. Constraint 7 puts the
platform's own cost on the front page, and it was on the front page and not on its own screen, so
the one place that exists to answer what Meter costs to run made a reader add four rows up.

The total is dated by its stalest module rather than its freshest. `grandTotal` takes the minimum
for that reason: a total is only as fresh as the oldest thing in it, and reporting the newest
would make a total containing a stale module look like it was read this morning. A test asserts
the older of two days is the one shown.

API routes are listed in the specification section 8. MCP tools exposing this
feature are listed in [ADR-0009](../adr/ADR-0009-mcp-alongside-http-api.md).

## Not doing

Does not attribute cost below module level in P0.
