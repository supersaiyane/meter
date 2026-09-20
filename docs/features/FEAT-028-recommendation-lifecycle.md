# FEAT-028: Recommendation lifecycle

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Specified |
| Specification | [P3 spec](../specs/2026-09-20-p3-utilization-and-rightsizing-design.md), section 5.1 |
| Tasks | TASK-P3-010 to TASK-P3-012, TASK-P3-017 |
| Refresh cadence | Live |

## What it does

Moves every recommendation through open, accepted, in progress, done and verified or regressed, with a named owner and a ticket.

## Why it exists

ISS-028. Recommendations without a workflow are ignored, every time. This is not a nice to have, it is the difference between a report and a saving.

## What is already known

**Severity is derived from the money**, per ADR-0016. `CRITICAL` at 1,000 USD a
month or more, `HIGH` at 100, `MEDIUM` at 20, `LOW` below. Never entered by
hand, so a person cannot raise a finding's priority by believing in it more
strongly.

Two rules matter more than the thresholds. **Confidence is tracked separately**,
because a 5,000 USD finding at 40 percent confidence is not the same as one at
95 percent. And **findings are grouped by cause before ranking**, because four
hundred findings at 15 USD each are `LOW` individually and 6,000 USD together,
and a systemic problem must not hide as four hundred trivial ones.

Ticketing target is OPEN-05. Target is above 80 percent reaching a terminal state within 30 days.

## How it works

Every recommendation moves through `OPEN`, `ACCEPTED`, `IN_PROGRESS`, `DONE`, and
then `VERIFIED` or `REGRESSED`, with `DISMISSED` available throughout. Every
transition writes an append only `recommendation_event` naming who and when.

**Severity is derived from the money**, per ADR-0016, through the same function the
query findings and the anomalies use. `CRITICAL` at 1,000 USD a month, `HIGH` at
100, `MEDIUM` at 20. Never entered by hand, so nobody can raise a finding's
priority by believing in it more strongly.

**Confidence is a separate figure and is never combined with severity.** Severity
answers how much money is at stake; confidence answers how sure the estimate is. A
ten thousand dollar recommendation resting on three days of data is `CRITICAL` and
`LOW`, and a reader needs both to decide whether to act this week.

## Failure behaviour

An illegal transition is refused: `VERIFIED` does not return to `OPEN`. Dismissal
requires a reason, enforced by the route rather than by the screen.

**A recommendation with no owner is reported as unowned**, because ISS-021's lesson
is that an unowned finding is never fixed. It is not hidden and not assigned to
somebody by inference.

The lifecycle column is not the lifecycle. It says where a recommendation is; only
the event log can show that somebody accepted it in March, nothing happened, and it
was quietly dismissed in June.

## Security considerations

Scoped by account. `recommendation_event` inherits the scope of the recommendation
it hangs off, through the guard's `Through` rule rather than a second copy of the
account.

## Interface

`GET /waste/recommendations`, `GET /waste/recommendations/{id}`, and two `POST`
transitions that carry no body: what to write is decided by the server from the row
it already holds.

## Not doing

**Choosing a ticketing system.** OPEN-05 is unanswered, so `TicketSink` is a port
with a fake and the Jira or ServiceNow adapter is one task waiting on the answer.
The lifecycle is complete without it.
