# FEAT-058: A performance dimension, underprovisioned as well as oversized

| Field | Value |
| --- | --- |
| Sub project | P5 |
| Status | Planned |
| Specification | None. [competitive review](../11-COMPETITIVE-REVIEW.md) 2026-09-26, sized Large |
| Tasks | None. Deliberately unscheduled, see below |
| Source | Adopted in principle from the IBM Turbonomic review on 2026-09-26 |

## What it does

Nothing yet. It would let the product say a workload is starved, not only that it is
oversized.

## Why it exists

It is the largest gap in the product and the one that most damages trust with engineers.
Every judgement Meter makes runs in one direction: this is bigger than it needs to be. An
engineer whose service is being throttled reads a tool that only ever asks them to shrink
things as a tool that is not on their side, and they are right.

**It is unscheduled on purpose, and that is the substance of this document.** It needs a
headroom rule and a service level input, and it changes what the existing waste collectors
mean. A collector that currently answers "is this oversized" would have to answer "is this
correctly sized", which is a different question with a different failure mode: today a wrong
answer costs money, and afterwards a wrong answer costs an outage.

Three things would have to be decided before a task could honestly be written.

1. **Where the headroom rule comes from.** A number in code is a policy decision in the wrong
   layer, and cadence already taught us that lesson: ADR-0012 made collection intervals data
   because a number in code is a number nobody can argue with.
2. **What the service level input is.** Without one, "starved" is our opinion about somebody
   else's latency budget.
3. **Whether ADR-0016 survives.** Severity comes from money. A performance finding has no
   money figure, or has one only as the cost of an outage that has not happened, so either
   severity gains a second source or performance findings sit outside the ranking that orders
   every other finding.

The competitive review records this as the thing worth arguing about before P5 starts. This
document exists so that the argument has somewhere to happen, and so that the gap is not
invisible in the register.
