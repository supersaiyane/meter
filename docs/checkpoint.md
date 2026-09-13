# Checkpoint log

Session continuity. One entry per completed task. A resume vector must be
precise enough that a cold session can continue without re reading the project.

Update trigger: end of every completed task.
Archive rule: at 50 entries, move the oldest 30 to
`docs/checkpoint_archive.md` and keep the latest 20 here.

| Date and time | Task | Status | What changed | Resume vector |
| --- | --- | --- | --- | --- |
| 2026-08-23 | Review the existing Grafana audit prototype from `publicsampledashboard.zip` | Done | No repository change. Findings recorded as ISS-020 through ISS-027 | `tasks/ISSUES.md`, section "Existing Grafana prototype". Source is `sample_lambda.py`, 2,740 lines, in the user's Downloads folder |
| 2026-08-23 | Requirement review across all nine requested areas, and decomposition into eight sub projects | Done | No repository change. Recorded as ADR-0001 and the roadmap | `docs/01-ROADMAP.md`, `docs/adr/ADR-0001-decompose-into-sub-projects.md` |
| 2026-08-23 | Confirm scale, stack, runtime and infrastructure as code | Done | Medium scale, Python and FastAPI, React and TypeScript, ECS Fargate, Terraform | `docs/02-ARCHITECTURE.md`, section "Confirmed technology choices" |
| 2026-08-23 | Park the authentication decision | Done | Recorded as OPEN-01 and ADR-0008. Isolated behind `IdentityProvider` and `EntitlementResolver` | `tasks/ISSUES.md` OPEN-01, `docs/adr/ADR-0008-identity-adapter-deferred.md` |
| 2026-08-23 | Initialize the repository and the documentation spine | Done | Created `.gitignore`, `README.md`, `CLAUDE.md`, `docs/`, `tasks/`, `context_index.md`. Eight ADRs. P0 specification written | Next action is user review of `docs/specs/2026-08-23-p0-foundation-design.md`. On approval, write `docs/plans/P0-implementation-plan.md` |
| 2026-08-23 | Commit the documentation spine as six granular commits | Done | Commits `e604ea9` chore init, `500d003` goal and roadmap and architecture, `3cd4851` eight ADRs, `c1daff8` P0 specification, `4b71590` status and issues and lessons, `6e2afcc` project map and context index. Em dash scan clean across files and commit messages | `git log --oneline` on branch `main`. Working tree clean at `6e2afcc` |
| 2026-08-23 | Relocate the checkpoint log and project map to the paths the enforcement hook expects | Done | `init_docs/project_map.md` moved to `project_map.md` at repository root. `init_docs/checkpoint.md` moved to `docs/checkpoint.md`. `init_docs/` removed. All references repointed in `README.md` line 30 to 40, `CLAUDE.md` line 30 to 45, `project_map.md` line 18 to 50 | Canonical paths are now `project_map.md` at root and `docs/checkpoint.md`. The kernel default of `init_docs/` is not used in this repository, because `~/.claude/scripts/hooks/enforce-checkpoint.js` enforces the other two paths |
| 2026-08-23 | Add the build and deployment layer | Done | `Makefile` with 28 targets, `docker/Dockerfile.api`, `Dockerfile.worker`, `Dockerfile.web`, `docker/nginx.conf`, `docker-compose.yml`, `.gitlab-ci.yml`, `pyproject.toml`, `.dockerignore`, `docs/04-DEPLOYMENT.md`, `scripts/run_migration_task.sh` | `make help` lists all targets. Nothing builds until P0 code exists, which is deliberate: the deployment contract is fixed before the code. Tracked as CHG-0003 |
| 2026-08-23 | Add the master index and the change control process | Done | `INDEX.md` with 41 features, 8 ADRs, 5 changes, 32 issues, 6 open questions. `docs/03-CHANGE-CONTROL.md` with the routing rule and the anti hallucination contract. Five templates in `docs/templates/`. `scripts/check_index.py` enforcing consistency | `make check-docs` passes, 24 references checked. Tracked as CHG-0004 |
| 2026-08-23 | Write the P0 implementation plan | Done | `docs/plans/P0-implementation-plan.md`, 28 tasks across 8 waves. Every task carries implements, files, acceptance criteria, named tests, depends on, do not, and evidence | Provisional until the P0 specification is approved. Tracked as CHG-0005 |
| 2026-08-23 | Answer whether MCP replaces the HTTP API | Done | ADR-0009. Both. The HTTP API stays the single enforcement point, the MCP server is a facade calling it over the network with the caller's token. Four P0 tools. FEAT-042 assistant bot added | `docs/adr/ADR-0009-mcp-alongside-http-api.md`, P0 spec section 8.0 |
| 2026-08-23 | Rebase every image on Minimus and establish a zero vulnerability posture | Done | ADR-0010. Three Dockerfiles rewritten against `reg.mini.dev`. Runtime images have no shell, so exec form only and health checking moved to the ALB. `--no-compile` keeps bytecode out. `security/` created with policy, allowlist, SBOM and report directories. Seven scanners. `docs/05-SECURITY.md` | `docker/`, `security/`, `docs/05-SECURITY.md`. ISS-033 to ISS-036, ISS-039 to ISS-041 |
| 2026-08-23 | Build the security tooling | Done | `scripts/security/scan.sh`, `check_dependency.sh`, `validate_allowlist.py`, `report.py`, `autofix.py`. Report generator verified against sample grype and trivy output, cross scanner dedup confirmed. Auto fix verified in dry run, classification confirmed | `scripts/security/`, `make security-scan`, `make dep-check`, `make security-fix` |
| 2026-08-23 | Adopt the ponytail and caveman ground rules | Done | ADR-0011. Six rung decision ladder before any new code, output discipline, automated code review and generated documentation as pipeline stages | `docs/adr/ADR-0011-minimal-code-decision-ladder.md`, `CLAUDE.md` section "Before writing any new code" |
| 2026-08-23 | Document every feature and build the file graph | Done | 42 feature documents, 10 full for P0 and 32 planned. `scripts/docs/check_feature_docs.py` enforces both directions. `scripts/docs/build_file_graph.py` builds a Mermaid and an interactive graph from Python, TypeScript, Terraform and Dockerfile edges, and fails on a layering violation | `docs/features/`, `docs/architecture/file-graph.md`, `make graph`. ISS-042, ISS-043 |
| 2026-08-23 | Decide refresh cadence | Done | ADR-0012. Cadence is a row in `collector_schedule` with its reason and cost, not a constant. Grafana audit at 6 hours as requested, kill switch event driven because a 6 hour gap on the original failure is still roughly 25,000 USD. Two timestamps on every figure | `docs/06-DATA-FRESHNESS.md`. ISS-037, ISS-038 |
| 2026-08-23 | Consolidate scripts and extend the P0 plan | Done | Every script under `scripts/` in four subdirectories with a README. P0 plan extended to 31 tasks, wave I added. TASK-P0-029 runs before everything else because it verifies the Minimus tags exist | `scripts/README.md`, `docs/plans/P0-implementation-plan.md`. ISS-044 |
| 2026-08-23 | Pin the image platform to linux/amd64 | Done | `FROM --platform` on every stage, `--platform` on every build command, `make verify-platform` after build and before push, and a registry manifest check in the pipeline. A push never converts an arm64 image, and the failure reads as `exec format error` | `docker/`, `Makefile` targets `build`, `verify-platform`, `buildx-setup`, `buildx-push`. ISS-047 |
| 2026-08-23 | Document the database schema | Done | `docs/07-DATA-MODEL.md`, 502 lines. Every table with its constraints, indexes, partitioning and the Alembic migration rules. Invariants are database constraints rather than conventions, because application code alone will eventually let a bad row through | `docs/07-DATA-MODEL.md`. ISS-048 |
| 2026-08-23 | Import the seven rung ladder from a prior project | Done | ADR-0013 supersedes the ladder in ADR-0011. Resolves the deadlock where ADR-0010 forbids a dependency and the ladder requires reusing it. Adds the disqualification record, the same rung check and the security sign off gate | `docs/adr/ADR-0013-seven-rung-ladder-and-disqualification.md`. Source: `PayVault/.kiro/reference/ponytail-rung-disqualification-guide.md`. ISS-045 |
| 2026-08-23 | Make derived documentation generated | Done | `docs/registry.yaml` is now the single source of truth. `scripts/docs/sync.py` regenerates the index tables, the roadmap status, the status summary and every feature header. Feature status previously lived in four places by hand. Building the registry immediately found six change rows missing a column | `make doc-sync`, `make check-docs`, `make session-end`. ADR-0014. ISS-046, ISS-049 |
| 2026-08-23 | Session checkpoint before context limit | Done | No code written. 25 commits, all gates green: registry sync, index 79 references, 42 feature documents, 0 layering violations, no banned characters. `make check-writing` ran for the first time and correctly failed on `CLAUDE.md`, which quoted the banned characters inside its own rule. Fixed by referencing the Makefile target instead | Everything below under "Next action". The gate is unchanged: user review of the P0 specification |
| 2026-08-23 | Complete the security gate chain and explain LocalStack | Done | Found and closed a real gap: images were signed with cosign but the signature was never verified, so anyone able to push to ECR could place an unscanned image where the deploy would find it. Added `verify-provenance` before every deploy, checking the signature and the SBOM attestation. Added pre commit and pre push hooks, and a compose `security` profile of one shot scanners that does not start with `make up`. Documented LocalStack and its limits | `.gitlab-ci.yml` job `verify-provenance`, `.pre-commit-config.yaml`, `docker-compose.yml` security profile, `docs/05-SECURITY.md` six layer table. ISS-051 to ISS-054 |
| 2026-08-23 | Rewrite the README as the operational anchor | Done | 721 lines, 12 sections. Six layer gate model, LocalStack explained where a developer looks for it, and ten worked gotcha examples each showing real output and exact commands. The writing rules gotcha had to be rewritten after it failed the check by reproducing the banned characters, which is the second time that trap has been hit | `README.md`. CHG-0016, CHG-0018, CHG-0019 |
| 2026-08-23 | Publish AUDIT-001 and establish the audit process | Done | `audits/` created with a naming convention, `A<nnn>-F<nn>` finding identifiers, a promotion rule into the registry, and a cadence. 18 findings, 1 critical, 5 high, 8 medium, 4 low. Verdict PROCEED WITH CONDITIONS. Every finding carries a reproducible command or a file and line | `audits/README.md`, `audits/AUDIT-001-2026-08-23-full-project.md`. CHG-0020 |
| 2026-08-23 | Close eleven findings, remediation wave one | Done | `finops_mcp` brought under an import linter contract, gitleaks added to the CI tool anchor, `setup` now installs the scanners, `local-auth.example.yaml` committed, CODEOWNERS and SECURITY.md and .editorconfig added, MCP packaged as a second process in the api image, `PARTIAL` defined, the dead HTML graph removed, the context index generator written, the duplicated roadmap table generated | `audits/REMEDIATION-LOG.md`. CHG-0021, commit `ef23f8a` |
| 2026-08-23 | Close the two blocking findings | Done | `docs/08-THREAT-MODEL.md`, STRIDE across six trust boundaries with five residual risks tracked as ISS-073 to ISS-077. `docs/09-DATA-CLASSIFICATION.md`, every table classified with retention, erasure and five enforcement jobs. It produced a schema change: `cloud_account.email` removed, because the account root email is personal data no feature reads | CHG-0022, commit `3a16bd0`. TASK-P0-032 added for retention |
| 2026-08-23 | Close the final five findings | Done | Disaster recovery in the architecture, observability as `docs/10-OBSERVABILITY.md`, the running cost estimate in the deployment guide, exit criteria in the roadmap, and the performance budget as P0 spec section 11b. Writing the cost estimate found a real error in prior work, ISS-080: the VPC endpoints were justified on cost and NAT is cheaper below roughly 1,560 GB per month. Reasoning corrected, conclusion kept on security grounds | CHG-0023, commit `6cceaa8`. TASK-P0-033 added for SLOs |

## Next action

**Blocked on user review of the P0 foundation specification.** Nothing else
should start until it is approved, because every other sub project depends on
P0.

### Source of truth, in order

| Question | Document |
| --- | --- |
| Anything at all, start here | `INDEX.md` |
| Feature, decision, change, issue or open question status | `docs/registry.yaml`. Everything else derives from it |
| Why a decision was made | `docs/adr/`, 14 records |
| What P0 delivers | `docs/specs/2026-08-23-p0-foundation-design.md` |
| What to build, in order | `docs/plans/P0-implementation-plan.md`, 31 tasks |
| The database | `docs/07-DATA-MODEL.md` |
| Security policy and posture | `docs/05-SECURITY.md`, `security/POSTURE.md` |
| Refresh cadence | `docs/06-DATA-FRESHNESS.md` |
| Deployment | `docs/04-DEPLOYMENT.md` |
| Where a change gets recorded | `docs/03-CHANGE-CONTROL.md` |
| Rules binding every change | `CLAUDE.md` |

### Resume vector, as of 2026-09-12

| What | Where |
| --- | --- |
| Git position | branch `main`, 43 commits, working tree clean |
| The gate, unchanged | User review of `docs/specs/2026-08-23-p0-foundation-design.md` |
| **First task on approval** | `docs/plans/P0-implementation-plan.md`, **TASK-P0-029**, not 001. It verifies the Minimus tags exist and every declared dependency passes the admission gate |
| Plan size | 33 tasks in 9 waves. 032 retention and erasure, 033 SLOs and runbooks, both added by the audit |
| Registers | 42 features, 14 decisions, 23 changes, 77 issues, 6 open questions |
| Audit state | AUDIT-001, all 18 findings FIXED. `audits/REMEDIATION-LOG.md` carries every transition with the command that verified it |
| Issues still OPEN | 21, none from AUDIT-001. Five threat model residual risks, two data protection questions needing a person, and pre existing P1 to P7 items |
| Needs a person, not an engineer | ISS-078, whether a regulatory floor exceeds the 37 month cost retention. ISS-079, sign off on the `audit_event` non erasure position |
| Check everything | `make check-docs && make check-writing` |
| End a session | `make session-end` |
| Next audit due | At the P0 boundary, scope `code`, per `audits/README.md` cadence |

### Earlier resume vector, as of 2026-09-02

| What | Where |
| --- | --- |
| Git position | branch `main`, 33 commits, working tree clean |
| The gate, unchanged | User review of `docs/specs/2026-08-23-p0-foundation-design.md` |
| First task to run on approval | `docs/plans/P0-implementation-plan.md`, **TASK-P0-029**, not 001. It verifies the Minimus tags exist |
| Registers | 42 features, 14 decisions, 19 changes, 51 issues, 6 open questions |
| One command to check everything | `make check-docs && make check-writing` |
| One command to end a session | `make session-end` |
| Known open items needing code | ISS-054, set ECR tags to IMMUTABLE, in TASK-P0-016 |

### Earlier resume vector

| What | Where |
| --- | --- |
| The document awaiting review | `docs/specs/2026-08-23-p0-foundation-design.md`, all 13 sections |
| The two sections most likely to need change | Section 5, data model, lines covering `cloud_account` and `org_node`. Section 8, API surface |
| Current position and open items | `tasks/STATUS.md`, phase 0 table. 9 done, 1 in progress, 1 blocked |
| Decisions already fixed, do not relitigate | `docs/adr/`, records 0001 to 0008 |
| Undecided items awaiting the user | `tasks/ISSUES.md`, open questions table, OPEN-01 through OPEN-06 |
| Binding rules for any change | `CLAUDE.md`, sections "Writing rules", "Definition of done", "Architectural constraints" |
| Git position | branch `main`, working tree clean |
| The task list to execute | `docs/plans/P0-implementation-plan.md`, TASK-P0-001 through TASK-P0-028 |
| How to run anything | `make help`. `make verify` is the merge request gate |
| Where a change gets recorded | `docs/03-CHANGE-CONTROL.md`, the routing rule table |
| Start here for anything | `INDEX.md`, 12 sections, 75 checked references |
| What every feature does | `docs/features/`, 42 documents |
| The security policy and the current posture | `docs/05-SECURITY.md`, `security/POSTURE.md` |
| How often data refreshes and why | `docs/06-DATA-FRESHNESS.md`, ADR-0012 |
| The first task to run | TASK-P0-029, before TASK-P0-001, because it verifies the Minimus tags exist |
| The database schema | `docs/07-DATA-MODEL.md`, and Alembic is the only way it changes |
| Where a status changes | `docs/registry.yaml`, then `make doc-sync`. Never in four places by hand |
| The reuse ladder | ADR-0013, seven rungs with a disqualification protocol |

### On approval, the next task

Execute `docs/plans/P0-implementation-plan.md`, starting with **TASK-P0-029**,
not TASK-P0-001. It verifies that the Minimus tags this project depends on
actually exist and that every declared dependency passes the admission gate.
Discovering at task 016 that a base image does not exist would invalidate three
Dockerfiles and a pipeline.

Then TASK-P0-001 onward. Waves A and D
are independent of waves B and C, so two people can work in parallel. One task,
one commit, and the commit body names the task identifier.

Before starting any task, read its **Do not** list. It names the plausible
mistake available at that task, which is the field that prevents the most
defects.

If reality does not match the specification, stop. Raise an `ISS-nnn` row, fix
the specification, add a `CHG-nnnn` row, update `INDEX.md`, then continue.
Working around a wrong specification produces code nobody can review.

### If the user asks to change direction instead

The decomposition itself is ADR-0001. Changing the build order means
superseding that record, not editing it, and updating the status table in
`docs/01-ROADMAP.md`.
