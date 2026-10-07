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

### 1. Overview, `/`

The front page opens on the FinOps practitioner's dashboard: the estate's Effective Cost, the
forecast, the budget, the savings rate, commitment coverage, cost allocated and what Meter
itself costs. The Executive and Engineering lead dashboards are one click away above it.

**Point at the Effective Cost tile.** It is the month to date total and the change against the
same days of the month before, and it is the same figure Cost Explorer shows, because the
Overview reads Cost Explorer's own query rather than computing its own.

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
- `fake-product-b` in `eu-fake-1` is **UNREAD**, cause `NotYetAttempted`. No read has
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

## P5, the quotas, and the half of them nobody can measure

`/governance/quotas`. Read the sentence above the two tables before scrolling.

**75 of 130 seeded quotas have a usage figure. The other 55 have a
limit and nothing measuring it.** That ratio is the sub project, not a gap in the seed. There
is no single API for used against limit across AWS: Service Quotas gives every limit, the
`AWS/Usage` CloudWatch namespace covers a subset, Trusted Advisor covers more and needs
Business or Enterprise support, and the rest needs service specific calls that do not all
exist. Say that out loud, because the alternative is a reader concluding the tool is broken.

**The two lists are two lists on purpose, and this is the question to invite.** A quota nothing
measured has no headroom, and that is not zero headroom. One list would have to sort those rows
somewhere and wherever they sort is a claim: at the top they read as urgent, at the bottom as
safe, and neither is known. Most tools show one list with a blank column, which is the same
decision taken without noticing it.

**Every unmeasured row says why, and the reasons are not interchangeable.** 2 of them in
the seeded estate say Trusted Advisor could have measured them and the account has no Business
support, which is a gap with a fix. The rest say AWS publishes no usage metric, which is a gap
with none. `fake-product-a` and `fake-product-b` carry no Business support and the platform
accounts do, so the same quota is measurable in one account and not in another. That is OPEN-03
as data rather than as a paragraph.

**Then click the fullest quota.** On Meter's own page for it: the current limit, the observed
peak, the value Meter would ask for, and the working behind that value. A reader who thinks
forty percent headroom is too generous can see which number to argue with rather than
dismissing the whole suggestion.

**Meter will not submit the request, and the screen says so beside the command.** This is the
part worth slowing down for. `RequestServiceQuotaIncrease` is a write into a member account and
constraint 6 forbids one in v1, so the product renders the console link and the exact CLI
command and hands them over. The cost is one paste. What it buys is the sentence "this product
has never written into your accounts", and every security review after that is shorter.

Three things enforce that and they fail separately, which is the answer to give if somebody
asks how they would know:

- The org reader role does not grant `servicequotas:RequestServiceQuotaIncrease`.
- `tests/contract/test_no_quota_writes.py` fails if the API name appears in production source
  at all, and separately if the IAM policy grants it.
- `quota_request.submitted_by_meter` is a column with a check constraint that admits only
  false, so reversing the decision takes a migration somebody has to write and defend.

**Finally, the requests.** 5 in the seeded estate, across 4 statuses
including a refusal, and one of them is for a quota this product cannot measure. That last one
is the point of the tracking half: nobody loses a quota increase because they could not find
the button, they lose it because nobody checked whether it was ever approved, and the request
somebody makes blind is exactly the one for a quota with no figure to look at. Open it and the
page says when the status changed, not only what it is now.

## P6, the containers, and the cluster that cannot say what it asked for

Three screens in three groups, because ADR-0020 fixes the groups and containers is not one of
them: `/cost/containers` under Cost, `/waste/containers` under Waste, `/inventory/clusters`
under Inventory. Every figure in this section was computed from the fake estate by the same
functions the collector runs, on the day this section was written, rather than typed.

**3 clusters are seeded, and 2 of them publish pod requests.**
`batch-eks` is the one that does not, on purpose. It has no enhanced observability, so
Container Insights reports what its pods used and never what they asked for, and requested
against used cannot be stated for any of its 3 workloads. Open
`/waste/containers` and find it: it is listed, with its measured cost and the sentence saying
why, and its rows carry no request column at all. Say why that matters, because it is the
design: an empty request cell reads as a request of zero, and a workload using something it
asked zero of looks infinitely wasteful.

**Every one of its workloads reads "could not be observed" for out of memory, and that is
the honest answer.** Across the seeded estate 1 workload has been killed for
running out of memory (`payments/payments-worker` in `platform-eks`),
9 were observed and were not, and 3 could not be
observed. Unobserved is not a synonym for not killed. Against a real account the adapter reports
unobserved for every EC2 workload, ISS-223, and the sizing rationale then says in words that the
check could not be made.

**Request and use are two columns and never one percentage.** A namespace at twenty percent
could be over requesting fivefold or could be idle. Point at `ledger` in `platform-eks`, which
requests five times what it uses, and then at `channels` beside it, which is sized correctly
and is not flagged. A detector that flagged everything would have flagged both.

**5 container recommendations are seeded into P3's list, not a second one.**
3 for EC2 backed workloads, sized against their measured split cost, and
2 for Fargate tasks, sized against the orderable task matrix and always rounded
up, never to the nearer size below. Open `/waste` and filter to the container class to show them
among the rest, ranked by money like every other finding. The Fargate saving is modelled from
Fargate's published rate and stated per task, and its rationale says both.

**`/cost/containers` reconciles in plain sight.** Each cluster states its workloads' share and
the capacity no pod requested, and the two make its total. That remainder is real money: the
cluster paid for it and nothing asked for it.

**`/inventory/clusters` measures bin packing for 1 of the 2 clusters
with nodes.** `batch-eks` cannot be packed because packing is requests over allocatable
and the requests are the missing thing. `product-ecs` is Fargate and has no nodes at all, so it
is listed with a different sentence and not counted, because a cluster with no fleet is not a
gap in the measurement.

**What is not real here, and should be said if asked.** The container adapter has never run
against AWS, ISS-002. It reads EKS and never ECS, so Fargate sizing produces nothing against a
real account until it does, ISS-224. And the bill's container grain needs split cost allocation
switched on in the Data Export, ISS-003; without it the cost screen says so rather than showing
clusters that cost nothing.

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
