# Implementation plans

One plan per sub project, written only after that sub project's specification
is approved. A plan breaks the specification into units small enough that each
unit is a single commit with its own tests.

Naming: `P<n>-implementation-plan.md`.

| Plan | Status |
| --- | --- |
| P0 foundation | Written. 39 tasks, all delivered |
| P1 cost intelligence | Written. 21 tasks, all delivered |
| P2 query cost governance | Written. 25 tasks, 21 delivered, 2 descoped, 2 parked |
| P3 utilization and rightsizing | Written 2026-09-20. 20 tasks in nine waves. Not started |
| P4 inventory and topology | Written 2026-09-20. 11 tasks in seven waves. Not started |
| P5 quotas and limits | Written 2026-09-20. 8 tasks in five waves. Not started |
| P6 containers, EKS and ECS | Written 2026-09-20. 12 tasks in five waves, first cut only. Not started |

Later sub projects get their plan when their specification is approved, per
ADR-0001. Writing a plan for work whose foundations do not exist yet produces
guesses that look like decisions.

P3's last task depends on P4 being delivered, because FEAT-044 scores blast
radius by walking the edge tables FEAT-031 creates. The build order decided on
2026-09-20 is P3 first without that task, then P4, then that task, which keeps the
money features first without pretending the dependency is not there.
