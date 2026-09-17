# ADR-0015: Deterministic forecasting is permitted where a language model number is not

Date: 2026-08-23
Status: Accepted

## Context

ADR-0007 states that the language model never computes a number. A competitive
review on 2026-08-23 found a product using an LSTM to forecast replica demand,
projecting a 7 day horizon from 24 input steps, and using the forecast to size
horizontal scaling.

That raised a fair question. If a model may not produce a number, may a trained
forecaster produce one? Treating both as "AI" and banning both would be lazy,
and so would allowing both because the first one worked.

## Decision

**A trained forecaster may produce a number. A language model may not.** They
are not the same kind of thing, and the difference is not the technology, it is
what can be said about the output afterwards.

| Property | Forecaster | Language model |
| --- | --- | --- |
| Reproducible from the same inputs | Yes | No |
| Backtestable against held out data | Yes | No |
| Has a stated error bound | Yes | No |
| Can be shown to be wrong, and by how much | Yes | Not meaningfully |
| Fails visibly when inputs drift | Yes, accuracy degrades measurably | No, it stays fluent |

The last row is the one that matters. A forecaster that becomes wrong shows it
in the backtest. A language model that becomes wrong produces the same
confident prose it always did.

**Four conditions. All four, or the forecast does not ship.**

1. **Backtested on held out data**, with the accuracy published in the product
   next to the number, exactly as FEAT-018 does for the modelled query cost.
2. **An error bound on every forecast.** A recommendation reads "6 to 9
   replicas, 80 percent interval", never "7 replicas".
3. **A deterministic fallback.** If the forecast is unavailable or its recent
   accuracy falls below a stated floor, the system falls back to the p95 rule
   and says so on the screen.
4. **Labelled `forecast`**, a third value alongside `measured` and `modelled`,
   so a reader can tell at a glance which kind of number they are looking at.

## Consequences

Positive.

- Predictive sizing becomes possible where the p95 rule is genuinely weak,
  which is workloads with a strong daily or weekly shape. A p95 over 30 days
  sizes for the peak of the worst day, every day.
- The four conditions are the same discipline already applied to the modelled
  query cost, so this introduces a precedent rather than an exception.

Negative.

- A trained model is a new artefact class: it needs versioning, retraining, a
  drift signal and a rollback. That is real operational cost, and it lands in
  P6 where there is already an in cluster agent to look after.
- Condition 1 means a forecast cannot ship until there is enough history to
  backtest it. At least one full seasonal cycle, so realistically 8 weeks of
  cluster telemetry.
- Condition 2 means the interface must render an interval, and an interval is
  harder to act on than a single number. That is honest rather than convenient.

## Alternatives rejected

**Ban all learned models, for consistency with ADR-0007.** Rejected. It is
consistency of vocabulary rather than of reasoning. ADR-0007 exists because a
language model cannot show its arithmetic, not because statistics are
suspicious.

**Allow the forecast with no error bound, as the reviewed product appears to
do.** Rejected. A point forecast presented without an interval is a modelled
number wearing the clothes of a measured one, which is the specific dishonesty
this project spends most of its effort avoiding.

**Use the forecast to act automatically.** Rejected for now. A forecast informs
a recommendation, and the recommendation goes through the same approval path as
any other. Revisit once the published backtest accuracy justifies it.
