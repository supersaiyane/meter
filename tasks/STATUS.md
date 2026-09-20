# Status

<!-- Basic boiler Plate Doc | Grade B
     Why this file exists: What is done and what is left, updated at the end of every working
     session.
     Grade B here: copy it, then replace all of the content. Keep the shape and the update trigger.
     Grades: A copy into a new project as is, no edits. B copy it and swap the
     names, paths or patterns named above. C leave behind, it is this project's
     own content rather than scaffolding, and is not tagged.
-->

Last updated: 2026-09-19
Update trigger: end of every work session
Master index: `INDEX.md`

Legend: `[x]` done, `[~]` in progress, `[ ]` not started, `[!]` blocked.

## Registers at a glance

<!-- generated:status-summary start -->
<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. Edit docs/registry.yaml, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

| Register | Counts |
| --- | --- |
| Features | 51 total, 9 specified, 10 in build, 5 delivered |
| Decisions | 21 architecture decision records |
| Changes | 90 recorded |
| Issues | 124 fixed, 55 open, 0 parked |
| Open questions | 9 awaiting a decision |

Generated from `docs/registry.yaml`. Change a status there, then run `make doc-sync`.

<!-- generated:status-summary end -->

## Where the project stands right now

**P0 is code complete and is NOT signed off.**

All 39 tasks are written, tested and committed. `make verify` passes: lint, the
writing rules, the eight documentation checks, the docstring gate, the memory
gate, 898 backend tests, 249 frontend tests, a typed web build, 6 Playwright
journeys, and a security scan with zero unresolved findings and five accepted
as unfixable.

The gate ran 545 of those backend tests until 2026-09-06, the subset that needs
no services. The other 211 are where ISS-175 and ISS-177 both lived, the same
bug on two tables. `make verify` now runs every one of them and therefore needs
Docker, because the database fixture starts a PostgreSQL container. ISS-154.

Lint and type checking cover every directory that holds Python, which is 181
files under mypy where it was 25. `scripts/`, `migrations/` and the test suite
had all been outside one or both.

**P1's cost surface is 13 of 13 done.** Ingest to two screens, against a fake
export. `/cost` and `/cost/allocation` read live data on a seeded estate, and
the navigation group's other three screens still say which sub project brings
them. Anomalies, commitments and the chargeback export are a deliberate second
cut, named in section 3 of the specification with a reason for each.

Two gaps inside it are recorded rather than hidden. The collector reads only the
latest billing period, so a restated closed month is never picked up, ISS-183,
and the seed works around it by ingesting each period itself. The Athena adapter
buffers a whole period, and that ceiling is unmeasured because nothing has run
against a real export, ISS-181.

**P2 is 21 of 26 done, 2 parked, 2 descoped, 1 not started.**

TASK-P2-026 was added late, after the restored prototype was read against what P2 delivered. Ad hoc query detection was in that prototype, reached neither the specification nor the code, and was brought into scope rather than left as ISS-171. It was small, exactly as predicted: the evidence the measured overlay already collects contained it. It is done, and FEAT-051 is live at `/governance/adhoc`.

The backend is complete through wave J. The collector runs, prices what it
reads, measures what it can observe, and attributes an owner. Six of the eight
routes in spec section 8.2 exist and are live; the other two read data that
does not exist yet and are held under ISS-148, which names what each one waits
on. One task has not started: TASK-P2-020, which needs real CUR data and so
cannot be started from inside this repository.

**The interface is built and every screen has been through a pass.** Ten screens
read live data against a seeded local estate, and each has been opened at 1440
px and corrected. That pass found fourteen defects, none of which any test could
see, and the rule it produced is in `tasks/lessons.md`: a route that has never
been called is not evidence. The remaining screens are unbuilt and each one
names the sub project that will fill it, which is what makes the front page the
progress view.

What the sentences above do not cover is the part that matters for a sign off.

**Nothing has ever run in CI either.** The repository has no git remote, so
`.gitlab-ci.yml` has never executed, and every statement anywhere in this
repository about what the pipeline does is a reading of the file rather than a
result. Found 2026-09-06, by asking what a variable in the test job was for:
the answer was nothing, and the job as written could not have run an
integration test at all. ISS-178 fixed the job, ISS-179 records that the first
push will be the first run and should be watched rather than trusted.

**Nothing has ever run against AWS.** The three Terraform stacks pass `validate`
and `fmt`, which checks syntax, provider schema and references, and checks
nothing about whether the stack builds. No plan has been produced and nothing
has been applied. ISS-122. This is also what keeps TASK-P2-016 parked, and
TASK-P2-016 is what two of the five missing routes wait on.

**The restore drill is performed except for its first step.** `make
restore-drill` restores a copy into a scratch database, runs the migrations to
head, starts the application against it and reads the freshness route, and it
has been run against a real restore. Restoring from an Aurora snapshot has not
been done, because there is no account. ISS-111 is now that one link rather
than the whole chain, and `docs/runbooks/restore.md` is the procedure.

Both are open and both are acceptance criteria. P0 is not done until they are
closed, and calling it done before then would be exactly the kind of claim this
project's verification rule exists to prevent: reading the code back is not
evidence.

Three external dependencies remain and none can be unblocked from inside the
repository. Trusted access between Organizations and CloudFormation, the
management account role deployment, and CUR 2.0. All three are ISS-002 and
ISS-003.

## Tasks

<!-- generated:task-status start -->
<!-- This block is GENERATED from docs/plans/ by scripts/docs/sync.py. Edit docs/plans/, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

| Sub project | Done | Partly | Parked | Descoped | Not started | Total | Plan |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P0 | 39 | 0 | 0 | 0 | 0 | 39 | [plan](../docs/plans/P0-implementation-plan.md) |
| P1 | 14 | 0 | 0 | 0 | 7 | 21 | [plan](../docs/plans/P1-implementation-plan.md) |
| P2 | 21 | 0 | 2 | 2 | 1 | 26 | [plan](../docs/plans/P2-implementation-plan.md) |

**P0, not in the default state**

| Task | Status | Title |
| --- | --- | --- |
| `TASK-P0-001` | **Done 2026-10-07** | create the Python workspace and quality gates |
| `TASK-P0-002` | Done, 2026-08-27 | add the frontend workspace |
| `TASK-P0-003` | Done, 2026-08-27 | add the index consistency checker |
| `TASK-P0-004` | Done, 2026-08-27 | add the CI pipeline gate and pre commit configuration |
| `TASK-P0-034` | Done, 2026-08-24 | settings object, feature flags and the no hardcoding gate |
| `TASK-P0-005` | Done, 2026-08-24 | define the typed error taxonomy |
| `TASK-P0-006` | Done, 2026-08-24 | define the domain entities |
| `TASK-P0-007` | Done, 2026-08-24 | define the eight ports |
| `TASK-P0-008` | Done, 2026-08-24 | implement the fake provider |
| `TASK-P0-009` | Done, 2026-08-24 | write the port contract test suite |
| `TASK-P0-010` | Done, 2026-08-24 | create the database schema and migrations |
| `TASK-P0-011` | Done, 2026-08-24 | implement repositories with the scope guard |
| `TASK-P0-012` | Done, 2026-08-24 | implement the identity ports with the local provider |
| `TASK-P0-013` | Done, 2026-08-29, not applied | Terraform for the management account role |
| `TASK-P0-014` | Done, 2026-08-29, not applied | Terraform for the member account StackSet |
| `TASK-P0-015` | Done, 2026-08-29, not applied | Terraform for the hub network and data layer |
| `TASK-P0-016` | Done, 2026-08-29, not applied | Terraform for ECS, ALB and ECR |
| `TASK-P0-017` | Done, 2026-08-24 | implement the AWS credential broker |
| `TASK-P0-018` | Done, 2026-08-24 | implement AWS account discovery |
| `TASK-P0-019` | Done, 2026-08-24 | implement the account health check |
| `TASK-P0-020` | Done, 2026-08-24 | implement the run ledger and watermarks |
| `TASK-P0-021` | Done, 2026-08-24 | implement the dispatcher and worker |
| `TASK-P0-022` | Done, 2026-08-24 | implement the organization tree and account health collectors |
| `TASK-P0-023` | Done, 2026-08-27 | implement the platform self cost collector |
| `TASK-P0-024` | Done, 2026-08-27 | implement the FastAPI application and scope dependency |
| `TASK-P0-025` | Done, 2026-08-27 | implement the P0 routes |
| `TASK-P0-035` | Done, 2026-08-27 | the component layer and the visual honesty system |
| `TASK-P0-026` | Done, 2026-08-27 | application shell, coverage banner and freshness indicator |
| `TASK-P0-027` | Done, 2026-08-27 | accounts screen and organization map |
| `TASK-P0-028` | Done, 2026-08-27, with one criterion not performed | ingest, freshness and platform cost screens, plus the end to end journey |
| `TASK-P0-032` | Done, 2026-08-27, with one criterion deferred to TASK-P0-015 | retention jobs and the erasure script |
| `TASK-P0-036` | Done, 2026-09-07 | routing, the seven groups, and the route migration |
| `TASK-P0-037` | Done, 2026-09-09 | the fixture seam and the fixture marker |
| `TASK-P0-038` | Done, 2026-09-11 | the home screen |
| `TASK-P0-039` | Done, 2026-09-21 | the visual layer |
| `TASK-P0-029` | **Done 2026-08-23**, commit `9754a59` | establish the security tool chain and the first posture |
| `TASK-P0-030` | Done, 2026-08-27 | MCP server scaffold and the four P0 tools |
| `TASK-P0-031` | Done, 2026-08-28 | wire the documentation and graph gates into the pipeline |
| `TASK-P0-033` | Done, 2026-08-29, not applied | SLOs, alerts and runbooks |

**P1, not in the default state**

| Task | Status | Title |
| --- | --- | --- |
| `TASK-P1-001` | Done, 2026-09-18 | the cost port and the types that carry a measure |
| `TASK-P1-002` | Done, 2026-09-18 | a fake estate with a bill |
| `TASK-P1-003` | Done, 2026-09-18, and unproved by construction | the Athena adapter, written and unproved |
| `TASK-P1-004` | Done, 2026-09-18 | the collector, and what makes a line item itself |
| `TASK-P1-005` | Done, 2026-09-18 | retraction, which is the dangerous half |
| `TASK-P1-006` | Done, 2026-09-19 | the monthly rollup, derived and never ingested |
| `TASK-P1-007` | Done, 2026-09-19 | cadence, as data |
| `TASK-P1-008` | Done, 2026-09-19 | the guard, then the repository |
| `TASK-P1-009` | Done, 2026-09-19 | four routes |
| `TASK-P1-010` | Done, 2026-09-19 | the spend and trend screen |
| `TASK-P1-011` | Done, 2026-09-19 | the allocation screen and the bucket nobody wants |
| `TASK-P1-012` | Done, 2026-09-19 | the demo estate gets a bill |
| `TASK-P1-013` | Done, 2026-09-19, and unapplied by construction | the infrastructure that will not be applied |
| `TASK-P1-014` | Done, 2026-09-20 | a day that does not look like the days before it |

**P2, not in the default state**

| Task | Status | Title |
| --- | --- | --- |
| `TASK-P2-001` | Done, 2026-09-02 | import the prototype and pin its behaviour |
| `TASK-P2-002` | Done, 2026-09-03 | extract the cost model under the golden files |
| `TASK-P2-003` | Done, 2026-09-04 | decompose the remainder and delete the legacy copy |
| `TASK-P2-004` | Done, 2026-09-05 | define the QuerySurface port |
| `TASK-P2-005` | Done, 2026-09-23 | the fake Grafana surface |
| `TASK-P2-006` | Done, 2026-09-24 | the AMG connection strategy |
| `TASK-P2-007` | Descoped, 2026-09-02 | the self hosted connection strategy |
| `TASK-P2-008` | Descoped, 2026-09-02 | the Grafana Cloud connection strategy |
| `TASK-P2-009` | Done, 2026-08-30 | the six P2 tables |
| `TASK-P2-010` | Done, 2026-08-31 | the query audit collector |
| `TASK-P2-011` | Done, 2026-09-01 | fingerprinting and template variables |
| `TASK-P2-012` | Done, 2026-09-14 | severity, ranking and grouping |
| `TASK-P2-013` | Done, 2026-09-05 | the measured overlay |
| `TASK-P2-014` | Done, 2026-09-06 | owner attribution |
| `TASK-P2-015` | Parked, 2026-08-29 | detection and alerting |
| `TASK-P2-016` | Parked, 2026-08-29 | throttle and deny, with the guardrails |
| `TASK-P2-017` | Done, 2026-09-14, the AMG write refuses. ISS-166 | the workspace refresh floor |
| `TASK-P2-018` | Done, 2026-09-15 | the CI policy gate |
| `TASK-P2-019` | Done, 2026-09-16, short on the notification. ISS-167 | panel rewrite with undo |
| `TASK-P2-021` | Done, 2026-09-08, short on two criteria. ISS-148 | routes and MCP tools |
| `TASK-P2-022` | Done, 2026-09-13 | the query findings screen |
| `TASK-P2-023` | Done, 2026-09-15 | the finding detail screen |
| `TASK-P2-024` | Done, 2026-09-17 | the query surfaces screen |
| `TASK-P2-025` | Done, 2026-09-05 | the enforcement screen and the end to end journey |
| `TASK-P2-026` | Done, 2026-09-06 | the queries that belong to nobody |

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
| `[x]` | TASK-P0-009, the port contract suite | One suite over all providers. Error type parity asserted. Wave B complete |
| `[x]` | TASK-P0-010, the schema and initial migration | Thirteen tables, invariants as constraints, proved on postgres 16 |
| `[x]` | TASK-P0-011, repositories with the scope guard | No unscoped path exists. Every read audited. ISS-109 closed |
| `[x]` | TASK-P0-012, identity ports and the local provider | Signed sessions, cache always expires, coverage over the real total. Wave C complete |
| `[x]` | TASK-P0-017, the AWS credential broker | Bounded retries, refresh before expiry, every code mapped to a typed cause |
| `[x]` | TASK-P0-018, AWS account discovery | The exact tree, every call paginated, no account dropped |
| `[x]` | TASK-P0-019, the account health check | NOT_DEPLOYED and ACCESS_DENIED kept apart by evidence, not a guess. Wave E complete |
| `[x]` | TASK-P0-020, the run ledger and watermarks | Idempotent claims, forward only watermarks, uniqueness scoped per tenant |
| `[x]` | TASK-P0-021, the dispatcher and worker | One transaction per unit. Only the six caught. Both section 11 tests pass |
| `[x]` | TASK-P0-022, the tree and account health collectors | Tree replaced in one transaction, departed accounts marked, cadence seeded |
| `[x]` | TASK-P0-023, the platform self cost collector | One grouped request a day, untagged cost named, metering charge owned. Wave F complete |
| `[x]` | TASK-P0-024, the application and scope dependency | Meta envelope enforced at startup. The adversarial leak test passes |
| `[x]` | TASK-P0-025, the seven P0 routes | Unreachable branches marked, typed errors with remediation. Wave G complete |
| `[x]` | TASK-P0-002, the frontend workspace | Builds, lints and tests. Flat eslint config, TypeScript pinned below 6 |
| `[x]` | TASK-P0-035, the component layer and visual honesty system | A number reaches a user only through Figure. No formatter is exported |
| `[x]` | TASK-P0-026, the application shell | Coverage and freshness page level and worst case. Client refuses a bare response |
| `[x]` | TASK-P0-027, accounts screen and organization map | Broken onboarding one click. Tree default. Unreachable branches drawn |
| `[x]` | TASK-P0-003 and 004, index checker tests and the pipeline gate | Failure paths tested. Dash rejection demonstrated. Wave A complete |
| `[~]` | TASK-P0-028, the last screens, journey and budgets | Screens and budgets done. Restore drill not performed, ISS-111 |
| `[x]` | Architect the interface | `docs/13-UI-ARCHITECTURE.md`, ADR-0020. Seven fixed navigation groups, every route, the home screen, and 25 screens mapped across P0 to P7. The visual system had no frame to hang screens on |
| `[x]` | Plan the interface | Seven tasks. Three in the P0 plan for routing, the fixture seam and the home screen, four in the P2 plan replacing the single screens task. Wave K does not wait for wave J |

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
