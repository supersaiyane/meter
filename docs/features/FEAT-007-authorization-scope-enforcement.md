# FEAT-007: Authorization and scope enforcement

| Field | Value |
| --- | --- |
| Sub project | P0 |
| Status | Specified |
| Specification | `docs/specs/2026-08-23-p0-foundation-design.md` sections 5.1 and 6 |
| Tasks | TASK-P0-011, 012, 024 |
| Decisions | ADR-0008 |
| Issues addressed | ISS-009, ISS-016, ISS-017, ISS-031 |
| Refresh cadence | Entitlements cached with an explicit expiry |

## What it does

Decides which accounts a person can see, enforces it in two independent places, and states coverage honestly on every screen.

## Why it exists

A reporting tool over an entire organization's finances is an access control problem first. And the subtle failure is not a leak, it is a silent partial total: showing a user 42 of 310 accounts and labelling the sum as the organization's cost.

## How it works

Two ports, `IdentityProvider` and `EntitlementResolver`, isolate the identity decision, which is parked as OPEN-01. P0 ships a configuration driven local provider that refuses to start when the environment is production. The intended production model uses the ADFS SAML assertion as the source of truth: its AWS role claim is multi valued, one entry per account and role the user is entitled to, which becomes the visibility scope directly, so no separate permission table can drift from Active Directory. Enforcement happens at a request dependency and independently at a repository guard, so a route that forgets the dependency still cannot read out of scope rows. An adversarial test asserts exactly that. Every scope evaluation writes an `audit_event`, and global viewer access is tagged separately. Every response carries `scope_coverage` so the interface says showing N of M accounts rather than presenting a partial total as an organization total.

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

Does not implement SAML. OPEN-01 is parked, and guessing at it would bend the port shape around a guess.
