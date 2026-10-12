# FEAT-085: The AI spend screen: cost per token, per request and per feature

| Field | Value |
| --- | --- |
| Sub project | P13 |
| Status | Specified |
| Specification | [P13 spec](../specs/2026-10-12-p13-finops-for-ai-design.md), sections 5.7 and 8 |
| Tasks | TASK-P13-007 and TASK-P13-008 |
| Decisions | OPEN-31 to OPEN-34 |
| Issues addressed | None yet |
| Refresh cadence | Reads what the collectors wrote |

## What it does

One screen for AI spend: totals by provider, the breakdown by model, token type, feature and
caller, cost per thousand tokens and per request, and the GPU fleet with its utilization.

## Why it exists

Each source answers part of the question, and a person asking what the AI spend bought needs the
parts side by side, each figure saying how it was arrived at.

## How it works

The screen reads `GET /v1/ai/spend`, `GET /v1/ai/callers` and `GET /v1/ai/gpu`. Each figure carries
its basis, measured or modelled, and each panel its freshness from `as_of` and `collected_at`.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| The three AI endpoints | On load | As fresh as the collectors behind them |

## Measured or modelled

Cost per thousand tokens is measured where cost and tokens come from the same rows. Cost per
request is modelled where cost and requests come from different sources, and cost per caller from
invocation logs is modelled.

## Failure behaviour

A source that failed shows its typed cause and its last good figures with their age. Not published
and not connected read as words, never as zero.

## Security considerations

Every figure comes through the API's scope dependency and repository guard. A provider's cost is
visible at global scope only.

## Interface

The AI spend screen in the web interface, reached from the navigation.

## Not doing

Editing anything, setting a cap, or comparing models' quality.
