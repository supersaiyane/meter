# FEAT-079: Ingest that runs, one composition and the dispatcher and worker processes

| Field | Value |
| --- | --- |
| Sub project | P12 |
| Status | Planned |
| Specification | [P12 spec](../specs/2026-10-12-p12-deployment-readiness-design.md), sections 5.1 to 5.3 and 5.6 |
| Tasks | TASK-P12-001 to TASK-P12-005 and TASK-P12-008 |

## What it does

Assembles every scheduled collector into one registry, built per unit of work from fake adapters
or AWS adapters as `METER_PROVIDERS` says, and runs it: a dispatcher that publishes each tenant's
due units to the queue and exits, and a worker that consumes the queue and runs them. The local
stack runs end to end on the fakes, and `make first-contact` proves each AWS adapter's first real
call once an account is connected.

## Why it exists

Nothing in production assembles the collectors, ISS-182, and the dispatcher and worker images
start a module with no entry point and exit, so a deployed Meter would collect nothing however
complete its collectors are.

## What is already known

33 collectors are scheduled (measured on 2026-10-12). The worker already claims, runs and records a
unit, and resolves each account's session through the credential broker; what is missing is the
composition that builds the collectors and the processes that call the worker. Whether the
processes run on fakes before an account was OPEN-28, answered 2026-10-12: fakes by a setting.

## Status of this document

Planned. Specified in the [P12 spec](../specs/2026-10-12-p12-deployment-readiness-design.md) and
planned in the [P12 plan](../plans/P12-implementation-plan.md) on 2026-10-12, approved the same day.
The sections a built feature carries are written as its tasks build it.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P12.
