# Meter

A production grade FinOps platform for AWS, built so that GCP, Azure and PCF
can be added later as connectors rather than rewrites.

Meter answers four questions for an entire AWS Organization:

1. What are we spending, on which resource, and why did it change?
2. What are we wasting, and what is the defensible right size?
3. What is about to hurt us, in quota headroom and in runaway query cost?
4. What does everything look like, and how is it connected?

## Why this exists

The trigger was a single observability failure mode. A set of Grafana
dashboards pointed at CloudWatch Logs Insights, left on a one second auto
refresh over a seven day window, produced a 100,000 USD bill in one week.
Nothing detected it, nothing prevented it, and nobody owned it.

Meter treats that class of problem as a first class product feature rather
than an afterthought. See `docs/01-ROADMAP.md`, sub project P2.

## Documentation map

| Document | Purpose |
| --- | --- |
| `docs/00-GOAL.md` | Goal, success criteria, non goals, north star metric |
| `docs/01-ROADMAP.md` | The eight sub projects, build order, current status |
| `docs/02-ARCHITECTURE.md` | Cross cutting architecture, ports, canonical schema |
| `docs/adr/` | Architecture decision records, one per significant choice |
| `docs/specs/` | Approved design specs, one per sub project |
| `docs/plans/` | Implementation plans and task docs for Claude Code |
| `init_docs/project_map.md` | Module level map, kept current |
| `init_docs/checkpoint.md` | Session continuity log with resume vectors |
| `context_index.md` | Function level index, name to file and line |
| `tasks/STATUS.md` | What is done, in progress, and remaining |
| `tasks/ISSUES.md` | Issue and open question tracker with fixed status |
| `tasks/lessons.md` | Corrections captured so they are not repeated |

## Current state

Design phase. No application code has been written yet.
See `tasks/STATUS.md` for the authoritative position.

## House rules

Project specific rules for contributors and for Claude Code live in
`CLAUDE.md` at the repository root. Read it before making any change.
