# FEAT-066: Spend forecast, month end and three months, with a published backtest

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Planned |
| Specification | [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 7 |
| Tasks | TASK-P8-008 |

## What it does

`GET /cost/forecast` forecasts spend to month end and three months ahead, with a band and the
method named. It is the first producer of forecast provenance in Meter.

## Why it exists

No screen shows a forecast today. Forecasting is a FinOps Framework capability, and the
approved navigation places Forecasts in Plan beside Budgets. The executive dashboard's forecast
to month end and the forecast band on the stacked area chart both depend on it.

## What is already known

It meets the four conditions ADR-0015 sets before any figure carries forecast provenance, and
where one cannot be met, no figure is shown and the reason is. Its accuracy is measured by
backtest over held out months and published beside the figure. It is drawn dashed with its
band, never as measured, because measured, modelled and forecast keep distinct marks: solid,
hatched and dashed.

## Status of this document

Planned. The feature is specified in the
[P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 7, and planned as
TASK-P8-008 in the [P8 plan](../plans/P8-implementation-plan.md), both pending the owner's
approval. The sections a built feature carries, how it works, its failure behaviour, its
security considerations, its interface and what it does not do, are written when it is built.
Recording only what is decided is deliberate: a document that invents detail ahead of the
build is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P8.
