# User interface architecture

Last updated: 2026-09-06
Update trigger: any new screen, any change to a route, any change to the navigation groups
Applies to: every sub project, P0 to P7
Closes: the gap that the product had a visual system and no information architecture

## 1. What this document is

`docs/12-UI-DESIGN.md` decides how a number looks. This document decides where
that number lives, how a person reaches it, and what they see first.

The split matters because the two go stale for different reasons. The visual
system changes when the honesty guarantees change, which is rarely. The
information architecture changes every time a sub project lands, which is eight
times.

| Decided in `docs/12-UI-DESIGN.md` | Decided here |
| --- | --- |
| Typography, colour, density, motion | The home screen |
| Provenance, freshness and failure rendering | The seven navigation groups |
| The seven data states | Every route in the product |
| The component inventory | The screen inventory, P0 to P7 |
| The library choice, ADR-0019 | Cross screen patterns: scope, search, export, drill down |
| | How a screen becomes visible before its data is real |

Section 13 of that document says each sub project adds its screens against the
visual system rather than inventing one. This document is the frame those
screens are added to.

**It does not restate the visual system.** A rule that appears in both documents
is a rule that will diverge. Where this document needs one, it links.

## 2. The four decisions

| # | Decision | Consequence |
| --- | --- | --- |
| 1 | **Home is a trust strip above the money** | Coverage, freshness and Meter's own cost sit above every figure, which satisfies architectural constraint 7 and puts the design thesis on the first screen |
| 2 | **Navigation is seven fixed groups** | A sub project adds screens inside a group. It never adds a top level entry, so the navigation is the same size at P7 as at P0 |
| 3 | **Full map, detail where a specification exists** | Every screen P0 to P7 is named here. Only P0 and P2 are designed here, because only they have approved specifications |
| 4 | **Screens are built against a typed contract, not a live route** | A screen becomes visible when its shape is known, not when its data is real |

Decision 2 is expensive to reverse, because it fixes every URL in the product.
Recorded as ADR-0020.

## 3. Who arrives, and what they came for

From `docs/12-UI-DESIGN.md` section 2. The audience is four roles, and the
information architecture is wrong if any of them has to learn the sub project
decomposition to find their work.

| Role | The question they arrive with | Where they land after Home |
| --- | --- | --- |
| FinOps practitioner | Where is the money going, and what is wasteful | Cost, then Waste |
| Platform engineer | Is this data trustworthy, and which collector is failing | Platform |
| Engineering director | What does my org cost, and what changed | Home filtered to their scope, then Waste |
| Finance | What is the allocated cost, and can I export it | Cost, allocation and export |

**Nobody navigates by sub project.** P2 is a delivery unit, not a user concept.
A user looking for an expensive dashboard looks under Govern, and never
needs to know that a sub project called P2 built it.

## 4. Information architecture

### The nine groups

**Amended 2026-10-05, ADR-0030.** The seven question groups of ADR-0020 became
nine groups named for the domains of the FinOps Framework, approved by the
owner with P8 (spec section 5.2), because the owner asked for the standard
nomenclature a FinOps practitioner already uses. The screens in each group are
listed in ADR-0030 and in `finops-web/src/shell/sections.ts`, which is the one
list.

| # | Group | Answers | Framework domain |
| --- | --- | --- | --- |
| 1 | **Overview** | Can I trust this, and where is the money | Understand Usage and Cost |
| 2 | **Analyze** | Where is the money going | Understand Usage and Cost |
| 3 | **Plan** | What will it cost, and is that within budget | Quantify Business Value |
| 4 | **Optimize** | What is being spent badly, and what did we recover | Optimize Usage and Cost |
| 5 | **Govern** | What rules and limits constrain the estate | Manage the FinOps Practice |
| 6 | **Inventory** | What do we have, and how is it connected | None; ITAM and Data Ingestion are nearest |
| 7 | **Report** | What can I take away, and who receives it | Understand Usage and Cost |
| 8 | **Assist** | Ask, and receive an answer with its provenance | AI for FinOps |
| 9 | **Platform** | Is Meter itself working | Manage the FinOps Practice |

Under ADR-0020 the third group was **Waste**, blunt on purpose. The Framework's
Optimize replaces it because the owner chose the names practitioners search
for; the screens under it still say what was spent badly in so many words.

### Why the groups do not grow

A flat navigation grows by one entry per screen, so it is five entries today and
roughly thirty by P4, at which point finding a screen requires knowing which
sub project built it. Grouping by the question being asked keeps the top level
fixed while the product grows underneath it, at nine groups since 2026-10-05.

The test for a new screen is: **which group's question, and so which Framework
domain, does it answer?**
A screen that answers none of them is a screen whose purpose has not been
decided yet, and the navigation refusing to place it is the correct outcome
rather than a limitation.

### Collapsing it

The groups are fixed, and the column holding them is not. Collapsing
narrows the grid column from 232 px to 56 px, which gives the content the width
rather than covering the navigation with it: at 1440 px the findings table goes
from 1208 px to 1384 px and its explanation column wraps in two lines instead of
four. On the dense screens that is the difference between reading a sentence and
scanning a paragraph.

Three properties make it correct rather than merely present.

- **The navigation is `hidden`, not painted over**, so it leaves the
  accessibility tree and the tab order together. A keyboard user never tabs
  through links that are not on screen.
- **There is no transition.** The motion rule permits a 120 ms opacity change
  and nothing else, and a sliding panel is exactly the decoration it rules out.
- **The choice is remembered per browser**, and a browser that refuses to answer
  about stored data opens the navigation rather than rendering a shell with no
  menu in it.

### Migration from the five flat sections

`finops-web/src/shell/sections.ts` is a flat array of five strings today. Five
built screens move:

| Today | Becomes |
| --- | --- |
| `Accounts` | Inventory, `/inventory/accounts` |
| `Organization` | Inventory, `/inventory/organization` |
| `Ingest` | Platform, `/platform/ingest` |
| `Freshness` | Platform, `/platform/freshness` |
| `Platform` | Platform, `/platform/cost` |

The constant becomes a group definition rather than a name list, so the
navigation and the router keep agreeing, which is the reason that file exists.

## 5. Routes

Every route carries its group. A URL that does not name a group is a screen
whose purpose was never placed. Since 2026-10-05, ADR-0030:

```
/                                  Overview
/analyze/explorer                  Cost Explorer: two groupings, a period and the one before
/analyze/allocation                Allocation and showback, the unallocated bucket
/analyze/anomalies                 Anomalies, ingested and detected
/analyze/kubernetes-cost           Kubernetes cost by cluster, namespace and workload
/analyze/kubernetes-rightsizing    Kubernetes rightsizing, requested against used
/analyze/clusters                  Clusters and their fleets
/plan/budgets                      Budgets and their burn
/plan/forecasts                    Spend forecast, arrives with P8
/plan/score                        FinOps Score, decomposed to the findings that moved it
/plan/unit-economics               Unit economics, no sub project planned
/optimize                          Every recommendation, ranked by dollar
/optimize/commitments              Savings Plan and Reserved Instance coverage
/optimize/savings                  Realized savings, the north star metric
/govern/query-cost                 Query findings, ranked by monthly cost
/govern/query-cost/findings/:id    Finding detail, the full working
/govern/query-cost/surfaces        Query surfaces, including unreachable ones
/govern/query-cost/adhoc           Ad hoc queries
/govern/quotas                     Quota utilization, with coverage gaps stated
/govern/quotas/:service/:quota     One quota, and the increase Meter would ask for
/govern/policies                   Active controls, expiry and revoke
/inventory/accounts                Accounts in scope, with role health
/inventory/accounts/organization   The organization tree and graph, a tab of Accounts
/inventory/resources               Config inventory by region and zone
/inventory/resources/:nodeId       One resource
/inventory/topology                The topology map
/inventory/topology/geography      The estate on a map, a tab of Topology
/report/library                    Report library, arrives with P8
/report/scheduled                  Scheduled reports, arrives with P8
/report/exports                    Chargeback and showback export
/assist                            Ask Meter
/assist/digests                    Per team digests and executive summaries
/platform/freshness                Freshness per collector against its cadence
/platform/ingest                   Runs, typed errors, per account causes
/platform/cost                     Meter's own cost, unallocated included
/platform/flags                    Configuration and feature flags, not yet surfaced
```

Before 2026-10-05 the routes were these, kept as the record. Each one that moved
redirects to its new home with its query string, through `REDIRECTS` in
`sections.ts`, and `sections.test.ts` names every one of them.

```
/                                  Home
/cost                              Spend, month to date and trend
/cost/allocation                   Allocation, showback, the unallocated bucket
/cost/anomalies                    Anomalies, ingested and detected
/cost/commitments                  Savings Plan and Reserved Instance coverage
/cost/export                       Chargeback and showback export
/waste                             Every recommendation, ranked by dollar
/waste/:id                         Recommendation detail, evidence and blast radius
/waste/savings                     Realized savings, the north star metric
/waste/score                       FinOps Score, decomposed to the findings that moved it
/governance/queries                Query findings, ranked by monthly cost
/governance/queries/:id            Finding detail, the full working
/governance/instances              Query surfaces, including unreachable ones
/governance/enforcement            Active controls, expiry and revoke
/governance/quotas                 Quota utilization, with coverage gaps stated
/inventory/accounts                Accounts in scope, with role health
/inventory/organization            The organization tree and graph
/inventory/resources               Config inventory by region and zone
/inventory/topology                The topology map
/platform/ingest                   Runs, typed errors, per account causes
/platform/freshness                Freshness per collector against its cadence
/platform/cost                     Meter's own cost, unallocated included
/platform/flags                    Configuration and feature flags
/assistant                         Ask, and narrated anomalies
/assistant/digests                 Per team digests and executive summaries
```

### Scope and filters live in the query string

```
/optimize?scope=ou-abc123&severity=1&provenance=measured
```

Not in the path. Three reasons, and the third is the product's own thesis.

1. Scope changes far more often than the screen does.
2. A scoped URL is shareable, and a shared URL is how one person hands a finding
   to the person who owns it.
3. **A screenshot pasted into a ticket can be traced back to exactly what was on
   screen.** A figure whose filters are invisible is a figure that cannot be
   argued with, which is the failure `docs/12-UI-DESIGN.md` exists to prevent.

Built on 2026-10-05, TASK-P8-003, closing ISS-235: until then nothing read the
query string. `useFilters` in `finops-web/src/shell/filters.ts` reads and writes a
screen's filters there, each change is a history entry so back and forward walk
through them, each screen declares its keys in `sections.ts`, and the shell names
any parameter the screen does not take rather than applying it.

## 6. The home screen

### Shape

```
+--------------------------------------------------------------------------+
| showing 297 of 310 accounts   as of 04:00 today, collected 6 min ago      |
| Meter this month $412.80 measured          2 collectors degraded  [show]  |
+--------------------------------------------------------------------------+
|                                                                          |
|  Total spend, month to date                          Trend, 30 days      |
|  $184,203.11  measured                               [sparkline]         |
|  297 of 310 accounts                                                     |
|                                                                          |
+--------------------------------------------------------------------------+
|  Top movers                                                              |
|  account / service          change        cause                          |
+--------------------------------------------------------------------------+
|  Top findings by dollar                                                  |
|  sev  finding              monthly   provenance  owner   group           |
+--------------------------------------------------------------------------+
|  Realized savings, trailing 60 days      not yet published               |
+--------------------------------------------------------------------------+
```

### The trust strip

Persistent, compact, full width, above everything. It is one band, not three
cards, because three cards of equal weight is the card grid that
`docs/12-UI-DESIGN.md` section 2 rules out.

Built 2026-09-11. It spent its first release inside the sidebar column, where a
1440 px screen pushed the freshness line below the fold, so the page lost the
one statement that says what its numbers are worth. ISS-156.

Coverage states one line per thing counted, not one ratio. Home holds a panel
counted in accounts beside one counted in workspaces, and the conservative rule
across both produced "Showing 0 of 3", which was true of nothing on the page.
The noun travels on `scope_coverage.unit`, set by the route that did the
counting, because the interface was guessing it and guessed "accounts"
everywhere. ISS-157.

| Element | Source | Rule |
| --- | --- | --- |
| Coverage | `scope_coverage` on every response | Complete coverage says so. Absence of a warning is not confirmation |
| Freshness | Worst case across the collectors feeding this page | Two timestamps, never one. Architectural constraint 10 |
| Meter's own cost | FEAT-008 | **Home only.** Architectural constraint 7 says front page, and Meter's own cost is not a property of the accounts screen. It is a figure like any other and carries its provenance |
| Degraded | `degraded` on the envelope | Names which collector, never a generic warning |

Worst case, not average. A page whose freshest collector is six minutes old and
whose stalest is nine hours old is a nine hour old page.

### The money

Five slots, in this order. The order is the priority order, and it does not
change per role. Scope changes per role; the questions do not.

| Slot | Content | Fills when |
| --- | --- | --- |
| 1 | Total spend, month to date, with its coverage denominator | P1 |
| 2 | Trend, 30 day sparkline, provenance aware | P1 |
| 3 | Top movers, the largest changes and their cause where known | P1, narrated by P7 |
| 4 | **Top findings by dollar**, every source pooled and ranked | P2 first, then P3 and P6 |
| 5 | Realized savings, trailing 60 days, the north star metric | P3 |

### Two rules that make the home screen safe

**1. Home owns no data of its own.** Every figure is a roll up of a screen that
exists elsewhere, computed by the same route that screen uses, and every figure
links to it. A home screen with its own query is a home screen that will one day
disagree with the screen it summarises, and a user who catches that disagreement
stops trusting both.

**2. An empty slot names the sub project that will fill it.** Before P1 lands
there is no cost data, and slot 1 must not render as zero, blank, or a broken
panel. It renders the `Empty, never collected` state from
`docs/12-UI-DESIGN.md` section 8, naming what is missing:

```
  Total spend, month to date
  not yet collected
  arrives with P1 Cost Intelligence
```

That second rule is why the home screen doubles as the build progress view.
**Each sub project that lands turns one slot from a named absence into a
number.** The progress is legible on the product's own front page rather than in
a separate dashboard that would need its own maintenance, and it is legible to a
user, not only to the team.

### Slot 4 is the one that matters

Top findings by dollar is the only screen in the product that pools findings
across sub projects: an expensive Grafana dashboard from P2, an oversized
instance from P3 and an over requested pod from P6 compete in one ranked list,
ordered by monthly cost, with severity by dollar per ADR-0016.

That pooling is the reason severity is a dollar amount rather than a category.
Three sources with three severity vocabularies cannot be ranked against each
other. Three sources reporting dollars can.

Each row links into its own group. The list is a router, and it holds no logic
of its own beyond the sort.

## 7. Screen inventory, P0 to P7

Twenty five screens. Status is the owning feature's status, not the screen's.

### Home

| Route | Screen | Features | Sub project | Status |
| --- | --- | --- | --- | --- |
| `/` | Home | FEAT-008, and a roll up of all | All | Designed here, not built |

### Cost

| Route | Screen | Features | Sub project | Status |
| --- | --- | --- | --- | --- |
| `/cost` | Spend and trend | FEAT-020, FEAT-021 | P1 | Planned |
| `/cost/allocation` | Allocation and showback | FEAT-022 | P1 | Planned |
| `/cost/anomalies` | Anomalies | FEAT-023 | P1 | Planned |
| `/cost/commitments` | Commitment coverage | FEAT-024 | P1 | Planned |
| `/cost/export` | Export | FEAT-045 | P1 | Planned |

### Waste

| Route | Screen | Features | Sub project | Status |
| --- | --- | --- | --- | --- |
| `/waste` | Recommendations, ranked | FEAT-025, FEAT-026, FEAT-027, FEAT-035, FEAT-036, FEAT-037, FEAT-047 | P3, P6 | Planned |
| `/waste/:id` | Recommendation detail | FEAT-028, FEAT-044, FEAT-048 | P3, P6 | Planned |
| `/waste/savings` | Realized savings | FEAT-029 | P3 | Planned |
| `/waste/score` | FinOps Score | FEAT-043 | P3 | Planned |

### Governance

| Route | Screen | Features | Sub project | Status |
| --- | --- | --- | --- | --- |
| `/governance/queries` | Query findings | FEAT-011, FEAT-012, FEAT-013, FEAT-016 | P2 | Specified, designed in section 9 |
| `/governance/queries/:id` | Finding detail | FEAT-012, FEAT-013, FEAT-017, FEAT-018 | P2 | Specified, designed in section 9 |
| `/governance/instances` | Query surfaces | FEAT-011, FEAT-019 | P2 | Specified, designed in section 9 |
| `/governance/enforcement` | Enforcement | FEAT-014, FEAT-015, FEAT-017 | P2 | Specified, designed in section 9 |
| `/governance/quotas` | Quotas | FEAT-033, FEAT-034 | P5 | Planned |

### Inventory

| Route | Screen | Features | Sub project | Status |
| --- | --- | --- | --- | --- |
| `/inventory/accounts` | Accounts | FEAT-001, FEAT-002 | P0 | Built |
| `/inventory/organization` | Organization | FEAT-009 | P0 | Built |
| `/inventory/resources` | Resource inventory | FEAT-030 | P4 | Planned |
| `/inventory/topology` | Topology map | FEAT-031, FEAT-032 | P4 | Planned |

### Platform

| Route | Screen | Features | Sub project | Status |
| --- | --- | --- | --- | --- |
| `/platform/ingest` | Ingest runs | FEAT-005, FEAT-006, FEAT-010 | P0 | Built |
| `/platform/freshness` | Freshness | FEAT-006, FEAT-010 | P0 | Built |
| `/platform/cost` | Meter's own cost | FEAT-008 | P0 | Built |
| `/platform/flags` | Flags and configuration | FEAT-049 | P0 | Planned |

### Assistant

| Route | Screen | Features | Sub project | Status |
| --- | --- | --- | --- | --- |
| `/assistant` | Ask | FEAT-038, FEAT-039, FEAT-042, FEAT-046 | P7 | Planned |
| `/assistant/digests` | Digests | FEAT-041 | P7 | Planned |

FEAT-040, remediation as a pull request, has no screen. It produces a pull
request, and the pull request is the interface. FEAT-003, FEAT-004, FEAT-007
and FEAT-050 have no screen of their own because they are the machinery every
screen runs on.

## 8. The five built screens, P0

These exist in `finops-web/src/screens/`. They need three changes, and no
redesign.

| Change | Why | When |
| --- | --- | --- |
| New routes under their groups, per section 4 | The flat section list does not survive P3 | TASK-P0-036 |
| The trust strip stays in the shell | Coverage, freshness and degraded are already there and stay there. Nothing to do | Built |
| Platform gains a fourth screen, flags | FEAT-049 has no surface today | **Deferred.** Listed in the navigation with its arrival, not built. It is not needed for any screen in this document and adding it would be scope with no reader waiting for it |

The screens themselves are correct. `Figure`, `StateBoundary`, `TypedError`,
`CoverageBanner` and `FreshnessIndicator` already carry the honesty guarantees,
and this document changes nothing about how they render.

## 9. The four screens, P2

Specified in `docs/specs/2026-08-23-p2-query-cost-governance-design.md` section
9. Designed here against the visual system, which is what section 13 of
`docs/12-UI-DESIGN.md` asks each sub project to do.

### 9.1 Query findings, `/governance/queries`

Dense. The user is scanning hundreds of rows for outliers, so 32 px rows per
`docs/12-UI-DESIGN.md` section 7.

| Column | Component | Notes |
| --- | --- | --- |
| Severity | `SeverityBadge` | Sequential ramp, dollar based per ADR-0016 |
| Dashboard, panel | text | Links to the finding detail |
| Refresh, window | text | The two inputs a reader will want to change |
| Runs per day, scan per run | `Figure` | Modelled until FEAT-013 measures them |
| **Monthly cost** | `Figure` | The sort column. Hatched while modelled |
| Owner | text | From FEAT-016. `unattributed` is a value, not a blank |
| Why | prose | Ported from the prototype |

**The `why` column is the product.** A ranked list of costs tells a user what to
look at. The prose telling them a panel refreshes every ten seconds against a
thirty day window is what tells them what to do. It is a column, not a tooltip,
because a tooltip is invisible in a screenshot and this list is read in tickets.

It is also the widest column, and was the narrowest. Every column shared the
width evenly until 2026-09-11, which wrapped the explanation into a ribbon about
eight characters across. A column declared `prose` takes the width the others do
not need.

**Density is a property of the table, not of the caller.** `DataTable` marks
everything inside it as dense and `Figure` reads that, so a table written next
year is dense without its author knowing the mechanism exists. Dense removes the
freshness line and the accuracy clause and nothing else: the fill, the tilde
prefix and the word all stay, and freshness moves to the trust strip, where this
document already puts it. Repeating it per cell made a three figure row 90 px
tall and pushed monthly cost off a 1440 px screen. ISS-155.

States: all seven. The one that matters is `Partial`, because an unreachable
instance means the list is incomplete and the count of what is missing sits
above the table, not inside it.

### 9.2 Finding detail, `/governance/queries/:id`

Generous density. The user is making a judgement and needs room to read the
evidence.

Publishes the full working, in this order: the query text, the target it runs
against, the engine classification, the formula with its inputs substituted, the
data window, and the measured evidence where FEAT-013 has produced any.

**Publishing the arithmetic is what makes a modelled number arguable rather than
magic.** An engineer who disagrees with the cost can point at the line they
disagree with, and that is the difference between a finding that gets fixed and
a finding that gets dismissed.

Every figure carries `~` and the hatch until FEAT-018 publishes an accuracy
percentage, at which point the label becomes `~ $12,400 modelled, +/- 9%`. Until
then it reads `accuracy not yet published`, which is worse looking and more
honest.

### 9.3 Query surfaces, `/governance/instances`

Every instance, its kind, its reachability, and the count of queries found.

**Unreachable instances are listed, never omitted.** This screen exists to stop
silent under counting: a workspace Meter cannot read reports its typed cause and
no number, per `docs/12-UI-DESIGN.md` section 5. An instance list that quietly
drops the three it could not reach makes the findings list look complete when it
is not.

The count of queries for an unreachable instance is not zero. It is `UNREACHABLE`
with the network cause and a recheck.

### 9.4 Enforcement, `/governance/enforcement`

What the control did, to whom, when it expires, and a revoke button.

| Column | Notes |
| --- | --- |
| Action | ALERT, THROTTLE or DENY |
| Principal | Who it was applied to |
| Applied at, expires at | Absolute for both. An expiry is a claim about the world |
| Reason | The finding that triggered it, linked |
| Revoke | Present on every active action, subject to the write level |

**This screen is the reason `deny` is safe to enable.** A control that cuts off
an engineer mid incident is a self inflicted second incident, and the mitigation
recorded against ISS-092 is auto expiry, a never deny list, a revoke route and
this screen. Without the screen, the other three are invisible and nobody
enables the feature.

Expiry is shown as an absolute time and a countdown together. The countdown
answers "how long do I have", the absolute answers "when exactly", and an
incident bridge needs both.

## 10. Cross screen patterns

Built once, in the shell. A screen that implements its own is a screen that will
implement it differently.

| Pattern | Behaviour |
| --- | --- |
| **Scope switcher** | In the shell, always visible, writes `?scope=`. Changing scope never silently changes what a figure means, because coverage is recomputed and shown. **Not yet planned**, because ADR-0008 parks the identity adapter and a switcher over one hardcoded scope would be a control that does nothing |
| **Trust strip** | Coverage, freshness and degraded are shell level on every screen, worst case across that screen's collectors. Meter's own cost is Home only, per constraint 7 |
| **Search** | One field, spanning accounts, resources, dashboards and findings. Results grouped by the seven groups, so the result list teaches the navigation. **Not yet planned**, because it wants at least three entity types to search over and P0 plus P2 supply two |
| **Drill down** | Always into the owning group, never a modal. A finding opens its own URL, so it can be linked |
| **Export** | Every table. **The export carries its coverage and both timestamps**, per FEAT-045 and `docs/12-UI-DESIGN.md` section 6. A spreadsheet that leaves without them becomes a number in a board pack with no way back to what it meant |
| **Fixture marker** | Any screen resolving to fixture data renders the `FIXTURE DATA` band above its own content, driven by the same resolution that chose the fixture. It is per screen rather than shell level, because the shell aggregates `meta` and a fixture is a property of one surface rather than of the view. Each such screen carries a test asserting the band renders. See section 11 |
| **Empty groups** | A group whose sub projects have not landed shows its screens with their arrival, never a hidden or disabled entry. Hiding it makes the product look smaller than it is and makes the roadmap invisible |

## 11. Contract first delivery

### The problem this solves

`TASK-P2-022` is a single L task, last in wave J, behind fourteen backend tasks.
Under that ordering the first pixel of P2 appears at task 21 of 22, which means
nobody sees the sub project until it is finished, and a design mistake is found
at the point where it is most expensive to fix.

### The seam

It already exists, built for P0.

| Piece | Where |
| --- | --- |
| Response types | `finops-web/src/api/types.ts` |
| Fixture data | `finops-web/src/screens/__tests__/fixtures.ts` |
| Client swap | `finops-web/src/api/ApiProvider.tsx` |

### The order

1. Define the response type for a surface, generated from the same model the
   route will return, so there is one definition and not two.
2. Write a fixture that satisfies it, including a failure case and a partial
   case. A fixture with only the happy path pins the wrong screen.
3. Build the screen against the fixture, with its tests and its axe pass.
4. Swap the fixture for the route when the route lands. A contract test asserts
   the route's response still satisfies the type the fixture satisfied.

### The rule that keeps this honest

**A fixture backed screen says so, on screen, in the trust strip.**

```
  FIXTURE DATA   this screen is not connected to a collector yet
```

Not a build flag, not a console warning, not a comment in the code. A visible
band, in the same place the coverage warning goes, using the same treatment as a
degraded state.

A product whose entire claim is that you can tell how much a number is worth
trusting cannot ship a screen of invented numbers that looks like a screen of
real ones. The marker is not a development convenience. It is the same rule as
section 5 of `docs/12-UI-DESIGN.md` applied to the one case that document did
not anticipate.

## 12. What lands when

The visibility ladder. This is the answer to "we will not be able to see the
progress".

| When | What becomes visible |
| --- | --- |
| Navigation regrouped, trust strip in the shell | The seven groups, the five P0 screens in their new homes, every future screen listed with its arrival |
| Home, with every slot empty and named | The shape of the finished product, on the front page, before any of it exists |
| Each P2 screen, fixture backed | Four screens under Governance, marked as fixture data, reviewable for layout and language |
| P2 route lands, fixture swapped | The same screen, marked as real, with no layout change to review |
| Each sub project lands | One Home slot turns from a named absence into a number |

The second row is the one that answers the original question. **The product's
own front page becomes the progress view**, because a slot that says
`arrives with P1 Cost Intelligence` is a roadmap a user can read.

## 13. What this does not cover

- Screen level design for P1 and P3 to P7. Each sub project specification adds
  its screens against this frame and the visual system, per
  `docs/12-UI-DESIGN.md` section 13.
- Chart provenance. P1 introduces charts beyond the sparkline and must extend
  section 7 of `docs/12-UI-DESIGN.md` before it does.
- Authentication and the sign in surface. ADR-0008 parks the identity adapter,
  and the sign in screen arrives with the adapter.
- The scope switcher, search, and the flags screen. All three are specified
  above and none is in the first implementation plan. Section 10 and section 8
  say which and why, so a reader can tell a deferral from an omission.
- Brand, logo, marketing. Meter is an internal instrument.
