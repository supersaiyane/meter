# FEAT-098: A plan reaching Meter from the pull request's pipeline

| Field | Value |
| --- | --- |
| Sub project | P16 |
| Status | Specified |
| Specification | [P16 spec](../specs/2026-10-16-p16-costing-before-deployment-design.md), section 5.1 |
| Tasks | TASK-P16-010 |
| Decisions | OPEN-44 |
| Issues addressed | None yet |
| Refresh cadence | Each plan |

## What it does

Brings the plan a repository's pipeline writes to Meter, with the tenant, the repository, the pull request, the commit and the folder, and records it through FEAT-095's reduction.

## Why it exists

Meter never runs Terraform, so the plan has to come from the pipeline that does. Everything else in P16 reads what this records.

## How it works

Not built, and blocked: the route waits on OPEN-44, held by the owner on 2026-10-16. The spec names three: the worker reads a workflow artifact through P15's GitHub App, recommended; the pipeline sends the plan signed by GitHub's OpenID Connect token; or the pipeline sends it with a token Meter issues per repository.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| The pull request's pipeline | Each plan | As the route allows, ten minutes for the recommended one |

## Measured or modelled

Neither: it carries the plan and computes nothing.

## Failure behaviour

A plan that cannot be read is recorded `REFUSED` with the reason. The route's own failures are typed once it is chosen.

## Security considerations

Whichever route is chosen, the plan passes through the reduction on arrival and is never stored whole. The routes differ in what they add: a permission on the GitHub App, a second kind of caller of the API, or a secret in each pipeline; spec section 5.1.

## Interface

The route OPEN-44 chooses.

## Not doing

Running Terraform, or reading state through it.
