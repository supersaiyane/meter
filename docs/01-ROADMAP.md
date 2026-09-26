# Roadmap

Last updated: 2026-08-23

The original requirement set described nine areas. Those nine areas are
really eight independent subsystems. Building them as one project produces a
shallow scaffold of everything and a working version of nothing, so the work
is decomposed. Each sub project gets its own design spec, its own
implementation plan, and its own delivery.

## Build order

The order is deliberately not numeric. P2 is built second because it reuses
an existing working prototype, it has provable return on investment inside
the first month, and stopping a 100,000 USD per week bleed buys the political
capital needed to fund the rest.

```
P0 Foundation
   |
   +--> P2 Query Cost Governance   (fast, visible, differentiated)
   |
   +--> P1 Cost Intelligence
           |
           +--> P3 Utilization and Rightsizing
           |
           +--> P4 Inventory and Topology --> P5 Quotas and Limits
           |
           +--> P6 Containers, EKS and ECS
                   |
                   +--> P7 Insight and LLM layer
```

## Sub project status

<!-- generated:roadmap-status start -->
<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. Edit docs/registry.yaml, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

| ID | Name | Features | Specified | Planned |
| --- | --- | --- | --- | --- |
| P0 | Foundation | 12 | 0 | 0 |
| P1 | Cost Intelligence | 7 | 4 | 0 |
| P2 | Query Cost Governance | 10 | 9 | 1 |
| P3 | Utilization and Rightsizing | 9 | 1 | 0 |
| P4 | Inventory and Topology | 6 | 1 | 0 |
| P5 | Quotas and Limits | 3 | 2 | 1 |
| P6 | Containers | 6 | 5 | 1 |
| P7 | Insight and LLM layer | 6 | 0 | 6 |

<!-- generated:roadmap-status end -->

## Exit criteria

Closes AUDIT-001 finding A001-F17, ISS-071. Without these, a sub project ends
when someone decides it feels finished.

**Every sub project exits on all seven of these**, plus its own specific
criterion. The specification template already carries a "Definition of done"
section, and a specification without one is not ready to be approved.

| # | Universal exit criterion |
| --- | --- |
| 1 | Every feature in the sub project is `Delivered` in `docs/registry.yaml`, and its feature document describes what was built rather than what was planned |
| 2 | `make ci` passes: lint, writing rules, document checks, tests, integration tests, security scan |
| 3 | Coverage at or above 80 percent for the code added |
| 4 | `security/POSTURE.md` reports zero findings against the deployed digest |
| 5 | An audit for that scope is published in `audits/`, with a `PROCEED` or `PROCEED WITH CONDITIONS` verdict, and every `CRITICAL` and `HIGH` finding closed |
| 6 | A restore drill performed and recorded, per the disaster recovery section of `docs/02-ARCHITECTURE.md` |
| 7 | The performance budgets for that sub project are asserted by a test, not measured once by hand |

Sub project specific criteria:

| Sub project | Exits when |
| --- | --- |
| P0 | A newly vended account appears within one hour with no human step, and a failed collection is visibly distinct from a zero |
| P2 | A policy violating dashboard is blocked at save, and a runaway query is detected and stopped within 15 minutes |
| P1 | Amortized cost reconciles to Cost Explorer within 1 percent for a full billing period, and allocation exceeds 95 percent |
| P3 | At least one recommendation has reached `verified` with realized savings confirmed against CUR |
| P4 | Every resource in a test account appears with its correct region and zone, and a three hop topology query returns in under 1 second |
| P5 | Quota utilization is reported for Ireland and London, with the coverage gaps stated on the screen rather than implied |
| P6 | Pod level cost is attributed for one cluster, and requested against used is reported per namespace |
| P7 | Every assistant answer carries provenance per figure, and the eval suite includes a partial scope case |

## When the project is done

Meter is not "done" in the sense of feature complete, because a FinOps platform
tracks a cloud that keeps changing. It reaches **steady state** when all seven
success criteria in `docs/00-GOAL.md` are met **and** the north star metric,
realized savings confirmed against CUR 60 days after a recommendation is marked
done, has been positive for three consecutive months.

Three months, because one month could be a single large rightsizing and two
could be luck. Three is the shortest window that shows the workflow is working
rather than that one saving happened.

## Sub projects

<!-- generated:subprojects start -->
<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. Edit docs/registry.yaml, then run make doc-sync. Hand edits here are overwritten and make check-docs will fail. See ADR-0014. -->

| ID | Name | Status | Features | Spec | Plan | Depends on |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | Foundation | Spec approved, in build | 12 (0 specified) | [spec](specs/2026-08-23-p0-foundation-design.md) | [plan](plans/P0-implementation-plan.md) | none |
| P1 | Cost Intelligence | Cost surface delivered, 13 of 13 tasks. Anomalies, commitments and the export are a second cut and are not started | 7 (4 specified) | [spec](specs/2026-09-18-p1-cost-intelligence-design.md) | [plan](plans/P1-implementation-plan.md) | P0 |
| P2 | Query Cost Governance | Spec approved, plan in review | 10 (9 specified) | [spec](specs/2026-08-23-p2-query-cost-governance-design.md) | [plan](plans/P2-implementation-plan.md) | P0 |
| P3 | Utilization and Rightsizing | Not started | 9 (1 specified) | not written | not written | P0, P1 |
| P4 | Inventory and Topology | Delivered | 6 (1 specified) | [spec](specs/2026-09-20-p4-inventory-and-topology-design.md) | [plan](plans/P4-implementation-plan.md) | P0 |
| P5 | Quotas and Limits | Not started | 3 (2 specified) | not written | not written | P0, P4 |
| P6 | Containers | Not started | 6 (5 specified) | not written | not written | P0, P1 |
| P7 | Insight and LLM layer | Not started | 6 (0 specified) | not written | not written | P1, P2, P3 |

<!-- generated:subprojects end -->

Status values: `Not started`, `Design in progress`, `Design approved, spec in
review`, `Spec approved, plan in progress`, `In build`, `Delivered`. Change one
in `docs/registry.yaml`, then run `make doc-sync`.

---

## P0 Foundation

**Goal.** The spine. Account onboarding, Organization topology, cross account
IAM, the provider abstraction, the canonical cost schema, the ingestion
framework, the authentication seam, and platform self metering.

**Delivers.** Log in, see the full Organization parent to child tree, see
every account with role health status, see an ingest and freshness dashboard
with typed per account errors, see Meter's own monthly cost. A newly vended
account appears automatically within one hour.

**Also in P0.** The security tool chain and the first zero vulnerability
posture, and the MCP server exposing the four P0 read tools. Both are cheaper
to establish now than to retrofit.

**Explicitly not in P0.** Cost data, recommendations, alerting, Config
ingest, any non AWS connector.

---

## P2 Query Cost Governance

**Goal.** Stop the failure mode that triggered this project. Detect, attribute,
prevent and remediate runaway observability query cost.

**Starting point.** A working 2,740 line prototype exists. It scans Amazon
Managed Grafana workspaces across accounts and regions, walks every dashboard
panel and alert rule, classifies the query engine, models cost from refresh
interval times window times log group ingestion rate, overlays measured
signal from CloudTrail StartQuery and DescribeQueries, detects trends across
days, and renders an HTML report to S3 with an SNS summary.

**What productionizing adds.**

1. Preventive control at the source. Set the Amazon Managed Grafana workspace
   `min_refresh_interval` floor. This is free, requires no code, and removes
   most of the exposure on its own.
2. A policy gate in continuous integration that rejects dashboard JSON where
   a Logs Insights panel combines a sub minute refresh with a window longer
   than 24 hours.
3. A near real time kill switch. An EventBridge rule on CloudTrail
   `StartQuery` counting per principal per hour, plus AWS Budgets Actions
   applying a deny policy on `logs:StartQuery` at threshold. This turns a
   week long 100,000 USD event into a 20 minute 300 USD event.
4. First class owner attribution from Grafana folder to team mapping and last
   editor, on top of the CloudTrail principal already extracted.
5. Auto remediation that rewrites the offending panel through the Grafana API
   with a change record and an undo.
6. Model calibration. Back test modelled cost against the CUR usage types for
   scanned bytes and metrics requested, and publish the accuracy percentage.
7. Support for self hosted Grafana and Grafana Cloud, not only Amazon Managed
   Grafana.
8. History moved from S3 snapshots into the warehouse. The HTML report becomes
   one view of the platform rather than the product itself.
9. Generalization. The same engine covers QuickSight SPICE refreshes, Athena
   workgroups, Redshift, and OpenSearch Dashboards. Grafana is the first
   adapter, not the only one.

**Specification written 2026-08-23.** All three Grafana surfaces are in scope,
Amazon Managed Grafana, self hosted and Grafana Cloud, behind per tenant flags.
Three enforcement levels, alert, throttle and deny, defaulting to alert. Three
write levels, none, workspace floor and full, defaulting to none. See
`docs/specs/2026-08-23-p2-query-cost-governance-design.md`.

**Why this is the differentiator.** The established FinOps vendors do not do
observability query cost governance. This is the part of Meter that has no
off the shelf substitute.

---

## P1 Cost Intelligence

**Goal.** The canonical cost surface. Per resource cost, trends, allocation,
anomalies, and commitment coverage.

**Key decisions already made.** Data Exports CUR 2.0 rather than legacy CUR,
Parquet and partitioned, with `resource_id` and split cost allocation data
enabled. Amortized and net amortized cost as the primary measures, with
unblended retained only for invoice reconciliation. Athena and Glue for
extract and load, Postgres for the served rollups. Ingestion is idempotent
because CUR is restated throughout the month.

**Also ingests.** Cost Categories, Savings Plan and Reserved Instance
utilization and coverage, Cost Anomaly Detection findings.

**Also delivers** chargeback and showback export, FEAT-045, because finance
does not work inside our interface and a FinOps tool that cannot hand finance a
file is missing its actual consumer.

---

## P3 Utilization and Rightsizing

**Goal.** Defensible right size recommendations with evidence, an owner, and a
lifecycle.

**Approach.** Ingest AWS Cost Optimization Hub, Compute Optimizer and Trusted
Advisor first, because they are free, organization wide, and already
consolidate rightsizing, idle, Graviton and commitment recommendations. Build
a bespoke collector only where AWS is blind: memory, EBS provisioned versus
used, gp2 to gp3, unattached volumes, aged snapshots, idle NAT Gateways, idle
load balancers, unassociated Elastic IPs, DynamoDB provisioned versus consumed.

**Includes the CloudWatch cost module.** Log groups with no retention policy,
high ingest groups with no queries in 90 days, duplicate delivery to both
CloudWatch Logs and S3, custom metrics never queried, alarms stuck in
insufficient data for 90 days. These findings are cheap to detect and
typically pay for the platform in the first month.

**Also delivers** the FinOps Score, FEAT-043, which ships only if it
decomposes to the findings that moved it, and blast radius scoring from the
dependency graph, FEAT-044, which turns the topology graph from a picture into
a control.

**Severity is derived from the money**, ADR-0016, not chosen.

**Rules that make recommendations defensible.** Never recommend on fewer than
14 days of data. Use p95 and p99, never max. Batch `GetMetricData` at 500
metrics per call at one hour period, never `GetMetricStatistics` per metric.
Account for burstable instance credits. Recommend at Auto Scaling group level,
not per instance.

---

## P4 Inventory and Topology

**Goal.** Every resource, by region and zone, with the connection map between
them.

**Approach.** AWS Config aggregator organization wide as the inventory
backbone, with Config relationships supplying the edges and Resource Explorer
for fast search. Writing hundreds of describe loops is a year of work and a
rate limit farm.

**Known cost risk.** Recording all resource types organization wide in Config
is itself a five figure monthly line item. Periodic recording for stable
resource types, continuous only for critical ones. This trade off is stated
to stakeholders up front.

**Graph storage.** Postgres node and edge tables with recursive common table
expressions. Around 95 percent of queries are one to three hops. A dedicated
graph database is added only once a need for deeper traversal is proven.
Rendered with Cytoscape.js, server side filtered to at most 2,000 nodes.

---

## P5 Quotas and Limits

**Goal.** Quota headroom per service, per region, for example Ireland and
London.

**Honest constraint.** There is no single API for used versus limit across all
services. Service Quotas provides limits, the `AWS/Usage` CloudWatch namespace
provides usage for a subset, Trusted Advisor covers more, and the remainder
needs service specific calls. Coverage is roughly 70 percent. Meter states
coverage gaps explicitly rather than presenting a misleadingly complete page.

**Positioning.** Quota headroom is a reliability metric, not a cost metric.
It belongs on the risk side of the product.

---

## P6 Containers, EKS and ECS

**Goal.** Cluster, namespace, workload and pod level cost and utilization.

**Key insight.** Split cost allocation data in CUR 2.0 provides pod level cost
directly from the billing pipeline, with no agent. It is free and widely
unknown. Enable it first.

**Beyond that.** In cluster telemetry through OpenCost or an ADOT collector
pushing to the warehouse.

**Metrics that matter.** Requested versus used CPU and memory per namespace,
which is the single largest source of Kubernetes waste and typically runs 40
to 60 percent. Node bin packing efficiency, idle and unallocated node cost,
Spot ratio, orphaned persistent volumes, unused LoadBalancer services.

**ECS.** Container Insights with task reservation versus utilization. Fargate
sizing is discrete, so recommendations must snap to valid vCPU and memory
combinations or engineers will correctly ignore them.

**Also delivers** node fleet optimisation as an integer linear program,
FEAT-047, which solves for the cheapest instance mix rather than reporting that
the cluster is 61 percent efficient. And predictive replica forecasting,
FEAT-048, under the four conditions in ADR-0015.

**Why this is late.** In cluster agents are a different deployment and
security story from read only IAM roles. Coupling it to P0 would slow P0 down.

---

## P7 Insight and LLM layer

**Goal.** Make the data explain itself.

**Where a language model earns its place.**

1. Natural language to cost question, over a governed semantic layer with tool
   calling. Never free form SQL against CUR, which is both a hallucination
   risk and a query cost risk inside a query cost tool.
2. Anomaly narration. Deterministic detection finds what changed. The model
   correlates the CUR delta with Config change events, CloudTrail, and deploy
   timestamps to explain why, and drafts the ticket.
3. Remediation authoring. Generate the Terraform or CloudFormation diff, or
   the Grafana panel patch, and open a pull request for human approval.
4. Weekly per team digests and executive summaries.

**The assistant bot, FEAT-042.** A conversational interface, in the product and
through any MCP client, that can find anything in the tool: an account, a
resource, a cost, a recommendation, a quota, a dashboard. Its backend is the
MCP server from ADR-0009, which calls the HTTP API with the caller's token, so
scope filtering, the audit log and rate limiting apply unchanged and cannot be
bypassed by adding a tool.

**Where it must never be.** Sizing arithmetic and cost figures stay
deterministic. The model explains a recommendation, it never computes one. A
single hallucinated savings number permanently destroys engineering trust.

**Also delivers** outbound AI request scanning, FEAT-046. Seven scanners look
at what comes in and none looked at what goes out, and in a financial services
environment a secret in a prompt is an exfiltration path with no control on it.

**AWS native capabilities used first.** Cost Optimization Hub, Compute
Optimizer, Trusted Advisor, Cost Anomaly Detection, Savings Plans
recommendations. Bedrock provides the narrative layer under a strict tool
contract, with provenance on every claim and a spend cap on the model itself.
