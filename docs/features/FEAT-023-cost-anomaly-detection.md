# FEAT-023: Cost anomaly detection

| Field | Value |
| --- | --- |
| Sub project | P1 |
| Status | Specified |
| Specification | [P1 spec](../specs/2026-09-18-p1-cost-intelligence-design.md), section 16 |
| Tasks | TASK-P1-014, TASK-P1-015 |
| Refresh cadence | 6 hours |

## What it does

Judges the most recent day of each account and service pair against the days
before it, and writes a row for every day that stood out. Each row carries the
money, the baseline, the difference and the sentence that explains the verdict.

## Why it exists

A monthly total tells nobody which day went wrong. Detection has to be
deterministic and reproducible, so the arithmetic is ours and has no clock, no
database and no provider in it. Narration is a separate feature, see FEAT-039 and
ADR-0007: this one finds what changed and never claims to know why.

## How it works

`finops_query/anomaly.py` takes a number and a list of numbers and returns a
verdict. Three decisions carry it, and each is there because the obvious
alternative fails quietly.

A **median, not a mean**, because one spike inside the baseline window drags a
mean up far enough to hide the next spike, which blinds the detector for exactly
as long as the window is wide. A **dollar floor as well as a ratio**, because a
service costing two cents that triples is not news and ranking by ratio fills the
screen with rounding. And a **refusal rather than a cautious guess** under
fourteen days of history, because a new account looks exactly like an anomaly on
its first day.

`finops_ingest/collectors/cost_anomaly.py` reads `cost_focus_daily`, asks for a
verdict and writes the ones worth a row. It judges one day, the most recent with
data, because re judging the whole history every run would rewrite verdicts
somebody may already have acted on, and an anomaly that disappears because the
baseline caught up was still real at the time. It reads twice the window it needs
and takes the last days that **have data**, so a quiet Sunday does not starve it
on Monday.

The day under test is never part of its own baseline. Including it drags the
baseline toward the value being tested, which makes the detector least sensitive
exactly when the move is largest.

Severity comes from the money through `finops_query/severity.py`, per ADR-0016,
which is the same function the query findings use, so two screens do not mean
different things by the word high.

## What is already known

Detection finds what changed. It never explains why, which is a different problem
with different failure modes.

A perfectly flat baseline has no answer to "how many deviations out", because
every departure from it is infinitely many. `deviations` is null in that case and
the dollar floor is the whole test, and the verdict says so rather than reporting
a confidence it does not have.

## Failure behaviour

A pair with too little history gets no row, not a row saying no. That makes an
empty table ambiguous, and the ambiguity is resolved on the screen rather than in
the data: the payload carries how many days have been collected and how many are
needed, and the screen says which of the two situations the reader is in. An
estate that is behaving is told so. An estate nobody can judge yet is told that
nothing has been looked at, because a reader who takes silence for safety will act
on it.

The collector refuses to run without settings rather than defaulting its
sensitivity and its severity boundaries. Those are configuration, and inventing
them would put a severity nobody chose onto a screen.

## Security considerations

`cost_anomaly` is scoped by account through `ByAccount("sub_account_id")` in
`finops_api/guards.py`, and the repository guard applies whether or not a route
remembers the request dependency, per constraint 3.

## Interface

`GET /cost/anomalies` and `/cost/anomalies`. Every row shows severity, the day,
the account and service, the money above usual, that day's total, the usual
total, and the whole verdict sentence. The sentence is never shortened: a verdict
a reader cannot argue with is one they have to take on trust, and nobody takes a
cost alert on trust twice.

A chart was added above the table on 2026-09-27, and this is the screen in the product where a
picture explains the most, because the finding is a comparison between two numbers that the table
puts in two adjacent columns for the reader to subtract. The bar is what the day cost, the tick is
what that day usually costs, and how far past the tick the bar runs is the anomaly.

Scaled to the largest observed day and never to a total, with no share printed. The days belong to
different accounts and services, so adding them up produces a figure that is not the estate's
spend and is not anything else either.

The tick is drawn on the same divisor as the bar. A bar scaled by the peak and a tick scaled by
the total would put the mark in a position that means nothing, and it would look entirely
plausible, so the arithmetic is tested at its source rather than through the rendering.

## Not doing

AWS Cost Anomaly Detection findings are not ingested. Our own detection is
deterministic and its working is on the screen; theirs is neither, and mixing the
two under one severity scale would make both unreadable. It is a separate source
when there is an account to read it from, ISS-122.
