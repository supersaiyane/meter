# Issues and open questions

Last updated: 2026-08-23
Update trigger: the moment an issue or open question is found, or closed
Source of truth: `docs/registry.yaml`. The register below is generated

Two registers. **Open questions** are decisions waiting on a person.
**Issues** are problems, risks and defects found in the design, the existing
prototype, or the build.

Severity: `CRITICAL` blocks delivery or risks data loss or a security breach.
`HIGH` is a real defect or a significant risk. `MEDIUM` is a maintainability
or accuracy concern. `LOW` is a minor improvement.

Status: `OPEN`, `IN PROGRESS`, `FIXED`, `WONT FIX`, `PARKED`, `CLOSED`.

---

## Open questions

| ID | Question | Raised | Status | Owner | Blocks |
| --- | --- | --- | --- | --- | --- |
| OPEN-01 | Identity provider approach. Can a new relying party trust be registered in ADFS for Meter, or is IAM Identity Center available, or must the existing AWS relying party be reused? | 2026-08-23 | PARKED at user request | User | Production login. Does not block P0 build, isolated behind ports per ADR-0008 |
| OPEN-02 | Single payer account or multiple payer accounts? Multi payer materially changes CUR ingest and organization tree merging. | 2026-08-23 | OPEN | User | P1 design |
| OPEN-03 | Is Business or Enterprise support available? Trusted Advisor limit checks and several quota utilization signals require it. | 2026-08-23 | OPEN | User | P3 and P5 coverage |
| OPEN-04 | Is Grafana only Amazon Managed Grafana, or is self hosted and Grafana Cloud also in scope? | 2026-08-23 | OPEN | User | P2 scope |
| OPEN-05 | Which ticketing system for the recommendation lifecycle, Jira or ServiceNow? | 2026-08-23 | OPEN | User | P3 design |
| OPEN-06 | Which regions are in scope beyond Ireland and London? | 2026-08-23 | OPEN | User | P0 dispatcher configuration |

---

## Register

<!-- generated:issue-register start -->
<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. Edit the registry, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

76 issues. 50 fixed, 26 open, 0 parked.

FIXED means the design decision is recorded, not that code exists. Implementation status lives only in `tasks/STATUS.md`.

| ID | Severity | Issue | Status | Detail |
| --- | --- | --- | --- | --- |
| ISS-001 | CRITICAL | Nine requirement areas as one project would produce a shallow scaffold of everything | FIXED | [ADR-0001](docs/adr/ADR-0001-decompose-into-sub-projects.md) |
| ISS-020 | CRITICAL | It reports, it does not prevent | OPEN | FEAT-014, FEAT-015 |
| ISS-033 | CRITICAL | The official Python base image ships with more than 400 known vulnerabilities before any application code is added | FIXED | [ADR-0010](docs/adr/ADR-0010-minimus-zero-cve-base-images.md) |
| ISS-034 | CRITICAL | Scanning only at build time reports zero forever while the deployed image degrades silently | FIXED | [docs/05-SECURITY.md](docs/05-SECURITY.md), nightly posture scan |
| ISS-055 | CRITICAL | No threat model exists for a platform holding organization wide financial data and cross account credentials in a financial services environment | FIXED | [A001-F11](audits/AUDIT-001-2026-08-23-full-project.md) -> [docs/08-THREAT-MODEL.md](docs/08-THREAT-MODEL.md) |
| ISS-005 | HIGH | A bespoke cost schema forces a migration per cloud provider | FIXED | [ADR-0002](docs/adr/ADR-0002-focus-canonical-schema.md) |
| ISS-006 | HIGH | Serving dashboards from Athena recreates the runaway query cost problem inside Meter | FIXED | [ADR-0003](docs/adr/ADR-0003-postgres-only-serving-layer.md) |
| ISS-007 | HIGH | Unblended per resource cost is meaningless with commitments in play | FIXED | [architecture](docs/02-ARCHITECTURE.md) |
| ISS-008 | HIGH | CUR is restated all month, so naive ingest double counts | FIXED | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 5.3 |
| ISS-009 | HIGH | Interface only scope enforcement is bypassable | FIXED | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 8 |
| ISS-010 | HIGH | ReadOnlyAccess grants data plane reads that cannot be defended | FIXED | [ADR-0004](docs/adr/ADR-0004-cross-account-access.md) |
| ISS-015 | HIGH | A failed collection rendered as zero silently produces wrong totals | FIXED | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 6 |
| ISS-016 | HIGH | Entitlement based visibility silently makes organization totals partial | FIXED | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 6 |
| ISS-021 | HIGH | No owner attribution, and an unowned finding is never fixed | OPEN | FEAT-016 |
| ISS-022 | HIGH | The cost model is never back tested against the bill | OPEN | FEAT-018 |
| ISS-028 | HIGH | No recommendation lifecycle, so recommendations are ignored | OPEN | FEAT-028 |
| ISS-029 | HIGH | No realized savings verification | OPEN | FEAT-029 |
| ISS-035 | HIGH | A dependency was addable with no vulnerability check, and most vulnerable code arrives transitively | FIXED | `make dep-check`, and a pipeline job on any manifest change |
| ISS-036 | HIGH | An unattended dependency upgrade that breaks production is worse than the vulnerability it closed | FIXED | Auto fix applies on a branch, gated on the full test suite, never auto merged |
| ISS-037 | HIGH | A single global refresh interval would be wasteful for billing data and useless for a cost control | FIXED | [ADR-0012](docs/adr/ADR-0012-collector-cadence-registry.md) |
| ISS-038 | HIGH | Reporting one timestamp lets a freshly collected copy of yesterday's data look current | FIXED | `as_of` and `collected_at` on every figure |
| ISS-045 | HIGH | A dependency blocked by the zero vulnerability rule had no defined escalation path, so the reuse ladder and the security gate deadlock each other | FIXED | [ADR-0013](docs/adr/ADR-0013-seven-rung-ladder-and-disqualification.md) |
| ISS-046 | HIGH | Feature status was maintained by hand in four places, the index, the roadmap, the status tracker and each feature document, which guarantees drift | FIXED | [ADR-0014](docs/adr/ADR-0014-generated-documentation.md) |
| ISS-047 | HIGH | A build on Apple Silicon produces an arm64 image and a push does not convert it, so an amd64 host fails with exec format error | FIXED | [docs/04-DEPLOYMENT.md](docs/04-DEPLOYMENT.md) |
| ISS-051 | HIGH | Images were signed at build time but the signature was never verified, so anyone able to push to ECR could place an unscanned image where the deploy would find it | FIXED | [docs/05-SECURITY.md](docs/05-SECURITY.md), verify-provenance runs before every deploy |
| ISS-056 | HIGH | No data classification or retention policy, while cloud_account.email already stores AWS account root email addresses, which are personal data | FIXED | [A001-F12](audits/AUDIT-001-2026-08-23-full-project.md) -> [docs/09-DATA-CLASSIFICATION.md](docs/09-DATA-CLASSIFICATION.md) |
| ISS-057 | HIGH | finops_mcp is absent from the pyproject packages and the import linter root packages, so the contract keeping it out of the service layer is unenforced | FIXED | [A001-F02](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-058 | HIGH | The issue register drifted: 22 issues existed only in docs/registry.yaml and not in tasks/ISSUES.md | FIXED | [A001-F01](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-059 | HIGH | The CI dependency-scan job runs scan.sh which requires gitleaks, but the security tools anchor does not install it, so the job exits 2 | FIXED | [A001-F03](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-060 | HIGH | make verify runs security-scan but nothing installs the scanners first, so a clean machine fails on tooling and it reads like a security failure | FIXED | [A001-F05](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-011 | MEDIUM | A model producing sizing numbers destroys trust on the first hallucination | FIXED | [ADR-0007](docs/adr/ADR-0007-llm-never-computes-a-number.md) |
| ISS-012 | MEDIUM | Organization wide AWS Config recording is a five figure monthly cost | OPEN | [tasks/ISSUES.md](tasks/ISSUES.md), resolved in P4 |
| ISS-013 | MEDIUM | Hundreds of describe loops for inventory is a year of work | FIXED | [roadmap](docs/01-ROADMAP.md) P4 |
| ISS-014 | MEDIUM | Neptune is a second database for capability not shown to be needed | FIXED | [ADR-0005](docs/adr/ADR-0005-postgres-adjacency-for-topology.md) |
| ISS-017 | MEDIUM | A local identity provider reaching production is a total auth bypass | FIXED | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 11 |
| ISS-018 | MEDIUM | Meter's own ingestion makes paid API calls and can become the cost problem | FIXED | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 5.5 |
| ISS-023 | MEDIUM | History as S3 snapshots cannot be queried or joined | OPEN | [roadmap](docs/01-ROADMAP.md) P2 |
| ISS-024 | MEDIUM | Only Amazon Managed Grafana is supported | OPEN | Blocked on OPEN-04 |
| ISS-025 | MEDIUM | The pattern is Grafana specific but the failure mode is not | OPEN | FEAT-019 |
| ISS-030 | MEDIUM | No data freshness contract | OPEN | FEAT-006 |
| ISS-031 | MEDIUM | No audit log for scope evaluation | OPEN | FEAT-007 |
| ISS-032 | MEDIUM | No accuracy contract on modelled figures | OPEN | FEAT-018 |
| ISS-039 | MEDIUM | A shell form CMD and a curl based HEALTHCHECK both break on a shell free runtime image | FIXED | Exec form only, health checking moved to the ALB target group |
| ISS-040 | MEDIUM | An allowlist entry with no expiry lapses silently into permanent acceptance | FIXED | `validate_allowlist.py` fails the build on an expired entry |
| ISS-041 | MEDIUM | Two vulnerability scanners disagree, and the disagreement is where a missed finding lives | FIXED | grype and trivy are merged, not chosen between, with the scanner recorded per finding |
| ISS-042 | MEDIUM | A feature with no document is a promise with nothing behind it | FIXED | 42 feature documents, enforced by `check_feature_docs.py` |
| ISS-043 | MEDIUM | Nothing showed how files actually depend on each other, so a layering violation was invisible | FIXED | `make graph`, which also fails on a layering violation |
| ISS-048 | MEDIUM | The database schema existed only inside a specification section, with no constraints, indexes, partitioning or migration rules recorded | FIXED | [docs/07-DATA-MODEL.md](docs/07-DATA-MODEL.md) |
| ISS-049 | MEDIUM | Six change log rows were missing their detail column, found by the registry parser rather than by a reader | FIXED | Registry generation makes a missing column impossible |
| ISS-050 | MEDIUM | The README described the project but did not tell a returning human where to look, what to run, or what happens to a security finding, so the knowledge lived only in conversation | FIXED | [README.md](README.md) |
| ISS-052 | MEDIUM | No local gate existed, so the first feedback on a secret, a writing rule breach or a bad dependency was the pipeline, minutes later | FIXED | Pre commit and pre push hooks, make hooks-install |
| ISS-053 | MEDIUM | LocalStack was undocumented, so its limits were invisible: it does not enforce IAM and its pagination and error codes differ from AWS | FIXED | [docs/04-DEPLOYMENT.md](docs/04-DEPLOYMENT.md) and inline in docker-compose.yml |
| ISS-061 | MEDIUM | make up mounts local-auth.yaml which is gitignored and has no example, so the first command a new engineer runs fails | FIXED | [A001-F04](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-062 | MEDIUM | ADR-0014 lists context_index.md as generated and no generator exists, so a file the reuse ladder depends on will stay empty | FIXED | [A001-F06](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-063 | MEDIUM | The interactive file graph renders nothing because cytoscape is never vendored and a CDN is ruled out | FIXED | [A001-F07](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-064 | MEDIUM | The MCP server has no build job, no ECR repository and no scan path, placing a fourth deployable outside the security gates | FIXED | [A001-F08](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-065 | MEDIUM | No disaster recovery position: no RPO, no RTO, no restore test, and Aurora defaults are not a decision | OPEN | [A001-F13](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-066 | MEDIUM | No observability plan for Meter itself, so a collector that silently stops pages nobody while the product serves confident stale numbers | OPEN | [A001-F14](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-067 | MEDIUM | No cost estimate for running Meter, which is the specific credibility failure a FinOps product exists to prevent in others | OPEN | [A001-F15](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-068 | MEDIUM | Missing governance files. CODEOWNERS matters most because ADR-0013 requires a security sign off and nothing defines who can give it | FIXED | [A001-F16](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-073 | MEDIUM | ExternalId rotation is not designed, so a leaked ExternalId has no defined replacement path | OPEN | [Threat model](docs/08-THREAT-MODEL.md) residual risk. Design before TASK-P0-014 |
| ISS-074 | MEDIUM | No per account API rate limit, so Meter could exhaust a member account quota and degrade their workloads | OPEN | [Threat model](docs/08-THREAT-MODEL.md) residual risk. Token bucket in the credential broker |
| ISS-075 | MEDIUM | Error messages may leak an account identifier across a scope boundary, and no test asserts otherwise | OPEN | [Threat model](docs/08-THREAT-MODEL.md) residual risk. Adversarial test in TASK-P0-024 |
| ISS-076 | MEDIUM | A model can narrate carelessly around a correct scope_coverage envelope, presenting a partial total as complete | OPEN | [Threat model](docs/08-THREAT-MODEL.md) residual risk. P7 eval suite must include a partial scope case |
| ISS-077 | MEDIUM | A deliberate backdoor in a package that scans clean is out of reach of any CVE scanner | OPEN | [Threat model](docs/08-THREAT-MODEL.md) residual risk. Mitigate by pinning digests and fewer dependencies |
| ISS-078 | MEDIUM | Unknown whether a regulatory retention floor exceeds the 37 month cost retention, which financial services often sets at 7 years | OPEN | [Data classification](docs/09-DATA-CLASSIFICATION.md) open question. Raised before data is aggregated away |
| ISS-079 | MEDIUM | The audit_event non erasure position needs sign off from whoever owns data protection | OPEN | [Data classification](docs/09-DATA-CLASSIFICATION.md) open question. Before the first production deployment |
| ISS-019 | LOW | A NAT Gateway for chatty cross account calls is billed per gigabyte | FIXED | [docs/04-DEPLOYMENT.md](docs/04-DEPLOYMENT.md) |
| ISS-026 | LOW | 2,740 lines in one file, against the 800 line ceiling | OPEN | [roadmap](docs/01-ROADMAP.md) P2 |
| ISS-027 | LOW | No automated tests in the prototype | OPEN | [roadmap](docs/01-ROADMAP.md) P2 |
| ISS-044 | LOW | Scripts were scattered between the root and one flat directory | FIXED | All under `scripts/`, grouped by purpose |
| ISS-054 | LOW | ECR tags were mutable, so a tag could be repointed at a different image after it was scanned and signed | FIXED | Set IMMUTABLE tags in TASK-P0-016 |
| ISS-069 | LOW | The PARTIAL ingest run status is permitted by a check constraint and defined nowhere, so it will be applied inconsistently | FIXED | [A001-F09](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-070 | LOW | The roadmap carries a generated status table and a hand written one describing the same sub projects | FIXED | [A001-F10](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-071 | LOW | No definition of done for any sub project beyond P0 | OPEN | [A001-F17](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-072 | LOW | No performance budget for ingestion throughput, full organization sweep time, or API latency under load | OPEN | [A001-F18](audits/AUDIT-001-2026-08-23-full-project.md) |

<!-- generated:issue-register end -->

## Detail and evidence

The narrative below is hand written and carries the reasoning behind each
resolution. The register above is generated from `docs/registry.yaml`, so the
identifiers and their state cannot diverge from the index. See ADR-0014.

## Issues

### Design and architecture

| ID | Severity | Issue | Found | Status | Resolution |
| --- | --- | --- | --- | --- | --- |
| ISS-001 | CRITICAL | Nine requirement areas treated as one project would produce a shallow scaffold of everything and a working version of nothing | 2026-08-23 | FIXED | Decomposed into eight sub projects, ADR-0001 |
| ISS-005 | HIGH | A bespoke internal cost schema would force a migration for every cloud provider added | 2026-08-23 | FIXED | FOCUS 1.1 adopted as canonical, ADR-0002 |
| ISS-006 | HIGH | Serving interactive dashboards from Athena would recreate, inside Meter, the exact runaway query cost problem the product exists to prevent | 2026-08-23 | FIXED | Athena is extract and load only. PostgreSQL serves pre aggregated rollups, ADR-0003 |
| ISS-007 | HIGH | Unblended per resource cost is meaningless when Reserved Instances and Savings Plans are in use | 2026-08-23 | FIXED | Amortized and net amortized are the primary measures. Unblended is retained for invoice reconciliation only |
| ISS-008 | HIGH | CUR is restated throughout the month, so a naive ingest double counts and makes trend lines jump | 2026-08-23 | FIXED | Idempotent upsert keyed on collector, scope and as of window, with an `as_of` column on every fact |
| ISS-009 | HIGH | Scope enforcement in the interface only can be bypassed by a route that forgets the dependency | 2026-08-23 | FIXED | Two independent enforcement points plus an adversarial test, in the P0 spec |
| ISS-010 | HIGH | The AWS managed `ReadOnlyAccess` policy grants S3 object reads, SSM parameter reads and Secrets metadata that Meter does not need and cannot defend in review | 2026-08-23 | FIXED | Curated policy of roughly 40 actions, ADR-0004 |
| ISS-011 | MEDIUM | A language model producing sizing numbers would destroy engineering trust on the first hallucinated figure | 2026-08-23 | FIXED | Deterministic computation only. The model explains and narrates, ADR-0007 |
| ISS-012 | MEDIUM | Recording all resource types organization wide in AWS Config is itself a five figure monthly line item | 2026-08-23 | OPEN | Mitigation decided: periodic recording for stable types, continuous for critical only. To be implemented and cost modelled in P4 |
| ISS-013 | MEDIUM | Writing hundreds of describe loops for inventory would take a year and hit rate limits | 2026-08-23 | FIXED | AWS Config aggregator is the inventory backbone, ADR-0005 and roadmap P4 |
| ISS-014 | MEDIUM | Neptune for topology is a second database, security boundary and cost centre for capability not yet shown to be needed | 2026-08-23 | FIXED | PostgreSQL adjacency tables with recursive CTEs, ADR-0005 |
| ISS-015 | HIGH | Collapsing a failed collection into the number zero silently produces wrong totals and destroys trust | 2026-08-23 | FIXED | Closed typed error taxonomy in the P0 spec, with a test asserting `NoData` and `AccessDenied` render differently |
| ISS-016 | HIGH | The entitlement list only contains accounts with a federated role, so log archive, shared services and newly vended accounts would be invisible and totals would be silently partial | 2026-08-23 | FIXED | The organization tree is the inventory of record. Every response carries `scope_coverage` and the interface states "showing N of M accounts" |
| ISS-017 | MEDIUM | A local development identity provider reaching production would be a total authentication bypass | 2026-08-23 | FIXED | The application refuses to start when the environment is production and the local provider is selected, with an integration test |
| ISS-018 | MEDIUM | Meter's own ingestion makes paid API calls, `GetMetricData` and Athena scanning in particular, so the platform can become the cost problem | 2026-08-23 | FIXED | Self metering is a P0 deliverable, tagged `finops:module`, shown on the front page |
| ISS-019 | LOW | A NAT Gateway for hundreds of chatty cross account calls is billed per hour and per gigabyte processed | 2026-08-23 | FIXED | VPC interface endpoints for STS, S3, SQS, Secrets Manager, Cost Explorer and Logs, in the P0 infrastructure section |

### Existing Grafana prototype, assessed 2026-08-23

The prototype is `sample_lambda.py`, 2,740 lines, from `publicsampledashboard.zip`.
It is good work. These are the gaps between it and a production module, and
they become the P2 backlog.

| ID | Severity | Issue | Status | Resolution |
| --- | --- | --- | --- | --- |
| ISS-020 | CRITICAL | It reports, it does not prevent. A report of money already burned is a post mortem, not a control | OPEN | P2: Amazon Managed Grafana `min_refresh_interval` floor, a continuous integration policy gate, and a CloudTrail `StartQuery` kill switch with AWS Budgets Actions |
| ISS-021 | HIGH | No owner attribution beyond the CloudTrail principal, and an unowned finding is never fixed | OPEN | P2: Grafana folder to team mapping, plus last editor from the Grafana API |
| ISS-022 | HIGH | The cost model is never back tested against the actual bill, so "modelled" stays unverifiable | OPEN | P2: back test against the CUR usage types for scanned bytes and metrics requested, and publish the accuracy percentage |
| ISS-023 | MEDIUM | History is kept as snapshot files in S3, which does not support querying, joining or retention policy | OPEN | P2: move history into the warehouse. The HTML report becomes one view, not the product |
| ISS-024 | MEDIUM | Only Amazon Managed Grafana is supported. Most organizations also run self hosted Grafana or Grafana Cloud | OPEN | P2, subject to OPEN-04 |
| ISS-025 | MEDIUM | The pattern is Grafana specific, but QuickSight, Athena workgroups, Redshift and OpenSearch Dashboards have the same failure mode | OPEN | P2: build as a query cost governance engine with Grafana as the first adapter |
| ISS-026 | LOW | 2,740 lines in a single file, against the 800 line project ceiling | OPEN | P2: decompose into scanner, classifier, cost model, measurement, trend and report modules during productionization |
| ISS-027 | LOW | No automated tests in the prototype | OPEN | P2: port the cost model with golden file tests as the first step |

### Requirement gaps found during review

Items that were not in the original requirement set but that production grade
demands. Recorded so that dropping one is a visible decision.

| ID | Severity | Gap | Status | Where it landed |
| --- | --- | --- | --- | --- |
| ISS-028 | HIGH | No recommendation lifecycle. Recommendations without an owner and a workflow are ignored every time | OPEN | P3 design: open, accepted, in progress, done, verified or regressed, with ticketing integration |
| ISS-029 | HIGH | No realized savings verification. Identified savings is a vanity metric that every tool inflates | OPEN | Adopted as the north star metric in `docs/00-GOAL.md`. Implemented in P3 |
| ISS-030 | MEDIUM | No data freshness contract. Users cannot tell whether a number is current | OPEN | P0: `as_of` on every fact, freshness on every screen, and a dedicated freshness screen |
| ISS-031 | MEDIUM | No audit log for scope evaluation, which is required to defend a global viewer credential | OPEN | P0: `audit_event` table, with global viewer access tagged separately |
| ISS-032 | MEDIUM | No accuracy contract on modelled figures anywhere in the product | OPEN | Principle set in `docs/00-GOAL.md`. Enforced per module, starting with ISS-022 |

---

