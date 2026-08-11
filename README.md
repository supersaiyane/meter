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

## Start here

**[INDEX.md](INDEX.md) is the master index.** Every feature, decision, change,
issue and open question is listed there with a pointer to the document holding
the detail. If something is not in the index, it does not exist as far as the
project is concerned.

## Documentation map

| Document | Purpose |
| --- | --- |
| `INDEX.md` | Master index. Features, ADRs, changes, issues, open questions |
| `docs/00-GOAL.md` | Goal, success criteria, non goals, north star metric |
| `docs/01-ROADMAP.md` | The eight sub projects, build order, current status |
| `docs/02-ARCHITECTURE.md` | Cross cutting architecture, ports, canonical schema |
| `docs/adr/` | Architecture decision records, one per significant choice |
| `docs/specs/` | Approved design specs, one per sub project |
| `docs/plans/` | Implementation plans and task docs for Claude Code |
| `project_map.md` | Module level map, kept current |
| `docs/checkpoint.md` | Session continuity log with resume vectors |
| `context_index.md` | Function level index, name to file and line |
| `tasks/STATUS.md` | What is done, in progress, and remaining |
| `tasks/ISSUES.md` | Issue and open question tracker with fixed status |
| `tasks/lessons.md` | Corrections captured so they are not repeated |
| `docs/03-CHANGE-CONTROL.md` | Where each kind of change is recorded |
| `docs/04-DEPLOYMENT.md` | GitLab to ECR to Terraform to ECS |
| `docs/templates/` | Templates for specs, tasks, ADRs, changes, issues |

## Current state

Design phase. The documentation spine, the build layer and the deployment
pipeline exist. No application code has been written yet.
See `tasks/STATUS.md` for the authoritative position.

## Quick start

```bash
make help     # every available target
make setup    # virtualenv plus frontend dependencies
make up       # PostgreSQL, LocalStack, API, worker, web
make verify   # what CI runs on a merge request
```

## House rules

Project specific rules for contributors and for Claude Code live in
`CLAUDE.md` at the repository root. Read it before making any change.
