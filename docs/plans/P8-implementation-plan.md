# P8 Experience and reporting: implementation plan

Date: 2026-10-05
Status: Approved by the owner on 2026-10-05, with its spec
Spec: `docs/specs/2026-10-05-p8-experience-and-reporting-design.md`
Depends on: P1 to P7 delivered
Tasks: counted in `tasks/STATUS.md`, which reads them from this plan

The first sub project that changes how Meter looks rather than what it knows. The owner
approved the direction on 2026-10-05: two themes of one glass design system, navigation
by the FinOps Framework, and four reporting capabilities. The risk is the one every
redesign carries, that the new look quietly drops what made the old screens honest.

## How to work this plan

Same contract as P0 through P7. One task, one commit.

**Five rules specific to P8.**

1. **No figure changes.** The spec moves labels, layout and exports, never a computation.
   A screen that needs a number the API does not return asks for a route; the browser
   never derives one, except a total over rendered rows of one unit and one provenance.

2. **The look never costs a figure its provenance.** Measured, modelled and forecast keep
   distinct marks, every figure keeps `as_of` and `collected_at`, and a failure is never a
   zero. Every restyling task keeps the tests that hold this and adds none that weaken it.

3. **Exports are made by the server and tested for parity.** Rows in a file equal the rows
   on the screen under the same scope, and a narrower scope never sees more. No task adds
   a browser export.

4. **Old paths never break.** A route that moves redirects, and the redirect table is
   tested against every path the navigation had before this sub project.

5. **The owner approves once more.** The full label table in TASK-P8-004 before any label
   changes. Hand built SVG charts and the Geist type family were settled at the approval of
   this plan on 2026-10-05.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. Foundations | 001 to 003 | Two themes, the Framework navigation, filters in the query string | This plan approved |
| B. Words | 004 | FOCUS and Framework names on every screen | A, the label table approved |
| C. Charts and tables | 005 to 006 | Chart primitives in Meter's look, tables that sort and total | 001 |
| D. Analyze and plan | 007 to 008 | Cost Explorer and the spend forecast | B, C |
| E. Reporting | 009 to 011 | Excel and CSV export, saved views, scheduled reports | 003, D for the explorer's export |
| F. Dashboards and screens | 012 to 013 | Persona dashboards, every remaining screen restyled | C, D |
| G. Proof and documents | 014 to 015 | Accessibility, journeys, performance, and the documents | All |
| H. Added 2026-10-05 | 016 to 017 | The account picker on every screen, and the geography map redrawn | 002 and 003 for the picker, 005 for the map |
| I. Added later on 2026-10-05 | 018 | The look as drawn: light by default, rich motion, the glass rail and the top bar | 001 and 002 |

**Build order, decided by the owner later on 2026-10-05.** 018, then 016, 012, 013 and
017, then 010, 011, 014 and 015. The look comes first because the built screens were still
in the old design when the owner compared them with the drawings.

---

### TASK-P8-001: two themes, one set of tokens, and glass that degrades

| Field | Value |
| --- | --- |
| Status | Done 2026-10-05 |
| Implements | P8 spec section 5.1, FEAT-063 |
| Delivers | FEAT-063 |
| Depends on | This plan approved |
| Estimate | M |

**Goal.** `finops-web/src/tokens.css` holds the dark and light token sets from the spec,
a panel surface in each, and a theme toggle over the operating system's choice.

**Acceptance criteria.**

- [x] Both token sets defined, the operating system chooses by default, and a toggle
      overrides it and is remembered per person
- [x] With transparency reduced, or without `backdrop-filter`, panels are opaque and the
      page glows are gone
- [x] A test over the tokens holds text, muted and faint at 4.5 to 1 or better on every
      panel tier in both themes
- [x] Print uses the light theme with no glass
- [x] Geist and Geist Mono, confirmed on 2026-10-05, self hosted and admitted through
      `make dep-check`
- [x] `docs/12-UI-DESIGN.md` amended with the date and the reason; its provenance,
      freshness, absence and numeral rules unchanged

**Delivered 2026-10-05.** The choice is remembered in the person's browser, beside the
navigation state; remembering it across their devices waits for per person storage, which
TASK-P8-010 brings. Two light values differ from the spec's table, for its own contrast rule:
faint is `#5a687d`, and the accent drawn as text is `#0064d2` with the table's `#0a84ff` kept
as the accent mark. `docs/12-UI-DESIGN.md` section 7 gives the ratios.

---

### TASK-P8-002: the shell, the Framework navigation and the redirects

| Field | Value |
| --- | --- |
| Status | Done 2026-10-05 |
| Implements | P8 spec section 5.2, FEAT-064 |
| Delivers | FEAT-064, with TASK-P8-004 |
| Depends on | TASK-P8-001 |
| Estimate | L |

**Goal.** `sections.ts` and `AppShell.tsx` carry the approved groups, the shell is drawn in
the new system, and every old path redirects.

**Acceptance criteria.**

- [x] Groups and screens as in spec section 5.2, each group's Framework domain named in a
      comment beside it
- [x] Every path in `sections.ts` before P8 redirects to its new home, and a test
      enumerates them
- [x] Organization, Geography and the three query cost screens become tabs of their new
      screens
- [x] Unit Economics is listed as arriving, never as built
- [x] The trust strip keeps freshness, coverage and failing collections in the new look
- [x] A new ADR supersedes ADR-0020, and `docs/13-UI-ARCHITECTURE.md` follows it
- [x] Axe clean in both themes

**Delivered 2026-10-05.** The spec named no home for three screens, and the owner placed them:
the three container screens stay separate under Analyze, Enforcement becomes Policies, and Flags
stays under Platform as arriving. The menu took the approved names now, by the owner's choice;
labels inside screens wait for TASK-P8-004. Axe, run on the shell in a real browser for the first
time, found the rail's faint text at 4.2 to 1, and `--nav-text-faint` moved to the dark theme's
faint. ADR-0030 supersedes ADR-0020.

---

### TASK-P8-003: filters live in the query string

| Field | Value |
| --- | --- |
| Status | Done 2026-10-05 |
| Implements | P8 spec section 5.6 |
| Delivers | ISS-235 closed |
| Depends on | TASK-P8-002 |
| Estimate | M |

**Goal.** One hook reads and writes every filter through the URL, so a link, a bookmark
and a saved view carry the same state.

**Acceptance criteria.**

- [x] Every filter control on every screen reads and writes the query string
- [x] The links from FinOps Score and from Geography land filtered, tested
- [x] Back and forward restore the filter
- [x] An unknown parameter is ignored and named, never silently applied

**Delivered 2026-10-05.** Four screens had filter controls: Accounts, Allocation, Resources
and, new, Recommendations, which narrows to the one finding a FinOps Score link names. Each
declares its keys once in `sections.ts`, which is also what saved views will store in
TASK-P8-010. The Geography link needed no change: the resource API already narrowed by
geography, and only the screen ignored it.

---

### TASK-P8-004: FOCUS and Framework names on every screen

| Field | Value |
| --- | --- |
| Status | Done 2026-10-05 |
| Implements | P8 spec section 5.3, FEAT-064 |
| Delivers | FEAT-064, with TASK-P8-002 |
| Depends on | TASK-P8-002 |
| Estimate | M |

**Goal.** Every label a person reads uses the standard term, with the provider's term in
its tooltip.

**Acceptance criteria.**

- [x] First output: a table of every label on every screen, today, proposed and basis,
      approved by the owner before any label changes
- [x] Every approved label changed, and journeys updated with them
- [x] Every cost column carries its provider term in a tooltip
- [x] No raw identifier on any screen, collector names and enum codes included, held by a
      test over the rendered text

**Delivered 2026-10-05.** The owner approved
`docs/specs/2026-10-05-p8-label-table.md` as written. Two things moved during the build.
The commitment KPI headings take the approved names and keep their old sentence beneath
them, because a test holds that two percentages side by side each name their denominator.
The collector names the API sends are the names each collector declares, which are not
always its module's, so the table's collector section was regenerated from the code before
it was applied. Two shapes stay on screen on purpose: a Meter setting an operator must type,
such as METER_ASSISTANT_MODEL_ID, and a register reference such as OPEN-10.

---

### TASK-P8-005: chart primitives in Meter's own look

| Field | Value |
| --- | --- |
| Status | Done 2026-10-05 |
| Implements | P8 spec section 5.4 |
| Delivers | The chart set the spec names |
| Depends on | TASK-P8-001 |
| Estimate | L |

**Goal.** Meter's chart set, hand built in SVG as the owner chose on 2026-10-05, with no
chart dependency.

**Acceptance criteria.**

- [x] Stacked area with forecast band and budget pace, stacked bar, ranked bar with a
      table, KPI tile with delta and sparkline, treemap and heatmap
- [x] Every chart has a table alternative, and a test holds its values equal to the marks
- [x] Measured, modelled and forecast drawn solid, hatched and dashed, in both themes
- [x] No motion under `prefers-reduced-motion`
- [x] The existing hand built charts replaced or wrapped so one set remains

**Delivered 2026-10-05.** The set is `finops-web/src/components/charts/`, hand built SVG with
no chart dependency. The ranked bars already wrote every value beside its bar, which is its
table; the bar chart gained one. Six series colours were added to the tokens, each held at 3
to 1 on the page and every panel in both themes by the contrast test. No screen uses the new
charts yet: Cost Explorer, the forecast and the persona dashboards do, in TASK-P8-007, 008 and
012.

---

### TASK-P8-006: tables that sort, total and drill

| Field | Value |
| --- | --- |
| Status | Done 2026-10-05 |
| Implements | P8 spec section 5.1 |
| Delivers | Sorting, totals and drill down in `DataTable` |
| Depends on | TASK-P8-001 |
| Estimate | M |

**Acceptance criteria.**

- [x] Sorting by keyboard and pointer, announced with `aria-sort`
- [x] A sticky header and a column chooser
- [x] A totals row only over figures of one unit and one provenance; a mixed column says
      why it has no total
- [x] A row opens its owning screen; virtualisation kept above 200 rows

**Delivered 2026-10-05.** `DataTable` sorts by a button in each header that declares a sort
value, so the keyboard and the pointer do the same thing, and `aria-sort` says which way. A
figure sorts largest first, and a figure that was not collected sorts last in either direction.
The header was already sticky inside the table's scroll box. The column chooser is closed until
opened and will not hide the last column. A column totals only where every row has a figure of
one unit and one provenance, and otherwise says which of those failed; a figure not collected
gives no total rather than a total that counts it as zero. A row opens its owning screen through
the link its name cell already drew on every table that has one (query findings, quotas and
resources), so no second link column was added. Virtualisation counts the sorted rows. Cost
Explorer adopts all of it: every column sorts, Effective Cost and Billed Cost total to the
headline figure above them, and the order the API sends is stated in the header by
`initialSort` rather than claimed by the caption, where a reader's sort would make it false. The
other tables take sort values in TASK-P8-013.

---

### TASK-P8-007: Cost Explorer

| Field | Value |
| --- | --- |
| Status | Done 2026-10-05 |
| Implements | P8 spec sections 5.3 and 7, FEAT-065 |
| Delivers | FEAT-065 |
| Depends on | TASK-P8-003, TASK-P8-005, TASK-P8-006 |
| Estimate | L |

**Goal.** `GET /cost/explore` and its screen: the question a practitioner asks first,
answered with the rows the product already holds.

**Acceptance criteria.**

- [x] Two group bys over FOCUS dimensions and tag keys from an allow list, and filters
- [x] Daily and monthly; month to date, 3, 6 and 12 months, year to date and custom
- [x] Comparison with the previous period
- [x] Effective Cost by default; another cost metric offered only where the table holds it
- [x] The same scope dependency and guard as `/cost`, coverage and failures in the
      envelope, and unallocated shown, never hidden
- [x] A bounded query: partition pruning on the period and a row limit the envelope names

**Delivered 2026-10-05.** The owner chose the layout, the eight groupings, tag keys from the
period's own line items and the like for like comparison, each the recommended option. The period
arithmetic is `finops_core/domain/explore.py`, the reads `finops_api/db/repositories/explore.py`,
every one derived from `scoped_select`, and the route `finops_api/routes/explore.py`, registered
as P8's first router. The table holds 500 rows and says what the rest add up to, and the
unallocated rows are read apart from the limit. The screen at `/analyze/explorer` replaced the
spend and trend screen: its view lives in the address, its table values are filter links, and its
chart is StackedBar drawn as columns, an orientation added for time. The chart set's legend and
rows had shipped with no styles in TASK-P8-005 and are styled now. The hook and fixture only the
old screen read were removed.

---

### TASK-P8-008: spend forecast

| Field | Value |
| --- | --- |
| Status | Done 2026-10-05 |
| Implements | P8 spec section 7, FEAT-066 |
| Delivers | FEAT-066 |
| Depends on | TASK-P8-005 |
| Estimate | M |

**Goal.** `GET /cost/forecast`, month end and three months ahead, with a band and the method
named, the first producer of forecast provenance.

**Acceptance criteria.**

- [x] Meets the four conditions ADR-0015 sets before any figure carries forecast
      provenance; where one cannot be met, no figure is shown and the reason is
- [x] Accuracy measured by backtest over held out months and published beside the figure
- [x] Drawn dashed with its band, never as measured

**Delivered 2026-10-05.** The owner chose the method, the band, the gate and the screen, each the
recommended option: a weekday profile over the eight weeks before the forecast, an 80 percent
band from its own misses on up to 12 held out months, and withheld below 3 tests or above a 15
percent median miss, with the reason shown where the figure would be. The arithmetic is
`finops_query/forecast.py`, the reads `finops_api/db/repositories/forecast.py` and the route
`finops_api/routes/forecast.py`, P8's second router. The Forecasts screen under Plan is built,
and `forecastUnproduced.test.ts` now names it as the one producer of a forecast. On the eight
month fake estate the month end was shown with a median miss of 5.95 percent over 5 months, and
the months ahead were shown, withheld for their misses and withheld for want of tests (measured
2026-10-05 on synthetic data).

---

### TASK-P8-009: Excel and CSV export behind the guard

| Field | Value |
| --- | --- |
| Status | Done 2026-10-05 |
| Implements | P8 spec section 5.5, FEAT-067 |
| Delivers | FEAT-067 and FEAT-045 |
| Depends on | TASK-P8-002 |
| Estimate | L |

**Goal.** One export responder for every route a screen reads, writing the view's own rows
with an About sheet.

**Acceptance criteria.**

- [x] XlsxWriter admitted through `make dep-check`
- [x] `format=xlsx` and `format=csv` on every list route a screen reads, enumerated by a
      test over the routers as the MCP drift gate does
- [x] A Data sheet with FOCUS headers and typed numbers, and an About sheet with every
      field in spec section 5.5 item 2
- [x] Every leading character in spec section 5.5 item 3 written as text, tested
- [x] The row limit is a setting, named in the About sheet, with CSV for the full set
- [x] One `report_run` row per export, migration included, every invariant a constraint
- [x] Parity: rows equal the screen's; scope: a narrower principal never sees more
- [x] An Export menu on every screen, and the old Export screen's CSV replaced by it

**Delivered 2026-10-05.** One responder, `finops_api/exports/`, applied to each list route
as `@exportable`, so no return can answer JSON for a file: 34 routes export, and
`tests/api/test_export_routes.py` fails for a GET route that neither exports nor states why
not. The workbook is XlsxWriter in constant memory mode, admitted through `make dep-check`
with zero findings. `/cost/export` became `/cost/showback`, its rows in the envelope, so
FEAT-045 is delivered through the same responder and `ENVELOPE_EXEMPT` holds no route with
tenant data. The Export menu sits beside every screen title, fed by the query hooks. Three
things were found on the way: a view with more than one table exports its first, ISS-247;
the savings screen printed a verdict code the raw identifier test could not see, ISS-248,
fixed; `report_run` holds a person's identifier no retention job or erasure reaches,
ISS-249; and the hub passes 6 of the 74 settings the API requires, so a deployed API
would not start, ISS-250. Against the local stack the showback workbook held 31 rows and 14 failures on its
About sheet, and both files wrote a `report_run` row (measured 2026-10-05 on synthetic
data).

---

### TASK-P8-010: saved views and the report library

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P8 spec section 5.6, FEAT-068 |
| Delivers | FEAT-068 |
| Depends on | TASK-P8-003, TASK-P8-009 |
| Estimate | M |

**Acceptance criteria.**

- [ ] `saved_view` migration with the constraints in spec section 6
- [ ] A private view is confined to its owner, ADR-0029; a shared one is visible to the
      tenant as configuration
- [ ] Opening a view renders it in the opener's scope, asserted with two principals
- [ ] The Report Library: open, rename, duplicate, share, delete and export

---

### TASK-P8-011: scheduled reports, rendered for each recipient

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P8 spec section 5.7, FEAT-069 |
| Delivers | FEAT-069 |
| Depends on | TASK-P8-010 |
| Estimate | L |

**Acceptance criteria.**

- [ ] `report_schedule` migration with the constraints in spec section 6
- [ ] A collector in `collector_schedule` with its reason and cost, ADR-0012, renders each
      due schedule once per recipient in that recipient's scope
- [ ] Files stored in the hub data bucket under the tenant prefix, fetched through a route
      that checks scope again
- [ ] A `ReportSender` port with a fake; runs listed as rendered and not sent until OPEN-11
- [ ] One recipient failing does not fail the run
- [ ] No deletion job until OPEN-15 is answered, and the screen says how long files are kept

---

### TASK-P8-012: persona dashboards on the Overview

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P8 spec section 5.8, FEAT-070 |
| Delivers | FEAT-070 |
| Depends on | TASK-P8-005, TASK-P8-007, TASK-P8-008 |
| Estimate | L |

**Acceptance criteria.**

- [ ] Executive, FinOps practitioner and engineering lead dashboards, the reader's last
      choice remembered
- [ ] Every KPI shows its formula and baseline, and every figure links to its owning screen
- [ ] A KPI the data cannot support says so and shows no figure
- [ ] Built from existing routes only; no new number
- [ ] The charts the owner chose on 2026-10-05: a 12 month trend by service, month to date
      against the forecast band, the top 10 accounts, a service treemap and savings by
      category, each with its table of numbers
- [ ] Every figure and chart narrowed by the account picker, TASK-P8-016, and All accounts
      combined when the Overview opens
- [ ] The FinOps view as drawn, decided later on 2026-10-05:
      `docs/design/2026-10-05-overview-frosted-ledger.jpg`, KPI tiles, daily cost by
      category with the forecast and the daily budget pace, cost by service, anomalies,
      top recommendations, scheduled reports and showback by team, with the Executive and
      Engineering dashboards one click away. A tile whose data is not collected says so
      and shows no figure

---

### TASK-P8-013: every remaining screen in the new system

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P8 spec section 5.1 |
| Delivers | One look across all screens |
| Depends on | TASK-P8-002, TASK-P8-004, TASK-P8-005, TASK-P8-006 |
| Estimate | L |

**Acceptance criteria.**

- [ ] Optimize, Govern, Inventory, Platform and Assist screens in the new system
- [ ] Every table sorts, and totals where its figures share a unit and a provenance, through
      `DataTable` as TASK-P8-006 built it
- [ ] No colour outside the tokens in any component, held by a test
- [ ] Axe clean in both themes
- [ ] A chart on every screen, as the owner chose on 2026-10-05: Allocation a team treemap and
      a team trend; Anomalies daily spend with anomaly markers; Commitments utilization and
      coverage over time and a day by day heatmap; Realized savings a cumulative savings area;
      Accounts the top accounts and a health heatmap; Resources by type and by region; Query
      cost by dashboard and its trend; Meter cost its trend by module

---

### TASK-P8-014: proof

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P8 spec sections 8 and 12 |
| Delivers | The exit criteria, measured |
| Depends on | TASK-P8-001 to TASK-P8-013, TASK-P8-016 and TASK-P8-017 |
| Estimate | M |

**Acceptance criteria.**

- [ ] Axe on every screen in both themes and with transparency reduced
- [ ] Journeys: change persona, group Cost Explorer by two dimensions, export to Excel,
      save the view, schedule it
- [ ] No `backdrop-filter` on any element inside a table or a list, held by a test
- [ ] Every exit criterion in spec section 12 met, each with its evidence

---

### TASK-P8-015: documents

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | `docs/03-CHANGE-CONTROL.md` |
| Delivers | The record |
| Depends on | TASK-P8-001 to TASK-P8-014 |
| Estimate | S |

**Acceptance criteria.**

- [ ] `docs/12-UI-DESIGN.md` and `docs/13-UI-ARCHITECTURE.md` describe what was built
- [ ] FEAT-063 to FEAT-070 and FEAT-045 carry as built sections
- [ ] The register, `project_map.md` and the checkpoint updated, and `make check-docs` clean

---

### TASK-P8-016: the account picker on every screen

Added 2026-10-05 at the owner's request: an estate of 1,399 accounts cannot be read only as
one sum.

| Field | Value |
| --- | --- |
| Status | Done |
| Implements | FEAT-075 |
| Delivers | FEAT-075 |
| Depends on | TASK-P8-002, TASK-P8-003, TASK-P8-018 for the top bar |
| Estimate | XL, after the owner widened the search on 2026-10-06 |

The owner decided two more things on 2026-10-06. A screen narrowed to one account states the
choice plainly rather than warning that it is partial, and the box in the top bar searches
services and resources as well as accounts, as the drawing's placeholder says.

The address keeps the choice as `account`, the account number Cost Explorer and Resources
already read as a filter, so those two filters become the one choice. The API takes it as its
own parameter, `chosen_account`, because `/api/v1/cost/explore` reads `account` as a list of
filter values, and a scope dependency reading the same name would narrow a request for two
accounts to one of them without saying so.

**Acceptance criteria.**

- [x] One search box in the top bar of every screen finds accounts, services and resources as
      it is typed: All accounts first and the default, then accounts by number or name,
      services by name and resources by name or ARN
- [x] Choosing an account narrows every screen and every export to it, the Overview included,
      and All accounts combines them again. Choosing a service opens Cost Explorer filtered to
      it, and choosing a resource opens its page, both keeping the account
- [x] The choice lives in the address, so a shared link opens the same account, and moving
      between screens keeps it
- [x] Narrowing is applied at the scope dependency, so every route obeys it at once, and it
      can only narrow what the session may already see, never widen it, held by a test. An
      account the session cannot see and one that does not exist get the same answer
- [x] A narrowed screen names the account under its title and counts coverage against the
      chosen account, so no partial warning appears, while a failure or missing data in that
      account still shows
- [x] Usable at 1,399 accounts: the accounts and the services load once and are searched
      without a round trip, resources are searched on the server with a bound, and the box is
      keyboard operable with the accessible combobox pattern

**Delivered 2026-10-06.** The choice is `account` in the address, sent to every route as
`chosen_account`, and `get_scope` narrows the resolved scope to it through `Scope.narrowed_to`,
which refuses an account the scope does not permit; an account outside the scope and one that
does not exist both answer 404. Every read carries the account in its cache key, every link keeps
it, and a test fails the build if a file uses the router's own links. A narrowed envelope carries
`scope_coverage.chosen` and counts coverage against the chosen account. The box offers 50
accounts at a time and searches services in the browser and resources on the server, through `q`
on `/api/v1/inventory/resources`. ISS-252 records that the resource search has no index.

---

### TASK-P8-017: the geography map redrawn

Added 2026-10-05 at the owner's request.

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | FEAT-061 |
| Delivers | FEAT-061, redrawn |
| Depends on | TASK-P8-005 |
| Estimate | M |

**Acceptance criteria.**

- [ ] The direction the owner chose on 2026-10-05: land as fine dots on a rounded world
      projection, each geography a glowing bubble sized by this month's Effective Cost with
      its resource count beside it, and lines for cross region links
- [ ] Glass tiles below the map, one per geography, each with a small trend
- [ ] Hover or focus on a bubble shows its numbers, and every number is also in a table
- [ ] The two stray horizontal lines on the current map gone, and a continent still the
      finest grain, because a region name says which geography and never which city
- [ ] Both themes, and still drawn by hand in SVG with no map library

---

### TASK-P8-018: the look as drawn

Added later on 2026-10-05 at the owner's request, after comparing the built screens with
the drawings: `docs/design/2026-10-05-overview-frosted-ledger.jpg` for the light theme and
`docs/design/2026-10-05-overview-aurora-glass.jpg` for the dark.

| Field | Value |
| --- | --- |
| Status | Done 2026-10-05 |
| Implements | P8 spec sections 2 and 5.1, FEAT-063 |
| Delivers | The shell and the motion of the drawings |
| Depends on | TASK-P8-001, TASK-P8-002 |
| Estimate | M |

**Acceptance criteria.**

- [x] Light, Frosted Ledger, opens for a reader who has chosen nothing; Dark and System
      stay in the toggle, and a choice already made is kept
- [x] The rail a glass panel in both themes, frosted in the light, inset as drawn, with its
      groups and screens listed
- [x] A top bar as drawn: the screen's title and its scope line, a toolbar holding the
      Export menu and the theme control, and the trust line beneath it
- [x] Motion as decided: hover, focus, menus and tabs in 150 to 200 ms; panels rising in a
      few at a time; a lift under the pointer with a token shadow; a cross fade between
      screens; a chart drawing in once, left to right
- [x] No number counts up and no bar grows from zero; reduced motion stops all of it, and
      reduced transparency and print keep their fallbacks, each held by a test
- [x] The surface tests rewritten to the new rule: a shadow only through a token, a
      transition never on width, height, position or `all`, keyframes from a named set
- [x] Axe clean and contrast held in both themes, the light rail included

**Delivered 2026-10-05.** Light opens for a reader who has chosen nothing, pinned in
`index.html` so a dark system never flashes a dark page. The rail is a glass panel whose groups open
one at a time, a bar with a menu drawer at or below 1024 pixels, and the column's top is the title and scope line, a toolbar holding Export
and the theme control, and the sticky trust line. Motion and elevation are tokens; the
keyframes are a named set of five, and a reduced motion block built from the same selectors
stops all of it. The journeys now run with reduced motion, because two of them read the
screen mid fade and failed at random, axe on a tab still fading in among them, and
`e2e/motion.spec.ts` proves both states from the computed animation. The screens' own panels
are still the ones they had: TASK-P8-012 and TASK-P8-013 redraw them.

On 2026-10-06 the six width sweep that found the narrow and phone faults was kept as
`e2e/viewports.spec.ts`. Run with the 2026-10-05 squeeze put back, it fails on every screen at
768 pixels with "gives the screen 64px of 744px".

---

## What this plan does not answer

- OPEN-11, where scheduled reports go. The schedule is built; delivery waits.
- OPEN-15, how long report files are kept.
- Unit economics, which needs a business metric source nobody has named.
