# Issues and open questions

<!-- Basic boiler Plate Doc | Grade B
     Why this file exists: Every issue and open question, opened the moment it is found and
     closed the moment it is resolved.
     Grade B here: copy it, then replace all of the content. Keep the shape and the identifier
     scheme.
     Grades: A copy into a new project as is, no edits. B copy it and swap the
     names, paths or patterns named above. C leave behind, it is this project's
     own content rather than scaffolding, and is not tagged.
-->

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
<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. Edit docs/registry.yaml, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

133 issues. 92 fixed, 39 open, 0 parked.

FIXED means the design decision is recorded, not that code exists. Implementation status lives only in `tasks/STATUS.md`.

| ID | Severity | Issue | Status | Detail |
| --- | --- | --- | --- | --- |
| ISS-001 | CRITICAL | Nine requirement areas as one project would produce a shallow scaffold of everything | FIXED | [ADR-0001](docs/adr/ADR-0001-decompose-into-sub-projects.md) |
| ISS-020 | CRITICAL | It reports, it does not prevent | OPEN | FEAT-014, FEAT-015 |
| ISS-033 | CRITICAL | The official Python base image ships with more than 400 known vulnerabilities before any application code is added | FIXED | [ADR-0010](docs/adr/ADR-0010-minimus-zero-cve-base-images.md) |
| ISS-034 | CRITICAL | Scanning only at build time reports zero forever while the deployed image degrades silently | FIXED | [docs/05-SECURITY.md](docs/05-SECURITY.md), nightly posture scan |
| ISS-055 | CRITICAL | No threat model exists for a platform holding organization wide financial data and cross account credentials in a financial services environment | FIXED | [A001-F11](audits/AUDIT-001-2026-08-23-full-project.md) -> [docs/08-THREAT-MODEL.md](docs/08-THREAT-MODEL.md) |
| ISS-097 | CRITICAL | The stated policy of zero vulnerabilities at any severity is unachievable: every Python base image carries unfixable CPython findings, so the rule would have been routed around rather than met | FIXED | [ADR-0018](docs/adr/ADR-0018-zero-fixable-not-zero-findings.md). Threshold is now zero findings that have a published fix |
| ISS-124 | CRITICAL | The security report parsed only the Vulnerabilities array from the trivy output and never the Misconfigurations array, so every infrastructure as code finding was dropped and the gate printed PASS over them | FIXED | Invisible while infra/terraform did not exist, because the scanner then had nothing to find and agreed with the parser. The first Terraform commit produced seven findings, two CRITICAL, and make security-scan reported zero. Four were real and were fixed: unrestricted egress, Performance Insights without a customer managed key, no VPC flow logs, and no S3 access logging. Five are deliberate and are now recorded in accepted.yaml with an argument |
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
| ISS-085 | HIGH | Nothing scans what leaves for the language model provider, so a secret could be sent outbound in a prompt | OPEN | FEAT-046. Seven scanners cover what comes in and none cover what goes out |
| ISS-090 | HIGH | A self hosted Grafana in a private subnet is not reachable from the hub VPC, so its queries cannot be scanned | OPEN | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) section 12. Instance marked unreachable and excluded with a stated note. Agent based collection is a later sub project |
| ISS-092 | HIGH | A deny action can cut an engineer off from Logs Insights during an incident, when it is exactly the tool they need | OPEN | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) section 12. Auto expiry, a never deny list, a revoke route and an enforcement screen |
| ISS-093 | HIGH | The modelled query cost has no published accuracy, so every figure is a projection presented alongside measured ones | OPEN | FEAT-018. Until it lands, every modelled figure carries a visible caveat |
| ISS-098 | HIGH | The chosen base image versions were picked by habit, not measurement. python 3.12 carried 3 High findings and nginx 1.27 carried 93 including 6 Critical | FIXED | Moved to python 3.13 and nginx 1.30, both measured at TASK-P0-029. node:22-dev was already clean |
| ISS-102 | HIGH | Every honesty guarantee in the product is enforced by a database constraint and then delivered by an undesigned pixel, so the constraint work could be thrown away in the last six inches | FIXED | [docs/12-UI-DESIGN.md](docs/12-UI-DESIGN.md). The Figure component makes a number unrenderable without its provenance |
| ISS-110 | HIGH | The import linter contracts forbidding external modules never worked: include_external_packages was not set, so boto3, fastapi and sqlalchemy were never checked and the contract looked like protection it was not providing | FIXED | Set in `pyproject.toml`, and verified by probe: finops_core importing boto3 now breaks the contract |
| ISS-111 | HIGH | The restore drill required by TASK-P0-028 has not been performed, because it needs an Aurora cluster to restore into a scratch database. P0 is not signed off until it is | OPEN | [P0 plan](docs/plans/P0-implementation-plan.md) TASK-P0-028 |
| ISS-114 | HIGH | The API image could never have started. Its CMD named finops_api.main:app and no such module level symbol has ever existed, so every deploy of that image would have failed at startup with an attribute error and nothing in the build would have caught it | FIXED | Found while adding the MCP server's command to the same image. Fixed with a bootstrap factory and `--factory`, and a test in `tests/mcp/test_contract.py` now imports every target the Dockerfile names |
| ISS-118 | HIGH | Five pipeline jobs called make on images that do not have it, so each would have failed with "make - command not found" before running a single check | FIXED | `python:slim` is Debian with no build tools. Fixed with a shared before_script, and `tests/scripts/test_pipeline.py` now fails when a job calls make on an image without it |
| ISS-122 | HIGH | No Terraform stack has been planned or applied. terraform validate and fmt pass on all three, which checks syntax, provider schema and references, and checks nothing about whether the stack builds | OPEN | A plan needs real credentials for the S3 state backend and for the caller identity data sources. Also outstanding from TASK-P0-033: the screenshot of a stalled collector in ALARM. P0 is not signed off until a plan runs |
| ISS-132 | HIGH | A CloudWatch metric maths expression using the FILTER function is classified as Logs Insights, because the engine test is a substring match on "filter " in the expression | OPEN | Pinned by tests/query/test_classify.py rather than fixed, because TASK-P2-002 is an extraction and changing it moves real numbers. The consequence is a metric query priced as a log scan, which overstates it by orders of magnitude. Fix in its own commit where the golden diff shows which figures moved |
| ISS-135 | HIGH | finops_query was in no layer list, so nothing constrained what it could import. Not the import-linter contract, not the graph builder, and not the distribution's own packages | FIXED | It could have imported finops_api and all three checks would have passed. Holding the two orderings equal did not catch it, because they agreed about a package neither mentioned. tests/scripts/test_layer_agreement.py now asserts every declared package has a layer, and the constraint was probed by importing finops_api and confirming it breaks |
| ISS-136 | HIGH | A failed request renders default coverage as though it were a complete answer. With no envelope the shell falls back to 0 of 0 and prints "Showing all 0 accounts" beside the typed failure, which reads as confident complete coverage of an empty estate. Section 6 of docs/12-UI-DESIGN.md requires complete coverage to say so, and section 4 requires an unknown state to suppress the figure rather than default it. Observed on 2026-09-06 running the P0 frontend with no API reachable | OPEN | [docs/12-UI-DESIGN.md](docs/12-UI-DESIGN.md) sections 4 and 6, `finops-web/src/shell/AppShell.tsx` |
| ISS-011 | MEDIUM | A model producing sizing numbers destroys trust on the first hallucination | FIXED | [ADR-0007](docs/adr/ADR-0007-llm-never-computes-a-number.md) |
| ISS-012 | MEDIUM | Organization wide AWS Config recording is a five figure monthly cost | OPEN | [tasks/ISSUES.md](tasks/ISSUES.md), resolved in P4 |
| ISS-013 | MEDIUM | Hundreds of describe loops for inventory is a year of work | FIXED | [roadmap](docs/01-ROADMAP.md) P4 |
| ISS-014 | MEDIUM | Neptune is a second database for capability not shown to be needed | FIXED | [ADR-0005](docs/adr/ADR-0005-postgres-adjacency-for-topology.md) |
| ISS-017 | MEDIUM | A local identity provider reaching production is a total auth bypass | FIXED | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 11 |
| ISS-018 | MEDIUM | Meter's own ingestion makes paid API calls and can become the cost problem | FIXED | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 5.5 |
| ISS-023 | MEDIUM | History as S3 snapshots cannot be queried or joined | OPEN | [roadmap](docs/01-ROADMAP.md) P2 |
| ISS-024 | MEDIUM | Only Amazon Managed Grafana is supported | BY DESIGN | Raised against the prototype as a gap. OPEN-04 was re answered on 2026-09-02 as Amazon Managed Grafana only, so this is the decision rather than a defect. It is not FIXED: nothing was built. Reopen it if self hosted or Grafana Cloud is ever wanted, and reinstate TASK-P2-007 and TASK-P2-008 with it |
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
| ISS-065 | MEDIUM | No disaster recovery position: no RPO, no RTO, no restore test, and Aurora defaults are not a decision | FIXED | [A001-F13](audits/AUDIT-001-2026-08-23-full-project.md) -> [Architecture, disaster recovery](docs/02-ARCHITECTURE.md) |
| ISS-066 | MEDIUM | No observability plan for Meter itself, so a collector that silently stops pages nobody while the product serves confident stale numbers | FIXED | [A001-F14](audits/AUDIT-001-2026-08-23-full-project.md) -> [docs/10-OBSERVABILITY.md](docs/10-OBSERVABILITY.md) |
| ISS-067 | MEDIUM | No cost estimate for running Meter, which is the specific credibility failure a FinOps product exists to prevent in others | FIXED | [A001-F15](audits/AUDIT-001-2026-08-23-full-project.md) -> [Deployment, what it costs to run](docs/04-DEPLOYMENT.md) |
| ISS-068 | MEDIUM | Missing governance files. CODEOWNERS matters most because ADR-0013 requires a security sign off and nothing defines who can give it | FIXED | [A001-F16](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-073 | MEDIUM | ExternalId rotation is not designed, so a leaked ExternalId has no defined replacement path | OPEN | [Threat model](docs/08-THREAT-MODEL.md) residual risk. Design before TASK-P0-014 |
| ISS-074 | MEDIUM | No per account API rate limit, so Meter could exhaust a member account quota and degrade their workloads | OPEN | [Threat model](docs/08-THREAT-MODEL.md) residual risk. Token bucket in the credential broker |
| ISS-075 | MEDIUM | Error messages may leak an account identifier across a scope boundary, and no test asserts otherwise | OPEN | [Threat model](docs/08-THREAT-MODEL.md) residual risk. Adversarial test in TASK-P0-024 |
| ISS-076 | MEDIUM | A model can narrate carelessly around a correct scope_coverage envelope, presenting a partial total as complete | OPEN | [Threat model](docs/08-THREAT-MODEL.md) residual risk. P7 eval suite must include a partial scope case |
| ISS-077 | MEDIUM | A deliberate backdoor in a package that scans clean is out of reach of any CVE scanner | OPEN | [Threat model](docs/08-THREAT-MODEL.md) residual risk. Mitigate by pinning digests and fewer dependencies |
| ISS-078 | MEDIUM | Unknown whether a regulatory retention floor exceeds the 37 month cost retention, which financial services often sets at 7 years | OPEN | [Data classification](docs/09-DATA-CLASSIFICATION.md) open question. Raised before data is aggregated away |
| ISS-079 | MEDIUM | The audit_event non erasure position needs sign off from whoever owns data protection | OPEN | [Data classification](docs/09-DATA-CLASSIFICATION.md) open question. Before the first production deployment |
| ISS-080 | MEDIUM | VPC interface endpoints were justified on cost, and the arithmetic shows NAT is cheaper below roughly 1,560 GB per month, which is far above Meter actual egress | FIXED | Found while writing the cost estimate. [Deployment, network](docs/04-DEPLOYMENT.md). Decision stands on security grounds, stated honestly |
| ISS-082 | MEDIUM | Cost finding severity was a chosen label rather than derived from impact, so the ranking reflected the author rather than the money | FIXED | [ADR-0016](docs/adr/ADR-0016-dollar-based-severity.md) |
| ISS-083 | MEDIUM | Anomaly detection had no thresholds defined at all, which is how anomaly detection becomes noise and gets muted | FIXED | [Competitive review](docs/11-COMPETITIVE-REVIEW.md). FEAT-023 amended with three concurrent thresholds |
| ISS-084 | MEDIUM | The topology graph was built and used only for drawing, when it can score the blast radius of a change and gate auto apply | OPEN | FEAT-044 |
| ISS-086 | MEDIUM | Allocation had no export path, and finance does not work inside the product interface | OPEN | FEAT-045 |
| ISS-087 | MEDIUM | Feature flag owners and CODEOWNERS entries are placeholders, and a flag with no named owner is a branch nobody will ever remove | OPEN | `make check-docs` warns on each. Becomes an error before the first merge request |
| ISS-088 | MEDIUM | Values were being written into code, compose and the Makefile with no single place to change them and no note of what each one does | FIXED | [ADR-0017](docs/adr/ADR-0017-configuration-and-feature-flags.md), `.env.example`, enforced by `scripts/ci/check_hardcoded.py` |
| ISS-089 | MEDIUM | The management account dependency sat on the critical path, blocking the credential broker and everything downstream of it | FIXED | Organizations is emulated by LocalStack, so the whole organization path is built and tested locally. The real management account is needed only for final verification. ISS-002 downgraded |
| ISS-091 | MEDIUM | Scanning Grafana Cloud puts a third party API key inside Meter, which the threat model does not currently cover | OPEN | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) section 12. Needs a new row in threat model boundary 5 |
| ISS-094 | MEDIUM | A change to the Grafana dashboard JSON shape could cause silent under reporting | OPEN | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) section 6. SchemaDrift is loud by design and an unrecognised panel raises rather than being skipped |
| ISS-095 | MEDIUM | Nobody owns the never deny list, and enabling deny without one risks cutting off incident response | OPEN | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) section 13. Blocks enabling deny, not building it |
| ISS-099 | MEDIUM | Base image tags were floating, so a build was not reproducible and a tag could be repointed after it was scanned | FIXED | `docker/base-images.lock` with resolved digests, `make base-images-check` fails on drift |
| ISS-100 | MEDIUM | Three unfixable CPython findings are accepted on a reachability argument that depends on nobody importing stringprep, poplib or urllib.request | OPEN | Enforced by `scripts/ci/check_forbidden_imports.py`, which fails the build. Review 2026-11-21 |
| ISS-103 | MEDIUM | No component inventory existed, so each sub project would have invented its own table and the product would acquire several visual languages | FIXED | [docs/12-UI-DESIGN.md](docs/12-UI-DESIGN.md) section 11, built once in P0 |
| ISS-104 | MEDIUM | No accessibility position, when provenance encoded by colour alone would fail for roughly 8 percent of men, in print, and in a screenshot pasted into a ticket | FIXED | [docs/12-UI-DESIGN.md](docs/12-UI-DESIGN.md) section 9. Provenance carried redundantly by fill, prefix and label |
| ISS-105 | MEDIUM | No state matrix, so loading, empty, partial, stale, degraded and failed would each be improvised per screen and several would be missed | FIXED | [docs/12-UI-DESIGN.md](docs/12-UI-DESIGN.md) section 8. Seven states, enforced by StateBoundary |
| ISS-106 | MEDIUM | TASK-P0-029 was completed without its Status, evidence or deviation being recorded in the plan, so the plan read as though no work had been done | FIXED | Plan corrected. The deviation, that 029 created package namespaces belonging to TASK-P0-001, is now recorded rather than absorbed |
| ISS-107 | MEDIUM | tasks/STATUS.md hand maintained a second copy of the plan task list and had drifted, showing 31 tasks and a finished task as not started | FIXED | Generated from the plan files by `scripts/docs/sync.py`. Each generated block now names its own source rather than all claiming the registry |
| ISS-108 | MEDIUM | project_map.md and CLAUDE.md named the Python packages with hyphens, finops-core rather than finops_core, so a reader following either would look for a directory that cannot exist because a Python package cannot contain a hyphen | FIXED | Both corrected and the map verified against the tree. Also fixed: the map claimed PLANNED modules had no directory, which stopped being true at TASK-P0-029, the feature count said 42 against an actual 50, and nine files were absent from the listing |
| ISS-109 | MEDIUM | Two of the five forbidden targets in the finops_mcp import contract are inert because finops_api.db and finops_api.guards do not exist yet, so the contract reads as more protective than it currently is | FIXED | Noted in `pyproject.toml`. TASK-P0-011 and TASK-P0-024 each carry a probe to confirm the contract fires once the module exists |
| ISS-112 | MEDIUM | TASK-P0-029 was marked done without running the dependency admission gate, one of its acceptance criteria | FIXED | Run 2026-10-07 against the full resolved tree: grype 0 findings across 97 packages, pip-audit 0 advisories across 113. Recorded in the task evidence |
| ISS-115 | MEDIUM | The layer ordering was written down twice and the two disagreed. pyproject.toml put finops_mcp above finops_api, correctly, and scripts/docs/build_file_graph.py put it below, so the graph check was enforcing the opposite of constraint 8 for that pair | FIXED | Neither check noticed, because each was internally consistent. Corrected in the graph builder and held equal by `tests/scripts/test_layer_agreement.py` |
| ISS-116 | MEDIUM | Two issue numbers were used twice each. ISS-110 and ISS-111 each named two different issues, so half of them could not be referred to unambiguously | FIXED | The later entries renumbered to ISS-112 and ISS-113. `scripts/docs/sync.py` now fails on a duplicate identifier in any section of the registry |
| ISS-119 | MEDIUM | The pipeline documentation gate ran three of the eight checks in make check-docs. The other five ran only in `make verify` on a contributor's own machine | FIXED | The five were the registry sync check, the context index check, the feature flag check, the hardcoded value check and the forbidden import check. The job now runs the target |
| ISS-120 | MEDIUM | The automated code review ran on merge requests only, leaving the default branch, the one everything deploys from, as the one branch nothing reviewed | FIXED | A default branch rule added, and the report is now exposed on the pipeline rather than only attached |
| ISS-123 | MEDIUM | .terraform.lock.hcl was gitignored, so the provider version could differ between the pipeline and a contributor's machine while base images were pinned by digest | FIXED | The constraint is `~> 6.0`, which lets any 6.x resolve. The lock files are now committed for linux_amd64 and darwin_arm64, matching the reproducibility argument in docker/base-images.lock |
| ISS-125 | MEDIUM | Mapping trivy's Resolution field onto fixed_in made the gate treat every misconfiguration as fixable by upgrade, so an acceptance record could never apply to one | FIXED | Resolution is advice text rather than a version. A misconfiguration is a design choice, so it is either changed or accepted under ADR-0018, and the advice now goes in the description |
| ISS-126 | MEDIUM | scripts/ and migrations/ were outside PY_SRC, so neither was linted or format checked, and mypy was pointed at four packages by name, silently skipping finops_mcp, both directories and the whole test suite | FIXED | 10 ruff findings and 36 mypy errors had accumulated unreported. Two were real: a list annotated flat while it held groups, and load_allowlist declaring a str key while the code keyed on a tuple, which is the only place a reader learns what an entry must match on. tests/scripts/test_lint_scope.py now asks the filesystem which directories hold Python and fails when one is not covered |
| ISS-127 | MEDIUM | Twelve type ignore comments in the test suite were stale, silencing errors that no longer existed and standing ready to silence whatever landed on those lines next | FIXED | Found the moment mypy was pointed at tests/ for the first time. All twelve removed rather than narrowed, and the four genuinely needed ones now carry a comment saying why |
| ISS-128 | MEDIUM | The memory gate rejected the one resume vector format CLAUDE.md asks for. It read `file.py:88` as a filename ending in colon eighty eight, so every citation with a line number failed as a path that does not exist | FIXED | CLAUDE.md asks a resume vector for exact files and line numbers. The suffix is now split off and the line checked against the length of the file, so a citation past the end of a file fails too. Probed by citing line 9999 and confirming it is caught |
| ISS-130 | MEDIUM | sync.py counted any task status it did not recognise as not started, so descoping two P2 tasks left the plan reading as 22 tasks of work remaining rather than 20, and the descoped tasks did not appear in the exceptions table either | FIXED | A Descoped bucket added, and an unrecognised status now raises rather than being absorbed. Probed by setting a status of Parked and confirming the generator refuses it |
| ISS-133 | MEDIUM | An unrecognised datasource reports its own type as the engine, so a Postgres panel is priced at zero rather than reported as not understood | OPEN | Zero reads as free. The honest answer for an engine with no rate is that the query was not priced, which is a different thing from a query that costs nothing. Pinned by tests/query/test_classify.py. Fix alongside ISS-132 |
| ISS-134 | MEDIUM | check_hardcoded.py never scanned finops_query, so TASK-P2-002's criterion that the gate passes was satisfied over code the gate had not read | FIXED | check_forbidden_imports.py already listed the package and this one did not, which is what two lists of one thing produces. Now 76 files scanned where 73 were, and probed by planting a region literal in cost_model.py and confirming it is caught |
| ISS-019 | LOW | A NAT Gateway for chatty cross account calls is billed per gigabyte | FIXED | [docs/04-DEPLOYMENT.md](docs/04-DEPLOYMENT.md) |
| ISS-026 | LOW | 2,740 lines in one file, against the 800 line ceiling | OPEN | [roadmap](docs/01-ROADMAP.md) P2 |
| ISS-027 | LOW | No automated tests in the prototype | OPEN | [roadmap](docs/01-ROADMAP.md) P2 |
| ISS-044 | LOW | Scripts were scattered between the root and one flat directory | FIXED | All under `scripts/`, grouped by purpose |
| ISS-054 | LOW | ECR tags were mutable, so a tag could be repointed at a different image after it was scanned and signed | FIXED | Set IMMUTABLE tags in TASK-P0-016 |
| ISS-069 | LOW | The PARTIAL ingest run status is permitted by a check constraint and defined nowhere, so it will be applied inconsistently | FIXED | [A001-F09](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-070 | LOW | The roadmap carries a generated status table and a hand written one describing the same sub projects | FIXED | [A001-F10](audits/AUDIT-001-2026-08-23-full-project.md) |
| ISS-071 | LOW | No definition of done for any sub project beyond P0 | FIXED | [A001-F17](audits/AUDIT-001-2026-08-23-full-project.md) -> [Roadmap, exit criteria](docs/01-ROADMAP.md) |
| ISS-072 | LOW | No performance budget for ingestion throughput, full organization sweep time, or API latency under load | FIXED | [A001-F18](audits/AUDIT-001-2026-08-23-full-project.md) -> [P0 spec section 11b](docs/specs/2026-08-23-p0-foundation-design.md) |
| ISS-081 | LOW | The pxpipe proxy currently compresses nothing, every request skipped as unsupported_model, so it provides accounting rather than savings. Its log is also machine global rather than scoped to this project | OPEN | Documented in [README.md](README.md). Re check with make stats after a session on the current model |
| ISS-096 | LOW | Unknown whether any dashboards are managed as code today, which determines the value of the CI policy gate | OPEN | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) section 13. Affects FEAT-014 scope |
| ISS-101 | LOW | The doc and policy scripts claimed to run before make setup, but pyyaml is absent from a system interpreter and PEP 668 blocks adding it | FIXED | They now run from the project venv, and `scripts/README.md` states this rather than the previous claim |
| ISS-113 | LOW | make lint failed on a terraform directory that Wave D has not created yet, leaving verify red for a reason unrelated to the change under review | FIXED | [P0 plan](docs/plans/P0-implementation-plan.md) TASK-P0-002 |
| ISS-117 | LOW | Docstring coverage on public symbols is 70.8 percent and the gate is set to that figure, so it blocks a drop but does not yet require 80 to match the test coverage floor | OPEN | The gap is real work rather than noise: the missing entries are classes and public methods such as OrgRepository and its list_tree, not restatements of a name. Raise fail-under in `[tool.interrogate]` as they are written. Never lower it |
| ISS-121 | LOW | The plan and the runbook index both said two alerts page. The alert table in docs/10-OBSERVABILITY.md marks four | FIXED | Both were misreadings of the sentence under the table: two of the four are unusual, which is not the same as two being the total. The table was followed, the two summaries corrected, and a test now holds the paging set against the four names |
| ISS-129 | LOW | The QuerySurface port has one implementation rather than three, so the abstraction is carrying no weight and could be read as speculative generality | BY DESIGN | Kept deliberately. The port exists for the fake, which is what lets the cost model be tested without a Grafana at all, and that is weight enough on its own. A second real strategy is a connector rather than a rewrite if OPEN-04 is ever re answered again |
| ISS-131 | LOW | The prototype emitted em dashes into generated UI copy, which the project's writing rules forbid, and its copy was excluded from make check-writing while it was a frozen baseline | FIXED | Fixed by deletion at TASK-P2-003 rather than by editing, which was never permitted while the file was a baseline. The exclusion went with the directory. One of the six survives as a recorded divergence in tests/query/test_cost_model.py, because the golden files still hold the string the prototype produced |

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

