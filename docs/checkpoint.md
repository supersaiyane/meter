# Checkpoint log

<!-- Basic boiler Plate Doc | Grade B
     Why this file exists: The session continuity log. One row per completed task, each carrying
     a resume vector precise enough that a cold session continues without re reading the
     project.
     Grade B here: copy it, then replace every row. The column set, the archive rule and the
     resume vector discipline are the asset.
     Grades: A copy into a new project as is, no edits. B copy it and swap the
     names, paths or patterns named above. C leave behind, it is this project's
     own content rather than scaffolding, and is not tagged.
-->

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
| 2026-08-23 | Record token usage for coding sessions | Done | `make dev` launches Claude Code behind the pxpipe proxy, `make stats` reports what a session cost. Verified against the real log, which reported a last write of 2026-08-10 and so proved this session was never behind the proxy. Two caveats written into the README rather than left to be discovered: the proxy currently compresses nothing, every request skipped as `unsupported_model`, and its log is machine global rather than scoped to Meter | `Makefile` targets `dev`, `stats`, `stats-json`. `README.md` section 3. CHG-0024, ISS-081, commit `a92ae60` |
| 2026-08-23 | Correct stale counts found by the checkpoint gate | Done | `project_map.md` and `INDEX.md` both claimed the Makefile had 28 targets when it has 51. Both now describe it without naming a number, because a count in prose goes stale silently and nothing checks it | `project_map.md` line 22, `INDEX.md` build and deployment table |
| 2026-08-23 | Competitive review of NudgeBee AI FinOps | Done | Six capabilities adopted as FEAT-043 to FEAT-048, three existing features amended, four rejected. Two adopted over my objection on the owner's decision, and both objections became design constraints: the FinOps Score ships only if it decomposes to the findings that moved it, and forecasting produced ADR-0015 drawing the line between a forecaster and a language model. Nothing on their page addresses observability query cost governance, which is evidence rather than assertion that P2 is the differentiator | `docs/11-COMPETITIVE-REVIEW.md`, ADR-0015, ADR-0016. CHG-0025, commit `c7f45f0` |
| 2026-08-23 | Configuration, feature flags, and the management account taken off the critical path | Done | Regions confirmed as eu-west-1 and eu-west-2, closing OPEN-06. TASK-P0-017 no longer depends on the member StackSet, because LocalStack emulates sts and organizations, which moves 6 tasks off somebody else's calendar. ADR-0017 with `.env.example` documenting 54 values by what, why and which file reads them, `docs/feature-flags.yaml` with owner, reason, expiry and removal per flag, and two checks that fail the build | `.env.example`, `docs/feature-flags.yaml`, `scripts/ci/check_flags.py`, `scripts/ci/check_hardcoded.py`. TASK-P0-034 added. CHG-0026, commit `5a78798` |
| 2026-08-23 | Write the P2 specification | Done | All three Grafana surfaces in scope, answering OPEN-04. The connection strategy sits below the adapter because the three variants share about 90 percent of their logic. Three enforcement levels and three write levels, per tenant, both defaulting safe. Two rules on the deny path enforced by database constraint rather than intention: no DENY without an expiry, and a never deny list | `docs/specs/2026-08-23-p2-query-cost-governance-design.md`, 458 lines. ISS-090 to ISS-096. CHG-0027, commit `ee3ea68` |
| 2026-08-23 | Fix a red gate I had committed through | Done | The previous commit marked eight features Specified while their documents carried only the Planned section set, and `make check-docs` was red when it landed. A process failure on my part, not a tooling one. All eight expanded from the specification | `docs/features/`, FEAT-011 to FEAT-018, commit `63329e6` |
| 2026-08-23 | Write the P2 implementation plan | Done | 22 tasks in ten waves. The prototype is pinned by golden files before anything touches it, and TASK-P2-001 forbids fixing even obvious bugs, because a baseline that already includes your fixes is not a baseline. Waves F and G do not depend on the audit path, which is the fastest route to the control that stops the bleed | `docs/plans/P2-implementation-plan.md`. CHG-0028, commit `80a0ac3` |
| 2026-08-23 | Correct another stale count found by the checkpoint gate | Done | `project_map.md` said the P0 plan had 28 tasks in 8 waves when it has 34 in eleven groups. Second occurrence of this defect class. Fixed the same way as the first: the map no longer names a number, and points at the command that counts them | `project_map.md` lines 57 to 62 |
| 2026-08-23 | P0 specification approved, execution begins | Done | Status moved to `Spec approved, in build` in the registry | `docs/registry.yaml` subprojects |
| 2026-08-23 | TASK-P0-029, verify the base images | Done | All four Minimus tags exist and pull anonymously. Scanning them changed two version choices and one policy. python 3.12 to 3.13 removed 3 High. nginx 1.27 to 1.30 removed 93 findings including 6 Critical. Neither move was suggested by any document, both found only by scanning. Digests pinned in `docker/base-images.lock`. Verified rather than assumed: no `/bin/sh` in the runtime, builder has python and pip, runtime is 93.9 MB | `docker/base-images.lock`, `scripts/ci/refresh_base_images.py`, `make base-images-check`. CHG-0029, commit `9754a59` |
| 2026-08-23 | Correct the security threshold | Done | Zero vulnerabilities at any severity is undeliverable: python 3.13 carries 3 unfixable CPython findings and no rebuild helps. ADR-0018 amends it to zero findings that have a published fix. Unfixable findings need an acceptance record with a reachability argument, and where the argument can be enforced it is: `check_forbidden_imports.py` fails the build if anyone imports stringprep, poplib or urllib.request | `docs/adr/ADR-0018-zero-fixable-not-zero-findings.md`, `security/policy/accepted.yaml`, `docs/05-SECURITY.md`. ISS-097 to ISS-101 |
| 2026-08-23 | First real security posture generated | Done | Zero fixable findings, three accepted as unfixable, gitleaks found no leaks. `security/POSTURE.md` is now generated from a scan rather than a placeholder | `security/POSTURE.md`, `security/reports/latest/` |
| 2026-08-23 | Correct the plan bookkeeping | Done | TASK-P0-029 was finished and the plan still read `Not started` for every task including that one. Status, evidence and the deviation now recorded. The deviation: 029 created the Python packages and the virtualenv, which belong to TASK-P0-001, so 001 is partly done | `docs/plans/P0-implementation-plan.md`. ISS-106 |
| 2026-08-23 | Design the interface | Done | The data model had 90 lines of constraints and the interface had 18 lines naming screens. Every honesty guarantee is enforced by a constraint and delivered by a pixel, so the constraint work was one careless screen away from worthless. `docs/12-UI-DESIGN.md`, 352 lines. The mechanism is the `Figure` component: provenance and freshness are required props, nothing else formats a number, so a screen that forgets provenance cannot be built | `docs/12-UI-DESIGN.md`, ADR-0019, FEAT-050, TASK-P0-035. ISS-102 to ISS-105. CHG-0030, commit `d904e7d` |
| 2026-08-23 | Stop STATUS.md keeping a second copy of the task list | Done | It hand maintained a copy of the plan's tasks and had already drifted, still showing 31 tasks and TASK-P0-029 as not started after it was finished. The task table is now generated from the plan files, and each generated block names its own source rather than all of them claiming the registry | `tasks/STATUS.md`, `scripts/docs/sync.py` |
| 2026-08-23 | Session close, context cleared | Done | No code change. 65 commits, tree clean, all 8 gates green. P0 is 1 done and 1 partly done of 35, P2 is 0 of 22. Handoff written below | This table, then the cold start section |
| 2026-08-23 | Verify project_map.md against the tree | Done | Four errors. The Python packages were named with hyphens in both the map and CLAUDE.md, so a reader would look for a directory that cannot exist. The map claimed PLANNED modules had no directory, untrue since TASK-P0-029. The feature count said 42 against an actual 50. Nine files were missing from the listing | `project_map.md`, `CLAUDE.md`. ISS-108, CHG-0032 |
| 2026-10-07 | Close the dependency admission gap left by TASK-P0-029 | Done | The task was marked done without running `make dep-check`, one of its own acceptance criteria. Run against the full resolved tree rather than package by package: grype 0 findings across 97 packages, pip-audit 0 advisories across 113. All 19 declared dependencies admitted | `docs/plans/P0-implementation-plan.md`, TASK-P0-029 evidence. ISS-111 |
| 2026-10-08 | TASK-P0-001, the workspace and quality gates | Done | Editable install, `tests/__init__.py`, `tests/conftest.py`, coverage parked at 0 with its restoration owned by TASK-P0-005. **Found that the import linter contracts had never worked**: `include_external_packages` was unset, so every contract forbidding boto3, fastapi or sqlalchemy passed because it never saw those imports. CLAUDE.md constraint 1 had been documented as machine enforced since the first week and was enforced by nothing | `pyproject.toml`, commit `a699d3c`. ISS-110, ISS-109. CHG-0033 |
| 2026-08-24 | Give the memory layer a validity gate | Done | `scripts/ci/check_memory.py` validates resume vectors, cited commits, identifiers and lesson shape. `scripts/docs/rotate_checkpoint.py` turns the archive rule into a mechanism. `scripts/docs/add_lesson.py` makes recording a correction one command. Wired into `make verify` and `make session-end`. Eight tests in `tests/test_checkpoint_rotation.py` | `make check-memory`. The live window is the latest 20 entries, older rows warn, the archive is exempt. First run found one dead resume vector and six historical ones. Harvest rate, 2 lessons across 47 tasks, is now printed every run. Tracked as CHG-0034 |
| 2026-08-24 | Tag every file that builds the base of the project | Done | 58 files carry a `Basic boiler Plate Doc` header stating why the file exists and its grade. A copy as is, B copy and swap the named parts, C left behind and untagged. Four generated files carry the tag from inside their generator, so regeneration cannot wipe it | `grep -rl "Basic boiler Plate Doc"` lists the boiler plate set. 28 are grade A, the rest B. `scripts/README.md` and `project_map.md` name every script. Tracked as CHG-0035 |
| 2026-08-24 | TASK-P0-005, the typed error taxonomy | Done | `finops_core/errors.py` with six causes and an abstract parent that refuses construction, so the catch all ISS-015 warns about cannot appear. `tests/core/test_errors.py`, ten tests, 100 percent coverage of the module. `--cov-fail-under` raised from 0 back to 80. N818 ignored for this one file because the six names are the stored cause values | `docs/plans/P0-implementation-plan.md` TASK-P0-005 is Done. Next is TASK-P0-034, the settings object, then TASK-P0-006 entities and TASK-P0-007 ports. Wave B is the critical path and unblocks C, E and G. Tracked as CHG-0036 |
| 2026-08-24 | TASK-P0-034, settings, constants and the flag resolver | Done | `finops_core/config.py` types all 46 `METER_` variables with no default except the eight flags, because a default in code is a value nobody can find when it is wrong and is how a region gets compiled into an image. `finops_core/constants.py`, `finops_api/flags.py`. `tests/core/test_config.py`, 15 tests. Suite at 33 tests and 100 percent | `docs/plans/P0-implementation-plan.md` TASK-P0-034 is Done. `FlagResolver` takes the tenant lookup as a callable because the `feature_flag` table lands in TASK-P0-010; TASK-P0-011 injects the real one. Next is TASK-P0-006, the domain entities, then 007 ports, 008 fake provider, 009 contract tests. Tracked as CHG-0037 |
| 2026-08-24 | TASK-P0-006, the domain entities | Done | `finops_core/domain/`, eight modules, every entity a frozen dataclass. `Fact` carries `as_of` and `collected_at` so constraint 10 is structural. `AccountKey` is `(provider, account_id)` and no other entity may hold a bare `account_id`. `Scope` has `is_global` plus an explicit set and no wildcard, empty means nothing. `CostRecord` uses FOCUS names. `tests/core/test_domain.py`, 21 tests, suite at 54 and 100 percent | `docs/plans/P0-implementation-plan.md` TASK-P0-006 is Done. The FOCUS test parses the `cost_focus_daily` block in `docs/07-DATA-MODEL.md`, so entity and table cannot drift. One file beyond the plan, `finops_core/domain/fact.py`, recorded as a deviation in the task. Next is TASK-P0-007, the eight ports, then 008 fake provider and 009 contract tests. Tracked as CHG-0038 |
| 2026-08-24 | TASK-P0-007, the eight ports | Done | `finops_core/ports/`, seven modules holding eight runtime checkable protocols. Every method names which of the six causes it raises, and `tests/core/test_ports.py` fails the build when one does not, because a caller left to guess writes a bare except and collapses the taxonomy. Three thin domain types added for the return signatures. Suite at 67 tests and 100 percent | `docs/plans/P0-implementation-plan.md` TASK-P0-007 is Done. `ProviderSession` is a ninth protocol kept out of `finops_core/ports/__init__.py` `__all__` deliberately. Next is TASK-P0-008, the fake provider, then TASK-P0-009 the port contract test suite, which closes Wave B. Tracked as CHG-0039 |
| 2026-08-24 | TASK-P0-008, the fake provider | Done | `finops_providers/fake/`, one class satisfying all eight ports. Any of the six causes can be planned for any scope, because the three behaviours this project cares most about are all failures. Fixture organization is one root, two units, five accounts, one denying access, and discovery still lists it because hiding an unreadable account hides the gap. `tests/providers/test_fake.py`, 27 tests, suite at 94 and 100 percent | `docs/plans/P0-implementation-plan.md` TASK-P0-008 is Done. Fixture account ids are not twelve digit numbers and the region is fictional, so `scripts/ci/check_hardcoded.py` stays green. ARG002 ignored for `finops_providers/fake/provider.py` because a port implementation must accept the whole declared signature. Next is TASK-P0-009, the contract suite, which closes Wave B. Tracked as CHG-0040 |
| 2026-08-24 | TASK-P0-009, the port contract suite. Wave B complete | Done | `tests/contract/`, one suite parameterised over providers rather than one file each, because two files drift apart within a month. The assertion it exists for is error type parity: a denied account raises `AccessDenied` from every provider and never something generic. 14 contract tests pass against the fake and 14 are visibly skipped for aws. Suite at 108 passed, 14 skipped, 100 percent | `tests/contract/conftest.py` holds `ProviderUnderTest` and the builder registry. TASK-P0-017 replaces the aws skip with a builder and changes nothing else. Wave B is complete, so Wave C persistence (TASK-P0-010 schema, 011 repositories, 012 identity) and Wave D Terraform are both unblocked and independent. Tracked as CHG-0041 |
| 2026-08-24 | TASK-P0-010, the schema and the initial migration | Done | Thirteen tables in `migrations/versions/0001_initial.py`, described again for the repository layer in `finops_api/db/models.py`. Two descriptions of one schema are safe because a drift test compares them on a real PostgreSQL. 22 metadata tests need no database, 12 integration tests do. Found and fixed two gaps in `docs/07-DATA-MODEL.md`: no self referencing key on `org_node`, and no `tenant_id` on `principal_scope` | `make test` is 130 passed at 100 percent, `pytest tests/db/test_schema.py` is 12 passed against postgres 16. The partitioned tables ship with no partitions on purpose, so a missing one raises instead of misfiling cost; TASK-P0-032 adds the job that creates them. Next is TASK-P0-011, repositories with the scope guard, then TASK-P0-012 identity. Tracked as CHG-0042 |
| 2026-08-24 | TASK-P0-011, repositories and the scope guard | Done | `finops_api/guards.py` plus four repositories under `finops_api/db/repositories/`. A caller cannot express an unscoped query, because the guard builds the predicate and nothing accepts a finished statement. Every read writes an `audit_event` in the same transaction. Empty scope returns nothing, never everything. `tests/db/test_scope_guard.py`, 9 unit and 8 integration. ISS-109 closed after confirming both forbidden targets actually fire | `make test` is 139 passed at 96.66 percent, `pytest tests/db/` is 51 passed against postgres 16. The first `assert_scoped` read rendered SQL and wrongly rejected the empty scope case, because SQLAlchemy folds a false predicate and drops the tenant filter from the text; it now checks an execution option that only `scoped_select` sets. Next is TASK-P0-012, the identity ports with the local provider, which closes Wave C. Tracked as CHG-0043 |
| 2026-08-24 | TASK-P0-012, identity ports and the local provider. Wave C complete | Done | `finops_api/identity/` with the local provider, signed sessions that always expire, an entitlement cache with an explicit expiry, and `ScopeCoverage`. The production refusal went into `finops_core/config.py` with the other startup guards and covers both `METER_IDENTITY_PROVIDER` and `METER_FEATURE_LOCAL_AUTH`. `tests/api/test_identity_local.py`, 22 tests | `make test` is 164 passed at 96.59 percent. `ScopeCoverage` refuses a total smaller than the visible count, which is ISS-016 itself. Wave C is complete, so Wave D Terraform (TASK-P0-013 to 016) and Wave E AWS adapters (TASK-P0-017 to 019) are both unblocked; the plan notes D is not required to start E. Tracked as CHG-0044 |
| 2026-08-24 | TASK-P0-017, the AWS credential broker | Done | `finops_providers/aws/`, the only package importing boto3. Timeouts and a bounded retry policy from settings, because default retries at three hundred accounts turn throttling into a herd. Sessions reused until five minutes before expiry, never past it. Every provider code maps to one of the six causes and an unknown one becomes SchemaDrift, never NoData. The ARN partition is derived from the region rather than written down. 25 tests | `pytest -m contract` now runs the aws adapter for CredentialBroker and reports AccountDiscovery as skipped by name until TASK-P0-018. The contract immediately caught the fake using a scope key without the region while the adapter used the documented provider:account:region; the fake was wrong and now matches. Next is TASK-P0-018, account discovery. Tracked as CHG-0045 |
| 2026-08-24 | TASK-P0-018, AWS account discovery | Done | `finops_providers/aws/accounts.py` walks roots, units and accounts recursively and paginates every call, because an unpaginated call does not fail, it returns the first hundred accounts and they become the denominator on every screen. Suspended and departing accounts are kept with their real status, and an unrecognised status becomes UNKNOWN rather than a drop. Throttling backs off with growing delays, bounded by METER_AWS_MAX_RETRIES. 15 tests | `pytest -m contract` is 28 passed with no skips, both providers, both ports. `AccountStatus` was realigned to the values `docs/07-DATA-MODEL.md` stores and a test now holds the enum and the check constraint equal; the initial migration was edited rather than superseded because it is not deployed. Next is TASK-P0-019, the account health check, which closes Wave E. Tracked as CHG-0046 |
| 2026-08-24 | TASK-P0-019, the account health check. Wave E complete | Done | `finops_providers/aws/health.py` assumes the role and makes one cheap call, because a session object proves the assume worked and nothing more. STS returns the same AccessDenied whether the role is missing or refusing, so the distinction comes from a `deployment_probe` and, without one, the answer is UNKNOWN with the provider's message recorded rather than a guess that pages the wrong owner. `RoleHealth` and `AccountHealth` went into the domain because role_health is a stored column. 16 tests | `make test` is 237 passed at 96.60 percent, `pytest -m contract` 28 passed. Wave E is complete. TASK-P0-014 supplies the real deployment probe from the StackSet. Next is Wave F ingestion, TASK-P0-020 the run ledger and watermarks, which depends on TASK-P0-010 and is unblocked. Tracked as CHG-0047 |
| 2026-08-24 | TASK-P0-020, the run ledger and watermarks | Done | `finops_ingest/ledger.py`. A run is claimed by inserting its idempotency key, which is a hash of the collector, scope and window and deliberately carries no wall clock, because a clock in the key makes every run unique while looking like it works. The watermark advances only after the write succeeds and only ever forward. A stale claim is taken over rather than duplicated. 16 tests, 13 of them against postgres | `make test` is 239 passed at 94.49 percent, `pytest tests/db tests/ingest` is 70 passed. The tests found a real collision: run uniqueness was global while the key carries no tenant, so two tenants sharing an account would starve one of them. Now `(tenant_id, idempotency_key)`, fixed in the migration, the models and `docs/07-DATA-MODEL.md`. Next is TASK-P0-021, the dispatcher and worker. Tracked as CHG-0048 |
| 2026-08-24 | TASK-P0-021, the dispatcher and worker | Done | `finops_ingest/registry.py`, `dispatcher.py`, `worker.py`. Each unit runs in its own transaction, because one transaction for a batch means one account's failure rolls back the other 299 and the run reports nothing wrong while writing nothing. Only the six domain errors are caught; a ValueError is allowed to crash the worker, and a test asserts it does. The dispatcher's dedup key is the ledger's claim key, so a redispatch is free at both ends. 35 ingest tests | Both spec section 11 tests pass: `test_one_account_access_denied_does_not_fail_run` and `test_no_data_and_access_denied_are_distinguishable`. `make test` is 247 passed at 91.51 percent, `pytest tests/db tests/ingest` is 89 passed. Next is TASK-P0-022, the organization tree and account health collectors, which puts real collectors behind this machinery. Tracked as CHG-0049 |
| 2026-08-24 | TASK-P0-022, the organization tree and account health collectors | Done | `finops_ingest/collectors/`. The tree is replaced inside the worker's own transaction, so a reader never sees an empty organization, and a test proves it by failing a rebuild half way and checking the old tree survives. A departed account is marked, never deleted, because its cost history has to outlive its membership. An empty discovery is refused rather than applied. 23 collector tests | `CollectorRunner` now takes a `CollectorContext` carrying the worker transaction, because a collector previously had no way to write. `install_default_schedule` seeds `collector_schedule` so the hourly claim is data per ADR-0012, and it never overwrites an operator's change. `make test` is 249 passed at 89.58 percent, `pytest tests/db tests/ingest` is 114 passed. Next is TASK-P0-023, the platform self cost collector, which closes Wave F. Tracked as CHG-0050 |
| 2026-08-27 | TASK-P0-023, the platform self cost collector. Wave F complete | Done | `finops_core/domain/platform.py`, `finops_providers/aws/platform_cost.py` and `finops_ingest/collectors/platform_cost.py`. One grouped Cost Explorer request a day, because the API charges per request and per module calls would multiply a metered API by the number of modules. Untagged cost is named `unallocated` rather than dropped, since a report that quietly under counts is worse than none. The Cost Explorer charge is re attributed to ingest rather than added as a synthetic row, which would double count. 19 tests | `make test` is 262 passed at 89.26 percent, `pytest tests/db tests/ingest` is 133 passed. Wave F is complete. Next is Wave G, TASK-P0-024 the FastAPI application and scope dependency, which depends on TASK-P0-012 and is unblocked. Tracked as CHG-0051 |
| 2026-08-27 | TASK-P0-024, the FastAPI application and scope dependency | Done | `finops_api/main.py`, `deps.py`, `middleware.py`, `schemas.py`. The meta envelope carries as_of, collected_at, scope_coverage and a computed `degraded`, and `create_app` refuses to start if a data route returns something bare. `/healthz` reports database reachability and per collector staleness against each collector's own cadence, so never collected reads as stale rather than healthy. 36 tests | The adversarial test for ISS-009 passes: a route that reads without the scope dependency returns 500 and no rows, and neither tenant's account appears in the body. The envelope check first walked `app.routes`, found nothing because FastAPI wraps included routers, and passed over an unexamined app; it now inspects the routers directly and refuses to start if it finds no routes. Next is TASK-P0-025, the P0 routes. Tracked as CHG-0052 |
| 2026-08-27 | TASK-P0-025, the seven P0 routes. Wave G complete | Done | `finops_api/routes/`, all seven routes from spec section 8, every one returning the meta envelope. `/org/tree` marks out of scope branches unreachable rather than pruning them, and a test asserts a narrow scope and a global one return the same node count. `/ingest/runs` returns the typed cause and its remediation, never an exception string. `/health/freshness` judges each collector against its own cadence from `collector_schedule`. 53 API tests | `make test` is 266 passed at 85.42 percent, integration is 101 passed. A recheck on an out of scope account and on a missing one return the same 404, so a caller cannot enumerate. Three repositories and `count_in_organization` were added beyond the file list; the count returns a number and never rows. Wave G is complete. Next is Wave H, the frontend, starting with TASK-P0-035. Tracked as CHG-0053 |
| 2026-08-27 | TASK-P0-002, the frontend workspace | Done | `finops-web/` on Vite, React 19 and TypeScript. `npm ci`, `npm run lint`, `npm run test -- --run` and `npm run build` all pass, and the frontend step of `make lint` passes at the repository root. No component library and no state library, per the task | Flat `eslint.config.js` rather than `.eslintrc.cjs`, because ESLint 9 and later do not read eslintrc and that file would have linted nothing while reporting success. TypeScript pinned below 6 because `typescript-eslint` declares `<6.1.0`; the reason is in `finops-web/README.md`. Node 25 raises an engine warning, so the pipeline image should be on an even numbered release. `make lint` used to stop at `terraform fmt` because the hub Terraform directory does not exist until TASK-P0-013; it now prints a skip instead, because a gate left red for an unrelated reason stops being read. Next is TASK-P0-035, the component layer and the visual honesty system. Tracked as CHG-0054 |
| 2026-08-27 | TASK-P0-035, the component layer and the visual honesty system | Done | `finops-web/src/components/`. `Figure` takes value and freshness as required props, and `FigureValue` is a union where a forecast has low and high and no single amount, so a point forecast cannot be expressed. A failure renders its cause and remediation and no numeral; `NoData` is the only cause that renders a zero. `StateBoundary` covers all seven states. Axe reports zero violations. 47 tests across 6 files | `finops-web/src/components/index.ts` exports no formatter and a test asserts it, because a screen that can import one will use it under pressure. Two defects found and fixed: tsc was emitting JS into a build directory that vitest then ran as a second copy of every test, and `css: false` made the token assertions read an empty string. Next is TASK-P0-026, the application shell. Tracked as CHG-0055 |
| 2026-08-27 | TASK-P0-026, the application shell | Done | `finops-web/src/shell/` and `finops-web/src/api/`. Every surface reports its meta and the shell shows the worst of them: oldest `as_of` in view, most conservative coverage, degraded if any panel is. The coverage banner has no dismiss control and says so when coverage is complete. The API client throws rather than returning an empty result, and refuses a response carrying no envelope. 69 frontend tests across 9 files | The screenshot the task asks for is deferred to TASK-P0-028, which introduces Playwright; the partial coverage state is asserted in `finops-web/src/shell/__tests__/AppShell.test.tsx` instead. Retries are off in the query client, because a retry hides a failure until it gives up. Next is TASK-P0-027, the accounts screen and organization map. Tracked as CHG-0056 |
| 2026-08-27 | TASK-P0-027, the accounts screen and organization map | Done | `finops-web/src/screens/` plus `OrgTree` and `GraphCanvas` added to the component inventory. Broken onboarding is one filter rather than four. The tree opens first and is the accessible path, not the consolation. An unreachable branch stays focusable and stops being actionable, asserted as behaviour rather than as an attribute. 95 frontend tests across 14 files | React Aria caught a real defect: expandable items had no expand control, so a screen reader user could not open a branch. The graph library is now loaded on demand, taking first load from 849 kB to 414 kB. The 300 account screenshot needs a browser and is deferred to TASK-P0-028 with Playwright; the cap and the 300 nodes handed to the library are asserted here. Next is TASK-P0-028. Tracked as CHG-0057 |
| 2026-08-27 | TASK-P0-003 and TASK-P0-004, closing Wave A | Done | `scripts/docs/check_index.py` grew a `problems_in(root)` entry point read at call time, and `tests/scripts/test_check_index.py` exercises both failure paths plus the exit code. The banned dash rejection was demonstrated with a probe document rather than assumed | `terraform-validate` carries no allow_failure and fails today because the Terraform directories do not exist; it stops failing when TASK-P0-013 to 016 land, which is what the criterion asks. Nothing was weakened to make it green early. Wave A is complete. Tracked as CHG-0058 |
| 2026-08-27 | TASK-P0-028, the last three screens, the journey and the budgets | Done, one criterion open | Ingest, freshness and platform cost screens. A refused run renders no Figure at all while a genuine zero renders one, which is ISS-015 made visible. Both performance budgets measured: 600 units in 0.94s against 900s, and p95 4.2ms against 500ms. Three Playwright journeys against the real bundle, and three screenshots produced | `tests/perf/test_budgets.py` states its conditions: budget 1 runs against the fake provider so it measures our machinery and not AWS latency, and budget 2 has no network hop. The restore drill was NOT performed because it needs an Aurora cluster, recorded as ISS-111 and open. The live end to end journey needs the deployed stack from Wave D. Next is TASK-P0-032. Tracked as CHG-0059 |

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

### Cold start, as of 2026-10-09

A fresh session with no memory of this one should work from this section alone.

**Read three things, in order.** `INDEX.md`, then `CLAUDE.md`, then
`docs/plans/P0-implementation-plan.md`.

**Position.**

| What | Where |
| --- | --- |
| Git | `main`, 70 commits, working tree clean |
| Gates | 8 of 8 green: `make check-docs && make check-writing` |
| P0 | Approved, in build. **2 done, 33 remaining of 35** |
| P2 | Specified and planned, 22 tasks. Built after P0 |
| P1 to P7 | Roadmapped only. Spec, then plan, then build, per ADR-0001 |
| Application code | The workspace only. No domain code yet |

**Done.** TASK-P0-029 base images and posture. TASK-P0-001 workspace and gates.

**Next.** TASK-P0-002, the frontend workspace. Then 003, 034, 031, 004.

**After 002, start TASK-P0-035 in parallel.** The component layer depends only
on the frontend workspace. Treating it as though it follows the API compresses
the interface work into the end of the project.

**Six things that are easy to get wrong.**

1. Run doc and policy scripts with `.venv/bin/python`. They need pyyaml, a
   system interpreter lacks it, and PEP 668 blocks adding it there.
2. The interpreter is python3.13, pinned to match the runtime image.
3. Never edit a generated block. Change `docs/registry.yaml` or the plan, then
   `make doc-sync`.
4. The security threshold is zero findings **that have a published fix**, not
   zero findings. ADR-0018.
5. No screen formats a number. Everything goes through `Figure`.
   `docs/12-UI-DESIGN.md`.
6. **Confirm a guard by making it fail**, not by reading it. The import
   contracts passed for weeks while enforcing nothing. TASK-P0-011 and
   TASK-P0-024 each carry a probe for the two contract targets still inert.

**Waiting on a person.**

| | Blocks | Tracker |
| --- | --- | --- |
| Regulatory retention floor above 37 months for cost data | TASK-P0-010, the schema. **Chase first** | ISS-078 |
| Real names for flag owners, CODEOWNERS, `accepted.yaml` | Hard build failure before the first merge request | ISS-087 |
| Management account access | Live verification at the end of wave E only | ISS-002 |
| Sign off on `audit_event` non erasure | Before first production deployment | ISS-079 |

**Next audit** at the P0 boundary, scope `code`.

### Earlier resume vector, as of 2026-09-29

| What | Where |
| --- | --- |
| Git position | branch `main`, 61 commits, working tree clean |
| **P0 spec** | **APPROVED.** Status `Spec approved, in build` |
| **Done** | TASK-P0-029 only. 1 of 34 |
| **Next** | TASK-P0-001, and it is **partly done**: packages and `.venv` exist, the editable install, `tests/conftest.py` and the pytest harness do not. Then 002, 003, 034, 031, 004 |
| Interpreter | python3.13, pinned in the Makefile to match the runtime image |
| Doc scripts | Run from `.venv`, not a system interpreter. PEP 668 blocks pyyaml there |
| Security posture | Zero fixable findings, 3 accepted unfixable, reviewed 2026-11-21 |
| Base images | Pinned by digest. `make base-images-check` fails on drift |
| Needs a person | ISS-087 flag and CODEOWNERS owners, and the placeholder owners in `security/policy/accepted.yaml`. ISS-078 retention floor, before TASK-P0-010 builds the schema |
| Check everything | `make check-docs && make check-writing` |
| Next audit due | P0 boundary, scope `code` |

### Earlier resume vector, as of 2026-09-26

| What | Where |
| --- | --- |
| Git position | branch `main`, 58 commits, working tree clean |
| **The gate, still open** | `docs/specs/2026-08-23-p0-foundation-design.md` is `In review`. The only thing between here and code |
| Also in review, not blocking | The P2 spec and plan |
| **First task** | TASK-P0-029, verify the Minimus tags. Then group 1: 001, 002, 003, 034, 031, 004 |
| Plans that exist | P0, 34 tasks in eleven groups. P2, 22 tasks in ten waves. **56 tasks total** |
| Plans that do not | P1, P3 to P7. Written when their spec is approved, per ADR-0001 |
| Unblocked in P0 | Waves A to E, 22 of 34, needing nobody |
| Answered this session | OPEN-04, all three Grafana surfaces in scope. OPEN-06 was answered earlier |
| Needs a person | ISS-095 who owns the never deny list, before `deny` is enabled. ISS-078 regulatory retention floor, before the schema is built. ISS-087 flag and CODEOWNERS owners, before the first merge request |
| Check everything | `make check-docs && make check-writing` |
| End a session | `make session-end` |
| Next audit due | P0 boundary, scope `code` |

### Earlier resume vector, as of 2026-09-20

| What | Where |
| --- | --- |
| Git position | branch `main`, 52 commits, working tree clean |
| **The gate, still open** | `docs/specs/2026-08-23-p0-foundation-design.md` status is `In review`. Never approved |
| **First task** | TASK-P0-029, verify the Minimus tags. Then group 1: 001, 002, 003, 034, 031, 004 |
| Unblocked now | **Waves A to E, 22 of 34 tasks.** The management account came off the critical path via LocalStack |
| Plan size | 34 tasks. 034 configuration and flags, added this session, runs in group 1 |
| Registers | 49 features, 17 decisions, 26 changes, 89 issues, 6 open questions of which 1 answered |
| Auth placeholder | TASK-P0-012. Two ports, a local provider that refuses to start in prod. The scope guard, audit and coverage are fully built, only the "who is this" adapter is deferred. OPEN-01 |
| Regions | `METER_REGIONS=eu-west-1,eu-west-2`. OPEN-06 answered |
| Needs a person | ISS-087 flag and CODEOWNERS owners, before the first merge request. ISS-078 regulatory retention floor, before the schema is built. ISS-079 audit_event non erasure sign off |
| Still needed from AWS | Management account access, ISS-002, for live verification at the end of wave E only. Not blocking |
| Check everything | `make check-docs && make check-writing` |
| End a session | `make session-end` |
| Next audit due | P0 boundary, scope `code` |

### Earlier resume vector, as of 2026-09-15

| What | Where |
| --- | --- |
| Git position | branch `main`, 47 commits, working tree clean |
| **The gate, still open** | User review of `docs/specs/2026-08-23-p0-foundation-design.md`. Status is `In review`. Nothing has approved it |
| First task on approval | `docs/plans/P0-implementation-plan.md`, **TASK-P0-029**, not 001 |
| Unblocked today, needing nobody | TASK-P0-029, then waves A, B and C, tasks 001 to 012. 16 of 33 tasks, none touching AWS |
| Blocked on other people | Management account trusted access and the organization reader role, ISS-002, needed by wave D. Regions beyond Ireland and London, OPEN-06, needed by wave F |
| Ask early | ISS-078, whether a regulatory floor exceeds the 37 month cost retention. If answered late it changes the schema |
| Start a session | `make dev`, not plain `claude`, or the session is not recorded |
| Check everything | `make check-docs && make check-writing` |
| End a session | `make session-end` |
| Next audit due | At the P0 boundary, scope `code` |

### Earlier resume vector, as of 2026-09-12

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
