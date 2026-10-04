# FEAT-036: In cluster telemetry

| Field | Value |
| --- | --- |
| Sub project | P6 |
| Status | Delivered |
| Specification | [P6 spec](../specs/2026-09-20-p6-containers-design.md), section 5.4 |
| Tasks | TASK-P6-004 to TASK-P6-007 |
| Refresh cadence | 15 minutes, pushed |

## What it does

Requested versus used CPU and memory per namespace, node bin packing efficiency, idle and unallocated node cost, Spot ratio, orphaned persistent volumes, unused LoadBalancer services.

## Why it exists

Over requesting is the single largest source of Kubernetes waste and typically runs 40 to 60 percent. It is invisible in billing data.

## What is already known

**Sizing rules, adopted from the competitive review on 2026-08-23.**

| Resource | Rule |
| --- | --- |
| CPU request | 99th percentile of the max rate |
| Memory request | Observed peak plus 15 percent, **or plus 25 percent if the workload has been OOMKilled** |
| Minimum evidence | 50 data points over a 2 week window |

The OOMKill condition is the part worth having. A workload that has been killed
for exceeding memory has already demonstrated that its observed peak was not
its real peak, so sizing it at peak plus the usual margin repeats the failure.
Widening the margin only for workloads with that history is more precise than
widening it for everything.

**Also in scope**, both cheap additions to a collector already being built:

- **Abandoned workload detection.** A deployment with no traffic and no
  meaningful CPU over a 7 day window.
- **Persistent volume growth forecasting.** Storage trend with a safety margin,
  so a volume is resized before it fills rather than after.

OpenCost or an ADOT collector pushes to the warehouse. Meter does not poll into a cluster. In cluster agents are a different deployment and security story from read only IAM roles, which is why P6 is late.

## How it works

**As built, 2026-10-04, TASK-P6-001, 004, 006, 007 and 009.** The entities in
`finops_core/domain/containers.py`, with OOM status as a three member enum because
`bool | None` fails open on a truth test. Container Insights through
`finops_providers/aws/container_insights.py`, each hourly series reduced by the rule its
figure is used under: the 99th percentile for CPU, the peak for memory, the latest value
for a request. `container_cluster` and `container_usage`, migration 0022, written by the
account scoped `container_usage` collector, which also sizes each workload with
`finops_query/containers.py` and writes the result into P3's `recommendation` table or a
refusal into `sizing_refusal`. The memory margins are P3's, imported. Where OOM status is
unobserved the rationale says the check could not be made. Never run against AWS,
ISS-002, and the adapter reports every kill status unobserved where the fake does not,
ISS-223.

CloudWatch Container Insights, read with the same cross account role as everything
else. No agent in the cluster: see P6 spec section 6 for why, and section 5.4 for
what that costs.

Sizing rules, adopted from the competitive review on 2026-08-23:

| Resource | Rule |
| --- | --- |
| CPU request | 99th percentile of the max rate |
| Memory request | Observed peak plus 15 percent, or plus 25 percent where OOMKilled |

CPU and memory are sized differently on purpose. A CPU request set too low
throttles a workload; a memory request set too low kills it. A percentile is right
for the first and reckless for the second.

## Failure behaviour

**Container Insights cannot reliably report OOMKilled events**, which is the gap
that changes a recommendation. Without it every memory request is sized at peak
plus 15 percent, including for workloads killed for running out of memory, which
are exactly the ones needing the larger margin.

So `was_oom_killed` is three valued, a null means unobserved rather than false, and
a recommendation for such a workload uses the 15 percent rule **and says in its
rationale that it could not check**. That sentence is what makes the no agent
decision reversible with evidence.

A cluster without enhanced observability has usage and no request, so requested
against used is unavailable and the screen says so per cluster.

## Security considerations

Read only, scoped by account. Nothing runs inside a customer cluster, which is the
security consideration: an artefact we shipped into their network would need a
threat model section that does not exist.

## Interface

`GET /waste/containers` and the `/waste/containers` screen, under Waste per ADR-0020,
and `GET /inventory/clusters` with its screen under Inventory for Spot ratio and bin
packing. Request and use are two columns, never one efficiency percentage: a namespace at
20 percent could be over requesting fivefold or could be idle, and those are different
conversations. Recommendations are P3's, in `/waste/recommendations` filtered to
`CONTAINER_RIGHTSIZE`. Corrected on 2026-10-04: this section named `/containers/usage`,
which broke ADR-0020.

## Not doing

**An agent in the cluster.** Decided 2026-09-20. **Orphaned persistent volumes and
unused LoadBalancer services** move to P3's existing waste classes, where the data
actually is, rather than being invented here.
