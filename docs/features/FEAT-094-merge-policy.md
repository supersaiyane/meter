# FEAT-094: Meter merges a reversible fix under the tenant's merge policy

| Field | Value |
| --- | --- |
| Sub project | P15 |
| Status | Specified |
| Specification | [P15 spec](../specs/2026-10-15-p15-pull-request-fixes-design.md), section 5.2 |
| Tasks | TASK-P15-001, TASK-P15-007 and TASK-P15-008 |
| Decisions | OPEN-41, ADR-0038 |
| Issues addressed | None yet |
| Refresh cadence | Every 10 minutes |

## What it does

Merges a pull request Meter opened for a fix that loses nothing if it is wrong, gp2 to gp3, when the tenant's merge policy names that class and GitHub reports the pull request mergeable with every required check passed and every required review given.

## Why it exists

Proposal 4 asks for graded autonomy: the low risk fixes merged without waiting for a person, and the saving measured afterwards. The risk is held in three places at once: a reversible set in the domain, a policy the tenant turns on, and the repository's own protections.

## How it works

Not built yet. The reversible set, `EBS_GP2_TO_GP3` alone, is in the domain, and a pure rule decides from the policy, the class, who opened the pull request and GitHub's report whether Meter may merge. `merge_policy` lists the classes a tenant allows, starts empty, and a database check refuses any class outside the reversible set. The `fix_pull_requests` collector merges through GitHub's own merge, so branch protection applies, and records the merge as a step with the policy that allowed it. The `pull_request_merge` flag turns every merge off.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| GitHub's mergeable state, checks and reviews | Every 10 minutes | Ten minutes |
| The tenant's merge policy | On change | Immediate |

## Measured or modelled

Measured: GitHub's report and the merge. The saving is measured by FEAT-029 afterwards.

## Failure behaviour

A pull request GitHub does not report mergeable waits, and says what it waits on; a merge GitHub refuses is a recorded failure, never retried past a protection. A deletion is never merged, whatever the policy says.

## Security considerations

ADR-0038. Meter merges only a pull request it opened, of a reversible class the policy names, through the repository's protections. It never approves, never merges a deletion and never applies. The policy is changed only by a person whose scope is the organization, with a reason, audited. A contract test refuses a merge call outside the one merge function.

## Interface

`GET` and `PUT /v1/remediation/merge-policy`, and the settings screen.

## Not doing

Merging a deletion, approving a pull request, or merging past a repository's protections.
