# P6 Containers, EKS and ECS: design specification

Date: 2026-09-20
Status: Provisional, pending approval
Sub project: P6
Features: FEAT-035, FEAT-036, FEAT-037 (first cut); FEAT-047, FEAT-048 (second cut)
Depends on: P0 delivered, P1 delivered, P3 delivered
Supersedes: nothing

## 1. Purpose

A cluster is the one place the account level cost view stops working. Fifty teams
share four node groups, the bill says EC2, and nobody can tell whose workload
caused it.

P6 answers that, in two cuts. The first measures: what each namespace and each
task actually cost, and how much of what they reserved they used. The second
optimises: the cheapest node fleet that satisfies the demand, and a forecast of
what the demand will be.

The split is deliberate and follows P1's precedent. Section 3 names what the
second cut defers and why.

## 2. Definition of done, first cut

- Pod, namespace and workload cost exists, taken from the bill rather than
  apportioned by us.
- Requested against used CPU and memory exists per namespace, from Container
  Insights.
- **The signals Container Insights cannot supply are named**, and the sizing rules
  depending on them are marked unavailable rather than approximated.
- ECS and Fargate recommendations snap to orderable sizes.
- Every recommendation joins P3's `recommendation` table and its lifecycle. There
  is no separate container recommendation list.

## 3. Out of scope, and what the second cut defers

**FEAT-047, node fleet optimisation**, and **FEAT-048, predictive replica
forecasting**, are the second cut.

The reason is not effort. It is that both consume the first cut's output, and
neither can be designed honestly before anybody has seen whether that output is
usable. An integer linear program fed by demand figures that turn out to be
partial produces a confident fleet recommendation that is wrong, and a forecaster
backtested against a short or gappy history has an error bound that means nothing.
P1 deferred anomalies and commitments for the same reason and came back to them in
its section 16; this document will do the same.

**A Meter agent inside the cluster.** Decided 2026-09-20. See section 6.

**Karpenter or Cluster Autoscaler configuration.** Reading their decisions is
useful; writing them is a write. Constraint 6.

## 4. Module structure

```
finops_core/
  domain/containers.py     Workload, ClusterSlice, ReservationVsUse
  ports/containers.py      ContainerTelemetry. Not a cost port: pod cost arrives
                           in the bill, see section 5.1
finops_providers/
  aws/container_insights.py  CloudWatch Container Insights. Unproved, ISS-122
  fake/containers.py         A cluster with a namespace nobody can measure
finops_ingest/collectors/
  container_cost.py        Split cost allocation columns, from the existing CUR
                           read rather than a new source
  container_usage.py       Container Insights, batched like the P3 collectors
finops_query/
  containers.py            The sizing rules in section 5.3. No provider
```

## 5. Data model

### 5.1 Pod cost is not a new source

FEAT-035 reads split cost allocation data, and split cost allocation data arrives
**in the billing export already being read**. It is extra columns on CUR 2.0 rows,
not a separate API.

So the first cut adds columns to the existing cost ingest rather than a new
collector: `eks_cluster_name`, `eks_namespace`, `eks_workload_name`,
`eks_workload_type`, `eks_pod_name`, and the split cost measures beside the
existing FOCUS ones.

This matters more than it sounds. It means pod cost is **measured**, carries the
same `as_of` and `collected_at` as every other charge, reconciles to the same
period total, and is scoped by the same guard. A product apportioning cluster cost
itself would be producing a modelled figure and would have to say so on every
screen that showed it.

**Prerequisite: split cost allocation data must be enabled on the Data Export.**
ISS-003. Until it is, the columns are absent, and the collector records that as a
named gap rather than as clusters costing nothing.

### 5.2 `container_usage`

| Column | Why |
| --- | --- |
| `tenant_id`, `sub_account_id`, `region_id` | Scope |
| `cluster_name`, `namespace`, `workload_name` | The grain |
| `cpu_requested`, `cpu_used_p99` | Requested against used, the whole point |
| `memory_requested`, `memory_used_peak` | Peak, not p99, because memory kills |
| `was_oom_killed` | **Nullable.** See 5.4 |
| `observation_days` | Below 14 there is no recommendation, as in P3 |
| `as_of`, `collected_at` | Constraint 10 |

### 5.3 The sizing rules

Adopted from the competitive review on 2026-08-23 and carried unchanged:

| Resource | Rule |
| --- | --- |
| CPU request | 99th percentile of the max rate |
| Memory request | Observed peak plus 15 percent, **or plus 25 percent where the workload has been OOMKilled** |

CPU and memory are sized differently on purpose, and the asymmetry is the
important part. A CPU request set too low throttles a workload; a memory request
set too low kills it. A percentile is right for the first and reckless for the
second.

### 5.4 What Container Insights cannot tell us

Decided 2026-09-20: Container Insights only, no agent. That decision has a cost,
and this section is it rather than a footnote.

| FEAT-036 signal | Container Insights | Consequence |
| --- | --- | --- |
| CPU and memory utilization per pod and namespace | Yes | Works |
| CPU and memory **requests** | Only with enhanced observability enabled | A cluster without it has usage and no request, so requested against used is unavailable and the screen says so per cluster |
| Node bin packing efficiency | Derivable from node and pod metrics | Works |
| Spot ratio | From the node capacity type label | Works |
| **OOMKilled events** | Not reliably | **The plus 25 percent memory rule cannot be applied.** See below |
| Orphaned persistent volumes | No, but EBS describe calls give it | Moves to P3's `EBS_UNATTACHED` class rather than being invented here |
| Unused LoadBalancer services | No, but ELB metrics give it | Moves to P3's `LOAD_BALANCER_IDLE` class |

**The OOMKilled gap is the one that changes a recommendation.** Without it, every
memory request is sized at peak plus 15 percent, including for workloads that have
been killed for running out of memory, which are exactly the ones needing the
larger margin.

So `was_oom_killed` is nullable, a null means unobserved rather than false, and a
recommendation for a workload with a null uses the 15 percent rule **and says in
its rationale that it could not check**. It does not silently apply the smaller
margin as though it had checked and found nothing.

That sentence in the rationale is what makes the agent decision reversible. When
somebody decides the gap matters more than an agent costs, the recommendations
that were affected are the ones that say so.

### 5.5 ECS and Fargate

Fargate sells a fixed matrix of vCPU and memory combinations. A recommendation of
0.7 vCPU is not orderable, and a product producing one has wasted the reader's time
and its own credibility.

Every ECS recommendation snaps **up** to the nearest valid combination, and its
estimated saving is computed from the snapped size rather than the ideal one.
Snapping down would produce a larger saving and a throttled task.

## 6. Why there is no agent

The alternative was a DaemonSet shipped by us, which would supply requests
reliably, OOMKilled events, and richer per pod detail than Container Insights
gives.

Decided against on 2026-09-20, and the reasons are worth keeping:

1. **It is a different product.** An artefact running inside customer clusters has
   its own release cadence, its own CVE surface, its own upgrade story, and its own
   failure mode where the thing measuring cost becomes the thing causing an
   incident.
2. **It needs an egress path out of their network into ours**, which
   `docs/08-THREAT-MODEL.md` does not cover and would have to.
3. **It changes what Meter is.** Everything else in this product reads AWS APIs
   with an assumed role. That is one sentence in a security review. "And a
   DaemonSet in your cluster" is a different conversation.

The cost of the decision is section 5.4, stated per signal rather than in general,
so the trade can be revisited with evidence instead of memory.

## 7. Flow

```
CUR 2.0 with split cost allocation ---> existing cost_focus collector
  (ISS-003 prerequisite)                 extra columns, same rows
                                                  |
                                                  v
                                      pod, namespace, workload cost
                                              (measured)
                                                  |
Container Insights ---> container_usage ----------+
  (no agent, section 6)         |                 |
                                v                 v
                    finops_query.containers   /containers screens
                      sizing rules, 5.3             |
                                |                   |
                                v                   |
                     P3 recommendation table <------+
                     one lifecycle, not two
```

**Container recommendations are P3 recommendations.** They land in the same table,
carry the same lifecycle, take the same severity from the same money, and appear
in the same list. A separate container recommendation list would be a second
lifecycle nobody maintains, which is the mistake P3 section 5.1 already refuses.

## 8. Interface

| Route | Answers |
| --- | --- |
| `GET /containers/cost` | Cost by cluster, namespace and workload |
| `GET /containers/usage` | Requested against used, and what could not be measured |
| `GET /containers/clusters` | Clusters, their node fleets, Spot ratio and bin packing |

Container recommendations are served by P3's existing `/waste/recommendations`,
filtered by waste class.

## 9. User interface

`/containers` and its children, currently unbuilt and named for this sub project.

The screen that matters is requested against used, because it tells a platform
team what its tenants are actually costing it. Two things it must do:

**Name the clusters it cannot measure**, per section 5.4, with the reason. A
cluster without enhanced observability appears in the list with its cost and
without its utilization, not absent.

**Show request and use as two figures, never as one efficiency percentage.** A
namespace at 20 percent efficiency could be over requesting by a factor of five or
could be idle, and those need different conversations.

## 10. Infrastructure

No new stack. The org reader role gains `cloudwatch:GetMetricData` for the
`ContainerInsights` namespace and `eks:Describe*`, `eks:List*`, `ecs:Describe*`
and `ecs:List*`, all read only.

Split cost allocation data is enabled on the Data Export, which is a change to the
P1 export configuration rather than a new stack. ISS-003.

## 11. Testing

**A cluster nobody can fully measure**, in the fake estate by default, for the same
reason P4's fake has an unreadable region.

**A workload that has been OOMKilled and one whose OOM status is unknown**, so both
rules and the null path are all exercised.

**A recommendation that does not snap to a valid Fargate size**, asserted to fail,
because a test that only checks valid inputs never sees the bug.

## 12. Risks

**ISS-003 is a prerequisite nobody has satisfied.** Without split cost allocation
data there is no pod cost, and the first cut loses its best feature. The collector
reports the absence by name.

**Enhanced observability is per cluster and optional**, so requested against used
will exist for some clusters and not others in the same estate. Sections 5.4 and 9
both exist for that.

**The second cut may not be worth building.** That is a real outcome and the reason
for the split. If the first cut shows the demand figures are too partial to solve
against, FEAT-047 should be reconsidered rather than built on them.

## 13. Open questions

| ID | Question | Effect if unanswered |
| --- | --- | --- |
| ISS-003 | Is split cost allocation data enabled on the export | FEAT-035 has no data. FEAT-036 and FEAT-037 are unaffected |
| OPEN-02 | Single or multiple payers | Affects which export the split columns arrive in |

## 14. Features delivered

First cut: FEAT-035, FEAT-036, FEAT-037.

Second cut: FEAT-047 and FEAT-048, specified in a later section of this document
written when the first cut has produced data worth optimising against, exactly as
P1's section 16 was written when its deferrals came back.

FEAT-048 additionally requires all four ADR-0015 conditions, including a third
provenance value `forecast` alongside `measured` and `modelled`. That is a change
to the `Figure` component and the provenance model every screen shares, and it is a
**first cut** task rather than a second cut one, so the vocabulary exists before
anything needs it.

## 15. Exit criteria, first cut

1. Pod, namespace and workload cost exists and reconciles to the same period total
   as `/cost/summary`.
2. A cluster without split cost allocation data is named as such, not absent and
   not zero.
3. Requested against used exists per namespace where enhanced observability is on,
   and is reported as unavailable where it is not.
4. A workload with unknown OOM status gets the 15 percent rule and a rationale
   saying the check could not be made, asserted by a test reading the rationale.
5. Every ECS recommendation is an orderable Fargate size.
6. Container recommendations appear in P3's list, in P3's lifecycle, with no second
   table.
7. `forecast` exists as a third provenance value and renders distinctly, before
   anything produces one.

None of these has been met against a real estate. ISS-122 and ISS-003.
