# Remediation log

Append only. One row per state transition of an audit finding.

Three artefacts, three jobs, and they do not overlap.

| Artefact | Holds | Mutable |
| --- | --- | --- |
| `audits/AUDIT-nnn-*.md` | The evidence, at the moment it was found | No. Never edited after publication |
| `docs/registry.yaml` | The current state of every issue | Yes. Generated views follow it |
| **This log** | **The history of how each finding got there** | Append only. Rows are never edited or removed |

The registry answers "what is the state now". This answers "what happened, when,
by what change, and how was it verified". Without it, a finding that was closed,
reopened and closed again looks identical to one that was closed once, and the
second is a much healthier signal than the first.

## Format

| Date | Finding | Issue | From | To | What was done | Commit | Verified by |

- **Date** is when the transition happened, absolute, never relative.
- **Finding** is the audit identifier, `A001-F03`.
- **Issue** is the promoted registry identifier, `ISS-059`.
- **From** and **To** use the register vocabulary: `OPEN`, `IN PROGRESS`,
  `FIXED`, `WONT FIX`, `PARKED`, `CLOSED`, plus `REOPENED` as a `To` value.
- **What was done** is one sentence, in the past tense, naming the mechanism
  rather than the intent.
- **Commit** is the short SHA. `pending` is only valid for the current session.
- **Verified by** is the **command that proves it**, or the file and line that
  now contains what was missing. "Reviewed" is not verification.

## Rules

1. **Every transition gets a row.** A finding that moves from OPEN to FIXED
   without a row did not move as far as this project is concerned.
2. **`WONT FIX` needs a reason and a named owner**, in the row.
3. **A reopened finding keeps its original identifier.** Never allocate a new
   one to make the history look cleaner.
4. **The verification column is not optional.** A fix with no command that
   proves it is a claim.
5. **Never edit a row.** A mistake is corrected by a new row saying so.

## Log

| Date | Finding | Issue | From | To | What was done | Commit | Verified by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-08-23 | A001-F01 | ISS-058 | OPEN | FIXED | Issue register in `tasks/ISSUES.md` brought under generation from the registry, closing a 22 record drift | `49514ea` | `make check-docs`, and set difference of the two files is empty |
| 2026-08-23 | A001-F02 | ISS-057 | OPEN | FIXED | finops_mcp added to pyproject packages and import linter roots, plus a forbidden contract blocking finops_api.db, guards, finops_providers, boto3 and sqlalchemy | `ef23f8a` | `.venv/bin/lint-imports`, and 3 contracts now listed in pyproject.toml |
| 2026-08-23 | A001-F03 | ISS-059 | OPEN | FIXED | gitleaks added to the .security_tools anchor so dependency-scan no longer exits 2 on a missing binary | `ef23f8a` | `grep -c gitleaks .gitlab-ci.yml` shows it in the anchor and the standalone job |
| 2026-08-23 | A001-F05 | ISS-060 | OPEN | FIXED | make setup now depends on security-tools, and scan.sh names `make security-tools` in its missing tool error | `ef23f8a` | `make setup` installs the scanners on a clean machine |
| 2026-08-23 | A001-F04 | ISS-061 | OPEN | FIXED | local-auth.example.yaml committed, .gitignore negation added, and make up now creates local-auth.yaml from it when absent | `ef23f8a` | `git add local-auth.example.yaml` succeeds, `make up` has a local-auth.yaml prerequisite |
| 2026-08-23 | A001-F16 | ISS-068 | OPEN | FIXED | CODEOWNERS, .editorconfig and SECURITY.md added. CODEOWNERS names the security owner that ADR-0013 step 5 requires | `ef23f8a` | Files present at the repository root |
| 2026-08-23 | A001-F08 | ISS-064 | OPEN | FIXED | MCP packaged as a second process in the meter-api image rather than a fourth image. ADR-0009 records the decision, the phantom Dockerfile.mcp removed from the plan, and ECR immutability and enhanced scanning added to TASK-P0-016 | `ef23f8a` | `grep -c Dockerfile.mcp docs/plans/P0-implementation-plan.md` returns 0 |
| 2026-08-23 | A001-F09 | ISS-069 | OPEN | FIXED | PARTIAL defined in P0 spec section 6.1 as a run that completed while at least one scope produced a typed error. Renders as degraded, never success, and the watermark advances only for successful scopes | `ef23f8a` | P0 spec section 6.1, and the data model references it |
| 2026-08-23 | A001-F07 | ISS-063 | OPEN | FIXED | The dead HTML graph output removed. It checked for a cytoscape bundle that was never vendored. Replaced by a JSON output for tools, alongside the Mermaid output people read | `ef23f8a` | `ls docs/architecture/` shows file-graph.md and file-graph.json only |
| 2026-08-23 | A001-F06 | ISS-062 | OPEN | FIXED | scripts/docs/build_context_index.py written, parsing the five packages for public symbols and resolving callers by name. Wired into make doc-sync and make check-docs | `ef23f8a` | `make check-docs` runs the generator in check mode and passes |
| 2026-08-23 | A001-F10 | ISS-070 | OPEN | FIXED | Sub project records extended in the registry with status, spec, plan and dependencies, and the hand written roadmap table replaced by a generated one | `ef23f8a` | `make check-docs` passes, and the generated relative links resolve from docs/ |
| 2026-08-23 | ISS-054 | ISS-054 | OPEN | FIXED | ECR tag immutability and enhanced scanning added to the TASK-P0-016 acceptance criteria | `ef23f8a` | Present in the plan, verified at TASK-P0-016 |
| 2026-08-23 | A001-F11 | ISS-055 | OPEN | FIXED | STRIDE threat model written across six trust boundaries, with five residual risks tracked as ISS-073 to ISS-077 rather than left implicit | `3a16bd0` | `docs/08-THREAT-MODEL.md`, and every Medium residual has a tracking row |
| 2026-08-23 | A001-F12 | ISS-056 | OPEN | FIXED | Every table classified with a retention period and an erasure position. Five retention jobs specified as TASK-P0-032. `cloud_account.email` removed from the schema, spec and plan because no feature reads it | `3a16bd0` | `docs/09-DATA-CLASSIFICATION.md`, and `grep email docs/07-DATA-MODEL.md` shows only the principal columns and the explanatory comment |
| 2026-08-23 | A001-F13 | ISS-065 | OPEN | FIXED | Disaster recovery section added to the architecture. RPO 5 minutes for audit and workflow data, 24 hours for derived data, RTO 4 hours. Restore drill is an acceptance criterion of TASK-P0-028, not a later intention | pending | `docs/02-ARCHITECTURE.md`, and TASK-P0-028 asserts the drill |
| 2026-08-23 | A001-F14 | ISS-066 | OPEN | FIXED | Four SLOs and ten alerts, of which exactly two page: collection stalled, and platform cost anomaly. TASK-P0-033 implements them with a runbook per paging alert | pending | `docs/10-OBSERVABILITY.md`, TASK-P0-033 |
| 2026-08-23 | A001-F15 | ISS-067 | OPEN | FIXED | Running cost estimated at roughly 420 USD per month for P0 and 1,000 to 1,400 at 300 accounts with P1 to P3 and Config mitigated. Every assumption stated so a reader can disagree with a number rather than the total | pending | `docs/04-DEPLOYMENT.md`, and FEAT-008 checks it against the bill |
| 2026-08-23 | A001-F17 | ISS-071 | OPEN | FIXED | Seven universal exit criteria plus one per sub project, and a definition of steady state for the project. A specification without them cannot be approved | pending | `docs/01-ROADMAP.md`, and change control makes it a gate |
| 2026-08-23 | A001-F18 | ISS-072 | OPEN | FIXED | Four performance budgets in P0 spec section 11b, each asserted by a test. Budget 1, a 300 account sweep under 15 minutes, is the one that constrains the design | pending | P0 spec section 11b, asserted in TASK-P0-028 |
| 2026-08-23 | new | ISS-080 | OPEN | FIXED | Found while computing the cost estimate: VPC endpoints were justified on cost and NAT is cheaper below roughly 1,560 GB per month. The decision stands on security grounds, and the reasoning is corrected rather than the conclusion | pending | `docs/04-DEPLOYMENT.md` network section carries the arithmetic |
