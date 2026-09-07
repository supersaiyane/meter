# Scripts

Every script in the project lives here, grouped by what it serves. Nothing
executable lives outside this directory.

| Directory | Contents |
| --- | --- |
| `security/` | Scanning, the dependency admission gate, the HTML report, the auto fix |
| `docs/` | Index consistency, feature document completeness, the file graph |
| `ci/` | Pipeline helpers, including the automated code review |
| `deploy/` | Deployment helpers, including the migration task runner |

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
| `docs/sync.py` | `make doc-sync` | Regenerates every derived document from `docs/registry.yaml` |
| `security/pre_commit_deps.sh` | pre commit hook | Runs the admission gate when a dependency manifest changes |
| `ci/code_review.py` | `make review` | Deterministic checks first, then the review checklist |
| `deploy/run_migration_task.sh` | GitLab pipeline | Runs migrations as a one off ECS task before rollout |

## Conventions

- Python scripts use only the standard library plus `pyyaml`, so they run
  before `make setup` has been done.
- Every script exits non zero on failure. A check that only warns is ignored
  within two weeks.
- Every script explains, in its own docstring, the reasoning behind any choice
  that looks odd.
