# FEAT-048: Predictive replica forecasting, under the four ADR-0015 conditions

| Field | Value |
| --- | --- |
| Sub project | P6 |
| Status | Planned |
| Specification | Not written. This document expands when P6 is specified |
| Tasks | Not planned |
| Refresh cadence | 24 hours, 7 day horizon |
| Source | Adopted from a competitive review on 2026-08-23, over an objection |

## What it does

Forecasts replica demand over a 7 day horizon and sizes horizontal scaling from the forecast rather than from a historical peak.

## Why it exists

A p95 over 30 days sizes every day for the peak of the worst day. For a workload with a strong daily or weekly shape, that is systematically wrong and expensive. Adopted on the project owner's decision after I argued that a trained model weakens a product whose credibility rests on reproducible numbers.

## What is already known

**The objection became ADR-0015**, which draws the line properly. A forecaster may produce a number because it is reproducible, backtestable, has a stated error bound, and fails visibly when its inputs drift. A language model has none of those properties, so ADR-0007 is unchanged.

Four conditions, all four or it does not ship. Backtest accuracy published in the product next to the number. An error bound on every forecast, so a recommendation reads "6 to 9 replicas, 80 percent interval" and never "7 replicas". A deterministic fallback to the p95 rule when the forecast is unavailable or its recent accuracy falls below a floor, shown on the screen. And a third provenance label, `forecast`, alongside `measured` and `modelled`.

It cannot ship before there is a full seasonal cycle of telemetry to backtest against, realistically 8 weeks.

## Status of this document

Planned. The remaining sections are written when P6 is specified. Recording
only what is decided is deliberate: a document that invents detail ahead of the
decision is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P6, and
[docs/11-COMPETITIVE-REVIEW.md](../11-COMPETITIVE-REVIEW.md).
