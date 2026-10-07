# P8 label table: FOCUS and Framework names on every screen

Date: 2026-10-05
Status: Approved by the owner as written on 2026-10-05, and applied in TASK-P8-004.
Task: TASK-P8-004, P8 spec section 5.3, FEAT-064

The rule, from the spec: a cost column takes its FOCUS display name, a screen or a KPI takes its FinOps Framework name, and the provider's own word stays in the cost column's tooltip, because practitioners search for both. No raw identifier appears on any screen.

Built from the code on 2026-10-05 by a script over `finops-web/src/screens`, `components` and `shell`: 353 labels in 44 files, of which 35 change, plus 69 codes that appear raw today and get display names. Counted by the script that wrote this document.

## 1. What changes

| Today | Proposed | Where | Basis |
| --- | --- | --- | --- |
| Spend and trend | Cost Explorer | Cost Explorer | Framework Reporting and Analytics; the menu name since TASK-P8-002 |
| Allocation | Allocation and Showback | Allocation | Framework Allocation; the menu name |
| Enforcement | Policies | Policies | Framework Governance, Policy and Risk; the owner placed it on 2026-10-05 |
| Export | Exports | Exports | Framework Reporting and Analytics; the menu name |
| Freshness | Data Freshness | Data Freshness | The menu name |
| Ingest runs | Ingestion runs | Ingestion | The menu name |
| Platform cost | Meter Cost | Meter Cost | The menu name |
| Assistant | Ask Meter | Ask Meter | The menu name |
| Container cost | Kubernetes cost | Kubernetes cost | Kubernetes cost allocation; the menu name |
| Container requests | Kubernetes rightsizing | Kubernetes rightsizing | Usage Optimization; the menu name |
| Query findings | Findings | Query Cost, its first tab | P8 spec section 5.3 |
| Query surfaces | Sources | Query Cost, a tab | P8 spec section 5.3; the Framework speaks of data sources |
| Ad hoc queries | Ad hoc | Query Cost, a tab | P8 spec section 5.3 |
| Surfaces under audit | Sources under audit | Overview | Follows Query surfaces becoming Sources |
| Total spend | Effective Cost, this period | Overview | FOCUS EffectiveCost; tooltip: AWS amortized cost |
| Amortized | Effective Cost | Cost Explorer, Allocation | FOCUS EffectiveCost; tooltip: AWS amortized cost |
| Amortized cost | Effective Cost | Meter Cost | FOCUS EffectiveCost; tooltip: AWS amortized cost |
| Billed | Billed Cost | Cost Explorer | FOCUS BilledCost; tooltip: AWS unblended cost |
| nobody tagged this | Unallocated cost | Allocation | Framework Allocation; the KPI on unallocated cost |
| More than usual | Impact | Anomalies | Framework Anomaly Management |
| That day | Actual cost | Anomalies | Framework Anomaly Management |
| Usually | Expected cost | Anomalies | Framework Anomaly Management |
| Of what we paid for, used | Commitment utilization | Commitments | KPI Commitment Utilization |
| Of what could be committed, is | Commitment coverage | Commitments | KPI on spend covered by commitment discounts |
| How much of what we paid for was used | Commitment utilization | Commitments, heading | KPI Commitment Utilization; the sentence stays beneath it, because two percentages side by side must each name their denominator |
| How much of the estate is on a commitment | Commitment coverage | Commitments, heading | KPI on spend covered by commitment discounts |
| Paid for and unused | Unused commitment | Commitments | FOCUS CommitmentDiscountStatus Unused; tooltip: AWS unused Savings Plan or RI commitment |
| On demand instead | On-Demand cost | Commitments | FOCUS PricingCategory Standard; tooltip: AWS On-Demand |
| Kind of commitment | Commitment discount type | Commitments | FOCUS CommitmentDiscountType |
| Monthly saving | Estimated monthly savings | Recommendations | Framework Usage Optimization; the figure is modelled |
| Saving a month | Estimated monthly savings | Commitments, resource page, Top actions | Same term as Recommendations |
| Bin packing | Cluster efficiency | Clusters | Common usage, P8 spec section 5.3 |

Not in this task: an effective savings rate is a new figure the API does not return, and P8 rule 1 says a screen asks for a route rather than deriving one, so it waits for a route. The forecast arrives with TASK-P8-008.

## 2. Codes that appear raw today, and their display names

### Waste classes, shown in Recommendations, Top actions and the resource page

| Code | Display name |
| --- | --- |
| `RIGHTSIZE_INSTANCE` | Rightsizing |
| `IDLE_INSTANCE` | Idle instance |
| `GRAVITON_CANDIDATE` | Graviton migration |
| `EBS_OVERPROVISIONED` | Overprovisioned volume |
| `EBS_GP2_TO_GP3` | gp2 to gp3 volume |
| `EBS_UNATTACHED` | Unattached volume |
| `SNAPSHOT_AGED` | Aged snapshot |
| `NAT_GATEWAY_IDLE` | Idle NAT gateway |
| `LOAD_BALANCER_IDLE` | Idle load balancer |
| `ELASTIC_IP_UNASSOCIATED` | Unassociated Elastic IP |
| `DYNAMODB_OVERPROVISIONED` | Overprovisioned DynamoDB capacity |
| `LOG_GROUP_NO_RETENTION` | Log group with no retention |
| `LOG_GROUP_UNQUERIED` | Unqueried log group |
| `LOG_DUPLICATE_DELIVERY` | Duplicate log delivery |
| `METRIC_UNQUERIED` | Unqueried metric |
| `ALARM_INSUFFICIENT_DATA` | Alarm with insufficient data |
| `CONTAINER_RIGHTSIZE` | Kubernetes rightsizing |
| `PARKABLE_WINDOW` | Off hours scheduling |
| `COMMITMENT_UNCOVERED` | Not covered by a commitment |

### Recommendation states, shown in Recommendations and the resource page

| Code | Display name |
| --- | --- |
| `OPEN` | Open |
| `ACCEPTED` | Accepted |
| `IN_PROGRESS` | In progress |
| `DONE` | Done |
| `VERIFIED` | Verified |
| `REGRESSED` | Regressed |
| `DISMISSED` | Dismissed |

### Recommendation sources

| Code | Display name |
| --- | --- |
| `COMPUTE_OPTIMIZER` | AWS Compute Optimizer |
| `COST_OPTIMIZATION_HUB` | AWS Cost Optimization Hub |
| `TRUSTED_ADVISOR` | AWS Trusted Advisor |
| `METER` | Meter |

### Realized savings verdicts

| Code | Display name |
| --- | --- |
| `VERIFIED` | Verified |
| `REGRESSED` | Regressed |
| `INCONCLUSIVE` | Inconclusive |

### Ingestion run states, shown lower case today

| Code | Display name |
| --- | --- |
| `pending` | Pending |
| `running` | Running |
| `succeeded` | Succeeded |
| `partial` | Partial |
| `failed` | Failed |

### Commitment discount types

| Code | Display name |
| --- | --- |
| `SavingsPlan` | Savings Plan |
| `ReservedInstance` | Reserved Instance |
| `SAVINGS_PLAN` | Savings Plan |
| `RESERVED_INSTANCE` | Reserved Instance |

### Collectors, shown in Data Freshness, Ingestion, the failure list and "Not yet collected by"

| Code | Display name |
| --- | --- |
| `account_health` | Account health |
| `budgets` | Budgets |
| `commitment` | Commitments |
| `commitment_actions` | Commitment actions |
| `container_usage` | Kubernetes usage |
| `cost_anomaly` | Cost anomalies |
| `cost_focus` | Cost and usage (FOCUS) |
| `finops_score` | FinOps Score |
| `iac_state` | Infrastructure as code state |
| `inventory` | Resource inventory |
| `org_tree` | Organization |
| `partition_maintenance` | Partition maintenance |
| `platform_cost` | Meter Cost |
| `query_audit` | Query audit |
| `query_evidence` | Query evidence |
| `quotas` | Service quotas |
| `realized_savings` | Realized Savings |
| `recommendations` | Recommendations |
| `retention_audit` | Retention, audit records |
| `retention_cost` | Retention, cost records |
| `retention_operational` | Retention, operational records |
| `retention_principal` | Retention, personal records |
| `retention_scope_cache` | Retention, scope cache |
| `team_digests` | Team digests |
| `waste_cloudwatch` | CloudWatch waste |
| `waste_compute` | Compute waste |
| `waste_parking` | Off hours scheduling |

## 3. Every label today, by screen

Unchanged means the label already says what it is in plain words, or names a dimension rather than a cost.


### AccountsScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Accounts | unchanged |  |
| aria-label | Filter by role health | unchanged |  |
| caption | Accounts in scope | unchanged |  |
| column | Account | unchanged |  |
| column | Name | unchanged |  |
| column | Role health | unchanged |  |
| column | Status | unchanged |  |
| span | healthy | unchanged |  |

### AssistantScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Ask a question | unchanged |  |
| aria-label | Assistant | Ask Meter | The menu name |
| column | Question | unchanged |  |
| column | Rule | unchanged |  |
| column | What happened | unchanged |  |
| column | When | unchanged |  |
| h2 | Earlier questions | unchanged |  |
| h2 | Kept out of a prompt | unchanged |  |
| h2 | Your last question | unchanged |  |
| label | Your question | unchanged |  |

### BudgetsScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Budgets | unchanged |  |

### ClustersScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Clusters | unchanged |  |
| th | Account | unchanged |  |
| th | Bin packing | Cluster efficiency | Common usage, P8 spec section 5.3 |
| th | Cluster | unchanged |  |
| th | Nodes | unchanged |  |
| th | On Spot | unchanged |  |
| th | Platform | unchanged |  |
| th | Region | unchanged |  |

### ContainerCostScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | `Cluster ${cluster.cluster_name}` | unchanged |  |
| aria-label | Container cost | Kubernetes cost | Kubernetes cost allocation; the menu name |
| caption | Each workload's measured share, the largest first | unchanged |  |
| th | Cost | unchanged |  |
| th | Kind | unchanged |  |
| th | Namespace | unchanged |  |
| th | Workload | unchanged |  |

### ContainerWasteScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | `Cluster ${cluster.cluster_name}` | unchanged |  |
| aria-label | Container requests | Kubernetes rightsizing | Usage Optimization; the menu name |
| caption | Each workload's request beside its use. Two figures, never one ratio. | unchanged |  |
| th | CPU requested | unchanged |  |
| th | CPU used, 99th percentile | unchanged |  |
| th | Memory requested | unchanged |  |
| th | Memory used, peak | unchanged |  |
| th | Namespace | unchanged |  |
| th | Out of memory | unchanged |  |
| th | Workload | unchanged |  |

### CostAllocationScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Allocation | Allocation and Showback | Framework Allocation; the menu name |
| column | Amortized | Effective Cost | FOCUS EffectiveCost; tooltip: AWS amortized cost |
| column | `By ${tag}` | unchanged |  |
| column | Line items | unchanged |  |
| restLabel | smaller owners | unchanged |  |
| span | nobody tagged this | Unallocated cost | Framework Allocation; the KPI on unallocated cost |

### CostAnomaliesScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Anomalies | unchanged |  |
| column | Account and service | unchanged |  |
| column | Day | unchanged |  |
| column | More than usual | Impact | Framework Anomaly Management |
| column | Severity | unchanged |  |
| column | That day | Actual cost | Framework Anomaly Management |
| column | Usually | Expected cost | Framework Anomaly Management |
| column | Why | unchanged |  |
| p | No day in the last fortnight stood out from the days before it | unchanged |  |

### CostCommitmentsScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Commitments | unchanged |  |
| caption | `${String(commitments.length)} commitments, most unused money first` | unchanged |  |
| caption | `${String(coverage.length)} services, most on demand spend first` | unchanged |  |
| column | Commitment | unchanged |  |
| column | Committed | unchanged |  |
| column | Could be committed | unchanged |  |
| column | Kind | unchanged |  |
| column | Kind of commitment | Commitment discount type | FOCUS CommitmentDiscountType |
| column | Of what could be committed, is | Commitment coverage | KPI on spend covered by commitment discounts |
| column | Of what we paid for, used | Commitment utilization | KPI Commitment Utilization |
| column | On demand instead | On-Demand cost | FOCUS PricingCategory Standard; tooltip: AWS On-Demand |
| column | Paid for and unused | Unused commitment | FOCUS CommitmentDiscountStatus Unused; tooltip: AWS unused Savings Plan or RI commitment |
| column | Service | unchanged |  |
| column | State | unchanged |  |
| h2 | How much of the estate is on a commitment | Commitment coverage | KPI on spend covered by commitment discounts |
| h2 | How much of what we paid for was used | Commitment utilization | KPI Commitment Utilization; the sentence stays beneath it, because two percentages side by side must each name their denominator |
| h2 | What to do about the gap | unchanged |  |
| th | Gap | unchanged |  |
| th | If it is wrong | unchanged |  |
| th | Saving a month | Estimated monthly savings | Same term as Recommendations |
| th | Severity | unchanged |  |

### CostExportScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Export | Exports | Framework Reporting and Analytics; the menu name |

### CostScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Spend and trend | Cost Explorer | Framework Reporting and Analytics; the menu name since TASK-P8-002 |
| caption | `${String(rows.length)} services, most expensive first` | unchanged |  |
| column | Amortized | Effective Cost | FOCUS EffectiveCost; tooltip: AWS amortized cost |
| column | Billed | Billed Cost | FOCUS BilledCost; tooltip: AWS unblended cost |
| column | Line items | unchanged |  |
| column | Service | unchanged |  |
| h2 | What this period has cost | unchanged |  |
| h2 | Which services it is on | unchanged |  |
| p | One day collected so far, which is not yet a trend | unchanged |  |
| restLabel | smaller services | unchanged |  |
| span | to | unchanged |  |

### DigestsScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Digests | unchanged |  |
| h2 | Weekly digests, newest first | unchanged |  |

### EnforcementScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Enforcement | Policies | Framework Governance, Policy and Risk; the owner placed it on 2026-10-05 |
| caption | Active and past controls, what they did and when they stop | unchanged |  |
| column | Action | unchanged |  |
| column | Applied | unchanged |  |
| column | Expires | unchanged |  |
| column | Principal | unchanged |  |
| column | Reason | unchanged |  |
| column | Revoke | unchanged |  |

### EntityScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Resource | unchanged |  |
| dt | Account | unchanged |  |
| dt | Identifier | unchanged |  |
| dt | Location | unchanged |  |
| h3 | What a change here can reach | unchanged |  |
| h3 | What is wrong with it | unchanged |  |
| h3 | What it cost | unchanged |  |
| h3 | What it is attached to | unchanged |  |
| h3 | What manages it | unchanged |  |
| h3 | Where it is | unchanged |  |
| p | No finding names this resource. | unchanged |  |
| p | Nothing is recorded as attached to this resource. | unchanged |  |
| p | Working out what this is connected to. | unchanged |  |
| th | Account | unchanged |  |
| th | Counted | unchanged |  |
| th | Finding | unchanged |  |
| th | How many | unchanged |  |
| th | If it is wrong | unchanged |  |
| th | Kind | unchanged |  |
| th | Relationship | unchanged |  |
| th | Resource | unchanged |  |
| th | Saving a month | Estimated monthly savings | Same term as Recommendations |
| th | Severity | unchanged |  |
| th | State | unchanged |  |
| th | What it means | unchanged |  |

### FreshnessScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Freshness | Data Freshness | The menu name |
| caption | Collector freshness | unchanged |  |
| column | Against its cadence | unchanged |  |
| column | Age | unchanged |  |
| column | Cadence | unchanged |  |
| column | Collector | unchanged |  |
| column | Scope | unchanged |  |
| column | State | unchanged |  |
| span | current | unchanged |  |
| span | never | unchanged |  |
| span | stale | unchanged |  |

### GeographyScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Geography | unchanged |  |
| aria-label | Resources here | unchanged |  |
| dt | Belonging to no region | unchanged |  |
| dt | In a region we cannot place | unchanged |  |
| dt | In a region we could not read | unchanged |  |
| th | Account | unchanged |  |
| th | Kind | unchanged |  |
| th | Region | unchanged |  |
| th | Resource | unchanged |  |
| th | Type | unchanged |  |

### HomeScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Budget | unchanged |  |
| aria-label | Largest cause | unchanged |  |
| aria-label | Meter cost | unchanged |  |
| aria-label | Not yet collected | unchanged |  |
| aria-label | Open findings | unchanged |  |
| aria-label | Summary | unchanged |  |
| aria-label | Surfaces under audit | Sources under audit | Follows Query surfaces becoming Sources |
| aria-label | Top actions | unchanged |  |
| aria-label | Top findings by dollar | unchanged |  |
| aria-label | Total spend | Effective Cost, this period | FOCUS EffectiveCost; tooltip: AWS amortized cost |
| caption | `The ${String(top.length)} most expensive, of ${String(rows.length)}` | unchanged |  |
| column | Finding | unchanged |  |
| column | Monthly | unchanged |  |
| column | Owner | unchanged |  |
| column | Severity | unchanged |  |
| h3 | Not yet collected | unchanged |  |
| label | Largest cause | unchanged |  |
| label | Meter cost | unchanged |  |
| p | no earlier period collected to compare against | unchanged |  |
| span | not yet collected, arrives with | unchanged |  |

### IngestScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Ingest runs | Ingestion runs | The menu name |
| caption | Recent collection runs | unchanged |  |
| column | Collector | unchanged |  |
| column | Items written | unchanged |  |
| column | Scope | unchanged |  |
| column | Status | unchanged |  |

### OrganizationScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Organization | unchanged |  |
| aria-label | View | unchanged |  |
| p | Loading the graph view | unchanged |  |

### PlatformScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Platform cost | Meter Cost | The menu name |
| caption | What Meter costs to run | unchanged |  |
| column | Amortized cost | Effective Cost | FOCUS EffectiveCost; tooltip: AWS amortized cost |
| column | Module | unchanged |  |
| column | Thirty days | unchanged |  |
| h2 | What Meter costs to run | unchanged |  |
| h2 | Which module it is on | unchanged |  |
| label | `${row.module} daily cost` | unchanged |  |
| restLabel | smaller modules | unchanged |  |

### QueryAdhocScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Ad hoc queries | Ad hoc | P8 spec section 5.3 |
| column | Account | unchanged |  |
| column | Cost | unchanged |  |
| column | Runs | unchanged |  |
| column | Scanned | unchanged |  |
| column | The query | unchanged |  |
| column | Who ran it | unchanged |  |
| h2 | Spent by queries nobody owns | unchanged |  |

### QueryFindingDetailScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Finding | unchanged |  |
| h3 | Measured evidence | unchanged |  |
| h3 | Monthly cost | unchanged |  |
| h3 | Over time | unchanged |  |
| h3 | Target | unchanged |  |
| h3 | The query | unchanged |  |
| h3 | The working | unchanged |  |
| label | `Monthly cost across ${String(costSeries.length)} days` | unchanged |  |
| label | Runs observed | unchanged |  |
| p | not yet collected, arrives with the measured overlay | unchanged |  |

### QueryFindingsScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Query findings | Findings | P8 spec section 5.3 |
| caption | Queries ranked by what they cost each month | unchanged |  |
| column | Dashboard and panel | unchanged |  |
| column | Monthly cost | unchanged |  |
| column | Owner | unchanged |  |
| column | Refresh | unchanged |  |
| column | Runs per day | unchanged |  |
| column | Scan per run, MiB | unchanged |  |
| column | Severity | unchanged |  |
| column | Trend | unchanged |  |
| column | Why | unchanged |  |
| column | Window | unchanged |  |
| label | `Monthly cost across ${String(series.length)} days` | unchanged |  |
| span | once | unchanged |  |

### QueryGroups

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | What is driving the cost | unchanged |  |
| caption | What is driving the cost, worst first. One row is one change. | unchanged |  |
| column | Cause | unchanged |  |
| column | Findings | unchanged |  |
| column | Monthly cost | unchanged |  |
| column | Severity | unchanged |  |

### QuerySurfacesScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Query surfaces | Sources | P8 spec section 5.3; the Framework speaks of data sources |
| caption | Where queries live, including the instances Meter could not read | unchanged |  |
| column | Instance | unchanged |  |
| column | Kind | unchanged |  |
| column | Location | unchanged |  |
| column | Queries found | unchanged |  |
| column | Reachable | unchanged |  |
| column | Refresh floor | unchanged |  |
| span | none set | unchanged |  |

### QuotaDetailScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Quota | unchanged |  |
| dt | Command | unchanged |  |
| dt | Console | unchanged |  |
| h3 | Requests against this quota | unchanged |  |
| h3 | The increase Meter would ask for | unchanged |  |
| span | , ask for | unchanged |  |

### QuotasScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Quotas | unchanged |  |
| caption | Quotas with a usage figure, the fullest first | unchanged |  |
| th | Account | unchanged |  |
| th | Asked for | unchanged |  |
| th | Full | unchanged |  |
| th | Limit | unchanged |  |
| th | Measured by | unchanged |  |
| th | Quota | unchanged |  |
| th | Region | unchanged |  |
| th | Requested | unchanged |  |
| th | Status | unchanged |  |
| th | Used | unchanged |  |
| th | Why there is no figure | unchanged |  |

### RemediationControls

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Remediation | unchanged |  |
| p | The request did not reach the server, so nothing changed. | unchanged |  |

### ResourceListScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Narrow the list | unchanged |  |
| aria-label | Pages | unchanged |  |
| aria-label | Resources | unchanged |  |
| label | Account | unchanged |  |
| label | Kind | unchanged |  |
| label | Region | unchanged |  |
| label | Type | unchanged |  |
| option | Any | unchanged |  |
| th | Account | unchanged |  |
| th | Kind | unchanged |  |
| th | Location | unchanged |  |
| th | Resource | unchanged |  |
| th | Type | unchanged |  |

### TopologyScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Bounds | unchanged |  |
| aria-label | Root resource | unchanged |  |
| aria-label | Topology | unchanged |  |
| caption | Relationships, with the API that supplied each one. | unchanged |  |
| h2 | Start the map from | unchanged |  |
| label | Hops | unchanged |  |
| label | Most nodes | unchanged |  |
| p | Choose a resource to map what it connects to. | unchanged |  |
| p | Loading the map | unchanged |  |
| span | (another account) | unchanged |  |
| span | (outside this view) | unchanged |  |
| th | Account | unchanged |  |
| th | From | unchanged |  |
| th | Read from | unchanged |  |
| th | Region | unchanged |  |
| th | Relationship | unchanged |  |
| th | Resource | unchanged |  |
| th | To | unchanged |  |
| th | Type | unchanged |  |
| th | Zone | unchanged |  |

### WasteSavingsScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | By verdict | unchanged |  |
| aria-label | Realized savings | unchanged |  |
| column | Cost after | unchanged |  |
| column | Cost before | unchanged |  |
| column | Usage before and after | unchanged |  |
| column | Verdict | unchanged |  |
| column | Why | unchanged |  |
| column | Windows | unchanged |  |
| span | not published, so there is no control | unchanged |  |

### WasteScoreScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | FinOps Score | unchanged |  |
| aria-label | Not assessed | unchanged |  |
| aria-label | `Score for ${score.account_id}` | unchanged |  |
| h3 | Not assessed | unchanged |  |
| label | `out of ${String(score.available_weight)} available weight` | unchanged |  |

### WasteScreen

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Examined and not flagged | unchanged |  |
| aria-label | Recommendations | unchanged |  |
| column | Confidence | unchanged |  |
| column | Monthly saving | Estimated monthly savings | Framework Usage Optimization; the figure is modelled |
| column | Owner | unchanged |  |
| column | Severity | unchanged |  |
| column | State | unchanged |  |
| column | What | unchanged |  |
| column | Where | unchanged |  |
| column | Why | unchanged |  |
| h2 | Looked at and left alone | unchanged |  |
| p | Showing one finding, | unchanged |  |
| restLabel | smaller classes | unchanged |  |
| span | Every open recommendation has an owner | unchanged |  |
| span | nobody yet | unchanged |  |
| th | Account | unchanged |  |
| th | Observed | unchanged |  |
| th | Resource | unchanged |  |
| th | Rule | unchanged |  |
| th | Why it was left alone | unchanged |  |

### CitedProse

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | `Citation ${String(number)}` | unchanged |  |
| h4 | Tool calls, in the order the model made them | unchanged |  |
| h4 | Where each value came from | unchanged |  |
| p | None. The model read no route for this. | unchanged |  |

### Exchange

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| dt | Estimated cost, at list prices | unchanged |  |
| dt | Input tokens | unchanged |  |
| dt | Model | unchanged |  |
| dt | Output tokens | unchanged |  |
| p | Asked | unchanged |  |
| span | , under a cent | unchanged |  |

### Figure

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| span | measured | unchanged |  |

### FixtureBand

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| p | FIXTURE DATA. This screen is not connected to a collector yet. | unchanged |  |

### OrgTree

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Organization | unchanged |  |
| span | + | unchanged |  |
| span | unreachable, outside your scope | unchanged |  |

### Sparkline

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | `${label}, ${provenance}, ${String(points.length)} points` | unchanged |  |

### StateBoundary

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| p | Nothing matches this filter. | unchanged |  |

### TopActions

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Top actions | unchanged |  |
| p | Nothing open in this group, which is an answer rather than a gap. | unchanged |  |
| th | Account | unchanged |  |
| th | Finding | unchanged |  |
| th | If it is wrong | unchanged |  |
| th | Saving a month | Estimated monthly savings | Same term as Recommendations |
| th | Severity | unchanged |  |

### AppShell

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | Problems affecting this view | unchanged |  |
| aria-label | Sections | unchanged |  |
| p | Each citation carries its own as of date | unchanged |  |
| p | Meter | unchanged |  |
| p | Not yet collected | unchanged |  |
| p | Oldest in view: | unchanged |  |

### ScreenTabs

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| aria-label | `${label} views` | unchanged |  |

### ThemeToggle

| Kind | Today | Proposed | Basis |
| --- | --- | --- | --- |
| legend | Theme | unchanged |  |
