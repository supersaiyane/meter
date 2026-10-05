# ADR-0030: Navigation follows the FinOps Framework

Date: 2026-10-05
Status: Accepted
Supersedes: ADR-0020
Relates to: P8 spec section 5.2, FEAT-064, TASK-P8-002

## Context

ADR-0020 fixed seven groups named for the questions a reader asks, Home, Cost, Waste,
Governance, Inventory, Platform and Assistant, and said that renaming one takes an ADR. On
2026-10-05 the owner asked for the product to use the standard nomenclature of a FinOps tool,
and approved a navigation whose groups answer to the domains of the 2026 FinOps Framework,
P8 spec section 5.2. Three screens had no home in the approved table, and the owner placed
them the same day.

## Decision

**Nine groups, each named for the Framework domain it answers to.**
`finops-web/src/shell/sections.ts` carries them, with the domain in a comment beside each
group, and it stays the one list of screen names.

| Group | Screens | Framework domain |
| --- | --- | --- |
| Overview | Overview | Understand Usage and Cost: Reporting and Analytics |
| Analyze | Cost Explorer, Allocation and Showback, Anomalies, Kubernetes cost, Kubernetes rightsizing, Clusters | Understand Usage and Cost: Reporting and Analytics, Allocation, Anomaly Management |
| Plan | Budgets, Forecasts, FinOps Score, Unit Economics | Quantify Business Value |
| Optimize | Recommendations, Commitments, Realized Savings | Optimize Usage and Cost |
| Govern | Query Cost, Quotas, Policies | Manage the FinOps Practice: Governance, Policy and Risk |
| Inventory | Accounts, Resources, Topology | None; the ITAM persona and Data Ingestion are nearest |
| Report | Report Library, Scheduled, Exports | Understand Usage and Cost: Reporting and Analytics |
| Assist | Ask Meter, Digests | AI for FinOps |
| Platform | Data Freshness, Ingestion, Meter Cost, Flags | Manage the FinOps Practice: Automation, Tools and Services |

The owner's three placements: the three container screens stay separate under Analyze,
Enforcement becomes Policies, and Flags stays under Platform as arriving. The menu takes the
approved table's screen names from this change; names inside the screens wait for the label
table of TASK-P8-004, which the owner approves first. Forecasts, Report Library and Scheduled
arrive with P8, and Unit Economics says that no sub project is planned for it rather than
naming one that does not exist.

**Screens that merged are tabs.** Organization is a tab of Accounts, Geography of Topology,
and the three query cost screens of Query Cost. A tab is a link with its own address, so it
can be bookmarked and sent.

**Every old address still lands.** `REDIRECTS` in `sections.ts` maps each path the navigation
had before this decision to its new home, two detail families follow by prefix, and the
query string and fragment travel with the redirect. `sections.test.ts` names every path from
before this decision and fails if one stops resolving.

## Consequences

- A link stored before the change keeps working: a bookmark, a digest link, a pull request
  body, and an assistant answer that names an old screen, whose link `Exchange.tsx` follows
  through the same table.
- The assistant's tools name the new screens, `finops_api/tools.py`.
- A new group, or a renamed one, still takes an ADR. A new screen goes into the group whose
  Framework domain it answers to.

## Alternatives considered

- **Keep the seven groups and rename only the screens inside them.** Rejected: the owner asked
  for the standard nomenclature, and the group names are the first words a reader sees.
- **One Kubernetes screen with three tabs.** Offered on 2026-10-05 and declined by the owner,
  so each container screen keeps its own address.
