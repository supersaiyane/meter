# FEAT-024: Savings Plan and Reserved Instance coverage

| Field | Value |
| --- | --- |
| Sub project | P1 |
| Status | Delivered |
| Specification | [P1 spec](../specs/2026-09-18-p1-cost-intelligence-design.md), section 16 |
| Tasks | TASK-P1-016, TASK-P1-017 |
| Refresh cadence | 24 hours |

## What it does

Reports, for one month at a time, how much of every commitment was consumed and
how much of the estate that could have been on a commitment actually was. Both
figures are money as well as percentages, and the unused money is the headline.

## Why it exists

Commitment waste is usually the largest single addressable line item, and it is
invisible in unblended cost.

## How it works

**Utilization and coverage are two facts at two grains, and neither is derived
from the other.** This is the decision the whole feature rests on. Utilization is
a fact about one commitment: this plan obliged us to pay so much and consumed so
much of it. Coverage is a fact about a slice of the estate: of the EC2 spend that
could have been on a commitment, this much was.

They are kept apart because they cannot honestly be joined. A dollar of covered
spend cannot be attributed to one of several overlapping plans, which is why no
provider reports coverage per commitment, and why `commitment_coverage` has no
`commitment_id` column. A schema that had one would carry a number nobody
measured, and summing it across commitments would count the same eligible dollar
once per plan.

They are also kept apart because they point at opposite actions. A plan at full
utilization covering a tenth of the estate says buy more. A plan at half
utilization covering everything says the last purchase was too large. A single
number could not say either.

The port is `finops_core/ports/commitment.py` with two methods, mirroring the two
grains and the two AWS APIs. The collector is
`finops_ingest/collectors/commitment.py`, which reads a whole month, because a
commitment's obligation is stated per month and a window straddling two of them
reports a figure matching neither invoice.

**Ranked by money, not by percentage**, per ADR-0016. A ranking by percentage puts
a ten dollar reservation at forty percent above a ten thousand dollar plan at
ninety five, and only one of those is worth a morning.

Since TASK-P8-013, 2026-10-06, the owner having chosen to collect daily, each run also reads
the last 35 days at Cost Explorer's daily grain: the same four reads, each asked once for the
whole span, so a month of days costs four requests and each run rewrites the days a late bill
changed. The days are kept per kind of commitment, never per plan, because the daily grain
reports Savings Plans use only as one total across every plan; one request per plan per day
would cost far more. They land in `commitment_day`, one row per kind per day, and the screen
draws three charts from the last thirty: use each day, used under unused money and stacked
to what was committed; coverage each day, covered under on demand and stacked to what was
eligible; and a heatmap of each kind's utilization and coverage per day, in percent. The two
percentages are never stacked or added, which is why they are rows of a heatmap rather than
layers of a chart. The collector's cost per run rose from 0.02 to 0.08 dollars, eight requests
at a cent each, written in `collector_schedule`.

## What is already known

Reads the AWS utilization and coverage APIs directly rather than deriving them,
because AWS owns the definition. There is one large exception, and it is stated on
the screen and in the adapter rather than buried.

**Savings Plans report money. Reservations report hours.**
`SavingsPlansUtilization` gives `TotalCommitment` and `UsedCommitment` in the
billing currency, so those figures are measured. `ReservationAggregates` gives
`PurchasedHours`, `TotalActualHours` and `TotalAmortizedFee` and no figure for the
money the used hours represent, so the reservation money is **modelled**: the
amortized fee scaled by the fraction of purchased hours used. That assumes every
purchased hour cost the same, which holds for one reservation and not for a group.
Reservation coverage is weaker still and is the first thing to check against a real
account.

Nothing in `finops_providers/aws/commitment.py` has ever made a call. ISS-122.

## Failure behaviour

A payer holding no commitments raises `NoData`, which the collector absorbs and
writes nothing for. That is a fact about the estate rather than a broken
collection, and marking the run failed would stop the screen saying so. Every
other cause propagates: an access failure rendered as an estate with no
commitments would be the zero constraint 5 forbids.

`utilization` is null where nothing was committed in the window, which is a
commitment that has not started. Zero would say the whole commitment was wasted.
`coverage` is null where nothing was eligible, which is different from zero: zero
says the estate is uncovered and somebody should buy, and null says there was
nothing there to buy for. The screen renders all four states distinctly and has a
test for each.

An expired commitment is reported as expired, never dropped. The money was spent,
and the coverage gap the expiry leaves is the finding.

The daily read is its own read. When it fails, its three charts say so and the window's
tables below still stand; a day with nothing committed has no utilization rather than a
utilization of zero, drawn as an outline in the heatmap.

## Security considerations

Both tables are `PayerWide` in `finops_api/guards.py`, a guard shape added for this
feature. It is distinct from `None`, and the distinction is the point: `None` means
the tenant filter is the whole of a table's scoping, which is right for a run
ledger and wrong for money. A commitment is bought by the payer and consumed by
whichever accounts ran the usage, and no API reports which, so a viewer restricted
to two accounts reading the payer's commitment position would learn the scale of
the organization. There is no honest way to narrow such a row, so a narrowed scope
reads nothing and the route answers 404. The screen says the figures are payer
wide.

## Interface

`GET /cost/commitments` and `/cost/commitments`. Two tables under two headings,
each heading naming what its percentage is a percentage of, and deliberately never
two percentages in adjacent columns of one table where the eye would compare them.
The unused money is shown above both.

Each percentage carries a bar under it, added 2026-09-27. A bar against a hundred and never a
share of a total, because coverage answers a question about one row: two services at eighty
percent coverage are both at eighty percent and neither is half of anything. That is why this uses
`PercentCell` and not the ranked bar the allocation screen draws.

The absence stayed an absence. A commitment that has not started and a service with nothing
eligible both render those words and draw no bar, because an empty track reads as a measurement
that came back zero, and for a commitment nought percent used says the money was wasted. The
change made that stronger rather than weaker: the helper used to format the percentage and return
the absent sentence as a string, so a sentence and a measurement were indistinguishable to
everything downstream. The null now travels and the component decides what an absence looks like.

`GET /api/v1/cost/commitments/daily`, since 2026-10-06: the last thirty days, oldest first,
one row per kind per day with `committed`, `used`, `utilization`, `eligible_spend`,
`covered_spend`, `coverage`, `as_of` and `collected_at`. A fraction is null with nothing to
divide by. Payer wide like the window, so a narrowed reader gets no days and an envelope
saying the payer was not visible.

## Not doing

**Purchase recommendations are not in this task.** AWS's recommendation API returns
a suggested commitment at a chosen term and payment option, and presenting one next
to our own figures would imply we had checked it against them. We have not, and
cannot without an account. ISS-122.

The commitment inventory API is not read either, so a reservation's real term is
unknown and the reported term is the window. A screen showing a term it had
inferred would be inventing a date somebody might plan a renewal around.

## Status of this document

Delivered on 2026-09-20 by TASK-P1-016 and TASK-P1-017. The registry and this document said Specified
until 2026-10-07, when the market research found the drift, CHG-0124.
