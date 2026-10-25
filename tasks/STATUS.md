# Status

<!-- Basic boiler Plate Doc | Grade B
     Why this file exists: What is done and what is left, updated at the end of every working
     session.
     Grade B here: copy it, then replace all of the content. Keep the shape and the update trigger.
     Grades: A copy into a new project as is, no edits. B copy it and swap the
     names, paths or patterns named above. C leave behind, it is this project's
     own content rather than scaffolding, and is not tagged.
-->

Last updated: 2026-08-24
Update trigger: end of every work session
Master index: `INDEX.md`

Legend: `[x]` done, `[~]` in progress, `[ ]` not started, `[!]` blocked.

## Registers at a glance

<!-- generated:status-summary start -->
<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. Edit docs/registry.yaml, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

| Register | Counts |
| --- | --- |
| Features | 50 total, 16 specified, 4 in build, 0 delivered |
| Decisions | 19 architecture decision records |
| Changes | 40 recorded |
| Issues | 73 fixed, 35 open, 0 parked |
| Open questions | 6 awaiting a decision |

Generated from `docs/registry.yaml`. Change a status there, then run `make doc-sync`.

<!-- generated:status-summary end -->

## Where the project stands right now

**P0 specification approved. P0 is in build.**

No application code exists yet. What exists is a verified toolchain, base
images pinned by digest and chosen by measurement, a corrected security policy
with a real posture, and a designed interface.

The next task is TASK-P0-001, which is partly done: the Python packages and the
virtualenv exist because TASK-P0-029 needed them, and the editable install, the
pytest harness and `conftest.py` do not.

## Tasks

<!-- generated:task-status start -->
<!-- This block is GENERATED from docs/plans/ by scripts/docs/sync.py. Edit docs/plans/, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

| Sub project | Done | Partly | Not started | Total | Plan |
| --- | --- | --- | --- | --- | --- |
| P0 | 7 | 0 | 28 | 35 | [plan](../docs/plans/P0-implementation-plan.md) |
| P2 | 0 | 0 | 22 | 22 | [plan](../docs/plans/P2-implementation-plan.md) |

**P0, not in the default state**

| Task | Status | Title |
| --- | --- | --- |
| `TASK-P0-001` | **Done 2026-10-07** | create the Python workspace and quality gates |
| `TASK-P0-034` | Done, 2026-08-24 | settings object, feature flags and the no hardcoding gate |
| `TASK-P0-005` | Done, 2026-08-24 | define the typed error taxonomy |
| `TASK-P0-006` | Done, 2026-08-24 | define the domain entities |
| `TASK-P0-007` | Done, 2026-08-24 | define the eight ports |
| `TASK-P0-008` | Done, 2026-08-24 | implement the fake provider |
| `TASK-P0-029` | **Done 2026-08-23**, commit `9754a59` | establish the security tool chain and the first posture |

<!-- generated:task-status end -->

Read from the plan files, not maintained here. This section used to be a hand
kept second copy of the task list, and it had already drifted: it showed 31
tasks and TASK-P0-029 as not started after it was finished. See ADR-0014.

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
| `[x]` | Answer whether MCP replaces the HTTP API | ADR-0009. Both, MCP is a facade over the API |
| `[x]` | Rebase all images on Minimus for a zero CVE posture | ADR-0010, three Dockerfiles rewritten |
| `[x]` | Security folder, seven scanners, policy and allowlist | `security/`, `docs/05-SECURITY.md` |
| `[x]` | Dependency admission gate | `make dep-check`, plus a pipeline job on any manifest change |
| `[x]` | HTML vulnerability report with suggested fixes | `scripts/security/report.py`, verified against sample scanner output |
| `[x]` | Branch scoped auto fix, gated on the full test suite | `scripts/security/autofix.py`, verified in dry run |
| `[x]` | Nightly posture scan of the running digest | `.gitlab-ci.yml`, `nightly-posture-scan` |
| `[x]` | Adopt the decision ladder and output discipline | ADR-0011, `CLAUDE.md` |
| `[x]` | Automated code review as a pipeline stage | `scripts/ci/code_review.py`, `make review` |
| `[x]` | One document per feature | 42 documents in `docs/features/`, enforced by `check_feature_docs.py` |
| `[x]` | File dependency graph, with layering enforced | `make graph`, 16 files and 17 edges at present |
| `[x]` | Consolidate every script under `scripts/` | `scripts/README.md`, four subdirectories |
| `[x]` | Decide refresh cadence per collector | ADR-0012, `docs/06-DATA-FRESHNESS.md`. Grafana audit at 6 hours |
| `[x]` | Extend the P0 plan for security and MCP | 31 tasks. TASK-P0-029 runs first |
| `[x]` | Pin the image platform to linux/amd64 | Five controls, including a registry manifest check after push |
| `[x]` | Document the database schema and the Alembic rules | `docs/07-DATA-MODEL.md` |
| `[x]` | Import the seven rung ladder and disqualification protocol | ADR-0013, supersedes the ladder in ADR-0011 |
| `[x]` | Make derived documentation generated from a registry | ADR-0014, `make doc-sync`, `make session-end` |
| `[x]` | User review of the P0 specification | **Approved 2026-08-23** |
| `[x]` | Write the P2 specification and plan | 22 tasks in ten waves |
| `[x]` | Design the interface | `docs/12-UI-DESIGN.md`, ADR-0019. The honesty guarantees were enforced in the database and undesigned at the pixel |
| `[x]` | TASK-P0-029, verify the base images and establish the posture | Moved to python 3.13 and nginx 1.30 by measurement. ADR-0018 corrected the threshold |
| `[x]` | TASK-P0-005, the typed error taxonomy | Six causes, no catch all. Coverage gate restored to 80 |
| `[x]` | TASK-P0-034, settings object, constants and flag resolution | 46 variables typed, no defaults in code, startup refuses a bad configuration |
| `[x]` | TASK-P0-006, the domain entities | Frozen throughout, FOCUS names, no bare account identifier |
| `[x]` | TASK-P0-007, the eight ports | Protocols only. Every method documents which of the six causes it raises |
| `[x]` | TASK-P0-008, the fake provider | All eight ports in memory. Any of the six causes plannable per scope |

## Remaining sub projects

See `docs/01-ROADMAP.md` for scope. None have a specification yet.

| Sub project | Status |
| --- | --- |
| P2 Query Cost Governance | **Specified and planned.** Built after P0 |
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
| `[ ]` | Confirm single or multiple payer accounts | OPEN-02 |
| `[ ]` | Confirm the support tier for Trusted Advisor limit checks | OPEN-03 |
| `[ ]` | Confirm whether self hosted Grafana and Grafana Cloud are in scope | OPEN-04 |
| `[ ]` | Confirm the ticketing system for the recommendation lifecycle | OPEN-05 |
| `[ ]` | Confirm which regions beyond Ireland and London | OPEN-06 |
