# P8 Experience and reporting: implementation plan

Date: 2026-10-05
Status: Approved by the owner on 2026-10-05, with its spec
Spec: `docs/specs/2026-10-05-p8-experience-and-reporting-design.md`
Depends on: P1 to P7 delivered
Tasks: 15

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
| Status | Not started |
| Implements | P8 spec section 5.4 |
| Delivers | The chart set the spec names |
| Depends on | TASK-P8-001 |
| Estimate | L |

**Goal.** Meter's chart set, hand built in SVG as the owner chose on 2026-10-05, with no
chart dependency.

**Acceptance criteria.**

- [ ] Stacked area with forecast band and budget pace, stacked bar, ranked bar with a
      table, KPI tile with delta and sparkline, treemap and heatmap
- [ ] Every chart has a table alternative, and a test holds its values equal to the marks
- [ ] Measured, modelled and forecast drawn solid, hatched and dashed, in both themes
- [ ] No motion under `prefers-reduced-motion`
- [ ] The existing hand built charts replaced or wrapped so one set remains

---

### TASK-P8-006: tables that sort, total and drill

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P8 spec section 5.1 |
| Delivers | Sorting, totals and drill down in `DataTable` |
| Depends on | TASK-P8-001 |
| Estimate | M |

**Acceptance criteria.**

- [ ] Sorting by keyboard and pointer, announced with `aria-sort`
- [ ] A sticky header and a column chooser
- [ ] A totals row only over figures of one unit and one provenance; a mixed column says
      why it has no total
- [ ] A row opens its owning screen; virtualisation kept above 200 rows

---

### TASK-P8-007: Cost Explorer

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P8 spec sections 5.3 and 7, FEAT-065 |
| Delivers | FEAT-065 |
| Depends on | TASK-P8-003, TASK-P8-005, TASK-P8-006 |
| Estimate | L |

**Goal.** `GET /cost/explore` and its screen: the question a practitioner asks first,
answered with the rows the product already holds.

**Acceptance criteria.**

- [ ] Two group bys over FOCUS dimensions and tag keys from an allow list, and filters
- [ ] Daily and monthly; month to date, 3, 6 and 12 months, year to date and custom
- [ ] Comparison with the previous period
- [ ] Effective Cost by default; another cost metric offered only where the table holds it
- [ ] The same scope dependency and guard as `/cost`, coverage and failures in the
      envelope, and unallocated shown, never hidden
- [ ] A bounded query: partition pruning on the period and a row limit the envelope names

---

### TASK-P8-008: spend forecast

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P8 spec section 7, FEAT-066 |
| Delivers | FEAT-066 |
| Depends on | TASK-P8-005 |
| Estimate | M |

**Goal.** `GET /cost/forecast`, month end and three months ahead, with a band and the method
named, the first producer of forecast provenance.

**Acceptance criteria.**

- [ ] Meets the four conditions ADR-0015 sets before any figure carries forecast
      provenance; where one cannot be met, no figure is shown and the reason is
- [ ] Accuracy measured by backtest over held out months and published beside the figure
- [ ] Drawn dashed with its band, never as measured

---

### TASK-P8-009: Excel and CSV export behind the guard

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P8 spec section 5.5, FEAT-067 |
| Delivers | FEAT-067 and FEAT-045 |
| Depends on | TASK-P8-002 |
| Estimate | L |

**Goal.** One export responder for every route a screen reads, writing the view's own rows
with an About sheet.

**Acceptance criteria.**

- [ ] XlsxWriter admitted through `make dep-check`
- [ ] `format=xlsx` and `format=csv` on every list route a screen reads, enumerated by a
      test over the routers as the MCP drift gate does
- [ ] A Data sheet with FOCUS headers and typed numbers, and an About sheet with every
      field in spec section 5.5 item 2
- [ ] Every leading character in spec section 5.5 item 3 written as text, tested
- [ ] The row limit is a setting, named in the About sheet, with CSV for the full set
- [ ] One `report_run` row per export, migration included, every invariant a constraint
- [ ] Parity: rows equal the screen's; scope: a narrower principal never sees more
- [ ] An Export menu on every screen, and the old Export screen's CSV replaced by it

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
- [ ] No colour outside the tokens in any component, held by a test
- [ ] Axe clean in both themes

---

### TASK-P8-014: proof

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P8 spec sections 8 and 12 |
| Delivers | The exit criteria, measured |
| Depends on | TASK-P8-001 to TASK-P8-013 |
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

## What this plan does not answer

- OPEN-11, where scheduled reports go. The schedule is built; delivery waits.
- OPEN-15, how long report files are kept.
- Unit economics, which needs a business metric source nobody has named.
