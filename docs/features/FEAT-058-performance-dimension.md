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

## The argument, held on 2026-09-28

[ADR-0027](../adr/ADR-0027-no-performance-dimension-in-p5.md) is the record. The decision
is no performance dimension in P5, and the reason that settled it is not on the list of
three above.

**The product cannot verify a performance finding, and verification is its whole claim.**
Realized savings is the north star precisely because identified savings is a vanity metric,
which is what ISS-029 was about, and FEAT-041 judges a change against the bill sixty days
later. A performance recommendation's success is an outage that did not happen, which is
unfalsifiable in exactly the shape ISS-029 objected to. It would put a class of finding
that can only be asserted beside a class that is measured, and the first would borrow the
credibility of the second.

Turbonomic can make the claim because it acts and then observes. Meter does not act, by
decision, so it would be left asserting.

The third question above, the service level input, turns out to be the blocking one rather
than one of three. It is undecided because the input does not exist, not because nobody
has thought about it.

**This is deferred, not rejected, and it is blocked on an input rather than an opinion.**
The argument reopens when Meter can read a service level objective: an APM signal, an SLO
recorded against a service, or a latency series it can read the way it reads CPU.

**What the argument produced** is [FEAT-062](FEAT-062-refusal-evidence.md). The complaint
the review actually makes is about trust, and the remedy for a tool that only recommends
shrinking is not to recommend growth: it is to show that the tool looked. Meter already
computes that judgement and discards it on one line of `waste_compute.py`.
