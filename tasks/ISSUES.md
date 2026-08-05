# Issues and open questions

Last updated: 2026-08-23
Update trigger: the moment an issue or open question is found, or closed

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

## Fixed and closed count

| Status | Count |
| --- | --- |
| FIXED | 14 |
| OPEN | 18 |
| PARKED | 1 |

Fixed here means the design decision is made and recorded. It does not mean
code exists. Implementation status lives in `tasks/STATUS.md`.
