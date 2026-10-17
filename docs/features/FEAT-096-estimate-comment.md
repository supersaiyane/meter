# FEAT-096: The estimate as one comment on the pull request, edited in place

| Field | Value |
| --- | --- |
| Sub project | P16 |
| Status | In build |
| Specification | [P16 spec](../specs/2026-10-16-p16-costing-before-deployment-design.md), section 5.5 |
| Tasks | TASK-P16-006 |
| Decisions | OPEN-45 |
| Issues addressed | None yet |
| Refresh cadence | Every 10 minutes |

## What it does

Writes one comment per pull request and folder with the estimate: the count of resources not priced first, then the monthly change, before and after, a line per resource, every reason, the assumptions and the catalogue version. A plan for a newer commit edits the same comment.

## Why it exists

The estimate is read where the change is reviewed. The owner chose one comment, edited in place, on 2026-10-16, OPEN-45: informational, blocking nothing.

## How it works

Built, TASK-P16-006. `finops_query/estimate_comment.py` renders the comment, opening with a marker hidden in its text that names the folder. The `plan_comments` collector, every ten minutes on the GitHub App, asks each pull request's state through P15's tracker and keeps it in `plan_pull_request`, with when it was first seen merged; it writes the head's estimate as the comment, or edits the one it wrote before, found by its marker and its app author; an older commit's estimate, or one whose pull request merged or closed first, is `SUPERSEDED` and says why. Pricing is a collector apart, so a code host that is down holds back only the comment.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| The estimate, FEAT-095 | Every 10 minutes | Ten minutes |
| The pull request's head and state, from GitHub | Every 10 minutes | Ten minutes |

## Measured or modelled

Modelled: the comment quotes list prices only.

## Failure behaviour

A comment GitHub refuses is recorded with its typed cause and tried again on the next run; the estimate stands on the screen either way. A rate limit stops the run's comments and leaves each estimate as it was.

## Security considerations

The comment quotes list prices, which AWS publishes, and never a figure from the bill, so a reader of the repository learns nothing of the organization's spend. Posting needs no permission beyond P15's Pull requests write; only the worker reaches GitHub, ADR-0036.

## Interface

The pull request's comment, and its link and state on `GET /v1/estimates` and the Estimates screen, TASK-P16-008.

## Not doing

Failing a check, blocking a merge, or a comment per commit.
