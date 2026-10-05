# P8 Experience and reporting: design specification

Date: 2026-10-05
Status: Approved by the owner on 2026-10-05
Sub project: P8
Features: FEAT-063, FEAT-064, FEAT-065, FEAT-066, FEAT-067, FEAT-068, FEAT-069, FEAT-070, and FEAT-045 delivered through FEAT-067
Depends on: P1 to P7 delivered
Supersedes: the visual rules in `docs/12-UI-DESIGN.md` named in section 5.1, and ADR-0020's seven groups, through a new ADR in TASK-P8-002

## 1. Purpose

Meter's figures are careful and its screens are not yet what a FinOps practitioner expects
to open. The owner said so on 2026-10-05 in three parts: the screens do not use standard
FinOps nomenclature, there is no graphical dashboard or report a person can take away as
an Excel sheet, and the look does not hold attention.

An audit of all 29 screens on the same day confirmed each part. The labels paraphrase
rather than name: FOCUS `EffectiveCost` reads as "Amortized" or "Total spend", commitment
utilization reads as "Of what we paid for, used", and the words showback, chargeback,
coverage and effective savings rate appear nowhere. There is one export, a cost CSV, and
its screen refuses Excel in words. There is no chart library, and no screen is called a
report or a dashboard.

This sub project changes how Meter looks, what its screens are called and how its numbers
leave it. It does not change how a number is computed, and every rule that makes the
numbers trustworthy survives it: measured, modelled and forecast stay visibly different,
every figure keeps `as_of` and `collected_at`, a failure is never drawn as zero, and scope
is enforced in two places.

## 2. Decisions the owner made on 2026-10-05

Recorded here because the rest of this document follows from them. They came after a
review of three directions drawn on the same Overview screen.

| Decision | Choice |
| --- | --- |
| Visual direction | Direction A, Aurora Glass, for the dark theme, and direction B, Frosted Ledger, for the light theme, as one design system |
| Navigation | The FinOps Framework layout shown in the mockups: Overview, Analyze, Plan, Optimize, Govern, Inventory, Report, Assist, Platform |
| Reporting in the first build | All four: Excel and CSV export, saved views and a report library, scheduled delivery, persona dashboards |

## 3. Definition of done

- Every screen uses the FOCUS display name for a cost column and the FinOps Framework name
  for a capability, with the provider's own term one hover away.
- Any view a person can see, they can download as an Excel workbook or a CSV whose rows
  equal the screen's, with a sheet that says what the numbers are, whose they are and when
  they were true.
- A view can be saved, named, shared as configuration and scheduled, and a shared or
  scheduled view always renders in the reader's own scope.
- The Overview opens on a dashboard for the reader's persona, and every figure on it links
  to the screen that owns it.
- Both themes pass the accessibility checks on every screen, including with transparency
  reduced and on a browser without backdrop blur.
- `make verify` passes, and the new export routes have a test that an export never holds a
  row the screen would refuse.

## 4. Out of scope

- **A report sender.** Scheduled reports are rendered and stored. Where they are delivered,
  email or Slack, is OPEN-11, already open for digests, and a sender is one adapter behind a
  port once it is answered.
- **Unit economics.** It needs a business metric source, for example requests or customers,
  and none exists. The navigation keeps the entry as arriving, the honest state.
- **PDF.** A workbook carries the figures and their provenance; a PDF is a picture of them.
  Revisit after the first build if the executive persona asks for one.
- **A new number, except the forecast.** No existing figure is computed differently. Where a
  screen gains a KPI, the KPI is derived from rows the API already returns, and its formula
  is written beside it. The spend forecast, FEAT-066, is the one new figure, and it meets
  ADR-0015's conditions or is not shown.

## 5. The decisions this sub project rests on

### 5.1 One design system, two themes

Direction A is the dark theme and direction B the light theme, one set of components and
two sets of tokens. The theme follows the operating system and a toggle overrides it,
remembered per person. Tokens live where they live today, `finops-web/src/tokens.css`,
and stay plain CSS under ADR-0021.

| Token group | Dark, Aurora Glass | Light, Frosted Ledger |
| --- | --- | --- |
| Page | `#070A12` under teal, violet and blue radial glows | `#EEF2F8` under indigo, cyan and pink glows |
| Panel | `rgba(15,20,32,0.55)`, blur 18px, saturate 140% | `rgba(255,255,255,0.64)`, blur 22px, saturate 170% |
| Hairline | `rgba(255,255,255,0.09)` with a 1px inner highlight | `rgba(15,23,42,0.08)` with a white inner highlight |
| Text, muted, faint | `#E8EEF7`, `#A1ACBE`, `#8390A6` | `#0F172A`, `#4A5870`, `#64738A` |
| Primary accent | teal `#5EEAD4` | electric blue `#0A84FF` |
| Second series and modelled marks | violet `#A78BFA` | indigo `#5B45E8` |
| Good, warning, critical | `#34D399`, `#FBBF24`, `#FB7185` | `#047857`, `#B45309`, `#C81E1E` |
| Radius | 16px panels, 10px controls | 18px panels, 10px controls |

**Typography is one system across both themes.** The mockups used Geist for A and Manrope
for B; one design system takes one type family. Geist for text and Geist Mono for figures,
with tabular numerals, self hosted as IBM Plex is today. Confirmed by the owner on 2026-10-05.

**Glass is a surface, never a reason to lose contrast.** Three rules hold it:

1. Text on glass meets 4.5 to 1 against the panel at its most transparent over the
   brightest point of the backdrop, which is why panels stay at or above the opacities
   in the table.
2. `prefers-reduced-transparency: reduce` and a browser without `backdrop-filter` both get
   an opaque panel of the same colour, and the page's glows are dropped.
3. Print uses the light theme with no glass and no glows.

**What changes in `docs/12-UI-DESIGN.md`.** Its rules against gradients and against a grid
of equal weight cards were written for the instrument direction the owner has now replaced.
They are amended, not deleted, with the date and the reason. Its rules on provenance,
freshness, absence and numerals stay word for word.

### 5.2 Navigation follows the FinOps Framework

The approved layout, with the Framework domain each group answers to. The 2026 Framework
names four domains; Meter's own platform and its inventory sit beside them, as the research
found no capability that owns them.

| Group | Screens | Framework domain and capability |
| --- | --- | --- |
| Overview | Persona dashboards | Understand Usage and Cost: Reporting and Analytics |
| Analyze | Cost Explorer, Allocation and Showback, Anomalies, Kubernetes | Understand Usage and Cost: Reporting and Analytics, Allocation, Anomaly Management |
| Plan | Budgets, Forecasts, FinOps Score, Unit Economics (arriving) | Quantify Business Value: Budgeting, Forecasting, KPIs and Benchmarking, Unit Economics |
| Optimize | Recommendations, Commitments, Realized Savings | Optimize Usage and Cost: Usage Optimization, Rate Optimization |
| Govern | Query Cost, Quotas, Policies | Manage the FinOps Practice: Governance, Policy and Risk |
| Inventory | Accounts, Resources, Topology | none; the ITAM persona and Data Ingestion are nearest |
| Report | Report Library, Scheduled, Exports | Understand Usage and Cost: Reporting and Analytics |
| Assist | Ask Meter, Digests | AI for FinOps |
| Platform | Data Freshness, Ingestion, Meter Cost | Manage the FinOps Practice: Automation, Tools and Services |

FinOps Score moves into Plan, beside the budgets it is read with, because the Framework
places KPIs and Benchmarking there. The mockup did not show it, and the owner confirmed
this placement on 2026-10-05.

**Every old path keeps working.** Each existing route redirects to its new home, so a
bookmark, a digest link or a link in a pull request body still lands. The redirect map is
a table in code with a test that every path in `sections.ts` before this sub project
resolves. Screens that merge become tabs: Organization under Accounts, Geography under
Topology, the three query cost screens under Query Cost.

ADR-0020 fixed seven groups and said renaming one takes an ADR. TASK-P8-002 writes the ADR
that supersedes it.

### 5.3 Names: FOCUS for columns, the Framework for capabilities

The rule is short. A cost column takes its FOCUS display name. A screen or a KPI takes its
FinOps Framework name. A provider's word, Amortized, Unblended or Savings Plan, appears in
the column's tooltip, because practitioners search for both.

| Today | Becomes | Basis |
| --- | --- | --- |
| Home | Overview | Common usage |
| Spend and trend | Cost Explorer | Reporting and Analytics; AWS Cost Explorer |
| Amortized, Amortized cost, Total spend | Effective Cost | FOCUS `EffectiveCost` |
| Billed | Billed Cost | FOCUS `BilledCost` |
| nobody tagged this, Spend no team tag claims | Unallocated cost | Framework Allocation; KPI on unallocated cost |
| More than usual, That day, Usually | Impact, Actual cost, Expected cost | Anomaly Management |
| Paid for and unused | Unused commitment | FOCUS `CommitmentDiscountStatus` Unused; KPI on commitment waste |
| Of what we paid for, used | Commitment utilization | KPI Commitment Utilization Score |
| Of what could be committed, is | Commitment coverage | KPI on compute spend covered by commitment discounts |
| SavingsPlan and other raw codes | Savings Plans, Reserved Instances | FOCUS commitment discount |
| Waste group | Optimize | Optimize Usage and Cost |
| RIGHTSIZE_INSTANCE and other enum codes | Rightsizing, Idle resource, and so on | Usage Optimization |
| Containers, cost and waste | Kubernetes cost, Kubernetes rightsizing | Kubernetes cost allocation |
| Bin packing | Cluster efficiency | Common usage |
| Governance | Govern | Governance, Policy and Risk |
| Query findings, surfaces, ad hoc | Query Cost: Findings, Sources, Ad hoc | Governance; Data Cloud Platforms |
| Enforcement | Policies | Governance, Policy and Risk |
| Export | Exports, under Report | Reporting and Analytics |
| Not yet collected by cost_focus | Not yet collected by the cost and usage collector | No raw identifiers on screen |
| Absent | Effective savings rate | KPI library, baseline named on screen |
| Absent | Forecast | Forecasting |

A full table, one row per label in every screen, is TASK-P8-004's first output, reviewed
before any label changes.

### 5.4 Charts are drawn by Meter, from primitives

ADR-0019 chose headless behaviour libraries and Meter's own visual layer, and rejected
component kits whose look is theirs. The owner chose on 2026-10-05 to go one step further
and keep charts hand built in SVG, as today, with no chart dependency, so every mark is
Meter's own. The options considered are kept below for the record.

| Option | Licence | Fit with ADR-0019 | Note |
| --- | --- | --- | --- |
| visx | MIT | Primitives, no look of its own | Recommended. Tree shaken per package |
| Hand built SVG, as today | none | Exact | Every new chart type is work from first principles |
| Recharts | MIT | Opinionated components | Theming fights its defaults |
| Apache ECharts | Apache 2.0 | A complete look of its own | Largest bundle; canvas by default |

The chart set, every one with a table alternative a keyboard and a screen reader can use:
stacked area over time with a forecast band and a budget pace line, stacked bar by
dimension, ranked bar with a table, KPI tile with a period delta and a sparkline, treemap,
and heatmap. Measured, modelled and forecast keep their distinct marks: solid, hatched and
dashed. No chart dependency is added.

### 5.5 Exports are made by the server, behind the same guard

An export is the view's own rows, written by the server, never assembled in the browser.

1. **One enforcement point.** Every route a screen reads accepts `format=xlsx` or
   `format=csv` and answers through one export responder, after the same scope dependency
   and repository guard as the screen. A test holds that the rows of every export equal the
   rows of the screen under the same scope, and another that an export for a narrower scope
   never holds a row outside it.
2. **The workbook says what it is.** A Data sheet with FOCUS display names as headers and
   typed numbers, and an About this export sheet: scope and coverage, filters, grouping,
   period, currency, cost metric, `as_of`, `collected_at`, every typed failure in the view,
   when it was made and by whom. A failed account is a row there, never a zero in the data.
3. **Hostile cells are neutralised.** Tag values come from member accounts. A cell that
   starts with `=`, `+`, `-`, `@`, a tab or a carriage return is written as text, and the
   writer's string-to-formula and string-to-URL conversions are off.
4. **Limits are explicit.** A workbook stops at a configured row limit below Excel's sheet
   maximum and says so in its About sheet, and offers CSV for the full set.
5. **Every export is recorded.** One `report_run` row per file: who, what view, which scope,
   how many rows, how many bytes.

The writer is XlsxWriter, BSD 2 Clause, chosen over openpyxl for its constant memory mode
and over the browser libraries for the reasons in item 1 and the SheetJS npm advisories.
It is admitted through `make dep-check`. FEAT-045, showback export, is delivered by this
mechanism rather than built again.

### 5.6 A saved view is configuration, never data

A saved view stores a screen and its query string, and nothing it rendered. Opening one
renders it in the opener's scope, so sharing a view shares a question, not an answer. This
needs filters to live in the query string, as `docs/13-UI-ARCHITECTURE.md` already says
they do and the code does not, ISS-235, which TASK-P8-003 closes.

### 5.7 A schedule renders for its recipient

A schedule names a saved view, a format, a cadence and recipients who are Meter
principals. Each run renders once per recipient, in that recipient's scope, so a schedule
cannot carry a row to someone who could not open it. Files are stored in the hub's data
bucket under the tenant's prefix and fetched through a Meter route that checks scope again.
Delivery is a port with a fake until OPEN-11 names email or Slack, and a run with no sender
is stored and listed as rendered and not sent, the shape digests already use.

### 5.8 Persona dashboards

The Overview opens on the dashboard for the reader's persona and offers the other two.

| Persona | KPIs |
| --- | --- |
| Executive | Effective cost to date, forecast to month end, budget consumed against time elapsed, effective savings rate, percentage of cost allocated, top movers |
| FinOps practitioner | Commitment coverage, utilization and unused commitment, unallocated cost, open anomalies, recommendation backlog value, realized savings |
| Engineering lead | Daily effective cost by service for the team's scope, anomalies in scope, rightsizing in scope, query cost of the team's dashboards |

Every KPI names its formula and baseline where it is shown. Effective savings rate is the
KPI library's: one minus actual spend with discounts over equivalent spend at the on demand
rate, and the tile says on demand equivalent, because FOCUS, Azure and Cloudability each use
a different baseline. A KPI the data cannot support yet says so, never shows zero.

## 6. Data model

Three tables, every invariant a constraint, constraint 11. Each holds a person's
identifier and is confined to that person or shared by configuration under ADR-0029.

| Table | Holds | Key constraints |
| --- | --- | --- |
| `saved_view` | tenant, owner, name, screen path, query object, visibility PRIVATE or SHARED, created and updated times | screen path is one the navigation knows; name not blank; query is a JSON object |
| `report_schedule` | tenant, owner, saved view, format XLSX or CSV, cadence DAILY, WEEKLY, MONTHLY or MONTH_CLOSE, recipient principals, enabled, next run | a recipient list is a non empty array; the view exists and is visible to the owner |
| `report_run` | tenant, schedule or none for an ad hoc export, rendered for, view snapshot, format, rows, bytes, storage key, status, typed failure cause, `as_of`, `collected_at`, started and finished times | a failure carries one of the seven causes; a success carries a storage key or was streamed |

Retention of `report_run` rows and stored files is a decision for a person, OPEN-15, the
same kind of question OPEN-14 asks for the assistant.

## 7. Interface

- `format=xlsx` and `format=csv` on every list route a screen reads, through one responder.
- `GET`, `POST`, `PATCH` and `DELETE /reports/views` for saved views; `GET /reports/views/{id}`.
- `GET`, `POST`, `PATCH` and `DELETE /reports/schedules`; `GET /reports/runs`;
  `GET /reports/runs/{id}/file`, scope checked again.
- `GET /cost/explore`, the Cost Explorer's query: two group bys over FOCUS dimensions and
  tags from an allow list, filters, granularity, period, and comparison to the previous period.
- `GET /cost/forecast`: month end and three months ahead, carrying forecast provenance under
  ADR-0015's conditions, with a band and the method named.

## 8. Testing

- Export parity and scope: rows equal the screen's; a narrower scope never sees more.
- Hostile cells: every leading character in section 5.5 item 3 comes back as text.
- Saved views and schedules render in the reader's scope, asserted with two principals.
- Redirects: every path the navigation had before P8 resolves.
- Accessibility: axe on every screen in both themes, with transparency reduced, and a
  contrast test over the theme tokens.
- Charts: every chart's table alternative holds the same values the marks draw.
- Journeys: open the Overview, change persona, open Cost Explorer, group by two dimensions,
  export to Excel, save the view, schedule it.

## 9. Risks

- **Glass reads as decoration over data.** Panels stay above the opacities in 5.1, and the
  densest screens use the most opaque panel tier.
- **Backdrop blur costs frames on weak machines.** Blur sits on panels, never on rows or
  cells, and reduced transparency turns it off.
- **A schedule becomes a scope leak.** Rendering per recipient and fetching through a
  scope checked route is the whole defence, and both are tested.
- **Renaming breaks muscle memory.** Redirects keep every path, and tooltips keep the old
  and provider words searchable.

## 10. Open questions

- OPEN-11, where scheduled reports and digests are delivered.
- OPEN-15, how long report runs and their files are kept.
- Settled at approval on 2026-10-05: charts stay hand built SVG, the type family is Geist,
  and FinOps Score sits under Plan.

## 11. Features delivered

FEAT-063 two theme design system; FEAT-064 Framework navigation and FOCUS names; FEAT-065
Cost Explorer; FEAT-066 spend forecast; FEAT-067 Excel and CSV export, delivering FEAT-045;
FEAT-068 saved views and report library; FEAT-069 scheduled reports; FEAT-070 persona
dashboards.

## 12. Exit criteria

1. Every screen in both themes, axe clean, with transparency reduced and without blur.
2. Every label in TASK-P8-004's table changed, and no raw identifier on any screen.
3. An Excel export of every exportable view, rows equal to the screen, with its About sheet.
4. A saved view shared between two principals renders in each one's scope.
5. A schedule rendered per recipient and stored, listed as rendered and not sent until OPEN-11.
6. Three persona dashboards, every figure linked to its owning screen.
7. Every path from before P8 resolving.
