# Scripts

<!-- Basic boiler Plate Doc | Grade B
     Why this file exists: What every script does and how it is run.
     Grade B here: copy it, then replace the script table.
     Grades: A copy into a new project as is, no edits. B copy it and swap the
     names, paths or patterns named above. C leave behind, it is this project's
     own content rather than scaffolding, and is not tagged.
-->

Every script in the project lives here, grouped by what it serves. Nothing
executable lives outside this directory.

| Directory | Contents |
| --- | --- |
| `security/` | Scanning, the dependency admission gate, the HTML report, the auto fix |
| `docs/` | Index consistency, feature document completeness, the file graph, checkpoint rotation |
| `ci/` | Pipeline helpers, including the automated code review and the memory gate |
| `deploy/` | Deployment helpers, including the migration task runner |
| `ops/` | Things a person runs against a live database, deliberately not API routes |

| Script | Entry point | Purpose |
| --- | --- | --- |
| `security/scan.sh` | `make security-scan` | Runs every scanner, writes a timestamped report |
| `security/check_dependency.sh` | `make dep-check pkg=x` | Admission gate. Scans a dependency and its whole transitive tree before it is added |
| `security/validate_allowlist.py` | called by `scan.sh` | Fails when an allowlist entry is malformed or expired |
| `security/report.py` | `make security-report` | Merges every scanner into one HTML report, a summary and the posture |
| `security/autofix.py` | `make security-fix` | Applies available fixes on a branch, runs tests, re scans. Never merges |
| `docs/check_index.py` | `make check-docs` | Fails when `INDEX.md` and the documents drift apart |
| `docs/check_feature_docs.py` | `make check-docs` | Fails when a feature has no document, or a document has no feature |
| `docs/build_file_graph.py` | `make graph` | Builds the file dependency graph and checks the layering |
| `docs/build_context_index.py` | `make doc-sync` | Generates `context_index.md` from the source, which rung two of the ladder depends on |
| `docs/rotate_checkpoint.py` | `make session-end` | Moves the oldest checkpoint entries to the archive at 50, keeping the latest 20. The archive rule was written on day one and never executed, because it had no mechanism |
| `docs/add_lesson.py` | `make lesson m="x"` | Appends a lesson skeleton. Recording a correction was losing to friction, so the friction was removed |
| `docs/sync.py` | `make doc-sync` | Regenerates every derived document from `docs/registry.yaml` |
| `security/pre_commit_deps.sh` | pre commit hook | Runs the admission gate when a dependency manifest changes |
| `ci/code_review.py` | `make review` | Deterministic checks first, then the review checklist |
| `ci/check_flags.py` | `make check-docs` | Fails on an expired feature flag, or one missing an owner, reason or removal plan |
| `ci/check_hardcoded.py` | `make check-docs` | Fails on a region, account id, ARN, URL, role name or bare threshold written into application code |
| `ci/check_forbidden_imports.py` | `make check-docs` | Enforces the reachability claims in `security/policy/accepted.yaml`. Importing a module an acceptance depends on not importing fails the build |
| `ops/erase_principal.py` | run by hand | Answers an erasure request in one transaction and prints what it changed, including the zero audit rows it removed. Defaults to a dry run. Not an API route, because an erasure endpoint is a deletion primitive exposed to the network |
| `ci/check_memory.py` | `make check-memory` | Fails when a resume vector points at a path that does not exist, a cited commit does not resolve, an identifier is defined nowhere, or a lesson is unfinished. Reports the lesson harvest rate every run |
| `ci/refresh_base_images.py` | `make base-images` | Re resolves the Minimus tags to digests and rewrites `docker/base-images.lock` |
| `deploy/run_migration_task.sh` | GitLab pipeline | Runs migrations as a one off ECS task before rollout |

## Conventions

- Python scripts use only the standard library plus `pyyaml`. `pyyaml` is not
  in a system interpreter and PEP 668 prevents adding it there, so these run
  from the project virtualenv. `make setup` creates it. The Makefile picks the
  venv interpreter when it exists and falls back otherwise.
- Every script exits non zero on failure. A check that only warns is ignored
  within two weeks.
- Every script explains, in its own docstring, the reasoning behind any choice
  that looks odd.
