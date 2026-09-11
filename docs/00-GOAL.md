# Goal

Last updated: 2026-08-23

## One sentence

Give an AWS Organization a single, trustworthy, account aware view of what it
spends, what it wastes, what it is about to break, and what it is running,
with enough evidence attached that an engineering team will actually act.

## The problem being solved

Three failures, observed in practice, that existing tooling handles badly.

1. **Cost is visible too late.** Cost Explorer shows yesterday at service
   granularity. By the time a spike is noticed, the money is spent. There is
   no owner attached and no explanation of the cause.
2. **Observability tooling silently bills like production workload.** Grafana
   dashboards pointed at CloudWatch Logs Insights, set to a one second auto
   refresh over a seven day window, produced 100,000 USD in a single week.
   No preventive control existed, no alert fired, and no person owned it.
3. **Rightsizing advice is not trusted.** Recommendations arrive without the
   evidence behind them, without an owner, and without a workflow, so they are
   ignored. Nobody tracks whether a recommendation ever produced real savings.

## Success criteria

Meter is successful when all of the following are true.

| # | Criterion | How it is measured |
| --- | --- | --- |
| 1 | Every account in the Organization is onboarded automatically | New account vended into an OU appears in Meter within one hour with no human step |
| 2 | Cost is attributable to a resource and an owner | Percentage of amortized cost allocated to a team, target above 95 percent, with the unallocated bucket visible and shrinking |
| 3 | Runaway query cost is prevented, not reported | Time from a policy violating dashboard being saved to it being blocked or alerted, target under 15 minutes |
| 4 | Recommendations are defensible | Every recommendation carries its evidence window, statistic used, and confidence, and is marked measured or modelled |
| 5 | Recommendations are actioned | Percentage of recommendations that reach a terminal state, accepted or rejected with reason, target above 80 percent within 30 days |
| 6 | The cost model is honest | Modelled cost back tested against the actual bill, with the accuracy percentage published in the product |
| 7 | The platform is accountable for itself | Meter's own AWS cost is shown on its front page, broken down by module |

## North star metric

**Realized savings.** Not identified savings, not potential savings. The
delta that actually appeared in the bill 60 days after a recommendation was
marked done, verified against CUR.

Identified savings is a vanity number. Every FinOps tool inflates it. Meter
tracks realized savings as the single measure of whether it is worth running.

## When it is done

Per sub project exit criteria, and the definition of steady state for the whole
project, are in `docs/01-ROADMAP.md` under "Exit criteria". Seven universal
criteria apply to every sub project, plus one specific to each.

Steady state is all seven success criteria above being met, **and** realized
savings being positive for three consecutive months. Three, because one month
could be a single large rightsizing and two could be luck.

## Non goals

Stated explicitly so that scope creep is a visible decision rather than a drift.

1. **Not a replacement for Cost Explorer or the AWS billing console.** Meter
   does not reconcile to the invoice. Where a number is modelled, it says so.
2. **Not a write plane, in v1.** Meter does not stop instances, delete
   volumes, or edit infrastructure. Remediation is a generated pull request
   that a human approves.
3. **Not a monitoring or alerting platform.** Meter governs the cost of
   observability. It does not replace observability.
4. **Not multi cloud on day one.** AWS is built first. The abstraction exists
   from day one so that GCP, Azure and PCF are connectors, not rewrites. No
   non AWS connector is built until the AWS product is proven.
5. **Not an LLM product.** The language model explains, narrates, and drafts.
   It never computes a sizing number or a cost figure.

## Guiding principles

1. **Honest numbers beat impressive numbers.** Every figure is labelled
   measured or modelled. A modelled figure that is later proven wrong damages
   trust more than a missing figure.
2. **Prevention beats reporting.** A report of money already burned is a post
   mortem. The product value is in the control that stops it.
3. **An unowned finding is never fixed.** Every finding carries a human owner
   or it does not ship.
4. **Absence of data is not zero.** A failed collection renders as a failure,
   never as the number zero.
5. **Boring beats clever.** The elegant solution is justified only when the
   boring one creates measurable pain.
