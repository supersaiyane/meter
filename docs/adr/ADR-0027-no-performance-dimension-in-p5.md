# ADR-0027: No performance dimension in P5, and what to build instead

Date: 2026-09-28
Status: Accepted

## Context

The competitive review of 2026-09-26 names one large thing worth arguing about before
P5 starts: Meter has no performance dimension. Every judgement it makes runs in one
direction, that something is bigger than it needs to be. FEAT-058 records the gap and
deliberately schedules nothing, so that the argument has somewhere to happen.

The complaint the review actually makes is worth quoting exactly, because the rest of
this decision turns on reading it precisely: "a tool that only ever recommends making
things smaller is one engineers learn to discount."

That is a statement about trust, not about capability.

## Decision

**No performance dimension in P5.** Three reasons, all specific to this product rather
than general objections, and one thing to build instead that addresses the complaint
directly.

### It inverts the risk model the product is built on

Today a wrong Meter answer costs money, and the architecture is shaped around that
being the worst case. Remediation is read only in v1, constraint 6. Irreversible
findings are labelled permanent and separated from the no regret group. The sizing rule
uses p99 CPU and an observed memory peak specifically to avoid a harmful shrink.

A performance finding's wrong answer is an outage, or is money spent silently on
capacity nothing needed. Nothing in the product is built for a recommendation whose
failure mode is an incident, and retrofitting that is not a feature, it is a different
posture.

### The product cannot verify a performance finding, and verification is its whole claim

This is the argument that decided it.

`docs/00-GOAL.md` names realized savings as the north star: not identified, not
potential. ISS-029 existed because identified savings is a vanity metric every tool
inflates, and FEAT-029 answers it by judging a change sixty days later against the
bill. That measurement is the reason a reader should believe anything this product
says.

A performance recommendation cannot be judged that way. Its success is an outage that
did not happen, which is unfalsifiable in exactly the shape ISS-029 objected to. We
would be adding a class of finding whose value can only be asserted, next to a class
whose value is measured, and the first would quietly borrow the credibility of the
second.

Turbonomic can make this claim because it acts: it scales the thing and observes the
response time. Meter does not act, by decision, so it would be left asserting.

### There is no service level input and no path to one

Turbonomic's SLO Guard scales against a user defined response time target using Instana
metrics. Meter reads CloudWatch, AWS Config and Cost Explorer: CPU, memory where an
agent publishes it, and ECS task utilization. It has no response times, no error rates
and no queue depths.

"Starved" inferred from resource saturation alone is a proxy for the thing, and
publishing it would mean asserting an opinion about somebody else's latency budget.
FEAT-058 already names this as one of the three undecided questions. It is not
undecided because nobody has thought about it. It is undecided because the input does
not exist.

## What to build instead

The complaint is that a tool which only recommends shrinking is discounted. The remedy
for that is not to start recommending growth. It is to show that the tool looked and
decided not to.

**Meter already computes exactly this and throws it away.** `finops_query/waste.py` has
`_refused`, which returns a judgement carrying a reason, and the reasons are good:

- `p99 of 87.3 percent leaves no room to shrink`
- `94 percent ceiling, so this is memory bound and a CPU rule must not shrink it`
- `no utilization was observed, which is not the same as none used`
- `No agent publishes memory here, so whether it is memory bound is not known`

`finops_ingest/collectors/waste_compute.py` ends `_judge` with
`return smaller if smaller.is_worth_acting_on else None`. The reasoning is computed and
discarded on that line.

Surfacing it is FEAT-062, and it answers the complaint at a fraction of the cost:

- An engineer sees that their service was examined and found correctly sized, with the
  measurement that says so. That is the thing that makes a tool feel like it is on your
  side, and it is what "we have no performance dimension" actually costs day to day.
- It needs no new data source, no headroom policy and no service level input, so none
  of FEAT-058's three open questions has to be answered first.
- A wrong answer costs nothing. The worst case is that we declined to recommend
  something we could have recommended, which is the direction this product already errs
  in deliberately.
- **ADR-0016 survives untouched.** Severity comes from money, a refusal has no money,
  and therefore a refusal has no severity and is not ranked. It is a different surface
  answering a different question, not a finding competing in the same list. That is the
  cleanest part of this: the awkward question FEAT-058 raised about severity simply
  does not arise.
- It is verifiable in the only sense available: the refusal names the measurement it
  rests on, and a reader can disagree with it. Nothing has to be asserted.

## Consequences

FEAT-058 stays in the register, stays Planned, and stays unscheduled. It is not
rejected and this decision is not permanent. It is blocked on an input rather than on
an opinion, which is a better place for it to sit than a backlog.

**The argument reopens when Meter can read a service level objective.** That is the
precondition, and it is a data question: an APM signal, an SLO recorded against a
service, or a latency series the product can read the way it reads CPU. Until one
exists, a performance dimension would be this product guessing, and guessing is the
thing it is built not to do.

FEAT-062 is registered as the work this decision produces, so the argument leaves
something behind rather than only a refusal to build.

The gap remains real and remains recorded. Anyone comparing Meter to Turbonomic on a
feature list will find it, and the honest answer is the one above: we do not have the
input that would let us say it truthfully, and we would rather say nothing than assert
it.

## Alternatives considered

**Build it with a headroom rule in configuration, per ADR-0012.** This solves the wrong
third of the problem. Cadence is a policy this deployment owns, so making it data was
right. A latency budget is a policy the workload's owner owns, and moving it into
Meter's configuration makes it our opinion in their settings file. It would look like
ADR-0012 and be the opposite of it.

**Emit performance findings with no severity, outside the ranking.** Closer, and this
is what FEAT-062 does for refusals. The difference is that a refusal is a statement
about a measurement we took, and an underprovisioning finding is a prediction about a
service level we cannot see. The first is checkable and the second is not.
