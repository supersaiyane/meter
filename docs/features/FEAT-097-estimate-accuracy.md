# FEAT-097: The estimate compared with the bill, and its accuracy published

| Field | Value |
| --- | --- |
| Sub project | P16 |
| Status | Delivered |
| Specification | [P16 spec](../specs/2026-10-16-p16-costing-before-deployment-design.md), section 5.6 |
| Tasks | TASK-P16-007 to TASK-P16-009 |
| Decisions | None |
| Issues addressed | None yet |
| Refresh cadence | Daily |

## What it does

For each resource a merged pull request's last plan created, compares the monthly estimate with thirty billed days once the resource is applied, and publishes, by resource type, how many came within 10 percent and the median absolute percentage error.

## Why it exists

An estimate nobody checks is a guess. Proposal 6 asks for the estimate set against the bill a month later, so the estimates earn trust or show where they are wrong.

## How it works

The daily `estimate_comparison` collector, TASK-P16-007, reads the latest priced plan of each merged pull request and folder, and for each created line waits until FEAT-057 first sees the address in the state the folder is mapped to after the merge, keeping when. The resource joins the bill by its identifier, as FEAT-029 does. The day it was seen and the first full day after are skipped, and the next thirty are the window; until the bill reaches its last day the line is `PENDING`. `finops_query/estimate_accuracy.py` then sets the window's list cost, scaled to 730 hours, against the estimate, effective cost beside it: `WITHIN` inside 10 percent, the boundary included, `ABOVE` or `BELOW` otherwise. The verdict is read again each day for sixty days after the window, so a restated bill restates it. Accuracy by type counts only what was judged.

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

`GET /v1/estimates/accuracy`, and the accuracy on the Estimates screen at `/plan/estimates`, TASK-P16-008; each created line's verdict on `GET /v1/estimates/{plan_id}`. Not yet in the MCP facade, ISS-302.

## Not doing

Comparing a replacement, a change to an existing resource or a destroy, in v1: a replacement keeps its address and Meter holds one row per resource, so the new resource cannot be told from the old. FEAT-029 measures a change a recommendation drove.
