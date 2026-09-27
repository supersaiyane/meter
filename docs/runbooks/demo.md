# Runbook: demonstrating Meter

For the person driving. Read the first section before the first demo, because it is
the one that stops a promise being made that somebody then has to keep.

## What is real and what is not

**No part of this demo talks to AWS.** ISS-122. Nothing in the product has ever made a
call to an AWS account, and the figures on every screen come from
`finops_fakes/`, seeded into a local PostgreSQL by `make seed`. ADR-0022 moved that
package out of the production tree, so the deployed image cannot import it.

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
<http://localhost:9735> and reload. There is no login screen, which is worth knowing
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

### 8. Waste, and the three screens that are allowed to disappoint

`/waste` first. It is ranked by money and the estimate carries a modelled label,
because it is arithmetic over metrics rather than a figure anybody has seen on a
bill. Two things to say out loud:

The money and the confidence are deliberately not adjacent columns. A reader
comparing them side by side reads confidence as a discount on the money, and it is
not one: a four hundred dollar finding on fifteen days of data is worth four
hundred dollars if it is right, and the confidence says how likely that is.

The top row has no owner, and the screen says so in words. An unowned finding is
never fixed, and a blank cell is the least noticeable way to render the single
fact most likely to kill the work.

`/waste/savings` next, and this is the screen worth slowing down for. It shows what
actually appeared in the bill sixty days after somebody marked a recommendation
done, and the figure is usually smaller than the one promised on the previous
screen. That gap is the point rather than a defect.

Stop on the inconclusive row. Its cost fell by forty percent and its usage
quantity was never published, so nobody can tell the saving apart from a workload
that shrank on its own. Most tools would leave that row out and show a page of
successes. This one lists it with the sentence explaining why, because a north star
metric that is only ever green is a vanity metric.

The totals are grouped by verdict and never added together, for the same reason the
estimate and the realization are served by different routes: one number here would
be summed with the one on `/waste` by the first person who saw both.

`/waste/score` last. A score out of eighty five, not out of a hundred, and the
screen says which. One of its four components could not be computed, so it is
excluded from the total rather than counted as nought, and it says that too. Under
the score are the components that produced it, each linking to the findings that
moved it. That decomposition is the condition this feature shipped on: it was
adopted over an objection that a composite number nobody can take apart is an
opinion with a number on it, and the objection became the requirement.

At the bottom, an account with no score at all. Nothing reached it, so it has no
number rather than a bad one.

## P4, the topology map, and the region that is unreadable on purpose

`/inventory/topology`. Open it and read the banner before touching anything.

**Two slices of the seeded estate cannot be read, and they are two different problems.**
The screen says which is which, and the difference is the whole of what this sub project
built.

- `fake-platform-a` in `fake-region-c` is **PARTIAL**, cause `NotOptedIn`. A read happened
  and fell short. Every account's `fake-region-c` slice is partial, because that region
  refuses in the fake estate.
- `fake-product-b` in `fake-region-b` is **UNREAD**, cause `NotYetAttempted`. No read has
  been attempted. `make seed` deliberately runs the inventory collector over nineteen of
  the twenty slices it enrols, so the twentieth keeps the row enrolment gave it.

Say the second one out loud. An estate where every slice was read cannot show the state
this sub project exists to distinguish: a region nobody has looked at and a region with
nothing in it are the same row count and opposite facts, and only one of them is safe to
score against. The unread slice is named in `scripts/demo/seed_demo.py` as
`UNREAD_ACCOUNT` and `UNREAD_REGION`, so it is a documented choice rather than a gap
somebody will report as a bug.

**Then pick a root and watch two more notices appear above the graph.** Choose the
platform VPC. The map is capped, so it says how many resources it omitted and out of how
many. And the walk crosses `fake-product-denied`, whose slice is PARTIAL with
`AccessDenied`, so the map says that too.

Both notices are above the drawing rather than under it, and that placement is
deliberate. A reader who sees the picture first has already concluded something by the
time they reach a footnote, and the conclusion they reach is that the estate is less
connected than it is.

**The interesting edge is the one going nowhere.** The platform VPC peers with a VPC in
the denied account, and that VPC has no box on the map because Meter has never read it.
The edge is drawn dashed to a boundary marker rather than dropped. An edge Meter cannot
see is not an absent edge, and a graph that quietly omitted it would answer "what talks to
this" with a shorter list and no warning. The relationships table below names the API that
supplied each edge, so a reader can tell a missing edge from a refused call.

**The table beside the map is not a summary of it.** A force directed layout cannot be
navigated by a screen reader, so the same nodes and edges are listed in a readable order
from the same payload. If somebody asks whether the map is accessible, the answer is that
the table is the accessible path and the map is the convenience, which is the same
arrangement the organization screen uses.

**What is not real here, beyond the usual.** Neither AWS adapter behind this screen has
ever made a call: ISS-200 for the Config aggregator and ISS-202 for the four APIs that
supply the cross account edges. And `infra/terraform/config` has never been planned or
applied, ISS-203, so the 1,440 USD a month in `infra/terraform/config/COST.md` is
modelled and not measured. If somebody asks what Config would cost, that file has the
working and says which assumption is least certain.

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

**"Why is a saving inconclusive rather than just counted?"** Because the honest
counterfactual, what a resource would have cost had nothing changed, is
unobservable. A resource that cost one hundred and then sixty did not necessarily
save forty; it may have been used less. Where the usage fell faster than the cost,
the product says so instead of taking the credit. Expect that verdict to be common,
and treat a tool that never produces it with suspicion.

**"Why is a score out of eighty five?"** Because one of its four components could
not be computed, and a component nobody could measure is excluded from the total
rather than scored as nought. Scoring it zero would report the worst possible
posture for a dimension nobody looked at.

**"Why is one account missing from the score?"** No waste collection reached it, so
it has no score. That is different from a bad score, and it is listed by name
underneath rather than quietly left out of the table.

**"Why is one account failing?"** Because the fake estate contains a failing account on
purpose. An estate where everything works cannot demonstrate what the product does when
something does not.

**"Why is one region unread rather than empty?"** Because they are different facts and
only one is safe to act on. A region with no resources and a region nobody has looked at
have the same row count, so the product stores the state rather than inferring it from
the count. `make seed` leaves one slice unread on purpose so the demo can show the
difference; the runbook section above names which.

**"Why does the map show a line to nothing?"** Because the thing at the other end is in an
account Meter has not read, and dropping the line would make the estate look less
connected than it is. That is the single rule this sub project is built on: an edge Meter
cannot see is not an absent edge.

**"Why is the map capped?"** Because a force directed drawing of twenty thousand nodes is
unreadable and makes the tab unresponsive, and because the honest answer to too much data
is to say how much was left out rather than to try. The cap is a number the reader can
change on the screen, and the route refuses a request above a ceiling.

**"Why does this screen count slices rather than accounts?"** Because a graph is read per
account and per region, so a view over eleven of twelve regions is partial in a way
counting accounts cannot express. Every route reports what it counted, and the interface
shows the noun the route sent.

## Afterwards

```bash
make unseed
```

Removes every row the seed wrote. The teardown is tested, because later is when nobody
remembers which tables were touched.
