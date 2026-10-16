# FEAT-097: The estimate compared with the bill, and its accuracy published

| Field | Value |
| --- | --- |
| Sub project | P16 |
| Status | Specified |
| Specification | [P16 spec](../specs/2026-10-16-p16-costing-before-deployment-design.md), section 5.6 |
| Tasks | TASK-P16-007 |
| Decisions | None |
| Issues addressed | None yet |
| Refresh cadence | Daily |

## What it does

For each resource a merged pull request's last plan created or replaced, compares the monthly estimate with thirty billed days once the resource is applied, and publishes, by resource type, how many came within 10 percent and the median absolute percentage error.

## Why it exists

An estimate nobody checks is a guess. Proposal 6 asks for the estimate set against the bill a month later, so the estimates earn trust or show where they are wrong.

## How it works

Not built yet. The daily `estimate_comparison` collector waits until FEAT-057 first sees the address in the state the folder is mapped to, joins the resource to the bill as FEAT-029 does, skips the first billed day, and reads the next thirty. List cost scaled to 730 hours is set against the estimate, effective cost beside it. The verdict is `WITHIN`, `ABOVE`, `BELOW`, or `NOT_COMPARED` with its reason, and is restated as the bill is restated.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| The bill, `cost_focus_daily` | Daily | A day |
| What Terraform manages, FEAT-057 | As FEAT-057 reads the state | As FEAT-057 |

## Measured or modelled

Measured: list and effective cost from the bill. Modelled: the estimate they are set against.

## Failure behaviour

A folder with no mapped state, a resource not seen within sixty days of the merge, and a window with no billed row, typed `NoData`, are each `NOT_COMPARED` with the reason and no variance; a database check holds it. None is read as accurate.

## Security considerations

Bill figures stay in Meter, read by a person whose scope is the organization, ADR-0025; none reaches the pull request.

## Interface

`GET /v1/estimates/accuracy`, and the accuracy on the Estimates screen.

## Not doing

Comparing a change to an existing resource or a destroy; FEAT-029 measures a change a recommendation drove.
