# FEAT-037: ECS and Fargate utilization

| Field | Value |
| --- | --- |
| Sub project | P6 |
| Status | In build |
| Specification | [P6 spec](../specs/2026-09-20-p6-containers-design.md), section 5.5 |
| Tasks | TASK-P6-008 |
| Refresh cadence | 24 hours |

## What it does

Task level reservation versus utilization, with recommendations snapped to valid Fargate vCPU and memory combinations.

## Why it exists

Fargate sizing is discrete. A recommendation that names an impossible size will be correctly ignored.

## What is already known

Container Insights supplies the metrics.

## How it works

**As built, 2026-10-04, TASK-P6-008, and why the status is In build.** The task
size matrix is a table in `finops_query/containers.py`, every recommendation is one of its
combinations, snapping is always up, and the saving is computed from the snapped size at
Fargate's published rate, per task. All of that is built and tested against the fake
estate. It produces nothing against a real account yet, because the AWS adapter reads EKS
through Container Insights and has no ECS path at all, ISS-224. That is a missing reader
rather than an unverified one, which is why this feature is In build while FEAT-035 and
FEAT-036 are Delivered with the usual ISS-002 caveat.

Container Insights supplies task level reservation against utilization. The sizing
uses the same two rules as FEAT-036, and then does one thing more.

**Every recommendation snaps up to a valid Fargate combination.** Fargate sells a
fixed matrix of vCPU and memory pairings, and a recommendation of 0.7 vCPU is not
orderable. The estimated saving is computed from the snapped size rather than the
ideal one.

## Failure behaviour

Snapping is always **up**. Snapping down would produce a larger saving and a
throttled task, and the larger saving is exactly what makes it tempting.

A task with fewer than 14 days of observation produces no recommendation, sharing
the floor with P3 and the anomaly detector rather than redefining it.

## Security considerations

Read only. `ecs:Describe*` and `ecs:List*` on the existing org reader role.

## Interface

Recommendations appear in P3's `/waste/recommendations`, filtered by waste class.
There is no separate container recommendation list, because a second lifecycle is
one nobody maintains.

## Not doing

**Applying the change.** Constraint 6. The recommendation carries the task
definition revision it would produce, and a human applies it.
