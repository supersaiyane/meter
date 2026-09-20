# FEAT-048: Predictive replica forecasting, under the four ADR-0015 conditions

| Field | Value |
| --- | --- |
| Sub project | P6 |
| Status | Specified |
| Specification | [P6 spec](../specs/2026-09-20-p6-containers-design.md), section 14 |
| Tasks | TASK-P6-012 in the first cut, the rest is second cut |
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

## How it works

Not yet designed in detail. **ADR-0015 governs it, and its four conditions are all
four or it does not ship.**

1. Backtested on held out data, with the accuracy published in the product next to
   the number.
2. An error bound on every forecast. A recommendation reads "6 to 9 replicas, 80
   percent interval", never "7 replicas".
3. A deterministic fallback to the p95 rule when the forecast is unavailable or its
   recent accuracy falls below a stated floor, and the screen says so.
4. Labelled `forecast`, a third value alongside `measured` and `modelled`.

## Failure behaviour

Condition 3 is the failure behaviour, and it is a condition rather than a
mitigation: a forecaster with no fallback is one that silently stops working.

## Security considerations

None beyond the read only posture. The risk here is epistemic rather than
technical: a number nobody can check, presented beside numbers that can be.

## Interface

Undecided, except that condition 4 requires the third provenance value to render
distinctly from the other two.

## Not doing

**Shipping without all four conditions.** ADR-0015 is explicit and this document
does not soften it.

Condition 4 is delivered early, in TASK-P6-012 of the **first** cut, because it
touches the `Figure` component every screen shares. Doing it inside the task that
first needs it would mean a forecasting feature also carrying a refactor of the
whole interface.
