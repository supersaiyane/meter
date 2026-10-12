# FEAT-080: Deployed settings from SSM Parameter Store, and a pipeline that applies its own plan

| Field | Value |
| --- | --- |
| Sub project | P12 |
| Status | Planned |
| Specification | [P12 spec](../specs/2026-10-12-p12-deployment-readiness-design.md), sections 5.4 and 5.5 |
| Tasks | TASK-P12-006 and TASK-P12-007 |

## What it does

Puts every setting a deployed task needs in SSM Parameter Store, one parameter per setting under
`/meter/<env>/`, injected into each task definition at start, with the secret ones created by
Terraform with a placeholder and set by the owner. And makes each deploy job apply the plan made
for its own environment.

## Why it exists

The hub's task definitions pass 6 of the settings the API requires, so a deployed API refuses to
start, ISS-250; and the deploy jobs share one plan file across two environments, so a deploy may
apply the wrong plan or none, ISS-260.

## What is already known

`.env.example` is the one complete description of the settings and `make up` holds a local `.env`
to it; nothing holds a deployed environment to it. Where deployed settings live was OPEN-29,
answered 2026-10-12: SSM Parameter Store.

## Status of this document

Planned. Specified in the [P12 spec](../specs/2026-10-12-p12-deployment-readiness-design.md) and
planned in the [P12 plan](../plans/P12-implementation-plan.md) on 2026-10-12, approved the same day.
The sections a built feature carries are written as its tasks build it.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P12.
