# Competitive review

Last updated: 2026-08-23
Update trigger: any review of a comparable product
Method: read the vendor's own claims, take what is better than ours, record
what we reject and why

A living document. One dated section per review. Reports are not edited after
they are written, in the same way audit reports are not, because the value is
in knowing what was believed at a point in time.

---

## 2026-08-23: NudgeBee AI FinOps

Source: `https://nudgebee.com/ai-finops`, read 2026-08-23. Claims are the
vendor's own and are not independently verified.

### What it validated

Worth recording, because convergence on a decision by an independent team is
evidence the decision is not eccentric.

| Their position | Ours |
| --- | --- |
| "510 rules and the FinOps Score run deterministically." Finding and ranking uses zero language model tokens | ADR-0007, almost word for word |
| Normalises first party savings from Compute Optimizer, Cost Optimization Hub, Cost Explorer, Trusted Advisor, Azure Advisor, GCP Recommender | ADR-0006 |
| STS AssumeRole with an ExternalId, no long lived credentials | ADR-0004 |
| OpenCost in the customer's own cluster for allocation | P6, FEAT-036 |
| Every change requires human approval, pull requests against GitHub or GitLab | FEAT-040 |
| Publishes the full working: parameters, formulas, data windows | Our measured versus modelled rule |
| Self hosted, zero telemetry, billing data queried in place | Our single tenant deployment, inherently |

### What we took

| Their capability | Became | Why it is better than what we had |
| --- | --- | --- |
| Severity by dollar impact, High at 100 USD a month, Medium at 20 | ADR-0016 | Ours was a chosen label, so the ranking reflected the author rather than the impact |
| Anomaly detection requiring Z score 3.0 **and** 50 USD absolute **and** 20 percent relative, on a 30 day clean baseline, auto resolving after two normal days | FEAT-023 amended | Ours had no thresholds at all. Requiring all three concurrently is the specific thing that stops anomaly detection becoming noise and being muted |
| Auto-Pilot scores blast radius from the dependency graph and auto applies only safe changes | FEAT-044 | The best idea on their page. We already build that graph in FEAT-031 and did nothing with it beyond drawing it |
| Outbound AI requests scanned for secrets, redact or block | FEAT-046 | We have seven scanners and none looked at what leaves for Bedrock |
| CSV and Excel export for chargeback and showback | FEAT-045 | Finance does not live in our interface. A FinOps tool that cannot hand finance a file is missing its actual consumer |
| Cluster node fleet optimisation as an integer linear program | FEAT-047 | Ours stopped at reporting bin packing efficiency. Theirs solves it |
| FinOps Score, 0 to 100, recalculated every 6 hours | FEAT-043 | Adopted with a condition, see below |
| LSTM replica forecasting, 24 steps to a 168 step horizon | FEAT-048, ADR-0015 | Adopted with four conditions, see below |
| Memory at peak plus 15 percent, or 25 percent after an OOMKill. 50 data points over 2 weeks | FEAT-036 amended | OOMKill awareness is a genuinely good detail we did not have |
| Abandoned workload detection over a 7 day window, persistent volume growth forecasting | FEAT-036 amended | Cheap additions to a collector we were already building |

### Two adopted against my recommendation, and how

Both were adopted on the project owner's decision after I argued against them.
Recorded plainly, because a decision taken over an objection should be
findable later along with what the objection was.

**The FinOps Score.** My objection: a single composite number is good for a
sales page and bad for an engineering team, because nobody can tell what moved
it or what to do about it.

The objection becomes a design constraint rather than being dropped. FEAT-043
ships only if **the score decomposes**. Every score shows its components,
every component links to the findings that moved it, and a change in the score
between two runs is explainable as a list of findings that opened or closed. A
score that cannot be taken apart is not shipped.

**LSTM replica forecasting.** My objection: it introduces a trained model into
a product whose credibility rests on every number being reproducible and
defensible.

ADR-0015 answers it by drawing the actual line. A forecaster may produce a
number because it is reproducible, backtestable, has a stated error bound, and
fails visibly when inputs drift. A language model has none of those properties.
Four conditions apply: published backtest accuracy, an error bound on every
forecast, a deterministic fallback to the p95 rule, and a third provenance
label `forecast` alongside `measured` and `modelled`.

### What we rejected

| Their capability | Why not |
| --- | --- |
| Cloud API remediation, writing directly to AWS, Azure and GCP | We are read only in v1, and that is load bearing in the threat model: it is why a compromised hub role gives reconnaissance rather than control. A legitimate v2 conversation, not something to adopt by copying |
| Live Kubernetes patching of deployments | Same reason. A write path into a customer cluster is a different security posture and needs its own threat model |
| A rule count as a headline, 510 rules across four clouds | A count is a marketing number. Two hundred rules nobody acts on is worse than twenty that get fixed. We track realized savings instead |
| 78 integrations | Not a capability, a surface area. Each one is a maintenance liability and a supply chain entry |

### What they have that we deliberately will not

They ship a free community edition, paid tiers, and a four assistant platform
including AI SRE and CloudOps. Meter is an internal platform for one
organization. Product packaging is not a gap.

### Honest position

They are ahead of us in three places: remediation paths, cluster level
optimisation maths, and breadth of first party integration. They are behind on
one thing that matters here, and it is the thing this project exists for:
**nothing on their page addresses observability query cost governance**, which
is the failure that cost 100,000 USD in a week and started this work.

That remains the differentiator, and it is worth noticing that a mature
commercial product in this exact category does not cover it.
