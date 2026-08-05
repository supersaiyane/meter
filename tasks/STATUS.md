# Status

Last updated: 2026-08-23
Update trigger: end of every work session

Legend: `[x]` done, `[~]` in progress, `[ ]` not started, `[!]` blocked.

## Where the project stands right now

Design phase. No application code has been written. The current gate is the
user reviewing the P0 foundation specification.

## Phase 0: project setup and design

| | Item | Notes |
| --- | --- | --- |
| `[x]` | Review the existing Grafana audit prototype | 2,740 line Lambda, assessed as roughly 70 percent of the P2 feature |
| `[x]` | Requirement review across all nine requested areas | Findings folded into `docs/01-ROADMAP.md` |
| `[x]` | Decompose into eight sub projects and fix build order | ADR-0001 |
| `[x]` | Confirm scale assumption | 50 to 300 accounts, 10 to 100 GB CUR per month |
| `[x]` | Confirm technology stack | Python and FastAPI, React and TypeScript, ECS Fargate, Terraform |
| `[x]` | Initialize repository and documentation spine | This commit set |
| `[x]` | Write goal, roadmap and architecture documents | `docs/00`, `docs/01`, `docs/02` |
| `[x]` | Write the eight foundational architecture decision records | `docs/adr/` |
| `[x]` | Write the P0 foundation design specification | `docs/specs/2026-08-23-p0-foundation-design.md` |
| `[~]` | User review of the P0 specification | Current gate |
| `[ ]` | Write the P0 implementation plan and task docs | Blocked on the review above |

## Phase 1: P0 foundation build

Not started. Every item below is blocked on the specification review.

| | Item |
| --- | --- |
| `[ ]` | Repository scaffold, Python packaging, linting, import linter rule, continuous integration |
| `[ ]` | `finops-core` domain entities and the eight ports |
| `[ ]` | Typed error taxonomy |
| `[ ]` | `FakeProvider` implementing every port |
| `[ ]` | Port contract test suite |
| `[ ]` | PostgreSQL schema and migrations |
| `[ ]` | Terraform: management account organization reader role |
| `[ ]` | Terraform: member account StackSet for the collector role |
| `[ ]` | Terraform: hub stack |
| `[ ]` | AWS `CredentialBroker` adapter |
| `[ ]` | AWS `AccountDiscovery` adapter |
| `[ ]` | Ingestion framework: dispatcher, worker, run ledger, watermarks |
| `[ ]` | Collector: organization tree |
| `[ ]` | Collector: account role health |
| `[ ]` | Collector: platform self cost |
| `[ ]` | Identity and entitlement ports with the local configuration provider |
| `[ ]` | Scope dependency and repository guard, with the adversarial test |
| `[ ]` | FastAPI routes |
| `[ ]` | Frontend shell and navigation |
| `[ ]` | Frontend: accounts screen |
| `[ ]` | Frontend: organization map, tree and graph views |
| `[ ]` | Frontend: ingest and freshness screen |
| `[ ]` | Frontend: platform cost screen |
| `[ ]` | End to end test, login through to the organization map |

## Remaining sub projects

See `docs/01-ROADMAP.md` for scope. None have a specification yet.

| Sub project | Status |
| --- | --- |
| P2 Query Cost Governance | Not started, next after P0 |
| P1 Cost Intelligence | Not started |
| P3 Utilization and Rightsizing | Not started |
| P4 Inventory and Topology | Not started |
| P5 Quotas and Limits | Not started |
| P6 Containers, EKS and ECS | Not started |
| P7 Insight and LLM layer | Not started |

## External dependencies

These are not engineering work and cannot be unblocked from inside the
repository. Tracked in `tasks/ISSUES.md`.

| | Dependency | Tracker |
| --- | --- | --- |
| `[ ]` | Management account: enable trusted access between Organizations and CloudFormation | ISS-002 |
| `[ ]` | Management account: deploy the organization reader role | ISS-002 |
| `[ ]` | Enable Data Exports CUR 2.0 with resource identifiers and split cost allocation data | ISS-003 |
| `[ ]` | Opt in to Compute Optimizer at organization level | ISS-004 |
| `[ ]` | Confirm the identity provider approach | OPEN-01 |
