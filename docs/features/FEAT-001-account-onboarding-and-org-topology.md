# FEAT-001: Account onboarding and organization topology

| Field | Value |
| --- | --- |
| Sub project | P0 |
| Status | In build |
| Specification | `docs/specs/2026-08-23-p0-foundation-design.md` sections 5.2 and 7 |
| Tasks | TASK-P0-014, 018, 019, 022, 025, 027 |
| Decisions | ADR-0004 |
| Issues addressed | ISS-016 |
| Refresh cadence | `org_tree` and `account_health`, hourly |

## What it does

Discovers every account in the AWS Organization, builds the exact parent to child tree of roots, organizational units and accounts, and reports whether the collector role in each account is actually usable.

## Why it exists

The original requirement asked to add accounts and scan for children. Scanning is unnecessary and incomplete: the AWS Organizations API already holds the exact tree. The real problem is not discovery, it is that a newly vended account silently never gets onboarded, so its cost is invisible and every organization total is quietly wrong.

## How it works

`ListRoots`, then `ListOrganizationalUnitsForParent` and `ListAccountsForParent` recursively, through `FinOpsOrgReaderRole` in the management account. The tree is stored as a plain adjacency list in `org_node` and traversed with a recursive common table expression. `FinOpsCollectorRole` reaches every account through a service managed CloudFormation StackSet with automatic deployment to the organization root, so a new account is onboarded with zero human steps. `account_health` then attempts an assume role plus one cheap call per account and records the outcome.

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

Does not read any resource or cost data. That is FEAT-030 and FEAT-020. Does not create, modify or move accounts.
