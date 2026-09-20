# FEAT-030: Config aggregator inventory

| Field | Value |
| --- | --- |
| Sub project | P4 |
| Status | Specified |
| Specification | [P4 spec](../specs/2026-09-20-p4-inventory-and-topology-design.md), section 5.1 |
| Tasks | TASK-P4-002, TASK-P4-003, TASK-P4-006, TASK-P4-010 |
| Refresh cadence | 6 hours, plus change driven |

## What it does

Every resource, by region and availability zone, from an organization wide AWS Config aggregator.

## Why it exists

The requirement asked for a list of all resources by zone and region. Writing hundreds of describe loops is a year of work and a rate limit farm, see ISS-013.

## What is already known

Known cost risk: recording all resource types organization wide is a five figure monthly line item, ISS-012. Mitigation is periodic recording for stable types and continuous only for critical ones, stated to stakeholders up front.

## How it works

An organization wide AWS Config aggregator supplies every resource with its region
and availability zone, and most of the relationships FEAT-031 needs.

**Selective recording**, decided 2026-09-20 against ISS-012: continuous recording
for the resource types the graph is built from and the ones carrying cost, periodic
for stable types, nothing for types no feature reads. The type list lives in
Terraform so what is recorded is reviewable in a diff.

## Failure behaviour

A region that refuses produces a typed cause and does not silently shorten the
result. Every account and region gets a `graph_coverage` row on every run,
including failed ones, and a slice never attempted is `UNREAD` rather than absent.

That distinction matters because an account with genuinely no resources in a region
and an account whose region refused us look identical by row count, and only one is
safe to reason about.

## Security considerations

Read only. The aggregator is in the payer account; the recorders are a member
StackSet.

## Interface

`GET /inventory/resources` and `GET /inventory/topology/coverage`.

## Not doing

**Configuration history.** Config records it and it is a different feature: "what
did this security group look like in March" is drift detection, not topology.
Recording it would also multiply the cost this feature is already careful about.

**Recording every resource type.** ISS-012 says that is a five figure monthly line
item, and the estimate for what is recorded instead is written into the task that
applies it, before it is applied.
