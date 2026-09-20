# FEAT-036: In cluster telemetry

| Field | Value |
| --- | --- |
| Sub project | P6 |
| Status | Specified |
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

`GET /containers/usage` and `/containers/usage`. Request and use are two columns,
never one efficiency percentage: a namespace at 20 percent could be over requesting
fivefold or could be idle, and those are different conversations.

## Not doing

**An agent in the cluster.** Decided 2026-09-20. **Orphaned persistent volumes and
unused LoadBalancer services** move to P3's existing waste classes, where the data
actually is, rather than being invented here.
