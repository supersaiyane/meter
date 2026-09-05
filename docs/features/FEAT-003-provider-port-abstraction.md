# FEAT-003: Provider port abstraction

| Field | Value |
| --- | --- |
| Sub project | P0 |
| Status | Delivered |
| Specification | `docs/02-ARCHITECTURE.md` section Ports |
| Tasks | TASK-P0-007, 008, 009 |
| Decisions | ADR-0002, ADR-0011 |
| Issues addressed | ISS-005 |
| Refresh cadence | Not applicable, this is structure |

## What it does

Eight interfaces that a cloud provider implements. `QuerySurface`, added by P2, is a ninth port in the same package and is deliberately not one of these: it describes a tool that holds saved queries rather than a cloud, and FEAT-011 owns it. AWS implements them now. GCP, Azure and PCF implement the same eight later without touching the domain, the API or the frontend.

## Why it exists

The requirement asked for an AWS product with a base for other providers. The cheap way to get that wrong is to build AWS specific code and promise to abstract it later. The abstraction has to exist before the first implementation or it never arrives.

## How it works

`AccountDiscovery`, `CredentialBroker`, `CostExport`, `MetricSource`, `ResourceInventory`, `QuotaSource`, `IdentityProvider` and `EntitlementResolver` are defined as protocols in `finops_core`, which imports no cloud SDK and no framework. An import linter contract in `pyproject.toml` fails the build if that is ever violated, so the rule holds by machine rather than by intention. A `FakeProvider` implements all eight, which is what lets every core and API test run with no AWS account at all. One contract test suite is parameterised over providers so the AWS adapter is held to exactly the contract the fake satisfies.

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

Does not implement any non AWS provider. No connector is built until the AWS product is proven.
