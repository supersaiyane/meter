# Status

Last updated: 2026-08-23
Update trigger: end of every work session
Master index: `INDEX.md`

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
| `[x]` | Write the master index | `INDEX.md`, 41 features, 8 ADRs, 5 changes, 32 issues, 6 open questions |
| `[x]` | Write the change control process | `docs/03-CHANGE-CONTROL.md`, routing rule plus the anti hallucination contract |
| `[x]` | Write five document templates | `docs/templates/` |
| `[x]` | Build layer: Makefile, three Dockerfiles, compose, nginx | 28 make targets, all parse |
| `[x]` | Deployment: GitLab pipeline and deployment document | `.gitlab-ci.yml`, `docs/04-DEPLOYMENT.md` |
| `[x]` | Index consistency checker and migration runner | `scripts/check_index.py` passes, `scripts/run_migration_task.sh` |
| `[x]` | Write the P0 implementation plan | `docs/plans/P0-implementation-plan.md`, 28 tasks in 8 waves |
| `[~]` | User review of the P0 specification | Current gate. The plan is provisional until it passes |

## Phase 1: P0 foundation build

Not started. Every item is blocked on the specification review.

The authoritative task list is `docs/plans/P0-implementation-plan.md`, which
carries acceptance criteria, named tests, and a "do not" list per task. The
table below is the summary view only.

| | Item | Task |
| --- | --- |
| `[ ]` | Repository scaffold, Python packaging, linting, import linter rule, continuous integration | TASK-P0-001, 004 |
| `[ ]` | `finops-core` domain entities and the eight ports | TASK-P0-006, 007 |
| `[ ]` | Typed error taxonomy | TASK-P0-005 |
| `[ ]` | `FakeProvider` implementing every port | TASK-P0-008 |
| `[ ]` | Port contract test suite | TASK-P0-009 |
| `[ ]` | PostgreSQL schema and migrations | TASK-P0-010 |
| `[ ]` | Terraform: management account organization reader role | TASK-P0-013 |
| `[ ]` | Terraform: member account StackSet for the collector role | TASK-P0-014 |
| `[ ]` | Terraform: hub stack | TASK-P0-015, 016 |
| `[ ]` | AWS `CredentialBroker` adapter | TASK-P0-017 |
| `[ ]` | AWS `AccountDiscovery` adapter | TASK-P0-018, 019 |
| `[ ]` | Ingestion framework: dispatcher, worker, run ledger, watermarks | TASK-P0-020, 021 |
| `[ ]` | Collector: organization tree | TASK-P0-022 |
| `[ ]` | Collector: account role health | TASK-P0-022 |
| `[ ]` | Collector: platform self cost | TASK-P0-023 |
| `[ ]` | Identity and entitlement ports with the local configuration provider | TASK-P0-012 |
| `[ ]` | Scope dependency and repository guard, with the adversarial test | TASK-P0-011, 024 |
| `[ ]` | FastAPI routes | TASK-P0-025 |
| `[ ]` | Frontend shell and navigation | TASK-P0-002, 026 |
| `[ ]` | Frontend: accounts screen | TASK-P0-027 |
| `[ ]` | Frontend: organization map, tree and graph views | TASK-P0-027 |
| `[ ]` | Frontend: ingest and freshness screen | TASK-P0-028 |
| `[ ]` | Frontend: platform cost screen | TASK-P0-028 |
| `[ ]` | End to end test, login through to the organization map | TASK-P0-028 |

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
