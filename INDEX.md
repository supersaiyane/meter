# Meter: master index

Last updated: 2026-08-23
Update trigger: every material change. See [change control](docs/03-CHANGE-CONTROL.md)
Consistency check: `make check-docs`

This is the entry point for the whole project. Every feature, decision, change,
issue and open question is listed here with a pointer to the document holding
the detail. If something is not in this index, it does not exist as far as the
project is concerned.

**How to use it.** Find the row, follow the reference, and read the detail
there. Do not treat a row in this table as the specification. The row is the
pointer, the referenced document is the truth.

---

## 1. Where to start

| I want to know | Read |
| --- | --- |
| Why this project exists and what counts as success | [docs/00-GOAL.md](docs/00-GOAL.md) |
| What is being built and in what order | [docs/01-ROADMAP.md](docs/01-ROADMAP.md) |
| How the pieces fit together | [docs/02-ARCHITECTURE.md](docs/02-ARCHITECTURE.md) |
| Where a change is recorded | [docs/03-CHANGE-CONTROL.md](docs/03-CHANGE-CONTROL.md) |
| How code reaches production | [docs/04-DEPLOYMENT.md](docs/04-DEPLOYMENT.md) |
| The rules a change must follow | [CLAUDE.md](CLAUDE.md) |
| What is done and what is left | [tasks/STATUS.md](tasks/STATUS.md) |
| What is broken or undecided | [tasks/ISSUES.md](tasks/ISSUES.md) |
| Where the last session stopped | [docs/checkpoint.md](docs/checkpoint.md) |
| The module layout | [project_map.md](project_map.md) |
| Where a function lives | [context_index.md](context_index.md) |
| Corrections already received | [tasks/lessons.md](tasks/lessons.md) |

---

## 2. Features

41 features across eight sub projects. Status is `Planned`, `Specified`,
`In build`, or `Delivered`.

### P0 Foundation

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| FEAT-001 | Account onboarding and organization topology, parent to child map | Specified | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 5.2, 7 |
| FEAT-002 | Cross account credential brokering by StackSet deployed role | Specified | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 10, [ADR-0004](docs/adr/ADR-0004-cross-account-access.md) |
| FEAT-003 | Provider port abstraction, eight ports | Specified | [architecture](docs/02-ARCHITECTURE.md) section "Ports" |
| FEAT-004 | FOCUS 1.1 canonical cost schema | Specified | [ADR-0002](docs/adr/ADR-0002-focus-canonical-schema.md) |
| FEAT-005 | Ingestion framework, idempotent and partial failure tolerant | Specified | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 7 |
| FEAT-006 | Typed error taxonomy and data freshness contract | Specified | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 6 |
| FEAT-007 | Authorization scope enforcement, two independent points | Specified | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 6, [ADR-0008](docs/adr/ADR-0008-identity-adapter-deferred.md) |
| FEAT-008 | Platform self metering | Specified | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 5.5 |
| FEAT-009 | Organization map, tree and graph views | Specified | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 9 |
| FEAT-010 | Ingest and freshness surface | Specified | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 9 |

### P2 Query Cost Governance

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| FEAT-011 | Grafana workspace, dashboard and alert rule scanner | Planned | [roadmap](docs/01-ROADMAP.md) P2. Prototype exists |
| FEAT-012 | Query cost model, Logs Insights and metric engines | Planned | [roadmap](docs/01-ROADMAP.md) P2. Prototype exists |
| FEAT-013 | Measured overlay from CloudTrail and DescribeQueries | Planned | [roadmap](docs/01-ROADMAP.md) P2. Prototype exists |
| FEAT-014 | Preventive controls: refresh floor and CI policy gate | Planned | [roadmap](docs/01-ROADMAP.md) P2. Addresses ISS-020 |
| FEAT-015 | Near real time kill switch with Budgets Actions | Planned | [roadmap](docs/01-ROADMAP.md) P2. Addresses ISS-020 |
| FEAT-016 | Owner attribution from folder, team and last editor | Planned | [roadmap](docs/01-ROADMAP.md) P2. Addresses ISS-021 |
| FEAT-017 | Auto remediation with change record and undo | Planned | [roadmap](docs/01-ROADMAP.md) P2 |
| FEAT-018 | Cost model calibration against actual CUR usage types | Planned | [roadmap](docs/01-ROADMAP.md) P2. Addresses ISS-022 |
| FEAT-019 | Multi platform query governance: QuickSight, Athena, Redshift, OpenSearch | Planned | [roadmap](docs/01-ROADMAP.md) P2. Addresses ISS-025 |

### P1 Cost Intelligence

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| FEAT-020 | CUR 2.0 ingest with resource identifiers and split cost allocation | Planned | [roadmap](docs/01-ROADMAP.md) P1 |
| FEAT-021 | Cost rollups, trends and per resource attribution | Planned | [roadmap](docs/01-ROADMAP.md) P1 |
| FEAT-022 | Allocation, showback and the unallocated bucket | Planned | [roadmap](docs/01-ROADMAP.md) P1 |
| FEAT-023 | Anomaly detection and ingest of AWS Cost Anomaly Detection | Planned | [roadmap](docs/01-ROADMAP.md) P1 |
| FEAT-024 | Savings Plan and Reserved Instance utilization and coverage | Planned | [roadmap](docs/01-ROADMAP.md) P1 |

### P3 Utilization and Rightsizing

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| FEAT-025 | Cost Optimization Hub, Compute Optimizer and Trusted Advisor ingest | Planned | [ADR-0006](docs/adr/ADR-0006-aws-native-recommendations-first.md) |
| FEAT-026 | Bespoke waste collectors where AWS is blind | Planned | [ADR-0006](docs/adr/ADR-0006-aws-native-recommendations-first.md) |
| FEAT-027 | CloudWatch cost module: retention, unqueried logs, stale alarms | Planned | [roadmap](docs/01-ROADMAP.md) P3 |
| FEAT-028 | Recommendation lifecycle with owner and ticketing | Planned | [roadmap](docs/01-ROADMAP.md) P3. Addresses ISS-028 |
| FEAT-029 | Realized savings verification, the north star metric | Planned | [docs/00-GOAL.md](docs/00-GOAL.md). Addresses ISS-029 |

### P4 Inventory and Topology

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| FEAT-030 | AWS Config aggregator inventory by region and zone | Planned | [roadmap](docs/01-ROADMAP.md) P4 |
| FEAT-031 | Topology graph, node and edge model | Planned | [ADR-0005](docs/adr/ADR-0005-postgres-adjacency-for-topology.md) |
| FEAT-032 | Topology map interface | Planned | [roadmap](docs/01-ROADMAP.md) P4 |

### P5 Quotas and Limits

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| FEAT-033 | Quota utilization per service per region, with stated coverage gaps | Planned | [roadmap](docs/01-ROADMAP.md) P5 |
| FEAT-034 | Quota increase request workflow | Planned | [roadmap](docs/01-ROADMAP.md) P5 |

### P6 Containers

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| FEAT-035 | EKS pod level cost from split cost allocation data | Planned | [roadmap](docs/01-ROADMAP.md) P6 |
| FEAT-036 | In cluster telemetry, requested versus used | Planned | [roadmap](docs/01-ROADMAP.md) P6 |
| FEAT-037 | ECS task and Fargate utilization, snapped to valid sizes | Planned | [roadmap](docs/01-ROADMAP.md) P6 |

### P7 Insight and LLM layer

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| FEAT-038 | Natural language cost query over a governed semantic layer | Planned | [ADR-0007](docs/adr/ADR-0007-llm-never-computes-a-number.md) |
| FEAT-039 | Anomaly narration correlating cost, Config and CloudTrail | Planned | [ADR-0007](docs/adr/ADR-0007-llm-never-computes-a-number.md) |
| FEAT-040 | Remediation authoring as an infrastructure as code pull request | Planned | [ADR-0007](docs/adr/ADR-0007-llm-never-computes-a-number.md) |
| FEAT-041 | Per team digests and executive summaries | Planned | [roadmap](docs/01-ROADMAP.md) P7 |

---

## 3. Architecture decision records

| ID | Decision | Status | Detail |
| --- | --- | --- | --- |
| ADR-0001 | Decompose into eight sub projects, build P0 then P2 then P1 | Accepted | [ADR-0001](docs/adr/ADR-0001-decompose-into-sub-projects.md) |
| ADR-0002 | FOCUS 1.1 is the canonical cost schema | Accepted | [ADR-0002](docs/adr/ADR-0002-focus-canonical-schema.md) |
| ADR-0003 | PostgreSQL only for the serving layer, no ClickHouse in P0 | Accepted | [ADR-0003](docs/adr/ADR-0003-postgres-only-serving-layer.md) |
| ADR-0004 | Cross account access by StackSet deployed role, curated policy | Accepted | [ADR-0004](docs/adr/ADR-0004-cross-account-access.md) |
| ADR-0005 | PostgreSQL adjacency tables for topology, not a graph database | Accepted | [ADR-0005](docs/adr/ADR-0005-postgres-adjacency-for-topology.md) |
| ADR-0006 | Ingest AWS native recommendation services before building a collector | Accepted | [ADR-0006](docs/adr/ADR-0006-aws-native-recommendations-first.md) |
| ADR-0007 | The language model never computes a number | Accepted | [ADR-0007](docs/adr/ADR-0007-llm-never-computes-a-number.md) |
| ADR-0008 | Identity adapter deferred, isolated behind two ports | Accepted | [ADR-0008](docs/adr/ADR-0008-identity-adapter-deferred.md) |

Index of records: [docs/adr/README.md](docs/adr/README.md)

---

## 4. Change log

| ID | Date | Type | What changed | Commit | Detail |
| --- | --- | --- | --- | --- | --- |
| CHG-0001 | 2026-08-23 | Process | Repository initialized. Goal, roadmap, architecture, eight ADRs, P0 specification, status, issues, lessons, project map, checkpoint | `e604ea9` to `6e2afcc` | [docs/checkpoint.md](docs/checkpoint.md) |
| CHG-0002 | 2026-08-23 | Process | Checkpoint log and project map moved to the paths the session enforcement script requires | `93e15aa` | [docs/checkpoint.md](docs/checkpoint.md) |
| CHG-0003 | 2026-08-23 | Infrastructure | Build and deployment layer added: Makefile, three Dockerfiles, docker-compose, GitLab pipeline, deployment document | pending | [docs/04-DEPLOYMENT.md](docs/04-DEPLOYMENT.md) |
| CHG-0004 | 2026-08-23 | Process | This index, the change control process, five document templates, and the index consistency checker | pending | [docs/03-CHANGE-CONTROL.md](docs/03-CHANGE-CONTROL.md) |
| CHG-0005 | 2026-08-23 | Design | P0 implementation plan written, 28 tasks across eight waves, each carrying the seven anti hallucination fields | pending | [P0 plan](docs/plans/P0-implementation-plan.md) |

---

## 5. Issues

**14 FIXED, 18 OPEN, 1 PARKED.** Full detail with evidence and resolution in
[tasks/ISSUES.md](tasks/ISSUES.md).

FIXED means the design decision is recorded, not that code exists.
Implementation status lives only in [tasks/STATUS.md](tasks/STATUS.md).

### Critical and high, design

| ID | Severity | Issue | Status | Detail |
| --- | --- | --- | --- | --- |
| ISS-001 | CRITICAL | Nine requirement areas as one project would produce a shallow scaffold of everything | FIXED | [ADR-0001](docs/adr/ADR-0001-decompose-into-sub-projects.md) |
| ISS-005 | HIGH | A bespoke cost schema forces a migration per cloud provider | FIXED | [ADR-0002](docs/adr/ADR-0002-focus-canonical-schema.md) |
| ISS-006 | HIGH | Serving dashboards from Athena recreates the runaway query cost problem inside Meter | FIXED | [ADR-0003](docs/adr/ADR-0003-postgres-only-serving-layer.md) |
| ISS-007 | HIGH | Unblended per resource cost is meaningless with commitments in play | FIXED | [architecture](docs/02-ARCHITECTURE.md) |
| ISS-008 | HIGH | CUR is restated all month, so naive ingest double counts | FIXED | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 5.3 |
| ISS-009 | HIGH | Interface only scope enforcement is bypassable | FIXED | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 8 |
| ISS-010 | HIGH | ReadOnlyAccess grants data plane reads that cannot be defended | FIXED | [ADR-0004](docs/adr/ADR-0004-cross-account-access.md) |
| ISS-015 | HIGH | A failed collection rendered as zero silently produces wrong totals | FIXED | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 6 |
| ISS-016 | HIGH | Entitlement based visibility silently makes organization totals partial | FIXED | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 6 |

### Medium and low, design

| ID | Severity | Issue | Status | Detail |
| --- | --- | --- | --- | --- |
| ISS-011 | MEDIUM | A model producing sizing numbers destroys trust on the first hallucination | FIXED | [ADR-0007](docs/adr/ADR-0007-llm-never-computes-a-number.md) |
| ISS-012 | MEDIUM | Organization wide AWS Config recording is a five figure monthly cost | OPEN | [tasks/ISSUES.md](tasks/ISSUES.md), resolved in P4 |
| ISS-013 | MEDIUM | Hundreds of describe loops for inventory is a year of work | FIXED | [roadmap](docs/01-ROADMAP.md) P4 |
| ISS-014 | MEDIUM | Neptune is a second database for capability not shown to be needed | FIXED | [ADR-0005](docs/adr/ADR-0005-postgres-adjacency-for-topology.md) |
| ISS-017 | MEDIUM | A local identity provider reaching production is a total auth bypass | FIXED | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 11 |
| ISS-018 | MEDIUM | Meter's own ingestion makes paid API calls and can become the cost problem | FIXED | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 5.5 |
| ISS-019 | LOW | A NAT Gateway for chatty cross account calls is billed per gigabyte | FIXED | [docs/04-DEPLOYMENT.md](docs/04-DEPLOYMENT.md) |

### Existing Grafana prototype

Assessed 2026-08-23. `sample_lambda.py`, 2,740 lines. These become the P2 backlog.

| ID | Severity | Issue | Status | Becomes |
| --- | --- | --- | --- | --- |
| ISS-020 | CRITICAL | It reports, it does not prevent | OPEN | FEAT-014, FEAT-015 |
| ISS-021 | HIGH | No owner attribution, and an unowned finding is never fixed | OPEN | FEAT-016 |
| ISS-022 | HIGH | The cost model is never back tested against the bill | OPEN | FEAT-018 |
| ISS-023 | MEDIUM | History as S3 snapshots cannot be queried or joined | OPEN | [roadmap](docs/01-ROADMAP.md) P2 |
| ISS-024 | MEDIUM | Only Amazon Managed Grafana is supported | OPEN | Blocked on OPEN-04 |
| ISS-025 | MEDIUM | The pattern is Grafana specific but the failure mode is not | OPEN | FEAT-019 |
| ISS-026 | LOW | 2,740 lines in one file, against the 800 line ceiling | OPEN | [roadmap](docs/01-ROADMAP.md) P2 |
| ISS-027 | LOW | No automated tests in the prototype | OPEN | [roadmap](docs/01-ROADMAP.md) P2 |

### Requirement gaps found in review

Not in the original brief, but required for production grade.

| ID | Severity | Gap | Status | Becomes |
| --- | --- | --- | --- | --- |
| ISS-028 | HIGH | No recommendation lifecycle, so recommendations are ignored | OPEN | FEAT-028 |
| ISS-029 | HIGH | No realized savings verification | OPEN | FEAT-029 |
| ISS-030 | MEDIUM | No data freshness contract | OPEN | FEAT-006 |
| ISS-031 | MEDIUM | No audit log for scope evaluation | OPEN | FEAT-007 |
| ISS-032 | MEDIUM | No accuracy contract on modelled figures | OPEN | FEAT-018 |

---

## 6. Open questions

| ID | Question | Status | Blocks | Detail |
| --- | --- | --- | --- | --- |
| OPEN-01 | Identity provider approach: new ADFS relying party, IAM Identity Center, or reuse the AWS relying party | PARKED at user request | Production login. Not the P0 build | [ADR-0008](docs/adr/ADR-0008-identity-adapter-deferred.md) |
| OPEN-02 | Single payer or multiple payer accounts | OPEN | P1 design | [tasks/ISSUES.md](tasks/ISSUES.md) |
| OPEN-03 | Is Business or Enterprise support available | OPEN | P3 and P5 coverage | [tasks/ISSUES.md](tasks/ISSUES.md) |
| OPEN-04 | Amazon Managed Grafana only, or self hosted and Grafana Cloud too | OPEN | P2 scope | [tasks/ISSUES.md](tasks/ISSUES.md) |
| OPEN-05 | Jira or ServiceNow for the recommendation lifecycle | OPEN | P3 design | [tasks/ISSUES.md](tasks/ISSUES.md) |
| OPEN-06 | Which regions beyond Ireland and London | OPEN | P0 dispatcher configuration | [tasks/ISSUES.md](tasks/ISSUES.md) |

---

## 7. Specifications and plans

| Sub project | Specification | Implementation plan | Status |
| --- | --- | --- | --- |
| P0 Foundation | [design spec](docs/specs/2026-08-23-p0-foundation-design.md) | [28 tasks](docs/plans/P0-implementation-plan.md) | Spec in review, plan provisional |
| P2 Query Cost Governance | not written | not written | Next after P0 |
| P1 Cost Intelligence | not written | not written | Not started |
| P3 Utilization and Rightsizing | not written | not written | Not started |
| P4 Inventory and Topology | not written | not written | Not started |
| P5 Quotas and Limits | not written | not written | Not started |
| P6 Containers | not written | not written | Not started |
| P7 Insight and LLM layer | not written | not written | Not started |

Templates for new documents: [docs/templates/](docs/templates/README.md)

---

## 8. Build and deployment

| Artefact | Path | Purpose |
| --- | --- | --- |
| Task runner | `Makefile` | 28 targets. `make help` lists them |
| API image | `docker/Dockerfile.api` | FastAPI on Python 3.12, non root, health checked |
| Worker image | `docker/Dockerfile.worker` | Dispatcher and worker, selected by `METER_ROLE` |
| Web image | `docker/Dockerfile.web` | React build served by nginx |
| Local stack | `docker-compose.yml` | PostgreSQL, LocalStack, API, dispatcher, worker, web |
| Pipeline | `.gitlab-ci.yml` | verify, build with Kaniko, plan, deploy |
| Packaging | `pyproject.toml` | Dependencies, lint rules, and the import linter contract |
| Index checker | `scripts/check_index.py` | Fails when this document drifts |
| Migration runner | `scripts/run_migration_task.sh` | One off ECS task before rollout |

Full description: [docs/04-DEPLOYMENT.md](docs/04-DEPLOYMENT.md)

---

## 9. Traceability

Every feature traces to a specification section, and every task traces to a
feature. The mapping from features to P0 tasks is in the
[P0 plan](docs/plans/P0-implementation-plan.md), section "Traceability".

A feature with no specification section, or a task with no feature, is a defect
in the documentation and is raised as an `ISS-nnn` row before work begins.
