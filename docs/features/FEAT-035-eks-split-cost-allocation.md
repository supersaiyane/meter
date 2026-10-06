# FEAT-035: EKS pod level cost

| Field | Value |
| --- | --- |
| Sub project | P6 |
| Status | Delivered |
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

**As built, 2026-10-04, TASK-P6-002 and TASK-P6-003.** Nine nullable columns on
`cost_focus_daily`, migration 0021, read by `finops_providers/aws/cur.py` only where the
catalog says the export has them, so an export without split cost allocation is read with
the same SQL as before. A split line carries no money of its own: `billed_cost` and
`effective_cost` are zero and the figure is in `split_cost`, because the charge is already
on the node's line and adding it again would double count. An export without the columns
records a `Misconfigured` gap under its own scope key, ISS-003, so the worker's clear on
success cannot delete it. Never run against AWS, ISS-002.

Split cost allocation data arrives **in the billing export already being read**. It
is extra columns on CUR 2.0 rows, not a separate API, so this feature widens the
existing cost ingest rather than adding a collector.

That is why pod cost is **measured**. It carries the same two timestamps as every
other charge, reconciles to the same period total, and is scoped by the same guard.
A product apportioning cluster cost itself would be producing a modelled figure and
would have to say so on every screen.

Since TASK-P8-013, 2026-10-06, each cluster's workload table is a `DataTable`, largest first and sortable, with the workloads' measured cost totalled under it, the figure the reconciliation above states.

## Failure behaviour

Split cost allocation data must be enabled on the Data Export, ISS-003. Until it
is, the columns are absent and a cluster is reported as having no breakdown, by
name, with its total still shown. It is never reported as costing nothing.

## Security considerations

None beyond the existing cost guard. These are the same rows, scoped the same way.

## Interface

`GET /cost/containers` and the `/cost/containers` screen, under Cost per ADR-0020,
grouped by cluster, namespace and workload. Each cluster states its workloads' share and
the capacity no pod requested, and the two make its total in plain sight. Corrected on
2026-10-04: this section named `/containers/cost`, which broke ADR-0020's seven fixed
groups and was removed from the spec in the 2026-09-28 planning pass.

## Not doing

**Apportioning cost for clusters without split data.** The data is either there or
it is not, and a division we invented would be a modelled number wearing a measured
number's clothes.
