# Implementation plans

One plan per sub project, written only after that sub project's specification
is approved. A plan breaks the specification into units small enough that each
unit is a single commit with its own tests.

Naming: `P<n>-implementation-plan.md`.

| Plan | Status |
| --- | --- |
| P0 foundation | Written. 39 tasks, all delivered |
| P1 cost intelligence | Written. 22 tasks, 21 delivered, 1 added 2026-09-26 |
| P2 query cost governance | Written. 25 tasks, 21 delivered, 2 descoped, 2 parked |
| P3 utilization and rightsizing | Written 2026-09-20. 21 tasks in nine waves, 1 added 2026-09-26. Not started |
| P4 inventory and topology | Written 2026-09-20. 13 tasks, 11 delivered, 2 added 2026-09-26 |
| P5 quotas and limits | Written 2026-09-20. 8 tasks in five waves. Not started |
| P6 containers, EKS and ECS | Written 2026-09-20. 12 tasks in five waves, first cut only. Not started |

## Tasks added after a plan was approved

Four, all on 2026-09-26, from the IBM Turbonomic competitive review. TASK-P1-022,
TASK-P3-021, TASK-P4-012 and TASK-P4-013.

They are appended to the owning sub project's plan rather than collected in a plan
of their own, because a task belongs with the specification it changes and a
separate adoption plan would be a second place to look for P3's work. The
precedent is TASK-P2-026, which was brought into scope the same way after the
restored prototype was read against what P2 delivered.

Two candidates from the same review are deliberately **not** tasks. FEAT-058, a
performance dimension, and FEAT-059, an application layer. Both are registered as
Planned with the decisions that would have to be made first written down, because
writing tasks for them now would produce the guesses this README warns about two
paragraphs below.


Later sub projects get their plan when their specification is approved, per
ADR-0001. Writing a plan for work whose foundations do not exist yet produces
guesses that look like decisions.

P3's last task depends on P4 being delivered, because FEAT-044 scores blast
radius by walking the edge tables FEAT-031 creates. The build order decided on
2026-09-20 is P3 first without that task, then P4, then that task, which keeps the
money features first without pretending the dependency is not there.
