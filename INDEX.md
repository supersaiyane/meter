# Meter: master index

<!-- Basic boiler Plate Doc | Grade B
     Why this file exists: The single entry point. Every feature, decision, change, issue and
     open question, each with a pointer to the document holding the detail. If something is not
     here, it does not exist as far as the project is concerned.
     Grade B here: copy it, then replace all of the content. The section structure and the
     generated block markers are what carry over.
     Grades: A copy into a new project as is, no edits. B copy it and swap the
     names, paths or patterns named above. C leave behind, it is this project's
     own content rather than scaffolding, and is not tagged.
-->

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
| Every configuration value, what it does, which file reads it | `.env.example` |
| Every feature flag, its owner and its expiry | [docs/feature-flags.yaml](docs/feature-flags.yaml) |
| How code reaches production | [docs/04-DEPLOYMENT.md](docs/04-DEPLOYMENT.md) |
| Security policy, scanners, gates | [docs/05-SECURITY.md](docs/05-SECURITY.md) |
| Pinned base images and their digests | `docker/base-images.lock` |
| Findings accepted as unfixable, and why | `security/policy/accepted.yaml` |
| Who attacks this, and what stops them | [docs/08-THREAT-MODEL.md](docs/08-THREAT-MODEL.md) |
| What data we hold, retention, erasure | [docs/09-DATA-CLASSIFICATION.md](docs/09-DATA-CLASSIFICATION.md) |
| SLOs, alerts, and what pages someone | [docs/10-OBSERVABILITY.md](docs/10-OBSERVABILITY.md) |
| How a number is shown, and how failure is shown | [docs/12-UI-DESIGN.md](docs/12-UI-DESIGN.md) |
| Where a screen lives, and what a user sees first | [docs/13-UI-ARCHITECTURE.md](docs/13-UI-ARCHITECTURE.md) |
| What Home should look like, and the open decisions | [docs/design/home-redesign.html](docs/design/home-redesign.html) |
| The prototype P2 was planned against | [docs/reference/](docs/reference/README.md) |
| Runbooks for the paging alerts | [docs/runbooks/](docs/runbooks/README.md) |
| Runbook, collection stalled and widespread | [docs/runbooks/collection-stalled.md](docs/runbooks/collection-stalled.md) |
| Runbook, API server errors | [docs/runbooks/api-5xx.md](docs/runbooks/api-5xx.md) |
| Runbook, platform cost anomaly | [docs/runbooks/platform-cost-anomaly.md](docs/runbooks/platform-cost-anomaly.md) |
| Runbook, deploy Meter for the first time | [docs/runbooks/deploy.md](docs/runbooks/deploy.md) |
| Runbook, onboard an account or a second organization | [docs/runbooks/onboard-account.md](docs/runbooks/onboard-account.md) |
| Runbook, restore the database, and the drill | [docs/runbooks/restore.md](docs/runbooks/restore.md) |
| How often data refreshes, and its limits | [docs/06-DATA-FRESHNESS.md](docs/06-DATA-FRESHNESS.md) |
| What Meter costs to run | [docs/04-DEPLOYMENT.md](docs/04-DEPLOYMENT.md) |
| When a sub project is done | [docs/01-ROADMAP.md](docs/01-ROADMAP.md) |
| The rules a change must follow | [CLAUDE.md](CLAUDE.md) |
| What is done and what is left | [tasks/STATUS.md](tasks/STATUS.md) |
| What is broken or undecided | [tasks/ISSUES.md](tasks/ISSUES.md) |
| Where the last session stopped | [docs/checkpoint.md](docs/checkpoint.md) |
| Older sessions, rotated out of the live window at 50 entries | [docs/checkpoint_archive.md](docs/checkpoint_archive.md) |
| The module layout | [project_map.md](project_map.md) |
| Where a function lives | [context_index.md](context_index.md) |
| Corrections already received | [tasks/lessons.md](tasks/lessons.md) |
| What an audit found, and when | [audits/](audits/README.md) |
| How we compare to a competing product | [docs/11-COMPETITIVE-REVIEW.md](docs/11-COMPETITIVE-REVIEW.md) |
| Every configuration value and what reads it | `.env.example` |
| Every feature flag, owner and expiry | [docs/feature-flags.yaml](docs/feature-flags.yaml) |

---

## 2. Features

<!-- generated:features start -->
<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. Edit docs/registry.yaml, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

51 features across 8 sub projects. 9 specified, 30 planned, 7 in build, 5 delivered.

**Every feature has its own document.** The identifier links to it.

### P0 Foundation

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| [FEAT-001](docs/features/FEAT-001-account-onboarding-and-org-topology.md) | Account onboarding and organization topology, parent to child map | In build | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 5.2, 7 |
| [FEAT-002](docs/features/FEAT-002-cross-account-credential-brokering.md) | Cross account credential brokering by StackSet deployed role | In build | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 10, [ADR-0004](docs/adr/ADR-0004-cross-account-access.md) |
| [FEAT-003](docs/features/FEAT-003-provider-port-abstraction.md) | Provider port abstraction, eight provider ports | Delivered | [architecture](docs/02-ARCHITECTURE.md) section "Ports" |
| [FEAT-004](docs/features/FEAT-004-focus-canonical-cost-schema.md) | FOCUS 1.1 canonical cost schema | In build | [ADR-0002](docs/adr/ADR-0002-focus-canonical-schema.md) |
| [FEAT-005](docs/features/FEAT-005-ingestion-framework.md) | Ingestion framework, idempotent and partial failure tolerant | In build | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 7 |
| [FEAT-006](docs/features/FEAT-006-typed-errors-and-freshness.md) | Typed error taxonomy and data freshness contract | Delivered | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 6 |
| [FEAT-007](docs/features/FEAT-007-authorization-scope-enforcement.md) | Authorization scope enforcement, two independent points | In build | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 6, [ADR-0008](docs/adr/ADR-0008-identity-adapter-deferred.md) |
| [FEAT-008](docs/features/FEAT-008-platform-self-metering.md) | Platform self metering | Delivered | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 5.5 |
| [FEAT-009](docs/features/FEAT-009-organization-map.md) | Organization map, tree and graph views | In build | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 9 |
| [FEAT-010](docs/features/FEAT-010-ingest-and-freshness-surface.md) | Ingest and freshness surface | Delivered | [P0 spec](docs/specs/2026-08-23-p0-foundation-design.md) section 9 |
| [FEAT-049](docs/features/FEAT-049-configuration-and-feature-flags.md) | Configuration and feature flags, everything switchable, nothing hardcoded | In build | [ADR-0017](docs/adr/ADR-0017-configuration-and-feature-flags.md) |
| [FEAT-050](docs/features/FEAT-050-visual-honesty-system.md) | Provenance, freshness and failure rendering, the visual honesty system | Delivered | [docs/12-UI-DESIGN.md](docs/12-UI-DESIGN.md) |

### P2 Query Cost Governance

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| [FEAT-011](docs/features/FEAT-011-grafana-workspace-scanner.md) | Grafana workspace, dashboard and alert rule scanner | Specified | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) |
| [FEAT-012](docs/features/FEAT-012-query-cost-model.md) | Query cost model, Logs Insights and metric engines | Specified | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) |
| [FEAT-013](docs/features/FEAT-013-measured-query-overlay.md) | Measured overlay from CloudTrail and DescribeQueries | Specified | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) |
| [FEAT-014](docs/features/FEAT-014-preventive-query-controls.md) | Preventive controls: refresh floor and CI policy gate | Specified | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) |
| [FEAT-015](docs/features/FEAT-015-query-cost-kill-switch.md) | Near real time kill switch with Budgets Actions | Specified | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) |
| [FEAT-016](docs/features/FEAT-016-query-owner-attribution.md) | Owner attribution from folder, team and last editor | Specified | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) |
| [FEAT-017](docs/features/FEAT-017-query-auto-remediation.md) | Auto remediation with change record and undo | Specified | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) |
| [FEAT-018](docs/features/FEAT-018-cost-model-calibration.md) | Cost model calibration against actual CUR usage types | Specified | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) |
| [FEAT-019](docs/features/FEAT-019-multi-platform-query-governance.md) | Multi platform query governance: QuickSight, Athena, Redshift, OpenSearch | Planned | [roadmap](docs/01-ROADMAP.md) P2. Addresses ISS-025 |
| [FEAT-051](docs/features/FEAT-051-adhoc-query-detection.md) | Ad hoc query detection | Specified | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) |

### P1 Cost Intelligence

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| [FEAT-020](docs/features/FEAT-020-cur-focus-ingest.md) | CUR 2.0 ingest with resource identifiers and split cost allocation | Planned | [P1 spec](docs/specs/2026-09-18-p1-cost-intelligence-design.md) sections 5 and 7 |
| [FEAT-021](docs/features/FEAT-021-cost-rollups-and-trends.md) | Cost rollups, trends and per resource attribution | Planned | [P1 spec](docs/specs/2026-09-18-p1-cost-intelligence-design.md) sections 8 and 9 |
| [FEAT-022](docs/features/FEAT-022-allocation-and-showback.md) | Allocation, showback and the unallocated bucket | Planned | [P1 spec](docs/specs/2026-09-18-p1-cost-intelligence-design.md) section 9 |
| [FEAT-023](docs/features/FEAT-023-cost-anomaly-detection.md) | Anomaly detection and ingest of AWS Cost Anomaly Detection | Planned | [roadmap](docs/01-ROADMAP.md) P1 |
| [FEAT-024](docs/features/FEAT-024-commitment-coverage.md) | Savings Plan and Reserved Instance utilization and coverage | Planned | [roadmap](docs/01-ROADMAP.md) P1 |
| [FEAT-045](docs/features/FEAT-045-chargeback-export.md) | Chargeback and showback export, CSV and Excel | Planned | [Competitive review](docs/11-COMPETITIVE-REVIEW.md) |

### P3 Utilization and Rightsizing

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| [FEAT-025](docs/features/FEAT-025-aws-native-recommendation-ingest.md) | Cost Optimization Hub, Compute Optimizer and Trusted Advisor ingest | Planned | [ADR-0006](docs/adr/ADR-0006-aws-native-recommendations-first.md) |
| [FEAT-026](docs/features/FEAT-026-bespoke-waste-collectors.md) | Bespoke waste collectors where AWS is blind | Planned | [ADR-0006](docs/adr/ADR-0006-aws-native-recommendations-first.md) |
| [FEAT-027](docs/features/FEAT-027-cloudwatch-cost-module.md) | CloudWatch cost module: retention, unqueried logs, stale alarms | Planned | [roadmap](docs/01-ROADMAP.md) P3 |
| [FEAT-028](docs/features/FEAT-028-recommendation-lifecycle.md) | Recommendation lifecycle with owner and ticketing | Planned | [roadmap](docs/01-ROADMAP.md) P3. Addresses ISS-028 |
| [FEAT-029](docs/features/FEAT-029-realized-savings-verification.md) | Realized savings verification, the north star metric | Planned | [docs/00-GOAL.md](docs/00-GOAL.md). Addresses ISS-029 |
| [FEAT-043](docs/features/FEAT-043-finops-score.md) | FinOps Score, decomposable to the findings that moved it | Planned | [Competitive review](docs/11-COMPETITIVE-REVIEW.md), ADR-0016 |
| [FEAT-044](docs/features/FEAT-044-blast-radius-scoring.md) | Blast radius scoring from the dependency graph, gating auto apply | Planned | [Competitive review](docs/11-COMPETITIVE-REVIEW.md) |

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
| [FEAT-047](docs/features/FEAT-047-node-fleet-optimisation.md) | Cluster node fleet optimisation as an integer linear program | Planned | [Competitive review](docs/11-COMPETITIVE-REVIEW.md) |
| [FEAT-048](docs/features/FEAT-048-predictive-replica-forecasting.md) | Predictive replica forecasting, under the four ADR-0015 conditions | Planned | [ADR-0015](docs/adr/ADR-0015-deterministic-forecasting-is-permitted.md) |

### P7 Insight and LLM layer

| ID | Feature | Status | Detail |
| --- | --- | --- | --- |
| [FEAT-038](docs/features/FEAT-038-natural-language-cost-query.md) | Natural language cost query over a governed semantic layer | Planned | [ADR-0007](docs/adr/ADR-0007-llm-never-computes-a-number.md) |
| [FEAT-039](docs/features/FEAT-039-anomaly-narration.md) | Anomaly narration correlating cost, Config and CloudTrail | Planned | [ADR-0007](docs/adr/ADR-0007-llm-never-computes-a-number.md) |
| [FEAT-040](docs/features/FEAT-040-remediation-authoring.md) | Remediation authoring as an infrastructure as code pull request | Planned | [ADR-0007](docs/adr/ADR-0007-llm-never-computes-a-number.md) |
| [FEAT-041](docs/features/FEAT-041-digests-and-summaries.md) | Per team digests and executive summaries | Planned | [roadmap](docs/01-ROADMAP.md) P7 |
| [FEAT-042](docs/features/FEAT-042-assistant-bot.md) | Assistant bot, chat and find anything in the tool | Planned | [ADR-0009](docs/adr/ADR-0009-mcp-alongside-http-api.md) |
| [FEAT-046](docs/features/FEAT-046-outbound-ai-scanning.md) | Outbound AI request scanning, redact or block secrets | Planned | [Competitive review](docs/11-COMPETITIVE-REVIEW.md), [docs/05-SECURITY.md](docs/05-SECURITY.md) |

<!-- generated:features end -->

---

## 3. Architecture decision records

<!-- generated:adrs start -->
<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. Edit docs/registry.yaml, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

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
| ADR-0010 | Minimus base images and a continuously maintained zero CVE posture | Accepted, threshold amended by ADR-0018 | [ADR-0010](docs/adr/ADR-0010-minimus-zero-cve-base-images.md) |
| ADR-0011 | A decision ladder before any new code, and token economy | Superseded by ADR-0013 | [ADR-0011](docs/adr/ADR-0011-minimal-code-decision-ladder.md) |
| ADR-0012 | Collection cadence is data, not code, and is bounded by the source | Accepted | [ADR-0012](docs/adr/ADR-0012-collector-cadence-registry.md) |
| ADR-0013 | Seven rung ladder with a Rung Disqualification Record and a security sign off gate | Accepted | [ADR-0013](docs/adr/ADR-0013-seven-rung-ladder-and-disqualification.md) |
| ADR-0014 | Derived documentation is generated from a registry, not hand maintained | Accepted | [ADR-0014](docs/adr/ADR-0014-generated-documentation.md) |
| ADR-0015 | Deterministic forecasting is permitted where a language model number is not | Accepted | [ADR-0015](docs/adr/ADR-0015-deterministic-forecasting-is-permitted.md) |
| ADR-0016 | Severity on a cost finding is derived from the money, never chosen | Accepted | [ADR-0016](docs/adr/ADR-0016-dollar-based-severity.md) |
| ADR-0017 | Nothing is hardcoded, and every feature flag has an owner and an expiry | Accepted | [ADR-0017](docs/adr/ADR-0017-configuration-and-feature-flags.md) |
| ADR-0018 | The threshold is zero fixable findings, not zero findings | Accepted | [ADR-0018](docs/adr/ADR-0018-zero-fixable-not-zero-findings.md) |
| ADR-0019 | Headless component behaviour, our own visual layer | Accepted, styling row superseded by ADR-0021 | [ADR-0019](docs/adr/ADR-0019-headless-components-own-visual-layer.md) |
| ADR-0020 | Seven fixed navigation groups, and the routes they fix | Accepted | [ADR-0020](docs/adr/ADR-0020-seven-fixed-navigation-groups.md) |
| ADR-0021 | Plain CSS over a utility framework, against our own tokens | Accepted | [ADR-0021](docs/adr/ADR-0021-plain-css-over-a-utility-framework.md) |

Index of records: [docs/adr/README.md](docs/adr/README.md)

<!-- generated:adrs end -->

---

## 4. Change log

<!-- generated:changes start -->
<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. Edit docs/registry.yaml, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

| ID | Date | Type | What changed | Commit | Detail |
| --- | --- | --- | --- | --- | --- | --- |
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
| CHG-0020 | 2026-08-23 | Process | AUDIT-001 published. Audits folder created with a naming convention, finding identifiers and a promotion rule. 18 findings promoted to the issue register | `eca070d` | [AUDIT-001](audits/AUDIT-001-2026-08-23-full-project.md) |
| CHG-0021 | 2026-08-23 | Correction | AUDIT-001 remediation wave one: eleven findings closed, covering the import contract, CI tooling, setup ordering, the first run experience, governance files, MCP packaging, the PARTIAL status, the dead graph output, the context index generator and the duplicated roadmap table | `ef23f8a` | [REMEDIATION-LOG](audits/REMEDIATION-LOG.md) |
| CHG-0022 | 2026-08-23 | Design | Threat model and data classification written, closing the two blocking audit findings. The account root email column removed from the schema as a result | `3a16bd0` | [docs/08-THREAT-MODEL.md](docs/08-THREAT-MODEL.md) |
| CHG-0023 | 2026-08-23 | Design | AUDIT-001 remediation wave three: disaster recovery, observability, the running cost estimate, exit criteria and the performance budget. All 18 findings now closed | `6cceaa8` | [REMEDIATION-LOG](audits/REMEDIATION-LOG.md) |
| CHG-0024 | 2026-08-23 | Process | Coding sessions run behind the pxpipe proxy so token usage is recorded. make dev launches, make stats reports | `a92ae60` | [README.md](README.md), "Starting a coding session" |
| CHG-0025 | 2026-08-23 | Scope | Competitive review of NudgeBee AI FinOps. Six features added, three amended, two decisions recorded, four capabilities explicitly rejected | `c7f45f0` | [Competitive review](docs/11-COMPETITIVE-REVIEW.md) |
| CHG-0026 | 2026-08-23 | Design | Configuration and feature flags: one typed settings object, a documented .env.example, a flag register with owners and expiries, and two checks that fail the build. Regions confirmed as Ireland and London. Management account taken off the critical path via LocalStack | `5a78798` | [ADR-0017](docs/adr/ADR-0017-configuration-and-feature-flags.md) |
| CHG-0027 | 2026-08-23 | Design | P2 query cost governance specification written. All three Grafana surfaces in scope, three enforcement levels and three write levels behind per tenant flags, both defaulting safe | `ee3ea68` | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) |
| CHG-0028 | 2026-08-23 | Design | P2 implementation plan written, 22 tasks in ten waves. The prototype is pinned by golden files before anything touches it | `80a0ac3` | [P2 plan](docs/plans/P2-implementation-plan.md) |
| CHG-0029 | 2026-08-23 | Correction | TASK-P0-029 complete. Base images verified by measurement, moved to python 3.13 and nginx 1.30, digests pinned. The zero vulnerabilities policy corrected to zero fixable findings, because no Python image can meet the original | `9754a59` | [ADR-0018](docs/adr/ADR-0018-zero-fixable-not-zero-findings.md) |
| CHG-0030 | 2026-08-23 | Design | UI design specification written, closing the gap where the product honesty guarantees were enforced in the database and undesigned at the pixel. Component library decided against written requirements as ADR-0019 | `d904e7d` | [docs/12-UI-DESIGN.md](docs/12-UI-DESIGN.md) |
| CHG-0031 | 2026-08-23 | Process | Task status generated from the plan files rather than copied into STATUS.md, and generated blocks name their own source | `d20d35c` | [tasks/STATUS.md](tasks/STATUS.md) |
| CHG-0032 | 2026-08-23 | Correction | project_map.md verified against the tree and four errors corrected, including hyphenated Python package names that also appeared in CLAUDE.md | `a9ef75c` | [project_map.md](project_map.md) |
| CHG-0033 | 2026-08-23 | Correction | TASK-P0-001 workspace and quality gates. The import contracts were found to have never worked, and the dependency admission gate missed by TASK-P0-029 was run | `a699d3c` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0034 | 2026-08-24 | Process | The memory layer given a validity gate. Resume vectors, cited commits and identifiers are checked, the checkpoint archive rule became a script, and recording a lesson became one command | `a7e44b7` | [docs/checkpoint.md](docs/checkpoint.md) |
| CHG-0035 | 2026-08-24 | Process | Every file that forms the reusable base of the project tagged Basic boiler Plate Doc, with why it exists and a grade of A, B or C, so the scaffolding can be lifted into a new project | `798dda0` | [scripts/README.md](scripts/README.md) |
| CHG-0036 | 2026-08-24 | Feature | TASK-P0-005, the closed error taxonomy. Six causes, no catch all, and the coverage gate raised back to 80 now that there is a module to cover | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0037 | 2026-08-24 | Feature | TASK-P0-034, the settings object and the flag resolver. Every value typed in one place, no defaults in code except a flag, and a startup that refuses a bad configuration | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0038 | 2026-08-24 | Feature | TASK-P0-006, the domain entities. Frozen throughout, no bare account identifier, and a Fact base class that makes the two timestamp rule structural rather than a habit | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0039 | 2026-08-24 | Feature | TASK-P0-007, the eight ports. Every method names which of the six causes it raises, and a test fails the build when one does not | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0040 | 2026-08-24 | Feature | TASK-P0-008, the fake provider. All eight ports in memory, any of the six causes plannable for any scope, and a fixture organization that never moves between runs | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0041 | 2026-08-24 | Feature | TASK-P0-009, the port contract suite. One suite parameterised over providers, with error type parity as the assertion it exists for. Wave B complete | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0042 | 2026-08-24 | Feature | TASK-P0-010, the database schema and the initial migration. Thirteen tables whose invariants are constraints rather than conventions, proved against a real PostgreSQL | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0043 | 2026-08-24 | Feature | TASK-P0-011, repositories with the scope guard. The second of the two independent enforcement points, plus an audit row on every read. ISS-109 closed | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0044 | 2026-08-24 | Feature | TASK-P0-012, the identity ports with the local provider. Signed sessions, an entitlement cache that always expires, and scope coverage that reports the real total. Wave C complete | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0045 | 2026-08-24 | Feature | TASK-P0-017, the AWS credential broker. Bounded timeouts and retries, sessions refreshed before expiry, and every provider code mapped to one of the six causes | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0046 | 2026-08-24 | Feature | TASK-P0-018, AWS account discovery. The exact tree, every call paginated, no account dropped, and the contract suite live across both providers with no skips | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0047 | 2026-08-24 | Feature | TASK-P0-019, the account health check. NOT_DEPLOYED and ACCESS_DENIED kept apart by a deployment probe rather than by guessing at an error message. Wave E complete | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0048 | 2026-08-24 | Feature | TASK-P0-020, the run ledger and watermarks. Idempotent claims, watermarks that only move forward, and run uniqueness scoped to the tenant after a collision was found | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0049 | 2026-08-24 | Feature | TASK-P0-021, the dispatcher and worker. One transaction per unit, only the six caught, and the two spec section 11 tests passing | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0050 | 2026-08-24 | Feature | TASK-P0-022, the organization tree and account health collectors, plus the cadence rows that make the hourly refresh data rather than a claim | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0051 | 2026-08-27 | Feature | TASK-P0-023, the platform self cost collector. One grouped request a day, untagged cost named rather than dropped, and the metering charge owned. Wave F complete | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0052 | 2026-08-27 | Feature | TASK-P0-024, the FastAPI application, the scope dependency and the meta envelope, with the adversarial test that proves a forgetful route cannot leak | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0053 | 2026-08-27 | Feature | TASK-P0-025, the seven P0 routes. Out of scope branches marked rather than pruned, typed errors with remediation, freshness per collector cadence. Wave G complete | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0054 | 2026-08-27 | Chore | TASK-P0-002, the frontend workspace. Vite, React and TypeScript that builds, lints and tests, with no component library and no state library yet | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0055 | 2026-08-27 | Feature | TASK-P0-035, the component layer. A number reaches a user only through Figure, which requires its provenance and its freshness, and no formatter is exported at all | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0056 | 2026-08-27 | Feature | TASK-P0-026, the application shell. Coverage and freshness are page level and show the worst panel, and the API client refuses a response with no envelope | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0057 | 2026-08-27 | Feature | TASK-P0-027, the accounts screen and organization map. Broken onboarding is one click, the tree is the default, and unreachable branches are drawn and marked | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0058 | 2026-08-27 | Chore | TASK-P0-003 and TASK-P0-004, the index checker's own tests and a demonstrated rejection of the banned dash by the local hook. Wave A complete | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0059 | 2026-08-27 | Feature | TASK-P0-028, the last three screens, the Playwright journey and both performance budgets measured. The restore drill is not performed and is recorded as open | `pending` | [P0 plan](docs/plans/P0-implementation-plan.md) |
| CHG-0060 | 2026-08-27 | Feature | TASK-P0-032, six retention jobs and the erasure script. Two tables were declared PARTITION BY RANGE with no partition anywhere, so both rejected every row. Partition maintenance added, and the cost roll up now aggregates into cost_focus_monthly then drops whole partitions | `b5750f3` | [Data classification](docs/09-DATA-CLASSIFICATION.md) |
| CHG-0061 | 2026-08-27 | Feature | TASK-P0-030, the MCP server as a facade over the HTTP API, with six read tools whose schemas are generated from the API's own models. Found that the API image could never have started, because its command named a symbol that has never existed | `2d6982c` | [ADR-0009](docs/adr/ADR-0009-mcp-alongside-http-api.md) |
| CHG-0062 | 2026-08-28 | Chore | TASK-P0-031, the documentation, memory and docstring gates wired into the pipeline. Found that five jobs called make on images without make, that the documentation job ran three of its eight checks, and that a duplicate job name silently deletes a job | `46147cc` | [ADR-0011](docs/adr/ADR-0011-minimal-code-decision-ladder.md) |
| CHG-0063 | 2026-08-29 | Feature | TASK-P0-013 to 016, the three Terraform stacks. Management account reader role, member account StackSet, and the hub with its network, data layer, ECR, ECS, load balancer and scheduler. No NAT Gateway, no ReadOnlyAccess, and no fifth image for the MCP server | `eb8a507` | [Deployment](docs/04-DEPLOYMENT.md) |
| CHG-0064 | 2026-08-29 | Feature | TASK-P0-033, four SLOs, ten alarms of which four page, three dashboards provisioned as code, and three runbooks. The plan said two alerts page and the specification's own table says four | `eb8a507` | [Observability](docs/10-OBSERVABILITY.md) |
| CHG-0065 | 2026-08-31 | Fix | The security report never read trivy's infrastructure as code findings. Seven were dropped and the gate printed PASS over them. Parser fixed, four real findings fixed, five deliberate ones accepted with a reachability argument | `74e9d28` | [ADR-0018](docs/adr/ADR-0018-zero-fixable-not-zero-findings.md) |
| CHG-0066 | 2026-09-02 | Chore | Lint and type check every directory that holds Python. scripts, migrations and the test suite were outside one or both, and the scripts that were missed are the ones implementing the gates. A test now asks the filesystem rather than trusting the list | `045b5b8` | [Change control](docs/03-CHANGE-CONTROL.md) |
| CHG-0067 | 2026-09-02 | Decision | OPEN-04 re answered as Amazon Managed Grafana only, superseding the 2026-08-23 answer of all three behind per tenant flags. TASK-P2-007 and TASK-P2-008 descoped rather than deleted, and ISS-024 closed as by design rather than fixed | `a2304cf` | [P2 plan](docs/plans/P2-implementation-plan.md) |
| CHG-0068 | 2026-09-02 | Feature | TASK-P2-001, the prototype imported byte identical and its behaviour pinned by 15 golden files across 14 dashboards and 4 alert rules. Runs entirely offline through the prototype's own switches rather than through mocks | `a2304cf` | [P2 plan](docs/plans/P2-implementation-plan.md) |
| CHG-0069 | 2026-09-03 | Refactor | TASK-P2-002, the cost model and the engine classifier extracted from the prototype under the golden files. Thirteen rates and thresholds moved from literals into settings. One string diverges, the em dash the writing rules forbid, and it is enumerated rather than absorbed | `70da3ae` | [P2 plan](docs/plans/P2-implementation-plan.md) |
| CHG-0070 | 2026-09-04 | Refactor | TASK-P2-003, the prototype decomposed into three modules and deleted. Six exclusions removed with it, including the one suppressing the urllib.request rule that CVE-2026-15806's acceptance depends on. The Grafana adapter raises typed causes rather than returning an empty list on failure | `f3f0758` | [P2 plan](docs/plans/P2-implementation-plan.md) |
| CHG-0071 | 2026-09-05 | Feature | TASK-P2-004, the QuerySurface port and the query domain. Named for the pattern rather than for Grafana, and a test holds every signature and every returned type against a list of vendor words. The ports package gained two grouping tuples, because it is no longer eight ports of one kind | `d86bfe1` | [P2 plan](docs/plans/P2-implementation-plan.md) |
| CHG-0072 | 2026-09-06 | Process | User interface architecture written, closing the gap where the product had a visual system and no information architecture. Seven fixed navigation groups replace the flat five section list, every route is fixed and recorded as ADR-0020, the home screen is a trust strip above the money, and screens are built against a typed fixture before their route exists so a sub project is visible while it is being built rather than after | `9687fd7` | [docs/13-UI-ARCHITECTURE.md](docs/13-UI-ARCHITECTURE.md) |
| CHG-0073 | 2026-09-06 | Process | The interface architecture planned. Three tasks added to the P0 plan for routing, the fixture seam and the home screen, and TASK-P2-022 split into four screen tasks in a new wave K that does not wait for wave J. Screens are now built against typed fixtures and marked on screen as such, so P2 is reviewable while it is being built rather than at task 21 of 22 | `9687fd7` | [P0 plan](docs/plans/P0-implementation-plan.md), [P2 plan](docs/plans/P2-implementation-plan.md) |
| CHG-0074 | 2026-09-07 | Feature | TASK-P0-036, the seven navigation groups and the route migration. Five screens moved from a five entry state machine to routes carrying their group. An unbuilt screen is listed with the sub project that brings it, and a wrong address renders differently from one merely unbuilt. react-router admitted at rung two of ADR-0013. AppShell lost its section and onSelect props | `295f032` | [ADR-0020](docs/adr/ADR-0020-seven-fixed-navigation-groups.md) |
| CHG-0075 | 2026-09-09 | Feature | TASK-P0-037, the fixture seam and its marker. A screen is built against a typed fixture before its route exists and renders a visible FIXTURE DATA band, not gated on a build flag. A failing route raises rather than falling back to invented numbers. The declared set holds route templates so a parameterised detail path matches, and tests/api/test_fixture_surfaces.py fails the build when one becomes a live route, discovering route modules rather than listing them | `bf90690` | [docs/13-UI-ARCHITECTURE.md](docs/13-UI-ARCHITECTURE.md) section 11 |
| CHG-0076 | 2026-09-11 | Feature | TASK-P0-038, the home screen. Meter's own cost on the front page and nowhere else, per architectural constraint 7. The screen owns no data of its own and a test asserts it requests only what PlatformScreen already requests. An unfilled slot names the sub project that will fill it and renders no figure and no currency, which makes the front page the progress view. P0 reaches 38 of 38 tasks, which is not the same as P0 being signed off | `623b2a3` | [docs/13-UI-ARCHITECTURE.md](docs/13-UI-ARCHITECTURE.md) section 6 |
| CHG-0077 | 2026-09-13 | Feature | TASK-P2-022, the query findings screen. The first fixture backed surface, ranked by monthly cost sorted as decimals, with the reason as a column of prose rather than a tooltip so it survives a screenshot. Fixture data moved to src/api/fixtures because the screen imports it and it ships to a browser. An unrecognised provenance renders as modelled, the only direction that does not overclaim. Scanned volume reported in MiB after GiB rounded a real scan to zero | `29676ef` | [P2 plan](docs/plans/P2-implementation-plan.md) TASK-P2-022 |
| CHG-0078 | 2026-09-15 | Feature | TASK-P2-023, the finding detail screen. Publishes the query, the target, the engine and the formula with its inputs substituted. The fixture arithmetic did not reconcile, 5,184 dollars of working printed under a headline of 12,400, and a screen whose purpose is that the sum can be checked must not fail when checked. Corrected, and a test now derives each cost from its own inputs and asserts the list and the detail quote the same figure. The first surface where the declared template and the fetched path differ | `1f34786` | [P2 plan](docs/plans/P2-implementation-plan.md) TASK-P2-023 |
| CHG-0079 | 2026-09-17 | Feature | TASK-P2-024, the query surfaces screen. An instance Meter could not read is listed with its typed cause and no numeral, beside a reachable instance holding a genuine zero, so the two cannot be mistaken for each other. All three fixture instances are managed_grafana rather than one per SurfaceKind as planned, because the other two kinds were descoped as TASK-P2-007 and 008 and a fixture claiming them would show an estate that cannot exist | `92e2eea` | [P2 plan](docs/plans/P2-implementation-plan.md) TASK-P2-024 |
| CHG-0080 | 2026-09-19 | Feature | TASK-P2-025, the enforcement screen and the P2 journey, left Partly rather than Done. Revoke is absent rather than disabled when the API says an action is not revocable, and on a fixture backed screen it says it did nothing rather than failing silently. Expiry carries an absolute stamp with its date and a countdown together, after a bare time made a control applied three days ago read as one applied this morning. The journey criterion needs the workspace floor and the undo from TASK-P2-017 and 019, which this task never depended on | `a9ac9d7` | [P2 plan](docs/plans/P2-implementation-plan.md) TASK-P2-025 |
| CHG-0081 | 2026-09-21 | Feature | TASK-P0-039, the visual layer, closing ISS-138. One stylesheet against the tokens that already existed, with zero component or screen files touched, which is the property ADR-0021 was decided on. Contrast is computed from the declared tokens rather than trusted, because axe cannot measure it in jsdom and every existing axe assertion had been passing without looking at a colour. ROW_HEIGHT moved from 28 to 32 to agree with the CSS. P0 reaches 39 of 39 tasks | `d5c8cdc` | [ADR-0021](docs/adr/ADR-0021-plain-css-over-a-utility-framework.md) |
| CHG-0082 | 2026-09-18 | Design | P1 cost surface design specification written, fifteen sections. Covers FEAT-020, FEAT-021 and FEAT-022 against a fake adapter and explicitly not anomalies, commitments or the export. The schema it writes to was already migrated by P0, so it adds no migration | `0000929` | [P1 spec](docs/specs/2026-09-18-p1-cost-intelligence-design.md) |
| CHG-0083 | 2026-09-18 | Design | P1 implementation plan written, 13 tasks in five waves, each carrying the anti hallucination fields. The sub project list in scripts/docs/sync.py was a literal and did not mention P1, so it is derived from the plan files present now and a test holds it there | `pending` | [P1 plan](docs/plans/P1-implementation-plan.md) |
| CHG-0084 | 2026-09-18 | Correction | TASK-P1-001. BillingPeriod, CostMeasure and CostTotal added to the domain. The port the task said to create already existed from P0 and is unchanged, which is ISS-180. The billing period end is exclusive, which the fixtures assumed and nothing had written down | `pending` | [P1 plan](docs/plans/P1-implementation-plan.md) TASK-P1-001 |

<!-- generated:changes end -->

---

## 5. Issues

<!-- generated:issues start -->
<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. Edit docs/registry.yaml, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

**123 FIXED, 52 OPEN, 0 PARKED.** Full detail with evidence in [tasks/ISSUES.md](tasks/ISSUES.md).

FIXED means the design decision is recorded, not that code exists. Implementation status lives only in [tasks/STATUS.md](tasks/STATUS.md).

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
| ISS-111 | HIGH | Narrowed 2026-09-17 from the whole drill to its first step. The procedure now exists as make restore-drill and docs/runbooks/restore.md, and three of its four steps have been performed against a real restore of a real database, 21 tables with the migrations reaching head, the application starting against the restored data and the freshness route reporting ten collectors. Those three are where restores actually fail. What has never run is restoring from an Aurora snapshot, because no account has ever been provisioned, which is ISS-122. P0 is not signed off until that one step has been done once | OPEN | [P0 plan](docs/plans/P0-implementation-plan.md) TASK-P0-028, `docs/runbooks/restore.md` |
| ISS-114 | HIGH | The API image could never have started. Its CMD named finops_api.main:app and no such module level symbol has ever existed, so every deploy of that image would have failed at startup with an attribute error and nothing in the build would have caught it | FIXED | Found while adding the MCP server's command to the same image. Fixed with a bootstrap factory and `--factory`, and a test in `tests/mcp/test_contract.py` now imports every target the Dockerfile names |
| ISS-118 | HIGH | Five pipeline jobs called make on images that do not have it, so each would have failed with "make - command not found" before running a single check | FIXED | `python:slim` is Debian with no build tools. Fixed with a shared before_script, and `tests/scripts/test_pipeline.py` now fails when a job calls make on an image without it |
| ISS-122 | HIGH | No Terraform stack has been planned or applied. terraform validate and fmt pass on all three, which checks syntax, provider schema and references, and checks nothing about whether the stack builds | OPEN | A plan needs real credentials for the S3 state backend and for the caller identity data sources. Also outstanding from TASK-P0-033: the screenshot of a stalled collector in ALARM. P0 is not signed off until a plan runs |
| ISS-132 | HIGH | A CloudWatch metric maths expression using the FILTER function is classified as Logs Insights, because the engine test is a substring match on "filter " in the expression | OPEN | Pinned by tests/query/test_classify.py rather than fixed, because TASK-P2-002 is an extraction and changing it moves real numbers. The consequence is a metric query priced as a log scan, which overstates it by orders of magnitude. Fix in its own commit where the golden diff shows which figures moved |
| ISS-135 | HIGH | finops_query was in no layer list, so nothing constrained what it could import. Not the import-linter contract, not the graph builder, and not the distribution's own packages | FIXED | It could have imported finops_api and all three checks would have passed. Holding the two orderings equal did not catch it, because they agreed about a package neither mentioned. tests/scripts/test_layer_agreement.py now asserts every declared package has a layer, and the constraint was probed by importing finops_api and confirming it breaks |
| ISS-136 | HIGH | A failed request renders default coverage as though it were a complete answer. With no envelope the shell falls back to 0 of 0 and prints "Showing all 0 accounts" beside the typed failure, which reads as confident complete coverage of an empty estate. Section 6 of docs/12-UI-DESIGN.md requires complete coverage to say so, and section 4 requires an unknown state to suppress the figure rather than default it. Observed on 2026-09-06 running the P0 frontend with no API reachable | OPEN | [docs/12-UI-DESIGN.md](docs/12-UI-DESIGN.md) sections 4 and 6, `finops-web/src/shell/AppShell.tsx` |
| ISS-138 | HIGH | ADR-0019 decided Tailwind driven by our tokens, and it was never installed or admitted through make dep-check. tokens.css carries 27 tokens of which 6 are consumed, and defines no layout selector at all, so every screen renders as browser default HTML. Sections 3 and 5 of docs/12-UI-DESIGN.md, provenance and failure, are implemented. Sections 7 and 10, density, spacing, surface, border and responsive, are not. The severity ramp is declared and never applied, so severity reads as repeated squares with no colour. Found 2026-09-16 while running the application | FIXED | [ADR-0021](docs/adr/ADR-0021-plain-css-over-a-utility-framework.md), TASK-P0-039, `finops-web/src/layout.css` |
| ISS-143 | HIGH | make up could not build or start, for six independent reasons found by running it. The builder stages ran as the base image's non root user and could not write /opt/venv. The dependency layer ran pip install with only pyproject.toml present, which setuptools cannot resolve without the package directories. pyproject listed top level packages explicitly, so subpackages like finops_api.db were never in the wheel and a migration inside the image failed on ModuleNotFoundError. finops_query was never added to either Dockerfile after TASK-P2-003 created it. docker-compose bound host port 5432 with no override. The services enumerated environment variables by hand and had never been given the query or retention settings. Fixed 2026-09-02 and make up, make seed and make unseed all verified working | FIXED | `docker/Dockerfile.api`, `docker/Dockerfile.worker`, `docker/Dockerfile.web`, `docker-compose.yml`, `pyproject.toml`, `.dockerignore` |
| ISS-144 | HIGH | default_ingest_rate passed the per day ingest setting into IngestRate, which _logs_insights_cost multiplies by a window measured in hours, overstating every Logs Insights figure by exactly 24. The seeded demo panel read 3,888,000 dollars a month against a correct 162,000. Introduced with the seed tooling on 2026-09-02 and fixed the same day, with the unit documented on IngestRate and pinned by a test, because the type carried no unit and nothing else in the codebase supplied one to compare against | FIXED | `finops_ingest/collectors/query_audit.py`, `finops_query/cost_model.py` |
| ISS-146 | HIGH | make security-scan could not complete and make security-scan-images had never run, because the images had never built. Three tooling faults hid the result. gitleaks ran with no config and reported two false positives on `collector=COLLECTOR`, matching a collector name as a secret. pip-audit was installed into the venv by make security-tools but the scan script looked only on PATH, so it reported the tool missing and stopped. pip-audit then audited the environment, which contains the project installed editable, failed to find `meter` on PyPI, and under --strict aborted before writing pip-audit.json, so Python dependencies were absent from every summary that reported zero findings. All three fixed 2026-08-29 and both scans pass | FIXED | `.gitleaks.toml`, `scripts/security/scan.sh` |
| ISS-147 | HIGH | The runtime images carried pip, setuptools and wheel, installed to build the venv and then copied into the runtime with it. setuptools 70.3.0 alone accounted for one High and one Medium in every image, four of the eight unresolved findings in the first image scan that had ever run. Build tools are not runtime code and are now removed from the venv before it is copied, which fixes the findings at the source rather than chasing a version and makes the image smaller. The remaining finding, CVE-2026-19672 in the base image, has no published fix and is accepted with an enforced reachability argument | FIXED | `docker/Dockerfile.api`, `docker/Dockerfile.worker`, `security/policy/accepted.yaml` |
| ISS-149 | HIGH | The local stack could never show the data it ships with. docker-compose pinned METER_LOCAL_TENANT_ID to a tenant that has no row, while make seed writes a different one, so every read resolved a scope for a tenant that does not exist and the first query failed on the audit insert with a foreign key error rather than an empty page. Found by calling the routes against the running stack, not by any test. Fixed 2026-08-29 by pointing the local stack at the tenant its only data source writes | FIXED | `docker-compose.yml`, `.env.example` |
| ISS-150 | HIGH | The web container had no proxy for `/api`, because a deployed environment terminates that path at the load balancer and the image config is written for that. Locally there is no load balancer, so every screen rendered an nginx 404 where its data should be. Fixed 2026-08-29 with a local only overlay mounted over the image config, leaving the deployed configuration untouched | FIXED | `docker/nginx.local.conf`, `docker-compose.yml` |
| ISS-151 | HIGH | The nginx image ships its own server block with `server_name localhost`, and nginx matches a server name exactly before falling back to the catch all. Every request whose Host is localhost was therefore served by the image default rather than by docker/nginx.conf, so the single page fallback was absent and a hard refresh on any route returned 404, and none of the three security headers were sent. A deployed environment is served under its own hostname and matches the catch all, so the effect there is limited to the day someone reaches the container as localhost. Fixed 2026-08-29 by copying an empty file over the image default, because the image has no shell to delete it with | FIXED | `docker/nginx.disabled.conf`, `docker/Dockerfile.web` |
| ISS-153 | HIGH | grafana_instance.account_id held a workspace identifier for every real workspace. The collector parsed `aws:account:region` out of the surface identifier and fell back to the identifier itself, and the AMG adapter names a listed workspace by its workspace id, so the fallback fired every time. Harmless until TASK-P2-021 made that column the one scope enforcement reads, at which point a scoped viewer silently lost every workspace. The upsert also never refreshed the column, so a corrected value would not have reached an existing estate. Fixed 2026-08-29 by carrying the account and region on SurfaceInstance from the adapter that knows them, and refreshing both on conflict | FIXED | `finops_core/domain/query.py`, `finops_providers/grafana/amg.py`, `finops_ingest/collectors/query_audit.py` |
| ISS-155 | HIGH | Every figure inside a table rendered its own provenance sentence and its own two timestamps, so a three figure row carried three copies of the same `as of` line and the phrase `accuracy not yet published`. Rows were about 90 px against the 32 px the design asks for, and the findings table ran 1297 px wide inside a 1147 px container on a 1440 px screen, which put monthly cost, the sort column and the point of the screen, off the right edge. Fixed 2026-09-11 with a density context that DataTable sets and Figure reads, so a table added later is dense without its author knowing the mechanism exists | FIXED | `finops-web/src/components/density.ts`, `finops-web/src/components/Figure.tsx` |
| ISS-158 | HIGH | The demo estate covered only the query tables, so five of the six built P0 screens had nothing to render and could not be assessed or verified at all. The seed now runs all four collectors, org tree then role health then platform cost then query audit, through the real run ledger, so the ingest and freshness screens fill from the same act of seeding rather than needing a second fixture that agrees with the first by hand. It also installs the default schedule, without which every collector read "not scheduled" and therefore "stale" one minute after it ran. Fixed 2026-09-12 | FIXED | `scripts/ops/seed_demo.py`, `finops_providers/fake/health.py`, `finops_providers/fake/platform_cost.py` |
| ISS-159 | HIGH | The ingest screen could never show a run. `build_meta` derives freshness from an `as_of` column, `ingest_run` has none, so the envelope carried two nulls and the screen reported the collector as never having run while listing its runs. The same route also compared its run count to the account count and reported "8 of 8 accounts" over a five account estate. Fixed 2026-09-12 by taking the timestamps from the newest run, which is a log and is as fresh as its last entry, and by counting runs. Freshness counts collectors and platform cost counts modules, both of which had the same wrong noun | FIXED | `finops_api/routes/ingest.py`, `finops_api/routes/platform.py` |
| ISS-168 | HIGH | There was no deployment procedure. docs/04-DEPLOYMENT.md explained why Terraform performs the deploy, why the images are amd64 and what the stack costs, and never said what to run or in what order. Nothing described creating the IAM roles, activating trusted access between Organizations and CloudFormation, creating the state bucket, generating the external id, or which of the three stacks to apply first. Nothing described onboarding an account either. Somebody trying to deploy this had the reasoning and none of the steps. Fixed 2026-09-17 with docs/runbooks/deploy.md and docs/runbooks/onboard-account.md, both of which say plainly that they have never been executed | FIXED | `docs/runbooks/deploy.md`, `docs/runbooks/onboard-account.md` |
| ISS-175 | HIGH | The findings list and the grouped view returned every audited day rather than each query's latest, so a finding appeared once per day the collector had run and the group sums added those days together. The estate's reported cost therefore grew by one estate per day. It was invisible for as long as the seeded estate held a single day of history, and became visible the moment a second existed, which is also what made the trend in ISS-172 possible. The front page read $5,088 for a group whose true cost was $2,544. Found 2026-09-06 while adding the sparkline column, by reading the rendered table rather than by any test. Fixed the same day by confining both reads to each query's most recent run date, per query rather than one global maximum so a query that stops being audited keeps its last known state | FIXED | `finops_api/db/repositories/query.py`, ranked and grouped, via _latest_only |
| ISS-177 | HIGH | The ad hoc query list reported one query once per day audited, and its cost that many times over. query_adhoc keeps one row per query per account, region and day, the same shape query_finding has, and most_expensive never filtered on the day. This is ISS-175 on the table that fix did not reach. Found 2026-09-06 by seeding seven days and reading the screen, which showed 14 rows for 2 queries and 356 runs where the newest day had 57. One seeded day hides it completely. The route had no test at all, which is what let a known bug reappear on a second table. Fixed the same day, the predicate is now one function both repositories call, named per table because getting the identity columns wrong drops rows silently rather than failing | FIXED | `finops_api/db/repositories/query.py`, latest_audit_only, and `tests/api/test_query_routes.py` |
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
| ISS-137 | MEDIUM | A scanned volume under one MiB renders as the numeral zero on the query findings screen. Figure formats a count with no decimal places, so any sub unit quantity rounds to zero and a query that scans something reads as a query that scans nothing. Found on 2026-09-12 when a one MiB fixture row rendered as 0 in a GiB column, which was corrected to MiB. The general fix is a byte aware unit on Figure that picks its scale from the magnitude, rather than a caller chosen divisor | OPEN | `finops-web/src/components/Figure.tsx`, `finops-web/src/screens/QueryFindingsScreen.tsx` |
| ISS-139 | MEDIUM | TASK-P2-025 acceptance requires an end to end journey applying the workspace floor and confirming the undo, but its dependency list names only TASK-P2-022 to 024. The floor is TASK-P2-017 and the undo is TASK-P2-019, so the criterion was written against the finished sub project rather than the task. The screen and the rest of the journey are built and the task is Partly. Complete the journey when TASK-P2-019 lands, then move the task to Done | OPEN | [P2 plan](docs/plans/P2-implementation-plan.md) TASK-P2-025 |
| ISS-140 | MEDIUM | Every Figure renders its own freshness inline, so a table cell carries the figure, its provenance, its accuracy and two timestamps, and a dense row cannot be the 32 px that docs/12-UI-DESIGN.md section 7 asks for. The shell already shows worst case freshness for the whole view, so the per cell repetition may be redundant rather than load bearing. Rows are a minimum of 32 px and grow with their content. Deciding this is a product question rather than a styling one, because removing per cell freshness would change what a reader is told, and hiding it in CSS would take it from assistive technology as well. Found 2026-09-21 while styling the tables | OPEN | `finops-web/src/components/Figure.tsx`, `finops-web/src/layout.css`, TASK-P0-039 |
| ISS-141 | MEDIUM | TASK-P2-006 asked for the contract suite under moto, and moto implements no Grafana operation at all. ListWorkspaces, DescribeWorkspace, CreateWorkspace and every service account call answer Not yet implemented, while botocore knows them from the service model, so the gap is invisible until a call is made. botocore.stub is used instead and is stronger for API correctness, validating a request and a response against the real model. It caught the first draft of the test fixture omitting created, modified, grafanaVersion and authentication, all required by ListWorkspaces. Revisit if moto adds a grafana backend. Found 2026-09-24 | OPEN | `tests/providers/test_amg_surface.py`, [P2 plan](docs/plans/P2-implementation-plan.md) TASK-P2-006 |
| ISS-145 | MEDIUM | scripts/ops was in no image, so erase_principal.py could not be run in a deployed environment even though docs/09-DATA-CLASSIFICATION.md commits to that erasure procedure. The api image now carries scripts/ops. Found 2026-09-02 while making make seed work, which failed for the same reason | FIXED | `docker/Dockerfile.api`, [docs/09-DATA-CLASSIFICATION.md](docs/09-DATA-CLASSIFICATION.md) |
| ISS-148 | MEDIUM | TASK-P2-021 names eight routes and three MCP tools. Five routes now exist. The two remediation routes landed 2026-09-05 once TASK-P2-019 gave them a mechanism, and they carry the guard the plan asked for, refusing a finding that is not an explicit policy violation because a judgement call is a recommendation rather than a remediation. Three routes remain and none can be built here. Enforcement and its revoke need TASK-P2-016, parked on the AWS infrastructure ISS-122 records as never provisioned, and accuracy needs FEAT-018 which needs real CUR data. Two of the three MCP tools are still missing for the same reason, because each would be a facade over a route that does not exist | OPEN | `finops_api/routes/query.py`, `finops_mcp/tools.py` |
| ISS-152 | MEDIUM | The partial coverage banner read "1 missing. outside your scope" whatever the cause. On the query screens the missing workspace is usually one Meter could not read, not one the viewer is not entitled to, and naming the wrong cause sends the reader to an access request for a permission they already hold. The interface had nothing better to say because the envelope carried no failure for an unreachable workspace, because the route knew and did not report it. Fixed 2026-09-11 at the source. The query routes now report every unreachable workspace as a typed failure, and the banner names the cause it was given, falling back to entitlement only when nothing else explains the gap | FIXED | `finops_api/routes/query.py`, `finops-web/src/screens/surfaceStateFor.ts` |
| ISS-156 | MEDIUM | The trust strip sat inside the sidebar column rather than as a band above the content, so on a 1440 px screen the freshness line fell below the fold and the page lost the one statement that says what its numbers are worth. Section 8 of docs/13-UI-ARCHITECTURE.md asks for one band, full width, above everything. Fixed 2026-09-11 | FIXED | `finops-web/src/shell/AppShell.tsx`, `finops-web/src/layout.css` |
| ISS-157 | MEDIUM | The coverage banner said `accounts` on every screen because the noun was hardcoded in the component, and the query screens count workspaces. The aggregate then took the smallest visible and the largest total across panels counting different things, which on Home produced "Showing 0 of 3", true of nothing on the page. Fixed 2026-09-11 by carrying the counted noun on scope_coverage, where the route that did the counting knows it, and by stating one line per unit rather than one ratio across all of them | FIXED | `finops_api/schemas.py`, `finops-web/src/components/CoverageBanner.tsx` |
| ISS-160 | MEDIUM | A sparkline whose series never changes drew every point on the floor, because normalising a series with no range divides by a span of zero and the fallback put everything at the minimum. A module costing the same amount every day for thirty days therefore drew the same line as one costing nothing. Fixed 2026-09-12 by drawing a flat series down the middle, and the component now has tests, which it did not before | FIXED | `finops-web/src/components/Sparkline.tsx` |
| ISS-162 | MEDIUM | The organization tree drew every node at the same left edge, so the one thing the screen exists to show, the shape of the organization, was invisible. React Aria stamps `--tree-item-level` on each row and leaves the indent to the stylesheet, and the first attempt put it on the cell, which draws no box at all because it is display contents, so its padding never rendered. Fixed 2026-09-12 on the row. The node kind is now a muted label beside the name rather than a word appended to it, which read as `platform ou` | FIXED | `finops-web/src/layout.css`, `finops-web/src/components/OrgTree.tsx` |
| ISS-163 | MEDIUM | The freshness screen listed watermarks, and a watermark only exists after a collector has succeeded once. A scope that had never succeeded was therefore absent from the page rather than shown as never collected, so the one collector in trouble was the one the freshness screen did not mention. Fixed 2026-09-13. The page now lists every pair that has been attempted, the union of watermarks and runs, and carries three states rather than two, because a collector that has never worked is not a stale one. Its age is null rather than zero, since a zero reads as collected this instant, and the row names the typed cause of its last attempt. is_stale is now derived from the state rather than set beside it | FIXED | `finops_api/routes/ingest.py`, `finops_api/db/repositories/ingest.py`, `finops-web/src/screens/FreshnessScreen.tsx` |
| ISS-164 | MEDIUM | security/reports/latest is a committed symlink and the scan script wrote it as an absolute path, so it stored the author's own home directory in the repository and resolved on exactly one machine. Fixed 2026-09-13 by linking to the basename, which is correct because the link sits in the directory it points into | FIXED | `scripts/security/scan.sh` |
| ISS-166 | MEDIUM | The AMG adapter reads a workspace refresh floor and refuses to write one. The read is implemented and exercised; the write raises NotOptedIn naming this issue, because no AWS workspace has ever been reachable to test a write against, per ISS-122, and an untested write into somebody's Grafana is the one thing FEAT-014 must not ship. The fake surface implements the write end to end, so the guard, the recording and the undo path are all exercised. What is missing is one adapter method and a workspace to run it against once | OPEN | `finops_providers/grafana/amg.py`, set_refresh_floor |
| ISS-167 | MEDIUM | FEAT-017 requires the owner of a rewritten panel to be told what changed and how to undo it, and Meter has no notification transport at all. No mail sender, no webhook, no queue consumer for one, and no decision recorded about which it should be. Building one for this task would ship a new subsystem without that decision, so the rewrite records applied_by and the change is discoverable, and the notification waits for somebody to choose a channel | OPEN | `finops_ingest/remediation.py`, FEAT-017 |
| ISS-169 | MEDIUM | The engine had two spellings for one fact and nothing compared them. The classifier produces logs_insights and the database constraint ck_query_definition__engine_valid stores LOGS_INSIGHTS, so the CI gate's rule, applied to a stored row, matched neither and found no violation anywhere. Caught 2026-09-05 by a remediation route refusing a finding that plainly breaks the rule. Normalised at the point the API reads the row, and the same mismatch is worth looking for wherever else a stored engine meets a classifier constant | FIXED | `finops_api/routes/query.py`, _violates |
| ISS-170 | MEDIUM | get_settings loaded configuration from the environment unconditionally, so create_app's settings argument was a lie for every route that took the dependency. The application was assembled with one configuration and its routes answered from another, which is two sources for one fact and was invisible until a test needed a non default write level. Fixed 2026-09-05 by preferring what the application was built with | FIXED | `finops_api/deps.py`, get_settings |
| ISS-171 | MEDIUM | Ad hoc query detection was in the prototype and is in neither the P2 spec nor the code. The prototype's extract_adhoc_queries and its own report tab found Logs Insights queries run directly by a person, from no dashboard and no alert rule, and named the caller from CloudTrail. Those are the queries nobody owns, and a one off thirty day scan costs real money, appears on no dashboard, and Meter as built cannot see it at all. The word adhoc appears zero times in the spec and in zero source files, and section 3 of the spec does not list it as out of scope either, so this was never deferred to a later sub project. It fell through the gap between the prototype and the specification written from it. Found 2026-10-11 by mapping the restored prototype against what P2 delivered | OPEN | `docs/reference/sample_lambda.py.txt`, extract_adhoc_queries and build_adhoc_tab. Needs a CloudTrail read the AWS adapter does not make yet |
| ISS-172 | MEDIUM | Meter has no memory of what a finding cost last week. The prototype saved a snapshot per run, loaded its own history and computed trends and a rogue cost from it, so a reader could see whether a workspace was getting worse. P2 has no snapshot table, no history and no trend, the word trend appears zero times in the spec, and section 3 does not place it out of scope. Every figure the product shows is the present moment. A cost governance tool that cannot say a query got more expensive can report a problem and not that somebody caused it. Found 2026-10-11 by mapping the restored prototype against what P2 delivered | OPEN | `docs/reference/sample_lambda.py.txt`, build_snapshot, save_snapshot, load_history, compute_trends and compute_rogue_cost. Needs a table and a retention decision, and overlaps P1 which owns trend for spend. Fixed 2026-09-06, and smaller than it read: query_finding upserts on tenant, query and run_date, so the audit had been writing one row per query per day since it was built and nothing ever read them. The history is a side effect of idempotency rather than something anybody had to build. Scoped to a finding rather than to spend, which keeps it clear of P1: whether one query costs more this week is a governance question, and what an account spends is not |
| ISS-178 | MEDIUM | The CI test job could not have run an integration test. It declared a PostgreSQL service and a METER_DATABASE_URL beside it, and nothing in the test path read either. The settings fixture builds from .env.example, and the database fixture started a testcontainer regardless, which python 3.13 slim has no Docker socket to do. Both were decoration, and the integration tests would have errored on every run. Found 2026-09-06 by asking what the variable was for. Fixed the same day. The fixture now runs against a database it is given through METER_TEST_DATABASE_URL, falling back to a testcontainer, and the job sets that. The name is deliberately not METER_DATABASE_URL, which is in every .env and in the shell of anybody who has run make seed, and the fixture refuses a host that is not local because it migrates the database and writes to it | FIXED | `tests/conftest.py`, the engine fixture, and the test job in `.gitlab-ci.yml` |
| ISS-179 | MEDIUM | No pipeline run has ever been observed. The repository has no git remote, so .gitlab-ci.yml has never executed, and every statement in this repository about what CI does is a reading of the file rather than a result. Found 2026-09-06 while chasing a variable in the test job, which turned out to be decoration, see ISS-178. Nothing here is known to be wrong. The point is that nothing here is known to be right either, and the first push will be the first run, so it should be treated as a first run and watched rather than trusted | OPEN | `.gitlab-ci.yml`, and any document that describes what the pipeline does |
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
| ISS-142 | LOW | strip_comments removes a comment marker that begins a line or follows whitespace, so a hash or a double hyphen inside a quoted string in a query is treated as the start of a comment and the rest of that line is dropped from the key. It affects the fingerprint and the query key only, never the stored query text, the targets or the cost, so the consequence is that two queries differing only after such a marker could share a key. Judged unlikely enough to accept for now against the alternative, which is a parser per query language. Found 2026-09-01 while implementing TASK-P2-011 | OPEN | `finops_query/policy.py`, TASK-P2-011 |
| ISS-154 | LOW | make test-integration can never pass on its own. It runs only the integration marker while the coverage gate is set for the whole suite, so it reports 77 percent against a threshold of 80 and exits non zero even when every test passes. The pipeline was believed to run both suites in one pytest invocation and reach 98 percent. That was never observed and was not true, and ISS-178 says why. The repository has no remote, and the job could not run an integration test anyway. So this was a local target that lies, next to a pipeline nobody had watched. Fixed 2026-09-06, in the pass that put the integration tests into make verify. The coverage gate now runs on the one invocation that covers everything, and both slice targets pass --no-cov, because a fraction of the suite graded against the whole suite's threshold is a number that cannot be read in either direction. It fails when nothing is wrong, and it would pass a slice covering nothing it touched | FIXED | `Makefile`, targets test, test-unit and test-integration |
| ISS-161 | LOW | The fake account and organization fixtures carry a fixed observation date, which is right for a test asserting a value and wrong for a demo estate. Two screens read as five days stale beside four reading as current, in one estate seeded in one act. The fake provider and the fake role health now accept the time they are observed at, restamping the fixtures rather than replacing them. Fixed 2026-09-12 | FIXED | `finops_providers/fake/provider.py`, `finops_providers/fake/health.py` |
| ISS-165 | LOW | Timestamped scan report directories accumulate in the working tree and 21 of them are committed, one per change that ran a scan. A local session that runs the scan a dozen times leaves a dozen more untracked, so git status is permanently noisy and the audit trail the tracked ones were meant to be is diluted by iteration output. The durable record is security/POSTURE.md, which is generated and tracked. Whether the timestamped directories belong in the repository at all is a decision for whoever owns the security posture, and is left open rather than changed unilaterally | OPEN | `security/reports/`, `.gitignore` |
| ISS-173 | LOW | The P2 specification was written from the prototype and never recorded what it chose to leave behind. Section 3 lists four things as out of scope, all of them whole sub projects or engines, and none of the prototype's own capabilities. Two features were dropped silently as a result, ISS-171 and ISS-172, and neither was visible as missing until the prototype was restored and read side by side with the delivered work. The gap is process rather than code, because a specification derived from a working thing should enumerate what it declines to carry over. Found 2026-10-11 | OPEN | `docs/specs/2026-08-23-p2-query-cost-governance-design.md` section 3, and `docs/reference/README.md` which now holds the prototype it was derived from |
| ISS-174 | LOW | The ad hoc screen cannot tell an estate with no hand run queries from one whose evidence could not be read. Both render as an empty table. `_observations` in the query audit collector catches a CollectionError and returns None so the run continues, which is correct for the findings, because a modelled estate is still worth reporting and an aborted one is not. It leaves nothing for this screen to read. The fix is to record the evidence failure as a typed failure on the envelope, which is a change to the collector's error path rather than to the screen. Found 2026-09-06 while writing TASK-P2-026, and left as the one acceptance criterion that task did not meet. Fixed 2026-09-06 by recording the failure through the run ledger, the same table and the same path an unreachable workspace uses, so it reaches the trust strip on every envelope rather than only this screen, and clears when the scope recovers. That also surfaces the reason every figure had quietly stayed modelled, which was invisible for the same reason | FIXED | `finops_ingest/collectors/query_audit.py`, _observations, and `finops-web/src/screens/QueryAdhocScreen.tsx` |
| ISS-176 | LOW | make unseed failed on a foreign key and could not remove the demo estate. query_adhoc was added in TASK-P2-026 and not added to DEMO_TABLES, so the teardown deleted everything else and then could not delete the tenant. The command reported an error and left a half removed estate behind. Found 2026-09-06 by running unseed, not by any test, because nothing derived the teardown list from the schema. Fixed the same day, and a test now derives every tenant scoped table from the model metadata and requires each to be either torn down or declared as never seeded, so the next table added is caught the day it is added rather than the day somebody unseeds | FIXED | `scripts/ops/seed_demo.py`, DEMO_TABLES, and `tests/scripts/test_seed_demo.py` |
| ISS-180 | LOW | The P1 specification and implementation plan were written from the roadmap and the specification without auditing what P0 had already delivered, so wave A overstates what is missing. finops_core/ports/cost.py already existed with latest_available_period and read_period, and it is better than what the plan proposed because it separates an export that has published nothing from one that is missing and it names SchemaDrift. FakeProvider already implements that port against a four row fixture. Found 2026-09-18 on the first line of TASK-P1-001, by reading the file the plan said to create. Corrected the same day in both documents rather than building a second port beside the first. The cost was small because the plan's own contract says to stop at a disagreement with reality, and the lesson is that a plan written from documents should be checked against the tree before its first task, not during it | FIXED | `docs/specs/2026-09-18-p1-cost-intelligence-design.md` section 4, `docs/plans/P1-implementation-plan.md` TASK-P1-001 and TASK-P1-002 |

<!-- generated:issues end -->

---

## 6. Open questions

<!-- generated:open-questions start -->
<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. Edit docs/registry.yaml, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

| ID | Question | Status | Blocks | Detail |
| --- | --- | --- | --- | --- |
| OPEN-07 | What does the cost screen show for a tenant whose first ingest has not run, an empty state or the same not built yet panel the unbuilt screens use | OPEN | Nothing. It is a decision to make before the screen is written rather than after | [P1 spec](docs/specs/2026-09-18-p1-cost-intelligence-design.md) section 13. They are different situations, no bill collected yet and no screen built yet, and looking the same would send a person to the wrong place |
| OPEN-08 | Is there a point at which a closed billing period is declared final and Meter stops re reading it | OPEN | The collector cadence for closed periods. Not the first cut | [P1 spec](docs/specs/2026-09-18-p1-cost-intelligence-design.md) section 13. A restatement can arrive months later, and the cost of confirming a month is one Athena query |
| OPEN-09 | Does the unallocated bucket belong on the main cost screen as well as on allocation | OPEN | Nothing | [P1 spec](docs/specs/2026-09-18-p1-cost-intelligence-design.md) section 13. It is the number most likely to embarrass an estate, which argues both for showing it first and for not leading with it |
| OPEN-01 | Identity provider approach: new ADFS relying party, IAM Identity Center, or reuse the AWS relying party | PARKED at user request | Production login. Not the P0 build | [ADR-0008](docs/adr/ADR-0008-identity-adapter-deferred.md) |
| OPEN-02 | Single payer or multiple payer accounts | OPEN | P1 design | [tasks/ISSUES.md](tasks/ISSUES.md) |
| OPEN-03 | Is Business or Enterprise support available | OPEN | P3 and P5 coverage | [tasks/ISSUES.md](tasks/ISSUES.md) |
| OPEN-04 | Amazon Managed Grafana only, or self hosted and Grafana Cloud too. ANSWERED 2026-08-23: all three, behind per tenant flags. RE ANSWERED 2026-09-02, superseding that: Amazon Managed Grafana only. The earlier answer is kept rather than overwritten, because the two connection strategies it authorised were planned as TASK-P2-007 and TASK-P2-008 and those tasks are now descoped rather than deleted, so the record has to say what changed | ANSWERED | nothing | [P2 spec](docs/specs/2026-08-23-p2-query-cost-governance-design.md) section 4.1 |
| OPEN-05 | Jira or ServiceNow for the recommendation lifecycle | OPEN | P3 design | [tasks/ISSUES.md](tasks/ISSUES.md) |
| OPEN-06 | Which regions beyond Ireland and London. ANSWERED 2026-08-23: those two only, eu-west-1 and eu-west-2 | ANSWERED | nothing | Set in METER_REGIONS, see .env.example section 3 |

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
| Task runner | `Makefile` | Every routine task. `make help` lists them |
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
| Session accounting | `make dev`, `make stats` | Runs a coding session behind the pxpipe proxy and reports its token usage |
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

[docs/architecture/overview.html](docs/architecture/overview.html) is the whole
system in five diagrams: deploying it, how it collects, how a screen reads,
what protects it, and what it is made of. Each section is one line of prose and
one picture, because the deployment order and the trust chain are faster to see
than to read. It is written by hand, unlike everything else in that directory,
and it states plainly what has never run against AWS. Open it in a browser.

[docs/architecture/file-graph.md](docs/architecture/file-graph.md) shows how
every file depends on every other: Python imports, TypeScript imports,
Terraform module references and Dockerfile COPY edges, read out of the source.

`make graph` rebuilds it, emitting Mermaid for people and JSON for tools. It
also fails on a layering violation, so the graph is a gate rather than only a
picture.

---

## 12. Traceability

Every feature traces to a specification section, and every task traces to a
feature. The mapping from features to P0 tasks is in the
[P0 plan](docs/plans/P0-implementation-plan.md), section "Traceability".

A feature with no specification section, or a task with no feature, is a defect
in the documentation and is raised as an `ISS-nnn` row before work begins.
