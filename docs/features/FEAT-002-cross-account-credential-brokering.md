# FEAT-002: Cross account credential brokering

| Field | Value |
| --- | --- |
| Sub project | P0 |
| Status | Specified |
| Specification | `docs/specs/2026-08-23-p0-foundation-design.md` section 10 |
| Tasks | TASK-P0-013, 014, 017 |
| Decisions | ADR-0004 |
| Issues addressed | ISS-010 |
| Refresh cadence | On demand, cached to 5 minutes before expiry |

## What it does

Produces a scoped, short lived AWS session for any member account, so every collector reads through one audited path rather than each inventing its own.

## Why it exists

Credentials are the part of a multi account platform most likely to be done badly. One broker means one place to get the trust policy, the ExternalId, the organization condition, the timeouts and the retry policy right.

## How it works

`FinOpsHubTaskRole` on the ECS task assumes `FinOpsCollectorRole` in the target account. The trust policy requires an ExternalId held in Secrets Manager and an `aws:PrincipalOrgID` condition. The member policy is a curated list of roughly 40 actions, each annotated with the collector that needs it, explicitly not the AWS managed `ReadOnlyAccess` policy, which grants S3 object reads and SSM parameter reads that Meter never uses and that cannot be defended in review. Sessions cache until 5 minutes before expiry. Connect and read timeouts are bounded so a broken network path fails fast instead of consuming the whole task timeout.

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

Does not broker credentials for a human. Identity propagated access for live drill down is part of FEAT-007.
