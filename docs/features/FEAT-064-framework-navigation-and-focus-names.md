# FEAT-064: Navigation by the FinOps Framework and FOCUS names on every screen

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Delivered |
| Specification | [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), sections 5.2 and 5.3 |
| Tasks | TASK-P8-002 and TASK-P8-004 |

## What it does

Arranges the screens in the groups the owner approved, each answering to a FinOps Framework
domain: Overview, Analyze, Plan, Optimize, Govern, Inventory, Report, Assist and Platform. A
cost column takes its FOCUS display name, a screen or a KPI takes its Framework name, and the
provider's own word, such as Amortized, Unblended or Savings Plan, stays in the column's
tooltip. Every old path redirects to its new home, so a bookmark, a digest link or a link in a
pull request body still lands.

## Why it exists

The owner said on 2026-10-05 that the screens do not use standard FinOps nomenclature, and an
audit of every screen the same day confirmed it. The labels paraphrase rather than name: FOCUS
`EffectiveCost` reads as "Amortized" or "Total spend", commitment utilization reads as "Of what
we paid for, used", and the words showback, chargeback, coverage and effective savings rate
appear nowhere. Practitioners search for both the standard term and the provider's, which is
why the provider's word stays one hover away.

## What is already known

FinOps Score moves into Plan, beside the budgets it is read with, because the Framework places
KPIs and Benchmarking there, and Unit Economics is listed as arriving, never as built. Screens
that merge become tabs: Organization under Accounts, Geography under Topology, and the three
query cost screens under Query Cost. ADR-0020 fixed seven groups and said renaming one takes an
ADR, so TASK-P8-002 wrote ADR-0030, which supersedes it. The full label table, one row per label
on every screen, is TASK-P8-004's first output, approved by the owner before any label changes.
On 2026-10-05 the owner placed the three screens the spec named no home for: the three container
screens stay separate under Analyze, Enforcement becomes Policies, and Flags stays under Platform
as arriving.

## How it works

`finops-web/src/shell/sections.ts` is the one list: nine groups, each with its Framework domain
in a comment, the screens in each, `TABS` for the screens that merged into another, and
`REDIRECTS` for every path that left. `App.tsx` routes the new paths, and any other address goes
through `redirectFor`, which sends a moved path to its new home with its query and fragment,
follows the two detail families by prefix, and otherwise shows the page that says the screen is
not built or that no screen answers. The shell draws a merged screen's views as links under its
heading, `ScreenTabs`, with the open one marked by `aria-current`.

The words on every screen follow the label table the owner approved on 2026-10-05,
`docs/specs/2026-10-05-p8-label-table.md`. A cost column takes its FOCUS display name, a
screen or a KPI its Framework name, and every code the API sends reaches the screen through
`finops-web/src/components/displayNames.ts`. `DataTable` puts the provider's own word in each
cost column's tooltip from `COST_COLUMN_TERMS`, keyed by the heading, so a table cannot forget
it. A test renders every built screen and tab from its fixtures and fails on a raw code or a
collector name in the text.

## Failure behaviour

An address that never existed is redirected nowhere; it gets the page that says no screen
answers it. A code the display names do not know is shown in words, never raw and never
hidden, because hiding it would hide the drift. A stored assistant answer that names a screen which moved keeps its link, because
`Exchange.tsx` follows the same table, and an answer naming anything else gets no link at all.

## Security considerations

The redirects are an exact list and two fixed prefixes inside the application, so no address can
be redirected off the site. A refusal's screen becomes a link only after an exact match against
the navigation or the redirect table.

## Interface

`GROUPS`, `TABS`, `REDIRECTS`, `UNPLANNED`, `redirectFor`, `tabsFor`, `screenTitleFor` and
`activeGroupFor` in `sections.ts`, and the `ScreenTabs` component.

## Not doing

It does not merge the three container screens, which keep their own addresses by the owner's
choice. It does not show an effective savings rate: that is a new figure the API does not
return, and P8 rule 1 says a screen asks for a route rather than deriving one. It does not
translate a Meter setting an operator must type, or a register reference such as OPEN-10.

## Status of this document

Delivered. TASK-P8-002 built the navigation and TASK-P8-004 the names, both on 2026-10-05.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P8.
