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

## Next action

**Blocked on user review of the P0 foundation specification.** Nothing else
should start until it is approved, because every other sub project depends on
P0.

### Resume vector

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

### On approval, the next task

Execute `docs/plans/P0-implementation-plan.md` from TASK-P0-001. Waves A and D
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
