# FEAT-035: EKS pod level cost

| Field | Value |
| --- | --- |
| Sub project | P6 |
| Status | Specified |
| Specification | [P6 spec](../specs/2026-09-20-p6-containers-design.md), section 5.1 |
| Tasks | TASK-P6-002, TASK-P6-003 |
| Refresh cadence | Follows FEAT-020 |

## What it does

Pod, namespace and workload level cost, taken directly from split cost allocation data in CUR 2.0.

## Why it exists

This is free, needs no agent, and is widely unknown. It should be enabled before anything else in P6 is built.

## What is already known

Requires split cost allocation data enabled on the Data Export, which is a prerequisite tracked as ISS-003.

## How it works

Split cost allocation data arrives **in the billing export already being read**. It
is extra columns on CUR 2.0 rows, not a separate API, so this feature widens the
existing cost ingest rather than adding a collector.

That is why pod cost is **measured**. It carries the same two timestamps as every
other charge, reconciles to the same period total, and is scoped by the same guard.
A product apportioning cluster cost itself would be producing a modelled figure and
would have to say so on every screen.

## Failure behaviour

Split cost allocation data must be enabled on the Data Export, ISS-003. Until it
is, the columns are absent and a cluster is reported as having no breakdown, by
name, with its total still shown. It is never reported as costing nothing.

## Security considerations

None beyond the existing cost guard. These are the same rows, scoped the same way.

## Interface

`GET /containers/cost` and `/containers/cost`, grouped by cluster, namespace and
workload, with the namespace figures reconciling visibly to the cluster total.

## Not doing

**Apportioning cost for clusters without split data.** The data is either there or
it is not, and a division we invented would be a modelled number wearing a measured
number's clothes.
