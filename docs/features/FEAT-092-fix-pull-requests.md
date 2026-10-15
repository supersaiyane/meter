# FEAT-092: A fix asked for, opened as a pull request, and followed until the inventory sees it

| Field | Value |
| --- | --- |
| Sub project | P15 |
| Status | Specified |
| Specification | [P15 spec](../specs/2026-10-15-p15-pull-request-fixes-design.md), sections 5.5, 5.6, 6 and 7 |
| Tasks | TASK-P15-004, TASK-P15-006 and TASK-P15-008 |
| Decisions | OPEN-13, OPEN-42 |
| Issues addressed | ISS-228 |
| Refresh cadence | Every 10 minutes |

## What it does

Lets a person ask for a recommendation to be fixed, opens the fix as a pull request in the mapped repository, and follows it: open, merged and by whom, or closed without merging, until the inventory sees the change and the recommendation is done.

## Why it exists

A fix nobody sends is a fix nobody makes, ISS-228, and a merged fix is not yet a saving: the organization's pipeline has to apply it. Following the pull request to the inventory is what lets FEAT-029 measure the saving from the bill.

## How it works

Not built yet. The API records the ask in `fix_pull_request`, because only the worker reaches GitHub, ADR-0036. The `fix_pull_requests` collector, every ten minutes, authors the fix with FEAT-040 or FEAT-093, opens it, and reads every open pull request's state. Opening moves the recommendation to `IN_PROGRESS`; a close without a merge returns it to `ACCEPTED`; after a merge it stays `IN_PROGRESS` until the inventory shows the resource gone, or the volume's type changed, and then it is `DONE`. Each step is a `fix_pull_request_event` with its principal.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| GitHub's pull requests, through the app | Every 10 minutes | Ten minutes |
| Meter's inventory, for the change seen | As the inventory runs | The inventory's own freshness |

## Measured or modelled

Measured: each pull request's state, from GitHub, and the change, from the inventory. The saving in the body stays modelled until FEAT-029 measures it from the bill.

## Failure behaviour

A fix that cannot be authored is recorded with the reason and opens nothing. A host that refuses or does not answer is the fix's typed cause, retried on the next run, and never shown as opened. Asked twice, Meter opens one pull request.

## Security considerations

A person may ask only for a recommendation in an account their scope includes. Meter never approves and never applies, constraint 6.

## Interface

`POST /v1/waste/recommendations/{id}/pull-request`, `GET /v1/remediation/pull-requests`, and the fix panel on a recommendation's detail page.

## Not doing

Opening a fix nobody asked for. A pull request is opened because a person asked.
