# Runbook: demonstrating Meter

For the person driving. Read the first section before the first demo, because it is
the one that stops a promise being made that somebody then has to keep.

## What is real and what is not

**No part of this demo talks to AWS.** ISS-122. Nothing in the product has ever made a
call to an AWS account, and the figures on every screen come from
`finops_providers/fake/`, seeded into a local PostgreSQL by `make seed`.

Say that out loud, early. A demo that implies a live connection creates an expectation
about integration effort that is not true, and the correction lands later, with an
audience.

What **is** real, and worth saying so:

- The collectors are the production collectors. `make seed` runs `CostFocusCollector`,
  `CostAnomalyCollector`, `CommitmentCollector` and the rest through the real run
  ledger, against the real schema, with the real scope guards. Only the provider
  adapter is swapped.
- The anomaly on the screen was **found**, not written. The fake estate contains one
  day where one account and service cost six times its usual, and the detector read the
  estate and judged it, like any other day. Nothing writes to `cost_anomaly` directly,
  and a test asserts that the same estate without its spike produces nothing.
- The AWS adapters exist and are held to the same contract as the fakes. They have
  never run. That is the honest summary of where integration stands.

## Before the demo

```bash
make up
make migrate
make seed
make token
```

`make seed` prints the tenant id it wrote to. `make token` prints a
`localStorage.setItem(...)` line: paste it into the browser console at
<http://localhost:5173> and reload. There is no login screen, which is worth knowing
before an audience is watching rather than during.

**Use the default subject.** `make token` signs in as `auditor@example.local`, who sees
every account. The other user in `local-auth.yaml` is scoped to two account ids the
seed never creates, so every screen shows an empty estate that looks like a bug. The
commitments screen in particular reads nothing at all for a narrowed session, because
a commitment belongs to the payer and cannot be apportioned, which is a feature and
does not look like one on stage.

If a screen is empty or a figure is missing, the first thing to check is that the token
was pasted and the page reloaded.

## The walk

Seven screens, in this order. `finops-web/e2e/demo.spec.ts` walks the same path and
asserts a figure on each, so a broken screen fails the build rather than the demo.

### 1. Home, `/`

The front page carries the estate's spend, what is open, and what Meter itself costs.

**Point at the spend tile.** It is the total for the period and the change against the
month before, and it is the same figure the spend screen shows, because Home reads that
screen's own hook rather than computing its own.

Note the failure banner at the top. One account in the estate refuses Meter's role, and
the product says so on every screen rather than quietly reporting a smaller estate.
That is constraint 5: a failure is never rendered as the number zero.

### 2. Spend and trend, `/cost`

**Point at the open period label.** The current month is still accruing and the screen
says so, rather than presenting a part month as a total.

Two money columns, amortized and billed, both named. They differ by the commitment
discount, and a single column headed "cost" is the thing finance argues about.

### 3. Allocation, `/cost/allocation`

**Point at the unallocated row.** Around a fifth of this estate is attributed to
nobody, and it is a row with a name rather than a gap. An allocation view that drops
what it cannot attribute reports a smaller estate than exists, and the difference is
the first thing finance finds.

### 4. Anomalies, `/cost/anomalies`

**Point at the "why" column.** The verdict is shown whole: the money, the baseline and
the number of deviations. A reader who cannot argue with a cost alert has to take it on
trust, and nobody does that twice.

Mention what the empty state would say. An estate with a fortnight of history and
nothing wrong is told it is behaving. An estate with four days is told nothing has been
judged yet. Those are opposite facts and the screen never renders them alike.

### 5. Commitments, `/cost/commitments`

**The best thirty seconds in the demo.** Two tables, and the point is that reading
either alone gives the wrong answer.

The compute plan is a hundred percent utilized: read that alone and the purchase looks
correct and finished. Its service is around forty percent covered: read that alone and
it says buy more. Both are true. A product reporting one number could not say so, which
is why the two are stored apart, read apart, and never placed in adjacent columns.

Then the reservation: healthy looking coverage, sixty two percent utilization, and
three hundred dollars already spent on nothing. That is the row somebody acts on.

### 6. Export, `/cost/export`

**Point at the figure above the button**, then download and sum the amortized column in
a spreadsheet. They match, because the file is generated from the same repository the
screens read.

That check takes ten seconds and is worth more than any assurance about the export
being correct.

### 7. Governance and inventory

`/governance/queries` for the P2 arc: dashboards ranked by what they cost, each with
its owner where anybody tagged one. `/inventory/organization` for the account tree,
including the one Meter cannot read.

## Questions that will be asked

**"Is this our data?"** No. See the first section.

**"How long to connect a real account?"** The adapters are written and contract tested,
and have never run. Honest answer: unknown until one runs, and the first things to
check are the CUR column mapping and the reservation figures, both of which are marked
in the code as the parts only a real account can settle.

**"Why does the commitments screen say the figures are payer wide?"** Because a
commitment is bought by the payer and consumed by whichever accounts happened to run
the usage, and no provider reports which. Rather than invent an apportionment, the
product says it cannot narrow the figure, and a scoped reader sees nothing there at
all.

**"Why is one account failing?"** Because the fake estate contains a failing account on
purpose. An estate where everything works cannot demonstrate what the product does when
something does not.

## Afterwards

```bash
make unseed
```

Removes every row the seed wrote. The teardown is tested, because later is when nobody
remembers which tables were touched.
