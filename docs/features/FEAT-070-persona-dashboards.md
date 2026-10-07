# FEAT-070: Persona dashboards for executive, FinOps practitioner and engineering lead

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Delivered |
| Specification | [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 5.8 |
| Tasks | TASK-P8-012 |

## What it does

The Overview opens on one of three dashboards, the FinOps practitioner's, the Executive's or
the Engineering lead's, and a switch above them changes it. The reader's last choice is
remembered, and the FinOps practitioner's, the one drawn in
`docs/design/2026-10-05-overview-frosted-ledger.jpg`, opens for a reader who has chosen nothing.
Every KPI tile names its provenance, its formula and its baseline, and links to the screen that
owns the figure. Meter's own cost is a tile on all three.

| Dashboard | KPI tiles | Panels |
| --- | --- | --- |
| FinOps practitioner | Effective Cost, forecast to month end, budget consumed, effective savings rate, commitment coverage, cost allocated | Daily Effective Cost with the estate budget's daily pace, Effective Cost by service, anomalies, top recommendations, scheduled reports, showback by team |
| Executive | Effective Cost to date, forecast to month end, budget consumed against time elapsed, effective savings rate, cost allocated, top movers | Twelve months by service, this month against the forecast band, the top 10 accounts, savings available by category |
| Engineering lead | Meter's own cost | Daily Effective Cost by service, where this month went, rightsizing, anomalies, Top actions from FEAT-052, the query cost of the dashboards, top findings by dollar |

## Why it exists

The owner said on 2026-10-05 that there is no graphical dashboard, and chose persona dashboards
as one of the four reporting capabilities in the first build. Each persona reads different
figures: an executive reads effective cost against budget and forecast, a practitioner reads
commitment coverage and unallocated cost, and an engineering lead reads cost, anomalies and
rightsizing in the team's scope.

## What is already known

It is built from existing routes only and adds no new number. Effective savings rate is the KPI
library's, one minus actual spend with discounts over equivalent spend at the on demand rate,
and the tile says on demand equivalent, because FOCUS, Azure and Cloudability each use a
different baseline. A KPI the data cannot support yet says so and shows no figure, never zero.

## How it works

`HomeScreen` holds the switch and renders the chosen view, `OverviewFinOps`, `OverviewExecutive`
or `OverviewEngineering`, with the slots still arriving under it. The Overview owns no data.
Every figure comes through the hook of the screen that owns it: the Effective Cost tile reads
Cost Explorer's month to date view with the query Cost Explorer itself sends, so the two share
one cache entry and cannot disagree. The reads the views share are made once, in
`useOverviewFigures`.

The FinOps practitioner's Scheduled reports panel lists the reader's schedules through
`useSchedules`, the Scheduled screen's own hook, FEAT-069: three at most, a paused one first,
because a report that will not arrive is the one its reader most needs telling about, then the
next to run. A schedule holds no figure, so a chosen account does not narrow the read.

The arithmetic is a pure module, `overviewKpis.ts`, tested without drawing a screen.

- Effective savings rate is one minus FOCUS Effective Cost over FOCUS List Cost, month to date.
  List Cost is the on demand equivalent, the baseline the tile names.
- Budget consumed is the budget most at risk, its spend over its limit against the share of its
  period that has passed, and the tile says how many budgets it was chosen from. The daily
  chart's pace is the estate budget's, the one budget whose scope is every account.
- Cost allocated is Effective Cost carrying a team tag over all Effective Cost, and unallocated
  spend is a row of the showback table, never left out.
- Commitment coverage is the commitments screen's figure, with its utilization beside it.
- Recommendations and savings count only the open ones. One already accepted, rejected or done
  is not a saving still to be had, the rule Top actions and the recommendations screen keep.

`KpiTile` takes the state of its read. While loading, when the read failed, when the source was
never collected and when it is empty, the state replaces the figure. A KPI the data cannot
support takes a reason instead of a figure. The choice of dashboard is kept in the browser
under `meter.persona`, as the theme is.

## Failure behaviour

Each tile and each panel shows the state of its own read, so one failed route leaves the rest of
the dashboard standing. A failure names its typed cause and is never drawn as zero. The daily
chart says that no single budget covers every account only once the budgets were read: when
that read fails, the budget tile shows the failure and the chart says nothing about budgets.
With no List Cost in the bill, the effective savings rate says why it has no figure.

## Security considerations

Nothing new reaches the server. Every read is an existing route behind the scope dependency and
the repository guard, narrowed by the account picker, FEAT-075, and never widened by it. The
browser keeps only the name of the chosen dashboard.

## Interface

- The switch above the dashboards: FinOps practitioner, Executive, Engineering lead.
- `meter.persona` in the browser's local storage: `finops`, `executive` or `engineering`.
- No new route and no new field. The dashboards read `/api/v1/cost/explore`,
  `/api/v1/cost/forecast`, `/api/v1/cost/budgets`, `/api/v1/cost/allocation`,
  `/api/v1/cost/commitments`, `/api/v1/cost/anomalies`, `/api/v1/cost/by-account`,
  `/api/v1/waste/recommendations`, `/api/v1/query/findings`, `/api/v1/query/groups`,
  `/api/v1/query/instances` and `/api/v1/platform/cost`, each through its screen's hook.

## Not doing

- A forecast band on the daily chart. The drawing has one, but the forecast route's figures are
  a running total for the month, so a daily band would need a number the route does not
  produce. The forecast is the month end tile, and the Executive dashboard draws the month's
  running total against its band.
- A dashboard choice saved on the server. It lives in the browser, as the theme does.

## Status of this document

Written when TASK-P8-012 was delivered, 2026-10-06. Updated 2026-10-07 by TASK-P8-014: the
Scheduled reports panel lists schedules, where until then it still promised them for P8, and
`finops-web/e2e/overview.spec.ts` holds every panel and tile on all three dashboards to a link
to a screen on the rail, P8 spec section 12 item 6.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P8.
