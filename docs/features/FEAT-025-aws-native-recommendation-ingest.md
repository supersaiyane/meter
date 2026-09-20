# FEAT-025: AWS native recommendation ingest

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Specified |
| Specification | [P3 spec](../specs/2026-09-20-p3-utilization-and-rightsizing-design.md), section 4 |
| Tasks | TASK-P3-003 to TASK-P3-005 |
| Refresh cadence | 24 hours |

## What it does

Ingests Cost Optimization Hub, Compute Optimizer and Trusted Advisor, which already consolidate rightsizing, idle, Graviton and commitment recommendations organization wide.

## Why it exists

ADR-0006. These are free, organization wide, and save months. Meter's value is attribution, evidence, ownership and workflow, not re deriving AWS sizing.

## What is already known

Compute Optimizer needs an organization level opt in, and Trusted Advisor limit checks need Business or Enterprise support. Both are stated prerequisites, see ISS-004 and OPEN-03.

## How it works

Three AWS services, one table. Cost Optimization Hub, Compute Optimizer and Trusted
Advisor all produce recommendations, and they land in the same `recommendation`
table as our own, keyed on the provider's own identifier so a re read updates
rather than duplicates.

One table and not three, because a lifecycle that works for a Compute Optimizer
recommendation and not for an unattached volume is two lifecycles, and the second
is the one nobody maintains.

## Failure behaviour

**`NotOptedIn` is an expected state, not a fault.** Compute Optimizer needs an
organization level opt in, ISS-004. An estate without it reports zero AWS native
recommendations, and that must render as "not opted in, here is how" rather than as
"no waste found".

Trusted Advisor limit checks need Business or Enterprise support, OPEN-03. Their
absence reduces coverage and is named, rather than producing an error.

A recommendation AWS has withdrawn is not deleted. It moves to `DISMISSED` with a
reason, because a row that vanishes takes its lifecycle history with it. A
recommendation a human has already accepted is not reopened by a re read: the
provider owns the finding, the lifecycle is ours.

## Security considerations

Read only. `compute-optimizer:Get*`, `cost-optimization-hub:List*` and
`support:Describe*` on the existing org reader role.

## Interface

Served by `GET /waste/recommendations` alongside our own, distinguished by a
`source` column rather than by a separate screen.

## Not doing

**Savings plan and reservation purchase recommendations.** AWS produces them, and
FEAT-024 already shows what is committed and covered. Presenting a purchase
recommendation beside our own figures would imply we had checked it against them,
and we have not.
