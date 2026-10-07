# FEAT-066: Spend forecast, month end and three months, with a published backtest

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Delivered |
| Specification | [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 7 |
| Tasks | TASK-P8-008 |
| Screen | `/plan/forecasts` |

## What it does

`GET /cost/forecast` forecasts Effective Cost to month end and for each of the next three
calendar months, every figure a range at 80 percent with the method named and its accuracy,
measured by backtest, beside it. Where a month cannot be forecast honestly, it says why instead.
It is the first producer of forecast provenance in Meter, and the Forecasts screen under Plan is
the one screen that draws it.

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

## How it works

The owner chose how ADR-0015's conditions are met on 2026-10-05, each the recommended option.

| Choice | Chosen |
| --- | --- |
| Method | A weekday profile: each day ahead is the average of the same weekday over the eight weeks before the forecast is made |
| Band | 80 percent, the 10th to 90th percentile of the method's own misses on held out months |
| Gate | Withheld with fewer than 3 complete months to test on, or a median miss above 15 percent of what a month cost |
| Screen | The month end range beside its accuracy, a chart of the month with the band, the next three months, and the backtest month by month |

The arithmetic is `finops_query/forecast.py`, with no database and no clock. A month end
forecast is what is billed so far plus the profile's days to the end of the month. To test it,
each of up to 12 complete months before this one is forecast again from the same day of its own
month with only the data that existed then, and the signed misses set the band: it applies to
the whole month's estimate, so a method that runs low by a steady few percent has its band moved
up by that much rather than drawn around a number that is always short. Each month ahead is
tested the same way from the same distance. The central estimate never leaves the module; what
does is a low and a high.

The reads are `finops_api/db/repositories/forecast.py`, both derived from `scoped_select`: the
first billing month and the last billed day the scope holds, and the effective cost of each UTC
day between them, with a collected day that billed nothing as a zero. The route is
`finops_api/routes/forecast.py`. The screen is `finops-web/src/screens/ForecastScreen.tsx`, and
`forecastUnproduced.test.ts`, which had refused every screen a forecast since TASK-P6-012, now
names it as the one producer, so a second is a decision somebody has to make in that file.

The chart is cumulative: billed to date as a solid area, then the band, which opens from
nothing on the last billed day and widens to exactly the month end range. The backtest table
applies today's band to what was forecast for each held out month, and says whether that band
held the month that happened.

## Failure behaviour

- A tenant with no cost is answered 404, never a forecast of zero.
- Fewer than eight weeks of history before the forecast: withheld, there is no weekday profile.
- Fewer than 3 complete months to test on: withheld, with how many there are.
- A median miss above 15 percent: withheld, with the miss it measured.
- A month already billed in full: withheld, because its total is measured.
- A withheld forecast's backtest shows its misses and no ranges, so the figure it was not allowed
  to show does not come in by the side door.
- A month that cost nothing, or was forecast as nothing, is not counted as a test, because it has
  no share to miss by.

## Security considerations

Scope is enforced in both places, the request dependency and the repository guard, so a scope
narrowed to one account is forecast from that account's line items alone. The route takes no
parameters. It is read only, like every route in v1.

## Interface

`GET /api/v1/cost/forecast`. `ForecastOut` in `finops_api/schemas.py` carries `provenance`,
always `forecast`; the method and its one sentence; the interval and the gate's two limits; the
day billed through and what is billed to date; the month end and the three months ahead, each a
range or the reason with its median miss and the months it was tested on; the days of this
month, billed or banded; and the backtest.

## Not doing

- A forecast by service, account or tag. One total first, tested, then the parts.
- Forecasting any measure but Effective Cost.
- Acting on a forecast. It informs a reader and the budget screen; it changes nothing, as
  ADR-0015 rejected automatic action.
- The executive dashboard's use of it, which is TASK-P8-012.

## Status of this document

Delivered on 2026-10-05 by TASK-P8-008.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P8.
