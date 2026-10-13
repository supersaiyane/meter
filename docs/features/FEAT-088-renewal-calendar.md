# FEAT-088: The renewal calendar and the ladder

| Field | Value |
| --- | --- |
| Sub project | P14 |
| Status | In build |
| Specification | [P14 spec](../specs/2026-10-13-p14-commitments-design.md), sections 5.4 and 8 |
| Tasks | TASK-P14-005 and TASK-P14-009 |
| Decisions | OPEN-38 |
| Issues addressed | None yet |
| Refresh cadence | Reads what the inventory collector wrote |

## What it does

Shows what expires in each of the next twelve months and its share of the organization's hourly commitment, against the tenant's ladder limit.

## Why it exists

A commitment that ends unnoticed puts its usage back on demand the next day. A month in which much of the estate's commitment ends at once is a cliff, and a ladder keeps any one month small.

## How it works

Built: the API, TASK-P14-005; the screen follows in TASK-P14-009. `commitment_policy` holds each
tenant's target coverage, term, payment option and ladder limit, the cautious default of 80 percent,
one year, no upfront and one twelfth installed for every tenant by migration 0055 and for a new one
by `install_default_policy`. `GET /v1/commitments/policy` reads it, or the default nobody changed;
`PUT` changes it, for a person whose scope is the organization, with a reason, audited.
`finops_query/commitment_calendar.py` groups the inventory by the month each commitment ends: a
Savings Plan's hourly amount is measured, and a reservation's hourly value is modelled, its count
times its recurring charge and its upfront price over 730 hours a month. Each month's share of the
hourly commitment held now is flagged above the ladder limit. `GET /v1/commitments/calendar` returns
twelve months, every one present, a month in which nothing ends a measured nought.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| The inventory | Daily | The day before |

## Measured or modelled

Measured: the end dates and amounts are the inventory's. The ladder limit is the tenant's policy.

## Failure behaviour

A month whose expiring share passes the limit is flagged. With the inventory unread, the calendar says so rather than showing empty months.

## Security considerations

Visible at global scope only. A policy change needs a reason and a global principal, and is audited.

## Interface

`GET /v1/commitments/calendar`, `GET` and `PUT /v1/commitments/policy`, and the calendar panel.

## Not doing

Renewing anything. The calendar shows; a person decides.
