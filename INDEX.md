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

**How this document is maintained.** Sections 2 to 6 are **generated** from
`docs/registry.yaml` by `make doc-sync`. Change a status in the registry, run
one command, and every derived view updates together. Hand editing a generated
block is caught by `make check-docs`. See
[ADR-0014](docs/adr/ADR-0014-generated-documentation.md).

## 1. Where to start

| I want to know | Read |
| --- | --- |
| Why this project exists and what counts as success | [docs/00-GOAL.md](docs/00-GOAL.md) |
| What is being built and in what order | [docs/01-ROADMAP.md](docs/01-ROADMAP.md) |
| How the pieces fit together | [docs/02-ARCHITECTURE.md](docs/02-ARCHITECTURE.md) |
| Where a change is recorded | [docs/03-CHANGE-CONTROL.md](docs/03-CHANGE-CONTROL.md) |
| The database schema and migration rules | [docs/07-DATA-MODEL.md](docs/07-DATA-MODEL.md) |
| The registry every derived document comes from | [docs/registry.yaml](docs/registry.yaml) |
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

<!-- generated:features start -->
<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. Edit the registry, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

42 features across 8 sub projects. 10 specified, 32 planned, 0 in build, 0 delivered.

**Every feature has its own document.** The identifier links to it.

### P0 Foundation

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| [FEAT-001](docs/features/FEAT-001-account-onboarding-and-org-topology.md) | Account onboarding and organization topology, parent to child map | Specified | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 5.2, 7 |
| [FEAT-002](docs/features/FEAT-002-cross-account-credential-brokering.md) | Cross account credential brokering by StackSet deployed role | Specified | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 10, [ADR-0004](docs/adr/ADR-0004-cross-account-access.md) |
| [FEAT-003](docs/features/FEAT-003-provider-port-abstraction.md) | Provider port abstraction, eight ports | Specified | [architecture](docs/02-ARCHITECTURE.md) section "Ports" |
| [FEAT-004](docs/features/FEAT-004-focus-canonical-cost-schema.md) | FOCUS 1.1 canonical cost schema | Specified | [ADR-0002](docs/adr/ADR-0002-focus-canonical-schema.md) |
| [FEAT-005](docs/features/FEAT-005-ingestion-framework.md) | Ingestion framework, idempotent and partial failure tolerant | Specified | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 7 |
| [FEAT-006](docs/features/FEAT-006-typed-errors-and-freshness.md) | Typed error taxonomy and data freshness contract | Specified | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 6 |
| [FEAT-007](docs/features/FEAT-007-authorization-scope-enforcement.md) | Authorization scope enforcement, two independent points | Specified | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 6, [ADR-0008](docs/adr/ADR-0008-identity-adapter-deferred.md) |
| [FEAT-008](docs/features/FEAT-008-platform-self-metering.md) | Platform self metering | Specified | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 5.5 |
| [FEAT-009](docs/features/FEAT-009-organization-map.md) | Organization map, tree and graph views | Specified | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 9 |
| [FEAT-010](docs/features/FEAT-010-ingest-and-freshness-surface.md) | Ingest and freshness surface | Specified | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 9 |

### P2 Query Cost Governance

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| [FEAT-011](docs/features/FEAT-011-grafana-workspace-scanner.md) | Grafana workspace, dashboard and alert rule scanner | Planned | [roadmap](docs/01-ROADMAP.md) P2. Prototype exists |
| [FEAT-012](docs/features/FEAT-012-query-cost-model.md) | Query cost model, Logs Insights and metric engines | Planned | [roadmap](docs/01-ROADMAP.md) P2. Prototype exists |
| [FEAT-013](docs/features/FEAT-013-measured-query-overlay.md) | Measured overlay from CloudTrail and DescribeQueries | Planned | [roadmap](docs/01-ROADMAP.md) P2. Prototype exists |
| [FEAT-014](docs/features/FEAT-014-preventive-query-controls.md) | Preventive controls: refresh floor and CI policy gate | Planned | [roadmap](docs/01-ROADMAP.md) P2. Addresses ISS-020 |
| [FEAT-015](docs/features/FEAT-015-query-cost-kill-switch.md) | Near real time kill switch with Budgets Actions | Planned | [roadmap](docs/01-ROADMAP.md) P2. Addresses ISS-020 |
| [FEAT-016](docs/features/FEAT-016-query-owner-attribution.md) | Owner attribution from folder, team and last editor | Planned | [roadmap](docs/01-ROADMAP.md) P2. Addresses ISS-021 |
| [FEAT-017](docs/features/FEAT-017-query-auto-remediation.md) | Auto remediation with change record and undo | Planned | [roadmap](docs/01-ROADMAP.md) P2 |
| [FEAT-018](docs/features/FEAT-018-cost-model-calibration.md) | Cost model calibration against actual CUR usage types | Planned | [roadmap](docs/01-ROADMAP.md) P2. Addresses ISS-022 |
| [FEAT-019](docs/features/FEAT-019-multi-platform-query-governance.md) | Multi platform query governance: QuickSight, Athena, Redshift, OpenSearch | Planned | [roadmap](docs/01-ROADMAP.md) P2. Addresses ISS-025 |

### P1 Cost Intelligence

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| [FEAT-020](docs/features/FEAT-020-cur-focus-ingest.md) | CUR 2.0 ingest with resource identifiers and split cost allocation | Planned | [roadmap](docs/01-ROADMAP.md) P1 |
| [FEAT-021](docs/features/FEAT-021-cost-rollups-and-trends.md) | Cost rollups, trends and per resource attribution | Planned | [roadmap](docs/01-ROADMAP.md) P1 |
| [FEAT-022](docs/features/FEAT-022-allocation-and-showback.md) | Allocation, showback and the unallocated bucket | Planned | [roadmap](docs/01-ROADMAP.md) P1 |
| [FEAT-023](docs/features/FEAT-023-cost-anomaly-detection.md) | Anomaly detection and ingest of AWS Cost Anomaly Detection | Planned | [roadmap](docs/01-ROADMAP.md) P1 |
| [FEAT-024](docs/features/FEAT-024-commitment-coverage.md) | Savings Plan and Reserved Instance utilization and coverage | Planned | [roadmap](docs/01-ROADMAP.md) P1 |

### P3 Utilization and Rightsizing

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| [FEAT-025](docs/features/FEAT-025-aws-native-recommendation-ingest.md) | Cost Optimization Hub, Compute Optimizer and Trusted Advisor ingest | Planned | [ADR-0006](docs/adr/ADR-0006-aws-native-recommendations-first.md) |
| [FEAT-026](docs/features/FEAT-026-bespoke-waste-collectors.md) | Bespoke waste collectors where AWS is blind | Planned | [ADR-0006](docs/adr/ADR-0006-aws-native-recommendations-first.md) |
| [FEAT-027](docs/features/FEAT-027-cloudwatch-cost-module.md) | CloudWatch cost module: retention, unqueried logs, stale alarms | Planned | [roadmap](docs/01-ROADMAP.md) P3 |
| [FEAT-028](docs/features/FEAT-028-recommendation-lifecycle.md) | Recommendation lifecycle with owner and ticketing | Planned | [roadmap](docs/01-ROADMAP.md) P3. Addresses ISS-028 |
| [FEAT-029](docs/features/FEAT-029-realized-savings-verification.md) | Realized savings verification, the north star metric | Planned | [docs/00-GOAL.md](docs/00-GOAL.md). Addresses ISS-029 |

### P4 Inventory and Topology

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| [FEAT-030](docs/features/FEAT-030-config-aggregator-inventory.md) | AWS Config aggregator inventory by region and zone | Planned | [roadmap](docs/01-ROADMAP.md) P4 |
| [FEAT-031](docs/features/FEAT-031-topology-graph.md) | Topology graph, node and edge model | Planned | [ADR-0005](docs/adr/ADR-0005-postgres-adjacency-for-topology.md) |
| [FEAT-032](docs/features/FEAT-032-topology-map-interface.md) | Topology map interface | Planned | [roadmap](docs/01-ROADMAP.md) P4 |

### P5 Quotas and Limits

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| [FEAT-033](docs/features/FEAT-033-quota-utilization.md) | Quota utilization per service per region, with stated coverage gaps | Planned | [roadmap](docs/01-ROADMAP.md) P5 |
| [FEAT-034](docs/features/FEAT-034-quota-increase-workflow.md) | Quota increase request workflow | Planned | [roadmap](docs/01-ROADMAP.md) P5 |

### P6 Containers

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| [FEAT-035](docs/features/FEAT-035-eks-split-cost-allocation.md) | EKS pod level cost from split cost allocation data | Planned | [roadmap](docs/01-ROADMAP.md) P6 |
| [FEAT-036](docs/features/FEAT-036-k8s-in-cluster-telemetry.md) | In cluster telemetry, requested versus used | Planned | [roadmap](docs/01-ROADMAP.md) P6 |
| [FEAT-037](docs/features/FEAT-037-ecs-task-utilization.md) | ECS task and Fargate utilization, snapped to valid sizes | Planned | [roadmap](docs/01-ROADMAP.md) P6 |

### P7 Insight and LLM layer

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| [FEAT-038](docs/features/FEAT-038-natural-language-cost-query.md) | Natural language cost query over a governed semantic layer | Planned | [ADR-0007](docs/adr/ADR-0007-llm-never-computes-a-number.md) |
| [FEAT-039](docs/features/FEAT-039-anomaly-narration.md) | Anomaly narration correlating cost, Config and CloudTrail | Planned | [ADR-0007](docs/adr/ADR-0007-llm-never-computes-a-number.md) |
| [FEAT-040](docs/features/FEAT-040-remediation-authoring.md) | Remediation authoring as an infrastructure as code pull request | Planned | [ADR-0007](docs/adr/ADR-0007-llm-never-computes-a-number.md) |
| [FEAT-041](docs/features/FEAT-041-digests-and-summaries.md) | Per team digests and executive summaries | Planned | [roadmap](docs/01-ROADMAP.md) P7 |
| [FEAT-042](docs/features/FEAT-042-assistant-bot.md) | Assistant bot, chat and find anything in the tool | Planned | [ADR-0009](docs/adr/ADR-0009-mcp-alongside-http-api.md) |

<!-- generated:features end -->

---

## 3. Architecture decision records

<!-- generated:adrs start -->
<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. Edit the registry, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

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
| ADR-0009 | An MCP server alongside the HTTP API, not instead of it | Accepted | [ADR-0009](docs/adr/ADR-0009-mcp-alongside-http-api.md) |
| ADR-0010 | Minimus base images and a continuously maintained zero CVE posture | Accepted | [ADR-0010](docs/adr/ADR-0010-minimus-zero-cve-base-images.md) |
| ADR-0011 | A decision ladder before any new code, and token economy | Superseded by ADR-0013 | [ADR-0011](docs/adr/ADR-0011-minimal-code-decision-ladder.md) |
| ADR-0012 | Collection cadence is data, not code, and is bounded by the source | Accepted | [ADR-0012](docs/adr/ADR-0012-collector-cadence-registry.md) |
| ADR-0013 | Seven rung ladder with a Rung Disqualification Record and a security sign off gate | Accepted | [ADR-0013](docs/adr/ADR-0013-seven-rung-ladder-and-disqualification.md) |
| ADR-0014 | Derived documentation is generated from a registry, not hand maintained | Accepted | [ADR-0014](docs/adr/ADR-0014-generated-documentation.md) |

Index of records: [docs/adr/README.md](docs/adr/README.md)

<!-- generated:adrs end -->

---

## 4. Change log

<!-- generated:changes start -->
<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. Edit the registry, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

| ID | Date | Type | What changed | Commit | Detail |
| --- | --- | --- | --- | --- | --- |
| CHG-0001 | 2026-08-23 | Process | Repository initialized. Goal, roadmap, architecture, eight ADRs, P0 specification, status, issues, lessons, project map, checkpoint | `f6d7603 to 9adb1aa` | [docs/checkpoint.md](docs/checkpoint.md) |
| CHG-0002 | 2026-08-23 | Process | Checkpoint log and project map moved to the paths the session enforcement script requires | `a3ea1cf` | [docs/checkpoint.md](docs/checkpoint.md) |
| CHG-0003 | 2026-08-23 | Infrastructure | Build and deployment layer added: Makefile, three Dockerfiles, docker-compose, GitLab pipeline, deployment document | `9f9e5ff` | [docs/04-DEPLOYMENT.md](docs/04-DEPLOYMENT.md) |
| CHG-0004 | 2026-08-23 | Process | This index, the change control process, five document templates, and the index consistency checker | `3c531e0` | [docs/03-CHANGE-CONTROL.md](docs/03-CHANGE-CONTROL.md) |
| CHG-0005 | 2026-08-23 | Design | P0 implementation plan written, 28 tasks across eight waves, each carrying the seven anti hallucination fields | `7e5525a` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0006 | 2026-08-23 | Design | MCP server added as a facade over the HTTP API, not a replacement. FEAT-042 assistant bot added | `7e4cc01` | [ADR-0009](docs/adr/ADR-0009-mcp-alongside-http-api.md) |
| CHG-0007 | 2026-08-23 | Infrastructure | Images rebased on Minimus, shell free runtime, no bytecode, exec form only. Health checking moved to the ALB | `2e22413` | [ADR-0010](docs/adr/ADR-0010-minimus-zero-cve-base-images.md) |
| CHG-0008 | 2026-08-23 | Process | Security folder, seven scanners, dependency admission gate, HTML report with fixes, branch scoped auto fix, nightly posture scan | `0c87ae5` | [docs/05-SECURITY.md](docs/05-SECURITY.md) |
| CHG-0009 | 2026-08-23 | Process | Decision ladder and output discipline adopted from ponytail and caveman. Code review and documentation generation added as pipeline stages | `7e4cc01` | [ADR-0011](docs/adr/ADR-0011-minimal-code-decision-ladder.md) |
| CHG-0010 | 2026-08-23 | Design | Collection cadence moved into a table with its reason and cost. Grafana audit at 6 hours, kill switch event driven | `7e4cc01` | [docs/06-DATA-FRESHNESS.md](docs/06-DATA-FRESHNESS.md) |
| CHG-0011 | 2026-08-23 | Process | One document per feature, 42 of them. File dependency graph generated and layering enforced. All scripts consolidated under scripts/ | `02eca11` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0012 | 2026-08-23 | Infrastructure | Platform pinned to linux/amd64 at five points, because a push never converts an arm64 image | `3591a1f` | [docs/04-DEPLOYMENT.md](docs/04-DEPLOYMENT.md) |
| CHG-0013 | 2026-08-23 | Design | Database schema documented in full, with Alembic migration rules and constraint level invariants | `0f0f1e9` | [docs/07-DATA-MODEL.md](docs/07-DATA-MODEL.md) |
| CHG-0014 | 2026-08-23 | Process | Ponytail ladder replaced by the seven rung version with a Rung Disqualification Record, imported from a prior project | `3d93f76` | [ADR-0013](docs/adr/ADR-0013-seven-rung-ladder-and-disqualification.md) |
| CHG-0015 | 2026-08-23 | Process | Derived documentation generated from docs/registry.yaml instead of hand maintained in four places | `5355ac3` | [ADR-0014](docs/adr/ADR-0014-generated-documentation.md) |
| CHG-0016 | 2026-08-23 | Process | README rewritten as the operational entry point: source of truth table, common tasks, the four security gates, the remediation path, and a gotchas table | `aaf6a6a` | [README.md](README.md) |
| CHG-0017 | 2026-08-23 | Process | Layered security gates documented and completed: pre commit and pre push hooks, a compose security profile for local scanning, and provenance verification before every deploy | `061c351` | [docs/05-SECURITY.md](docs/05-SECURITY.md) |
| CHG-0018 | 2026-08-23 | Process | README gotchas expanded into ten worked examples, each showing the actual output and the exact commands | `403c57b` | [README.md](README.md) |
| CHG-0019 | 2026-08-23 | Process | README security section rewritten around the six layer gate model, with LocalStack explained and its limits stated | `f3b5aef` | [README.md](README.md) |

<!-- generated:changes end -->

---

## 5. Issues

<!-- generated:issues start -->
<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. Edit the registry, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

**36 FIXED, 15 OPEN, 0 PARKED.** Full detail with evidence in [tasks/ISSUES.md](tasks/ISSUES.md).

FIXED means the design decision is recorded, not that code exists. Implementation status lives only in [tasks/STATUS.md](tasks/STATUS.md).

| ID | Severity | Issue | Status | Detail |
| --- | --- | --- | --- | --- |
| ISS-001 | CRITICAL | Nine requirement areas as one project would produce a shallow scaffold of everything | FIXED | [ADR-0001](docs/adr/ADR-0001-decompose-into-sub-projects.md) |
| ISS-020 | CRITICAL | It reports, it does not prevent | OPEN | FEAT-014, FEAT-015 |
| ISS-033 | CRITICAL | The official Python base image ships with more than 400 known vulnerabilities before any application code is added | FIXED | [ADR-0010](docs/adr/ADR-0010-minimus-zero-cve-base-images.md) |
| ISS-034 | CRITICAL | Scanning only at build time reports zero forever while the deployed image degrades silently | FIXED | [docs/05-SECURITY.md](docs/05-SECURITY.md), nightly posture scan |
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
| ISS-019 | LOW | A NAT Gateway for chatty cross account calls is billed per gigabyte | FIXED | [docs/04-DEPLOYMENT.md](docs/04-DEPLOYMENT.md) |
| ISS-026 | LOW | 2,740 lines in one file, against the 800 line ceiling | OPEN | [roadmap](docs/01-ROADMAP.md) P2 |
| ISS-027 | LOW | No automated tests in the prototype | OPEN | [roadmap](docs/01-ROADMAP.md) P2 |
| ISS-044 | LOW | Scripts were scattered between the root and one flat directory | FIXED | All under `scripts/`, grouped by purpose |
| ISS-054 | LOW | ECR tags were mutable, so a tag could be repointed at a different image after it was scanned and signed | OPEN | Set IMMUTABLE tags in TASK-P0-016 |

<!-- generated:issues end -->

---

## 6. Open questions

<!-- generated:open-questions start -->
<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. Edit the registry, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

| ID | Question | Status | Blocks | Detail |
| --- | --- | --- | --- | --- |
| OPEN-01 | Identity provider approach: new ADFS relying party, IAM Identity Center, or reuse the AWS relying party | PARKED at user request | Production login. Not the P0 build | [ADR-0008](docs/adr/ADR-0008-identity-adapter-deferred.md) |
| OPEN-02 | Single payer or multiple payer accounts | OPEN | P1 design | [tasks/ISSUES.md](tasks/ISSUES.md) |
| OPEN-03 | Is Business or Enterprise support available | OPEN | P3 and P5 coverage | [tasks/ISSUES.md](tasks/ISSUES.md) |
| OPEN-04 | Amazon Managed Grafana only, or self hosted and Grafana Cloud too | OPEN | P2 scope | [tasks/ISSUES.md](tasks/ISSUES.md) |
| OPEN-05 | Jira or ServiceNow for the recommendation lifecycle | OPEN | P3 design | [tasks/ISSUES.md](tasks/ISSUES.md) |
| OPEN-06 | Which regions beyond Ireland and London | OPEN | P0 dispatcher configuration | [tasks/ISSUES.md](tasks/ISSUES.md) |

<!-- generated:open-questions end -->

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
| Index checker | `scripts/docs/check_index.py` | Fails when this document drifts |
| Feature doc checker | `scripts/docs/check_feature_docs.py` | Fails when a feature has no document |
| File graph | `scripts/docs/build_file_graph.py` | Builds the graph, fails on a layering violation |
| Migration runner | `scripts/deploy/run_migration_task.sh` | One off ECS task before rollout |
| Code review | `scripts/ci/code_review.py` | Deterministic checks, then the review checklist |
| Script index | `scripts/README.md` | Every script, what it does, how it is run |

Base images are Minimus from `reg.mini.dev`. The runtime images have no shell
and no package manager, so every `CMD` and `ENTRYPOINT` is in exec form and
health checking is done by the ALB target group. See
[ADR-0010](docs/adr/ADR-0010-minimus-zero-cve-base-images.md).

Full description: [docs/04-DEPLOYMENT.md](docs/04-DEPLOYMENT.md)

---

## 9. Security

Policy is **zero vulnerabilities at any severity, at all times**. Not zero
critical, not zero high. Zero.

| Artefact | Path |
| --- | --- |
| Policy and controls | [docs/05-SECURITY.md](docs/05-SECURITY.md) |
| Current posture | `security/POSTURE.md`, generated |
| Scan reports | `security/reports/`, one directory per run, committed |
| SBOMs | `security/sbom/`, one per image per build |
| Code review reports | `security/reviews/` |
| Allowlist | `security/policy/allowlist.yaml`, owner and expiry required |
| Scanner configuration | `security/policy/grype.yaml`, `trivy.yaml` |

Seven tools: `grype`, `syft`, `trivy`, `pip-audit`, `npm audit`, `gitleaks`,
`cosign`. Two vulnerability scanners deliberately, because their databases
differ and the difference is where a missed finding lives.

```bash
make dep-check pkg=x    # admission gate, before adding a dependency
make security-scan      # everything, writes a timestamped HTML report
make security-fix       # apply fixes on a branch, run tests, re scan
```

---

## 10. Data freshness

Full detail: [docs/06-DATA-FRESHNESS.md](docs/06-DATA-FRESHNESS.md), decided in
[ADR-0012](docs/adr/ADR-0012-collector-cadence-registry.md).

Freshness is capped by AWS, not by Meter. CUR refreshes at most three times a
day, Cost Explorer is roughly a day behind, Compute Optimizer rebuilds daily.
Every figure therefore carries two timestamps: `as_of`, when the data was true
at the source, and `collected_at`, when Meter fetched it.

| Collector | Cadence |
| --- | --- |
| `org_tree`, `account_health` | 1 hour |
| `cur_focus` | 4 hours |
| **`grafana_query_audit`** | **6 hours** |
| **`grafana_kill_switch`** | **Event driven** |
| `config_inventory`, `quotas`, `cost_anomaly` | 6 hours |
| `platform_cost`, `compute_optimizer`, `metrics_rightsizing` | 24 hours |
| `k8s_telemetry` | 15 minutes, pushed |

Cadence lives in a `collector_schedule` table with its reason and its estimated
cost per run, not in code.

---

## 11. Architecture graph

[docs/architecture/file-graph.md](docs/architecture/file-graph.md) shows how
every file depends on every other: Python imports, TypeScript imports,
Terraform module references and Dockerfile COPY edges, read out of the source.

`make graph` rebuilds it. It also fails on a layering violation, so the graph
is a gate rather than only a picture.

---

## 12. Traceability

Every feature traces to a specification section, and every task traces to a
feature. The mapping from features to P0 tasks is in the
[P0 plan](docs/plans/P0-implementation-plan.md), section "Traceability".

A feature with no specification section, or a task with no feature, is a defect
in the documentation and is raised as an `ISS-nnn` row before work begins.
